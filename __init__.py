from nonebot import on_message
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment
from nonebot.exception import IgnoredException, FinishedException
from nonebot.rule import Rule
from .commands.prompt import get_all_prompts
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Callable
from nonebot.adapters.onebot.v11 import MessageEvent
import requests
import asyncio
import os
import json
import random
from .commands import handle_command
from .commands.reply import is_reply_enabled
from .commands.model import get_current_model
from .commands.memory import get_memory_key, get_memory_content, update_memory, update_memory_chat
from .commands.split import is_split_enabled, get_split_prompt, split_text
from .utils.logger import get_logger

# ==================== 配置加载逻辑 ====================
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# 使用配置管理器
from .utils.config import config_manager

# 默认配置
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

# 确保配置管理器完全初始化并加载配置
config_manager.initialize()

# 从配置管理器加载核心配置
# 为了获取整个配置对象，我们使用load_config方法而不是get_value
CORE_CONFIG = config_manager.load_config("core_config.json")
# ========================================================

# ==================== 配置参数读取 ====================
# 从配置管理器读取配置参数
GEMINI_API_KEY = config_manager.get_value("core_config.json", "api_keys.gemini", default="")
GEMINI_MODEL = config_manager.get_value("core_config.json", "models.gemini", default="gemini-2.5-pro")
GEMINI_URL = config_manager.get_value("core_config.json", "urls.gemini", default="https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={key}").format(
    model=GEMINI_MODEL, 
    key=GEMINI_API_KEY
)

DEEPSEEK_API_KEY = config_manager.get_value("core_config.json", "api_keys.deepseek", default="")
DEEPSEEK_MODEL = config_manager.get_value("core_config.json", "models.deepseek", default="deepseek-chat")
DEEPSEEK_URL = config_manager.get_value("core_config.json", "urls.deepseek", default="https://api.deepseek.com/v1/chat/completions")

PROXIES = config_manager.get_value("core_config.json", "proxies", default={})

USER_REQUEST_CACHE: Dict[str, datetime] = {}
GEMINI_COOLDOWN = timedelta(seconds=config_manager.get_value("core_config.json", "rate_limit.gemini_cooldown", default=15))
DEEPSEEK_COOLDOWN = timedelta(seconds=config_manager.get_value("core_config.json", "rate_limit.deepseek_cooldown", default=2))
GLOBAL_REQUEST_CACHE: Dict[str, int] = {"count": 0, "last_reset": datetime.now()}
GLOBAL_QPS_LIMIT = config_manager.get_value("core_config.json", "rate_limit.global_qps_limit", default=2)
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

def prepare_gemini_request(user_msg: str, memory_content: str = "", event: Optional[MessageEvent] = None) -> dict:
    prompts_text = get_all_prompts(event)
    split_prompt = get_split_prompt() if is_split_enabled() else ""
    
    full_prompt = []
    if prompts_text:
        full_prompt.append(prompts_text)
    if split_prompt:
        full_prompt.append(split_prompt)
    if memory_content:
        full_prompt.append(memory_content)
    
    # 将新消息用<新消息>标签包裹
    wrapped_user_msg = f"<新消息>{user_msg}</新消息>"
    full_message = "\n\n".join(full_prompt) + f"\n\n{wrapped_user_msg}" if full_prompt else wrapped_user_msg
    
    return {
        "contents": [{"role": "user", "parts": [{"text": full_message}]}],
        "generationConfig": {
            "maxOutputTokens": 2048,
            "temperature": 0.7,
            "topP": 0.95
        }
    }

def prepare_deepseek_request(user_msg: str, memory_content: str = "", event: Optional[MessageEvent] = None) -> dict:
    prompts_text = get_all_prompts(event)
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
    # 将新消息用<新消息>标签包裹
    wrapped_user_msg = f"<新消息>{user_msg}</新消息>"
    messages.append({"role": "user", "content": wrapped_user_msg})
    
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

def process_message_with_cqcodes(event: MessageEvent) -> str:
    """
    处理消息中的CQ码，将@指令转换为@昵称格式，不添加发信人标识
    """
    result = []
    for segment in event.message:
        if segment.type == 'at':
            # 获取被@用户的昵称或QQ号
            name = segment.data.get('name', f"QQ_{segment.data.get('qq', 'unknown')}")
            result.append(f"@{name}")
        else:
            # 保留其他类型的消息内容
            result.append(segment.data.get('text', str(segment)))
    
    return ''.join(result).strip()

def add_sender_identifier(event: MessageEvent, message: str) -> str:
    """
    在群聊环境下为消息添加发信人标识
    """
    if event.message_type == 'group':
        # 获取用户昵称
        user_name = event.sender.card or event.sender.nickname or f"用户{event.user_id}"
        # 格式为：昵称（QQ号）：消息内容
        return f"{user_name}（{event.user_id}）：{message}"
    return message

