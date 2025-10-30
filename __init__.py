from nonebot import on_message
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment
from nonebot.exception import IgnoredException, FinishedException
from nonebot.rule import Rule
from .commands.prompt import get_all_prompts
from datetime import datetime, timedelta
from typing import Dict
import requests
import asyncio
import os
import json
from .commands import handle_command
from .commands.reply import is_reply_enabled
from .commands.model import get_current_model
from .commands.memory import get_memory_key, get_memory_content, update_memory
from .commands.split import is_split_enabled, get_split_prompt, split_text

# ==================== 配置加载逻辑 ====================
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CORE_CONFIG_FILE = os.path.join(DATA_DIR, "core_config.json")

os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_CORE_CONFIG = {
    "api_keys": {
        "gemini": "",
        "deepseek": ""
    },
    "models": {
        "gemini": "gemini-2.5-pro",
        "deepseek": "deepseek-chat"
    },
    "urls": {
        "gemini": "https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={key}",
        "deepseek": "https://api.deepseek.com/v1/chat/completions"
    },
    "proxies": {},
    "rate_limit": {
        "gemini_cooldown": 15,
        "deepseek_cooldown": 2,
        "global_qps_limit": 2
    }
}

def load_core_config() -> Dict:
    try:
        if not os.path.exists(CORE_CONFIG_FILE):
            with open(CORE_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CORE_CONFIG, f, ensure_ascii=False, indent=2)
            return DEFAULT_CORE_CONFIG
        
        with open(CORE_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        print(f"加载核心配置失败：{str(e)}，使用默认配置")
        return DEFAULT_CORE_CONFIG

CORE_CONFIG = load_core_config()
# ========================================================

# ==================== 配置参数读取 ====================
GEMINI_API_KEY = CORE_CONFIG["api_keys"]["gemini"]
GEMINI_MODEL = CORE_CONFIG["models"]["gemini"]
GEMINI_URL = CORE_CONFIG["urls"]["gemini"].format(
    model=GEMINI_MODEL, 
    key=GEMINI_API_KEY
)

DEEPSEEK_API_KEY = CORE_CONFIG["api_keys"]["deepseek"]
DEEPSEEK_MODEL = CORE_CONFIG["models"]["deepseek"]
DEEPSEEK_URL = CORE_CONFIG["urls"]["deepseek"]

PROXIES = CORE_CONFIG["proxies"]

USER_REQUEST_CACHE: Dict[str, datetime] = {}
GEMINI_COOLDOWN = timedelta(seconds=CORE_CONFIG["rate_limit"]["gemini_cooldown"])
DEEPSEEK_COOLDOWN = timedelta(seconds=CORE_CONFIG["rate_limit"]["deepseek_cooldown"])
GLOBAL_REQUEST_CACHE: Dict[str, int] = {"count": 0, "last_reset": datetime.now()}
GLOBAL_QPS_LIMIT = CORE_CONFIG["rate_limit"]["global_qps_limit"]
# ========================================================

def is_allowed() -> Rule:
    async def _is_allowed(event: MessageEvent) -> bool:
        return event.message_type == "private" or (event.message_type == "group" and event.is_tome())
    return Rule(_is_allowed)

ai_chat = on_message(rule=is_allowed(), priority=5)

async def handle_rate_limit(user_id: str) -> float:
    now = datetime.now()
    current_model = get_current_model()
    cooldown = GEMINI_COOLDOWN if current_model == "gemini" else DEEPSEEK_COOLDOWN
    
    if now - GLOBAL_REQUEST_CACHE["last_reset"] > timedelta(seconds=1):
        GLOBAL_REQUEST_CACHE["count"] = 0
        GLOBAL_REQUEST_CACHE["last_reset"] = now
    global_delay = 0
    if GLOBAL_REQUEST_CACHE["count"] >= GLOBAL_QPS_LIMIT:
        global_delay = 1
    
    user_delay = 0
    if user_id in USER_REQUEST_CACHE:
        time_since_last = now - USER_REQUEST_CACHE[user_id]
        if time_since_last < cooldown:
            user_delay = (cooldown - time_since_last).total_seconds()
    
    delay = max(global_delay, user_delay)
    if delay > 0:
        await asyncio.sleep(delay)
    
    USER_REQUEST_CACHE[user_id] = datetime.now()
    GLOBAL_REQUEST_CACHE["count"] += 1
    
    return delay

def prepare_gemini_request(user_msg: str, memory_content: str = "") -> dict:
    prompts_text = get_all_prompts()
    split_prompt = get_split_prompt() if is_split_enabled() else ""
    
    full_prompt = []
    if prompts_text:
        full_prompt.append(prompts_text)
    if split_prompt:
        full_prompt.append(split_prompt)
    if memory_content:
        full_prompt.append(memory_content)
    
    full_message = "\n\n".join(full_prompt) + f"\n\n用户消息：{user_msg}" if full_prompt else user_msg
    
    return {
        "contents": [{"role": "user", "parts": [{"text": full_message}]}],
        "generationConfig": {
            "maxOutputTokens": 2048,
            "temperature": 0.7,
            "topP": 0.95
        }
    }

def prepare_deepseek_request(user_msg: str, memory_content: str = "") -> dict:
    prompts_text = get_all_prompts()
    split_prompt = get_split_prompt() if is_split_enabled() else ""
    
    full_prompt = []
    if prompts_text:
        full_prompt.append(prompts_text)
    if split_prompt:
        full_prompt.append(split_prompt)
    if memory_content:
        full_prompt.append(memory_content)
    
    system_prompt = "\n\n".join(full_prompt) if full_prompt else ""
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_msg})
    
    return {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.7,
        "top_p": 0.95
    }

def parse_gemini_response(response_data: dict) -> str:
    if "error" in response_data:
        error_msg = response_data["error"].get("message", "未知错误")
        return f"Gemini API错误：{error_msg[:30]}..."
    
    if "candidates" in response_data and isinstance(response_data["candidates"], list) and len(response_data["candidates"]) > 0:
        candidate = response_data["candidates"][0]
        finish_reason = candidate.get("finishReason", "UNKNOWN")
        total_tokens = response_data.get("usageMetadata", {}).get("totalTokenCount", 0)
        
        if "content" in candidate and "parts" in candidate["content"]:
            parts = candidate["content"]["parts"]
            if parts and isinstance(parts, list) and "text" in parts[0]:
                return parts[0]["text"].strip()
        
        if finish_reason == "MAX_TOKENS" and total_tokens >= 2000:
            return "响应长度超出限制（已达2048令牌上限），请简化问题～"
    
    return "未获取到有效回复"

def parse_deepseek_response(response_data: dict) -> str:
    if "error" in response_data:
        error_msg = response_data["error"].get("message", "未知错误")
        return f"DeepSeek API错误：{error_msg[:30]}..."
    
    if "choices" in response_data and isinstance(response_data["choices"], list) and len(response_data["choices"]) > 0:
        choice = response_data["choices"][0]
        if "message" in choice and "content" in choice["message"]:
            return choice["message"]["content"].strip()
        
        finish_reason = choice.get("finish_reason", "unknown")
        if finish_reason == "length":
            return "响应长度超出限制，请简化问题～"
    
    return "未获取到有效回复"

@ai_chat.handle()
async def handle_chat(event: MessageEvent):
    user_id = str(event.user_id)
    user_msg = event.get_plaintext().strip()
    print(f"\n===== 用户 {user_id} 发送消息：{user_msg} =====")

    # 优先处理指令
    if await handle_command(event, user_msg):
        raise FinishedException()
    
    # 检查回复开关
    if not is_reply_enabled(event):
        raise IgnoredException("回复已关闭，忽略消息")
    
    # 过滤空消息和过长消息
    if not user_msg:
        raise IgnoredException("空消息，跳过处理")
    if len(user_msg) > 1000:
        await ai_chat.finish("消息太长啦～ 请控制在1000字内哦～")
        return
    
    # 处理频率限制
    try:
        delay = await handle_rate_limit(user_id)
        if delay > 1:
            await ai_chat.send(f"请求稍作延迟，正在处理中...（延迟 {delay:.1f} 秒）")
    except Exception as e:
        await ai_chat.finish(f"处理频率限制时出错：{str(e)}")
        return
    
    # 获取记忆内容
    memory_key = get_memory_key(event)
    memory_content = get_memory_content(memory_key)
    
    # 调用API生成回复
    current_model = get_current_model()
    try:
        if current_model.startswith("gemini"):
            data = prepare_gemini_request(user_msg, memory_content)
            headers = {"Content-Type": "application/json"}
            response = requests.post(
                GEMINI_URL,
                json=data,
                headers=headers,
                proxies=PROXIES,
                timeout=30
            )
            response_data = response.json()
            ai_reply = parse_gemini_response(response_data)
        elif current_model.startswith("deepseek"):
            data = prepare_deepseek_request(user_msg, memory_content)
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
            }
            response = requests.post(
                DEEPSEEK_URL,
                json=data,
                headers=headers,
                proxies=PROXIES,
                timeout=30
            )
            response_data = response.json()
            ai_reply = parse_deepseek_response(response_data)
        else:
            await ai_chat.finish(f"不支持的模型：{current_model}")
            return
        
        print("准备更新记忆...")
        await update_memory(
            event=event,
            user_msg=user_msg,
            ai_reply=ai_reply,
            current_model=current_model,
            prepare_request=prepare_gemini_request if current_model.startswith("gemini") else prepare_deepseek_request,
            parse_response=parse_gemini_response if current_model.startswith("gemini") else parse_deepseek_response,
            api_url=GEMINI_URL if current_model.startswith("gemini") else DEEPSEEK_URL,
            headers={"Content-Type": "application/json"} if current_model.startswith("gemini") else {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
            },
            proxies=PROXIES
        )

        # 处理文本分割（如果启用）
        if is_split_enabled():
        # 分割文本并逐条发送
            split_parts = split_text(ai_reply)
            for part in split_parts:
                await ai_chat.send(part)
            # 正确用法：通过finish()终止处理，避免异常被错误捕获
            await ai_chat.finish()
        else:
            await ai_chat.finish(ai_reply)
        
        # 更新记忆
        
    except (FinishedException, IgnoredException):
    # 重新抛出框架控制流异常，不当作错误处理
        raise
    except requests.exceptions.Timeout:
        await ai_chat.finish("请求超时，请稍后再试～")
    except requests.exceptions.RequestException as e:
        await ai_chat.finish(f"请求出错：{str(e)[:30]}...")
    except Exception as e:
        await ai_chat.finish(f"处理消息时出错：{str(e)}")