@ai_chat.handle()
async def handle_chat(event: MessageEvent):
    user_id = str(event.user_id)
    
    # 获取原始消息内容用于指令处理
    raw_user_msg = process_message_with_cqcodes(event)  # 只处理CQ码但不添加发信人标识
    
    print(f"\n===== 用户 {user_id} 发送消息：{raw_user_msg} =====")
    
    # 获取日志器
    ai_logger = get_logger()

    # 优先处理指令 - 使用原始消息内容
    if await handle_command(event, raw_user_msg):
        raise FinishedException()
    
    # 检查回复开关
    if not is_reply_enabled(event):
        raise IgnoredException("回复已关闭，忽略消息")
    
    # 过滤空消息和过长消息
    if not raw_user_msg:
        raise IgnoredException("空消息，跳过处理")
    if len(raw_user_msg) > 1000:
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
    group_id = str(event.group_id) if event.message_type == 'group' else None
    try:
        if current_model.startswith("gemini"):
            # 为AI请求添加发信人标识
            ai_input_msg = add_sender_identifier(event, raw_user_msg)
            data = prepare_gemini_request(ai_input_msg, memory_content, event)
            headers = {"Content-Type": "application/json"}
            response = requests.post(
                GEMINI_URL,
                json=data,
                headers=headers,
                proxies=PROXIES,
                timeout=30
            )
            response.raise_for_status()
            response_data = response.json()
            ai_reply = parse_gemini_response(response_data)
            
            # 记录API交互日志
            ai_logger.log_api_interaction(
                user_id=user_id,
                group_id=group_id,
                model_name=current_model,
                request_data=data,
                response_data=response_data,
                user_message=raw_user_msg,
            ai_reply=ai_reply,
                memory_content=memory_content
                # 完整的请求数据已经包含在request_data中
            )
            
        elif current_model.startswith("deepseek"):
            # 为AI请求添加发信人标识
            ai_input_msg = add_sender_identifier(event, raw_user_msg)
            data = prepare_deepseek_request(ai_input_msg, memory_content, event)
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
            response.raise_for_status()
            response_data = response.json()
            ai_reply = parse_deepseek_response(response_data)
            
            # 记录API交互日志
            ai_logger.log_api_interaction(
                user_id=user_id,
                group_id=group_id,
                model_name=current_model,
                request_data=data,
                response_data=response_data,
                user_message=raw_user_msg,
            ai_reply=ai_reply,
                memory_content=memory_content
                # 完整的请求数据已经包含在request_data中
            )
        else:
            await ai_chat.finish(f"不支持的模型：{current_model}")
            return
        
        # 处理文本分割（如果启用）
        split_parts = []
        if is_split_enabled():
            # 分割文本并逐条发送
            split_parts = split_text(ai_reply)
            for i, part in enumerate(split_parts):
                await ai_chat.send(part)
                # 为除第一个消息外的每个消息添加200-800ms的随机延迟
                if i < len(split_parts) - 1:
                    delay_ms = random.randint(200, 800)
                    await asyncio.sleep(delay_ms / 1000)  # 转换为秒
            # 正确用法：通过finish()终止处理，避免异常被错误捕获
        else:
            await ai_chat.send(ai_reply)
        
        # 更新记忆 - 使用兼容函数处理聊天记录更新
        print("准备更新记忆...")
        await update_memory_chat(
            event=event,
            user_msg=raw_user_msg,
            ai_reply=ai_reply,
            split_parts=split_parts if split_parts else None,  # 传递分割后的消息部分
            current_model=current_model,
            prepare_request=lambda user_msg, memory_content: prepare_gemini_request(add_sender_identifier(event, user_msg), memory_content, event) if current_model.startswith("gemini") else prepare_deepseek_request(add_sender_identifier(event, user_msg), memory_content, event),
            parse_response=parse_gemini_response if current_model.startswith("gemini") else parse_deepseek_response,
            api_url=GEMINI_URL if current_model.startswith("gemini") else DEEPSEEK_URL,
            headers={"Content-Type": "application/json"} if current_model.startswith("gemini") else {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
            },
            proxies=PROXIES
        )
        
        await ai_chat.finish()
        
    except (FinishedException, IgnoredException):
    # 重新抛出框架控制流异常，不当作错误处理
        raise
    except (FinishedException, IgnoredException):
        # 重新抛出框架控制流异常，不当作错误处理
        raise
    except requests.exceptions.Timeout:
        # 记录超时错误
        ai_logger.log_api_interaction(
            user_id=user_id,
            group_id=group_id,
            model_name=current_model,
            user_message=raw_user_msg,
            memory_content=memory_content,
            error="请求超时"
        )
        await ai_chat.finish("请求超时，请稍后再试～")
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        # 记录请求错误
        ai_logger.log_api_interaction(
            user_id=user_id,
            group_id=group_id,
            model_name=current_model,
            user_message=raw_user_msg,
            memory_content=memory_content,
            error=error_msg
        )
        await ai_chat.finish(f"请求出错：{error_msg[:30]}...")
    except Exception as e:
        error_msg = str(e)
        # 记录其他错误
        ai_logger.log_api_interaction(
            user_id=user_id,
            group_id=group_id,
            model_name=current_model,
            user_message=raw_user_msg,
            memory_content=memory_content,
            error=error_msg
        )
        await ai_chat.finish(f"处理消息时出错：{error_msg}")