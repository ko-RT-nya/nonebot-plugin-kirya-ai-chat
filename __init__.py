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
import time
from .commands import handle_command
from .commands.reply import is_reply_enabled, is_active_mode
from .commands.model import get_current_model
from .commands.memory import get_memory_key, get_memory_content, update_memory, update_memory_chat
from .commands.split import is_split_enabled, get_split_prompt, split_text
from .utils.logger import get_logger
from .utils.config import config_manager

# ==================== 配置加载逻辑 ====================
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# 初始化日志记录器
ai_logger = get_logger(DATA_DIR)  # 使用数据目录初始化日志记录器

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

# ==================== 配置参数管理 ====================
USER_REQUEST_CACHE: Dict[str, datetime] = {}
GLOBAL_REQUEST_CACHE: Dict[str, int] = {"count": 0, "last_reset": datetime.now()}

# 动态获取配置的辅助函数
def get_gemini_config() -> Dict:
    """动态获取Gemini相关配置"""
    api_key = config_manager.get_value("core_config.json", "api_keys.gemini", default="")
    # 获取当前设置的模型
    current_model = get_current_model()
    # 如果当前模型是Gemini系列，直接使用当前模型
    if current_model.startswith("gemini"):
        model = current_model
    else:
        # 否则使用默认的Gemini模型
        model = config_manager.get_value("core_config.json", "models.gemini", default="gemini-2.5-pro")
    url_template = config_manager.get_value("core_config.json", "urls.gemini", 
                                         default="https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={key}")
    url = url_template.format(model=model, key=api_key)
    return {"api_key": api_key, "model": model, "url": url}

def get_deepseek_config() -> Dict:
    """动态获取DeepSeek相关配置"""
    api_key = config_manager.get_value("core_config.json", "api_keys.deepseek", default="")
    # 获取当前设置的模型
    current_model = get_current_model()
    # 如果当前模型是DeepSeek系列，直接使用当前模型
    if current_model.startswith("deepseek"):
        model = current_model
    else:
        # 否则使用默认的DeepSeek模型
        model = config_manager.get_value("core_config.json", "models.deepseek", default="deepseek-chat")
    url = config_manager.get_value("core_config.json", "urls.deepseek", 
                                 default="https://api.deepseek.com/v1/chat/completions")
    return {"api_key": api_key, "model": model, "url": url}

def get_proxies() -> Dict:
    """动态获取代理配置"""
    return config_manager.get_value("core_config.json", "proxies", default={})

def get_cooldown_for_model(model_id: str) -> timedelta:
    """根据模型ID获取对应的冷却时间"""
    # 首先尝试从model_config.json的cooldowns中获取特定模型的冷却时间
    specific_cooldown = config_manager.get_value("model_config.json", f"cooldowns.{model_id}")
    if specific_cooldown is not None:
        return timedelta(seconds=specific_cooldown)
    
    # 如果没有特定配置，则根据模型类型使用默认值
    if model_id.startswith("gemini"):
        return timedelta(seconds=config_manager.get_value("core_config.json", "rate_limit.gemini_cooldown", default=15))
    else:  # deepseek模型
        return timedelta(seconds=config_manager.get_value("core_config.json", "rate_limit.deepseek_cooldown", default=2))

def get_global_qps_limit() -> int:
    """动态获取全局QPS限制"""
    return config_manager.get_value("core_config.json", "rate_limit.global_qps_limit", default=2)
# ========================================================

def is_allowed() -> Rule:
    async def _is_allowed(event: MessageEvent) -> bool:
        # 允许所有私聊和群聊消息，但在handle_chat中会进一步判断是否需要AI回复
        return event.message_type == "private" or event.message_type == "group"
    return Rule(_is_allowed)

ai_chat = on_message(rule=is_allowed(), priority=5)

async def handle_rate_limit(user_id: str) -> float:
    now = datetime.now()
    current_model = get_current_model()
    cooldown = get_cooldown_for_model(current_model)
    global_delay = 0
    
    if now - GLOBAL_REQUEST_CACHE["last_reset"] > timedelta(seconds=1):
        GLOBAL_REQUEST_CACHE["count"] = 0
        GLOBAL_REQUEST_CACHE["last_reset"] = now
    if GLOBAL_REQUEST_CACHE["count"] >= get_global_qps_limit():
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
    
    # 动态获取DeepSeek模型配置
    deepseek_config = get_deepseek_config()
    
    return {
        "model": deepseek_config["model"],
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
        # 获取用户昵称 - 优先使用QQ昵称，其次是群昵称，最后是默认值
        user_name = event.sender.nickname or event.sender.card or f"用户{event.user_id}"
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
    
    # 过滤空消息
    if not raw_user_msg:
        raise IgnoredException("空消息，跳过处理")
    
    # 对于群聊消息，无论是否@机器人都进行记忆更新
    # 但只有@机器人的消息才会触发AI回复
    is_tome = event.is_tome() if event.message_type == "group" else True
    
    # 检查回复开关（仅对需要AI回复的消息有效）
    if is_tome and not is_reply_enabled(event):
        raise IgnoredException("回复已关闭，忽略消息")
    
    # 过滤过长消息（仅对需要AI回复的消息有效）
    if is_tome and len(raw_user_msg) > 1000:
        await ai_chat.finish("消息太长啦～ 请控制在1000字内哦～")
        return
    
    # 如果不是需要AI回复的消息（群聊中未@机器人），处理逻辑
    if not is_tome:
        print("群聊消息未@机器人，处理中...")
        # 更新记忆 - 只添加用户消息
        memory_key = get_memory_key(event)
        await update_memory_chat(
            event=event,
            user_msg=raw_user_msg,
            ai_reply="",  # 未触发AI回复，所以是空的
            split_parts=None,
            current_model=get_current_model()
        )
        
        # 检查是否处于主动回复模式
        if is_active_mode(event):
            # 从配置文件读取主动回复相关配置
            try:
                active_config = config_manager.load_config("active_reply_config.json")
                active_reply_prompt = active_config.get("active_reply_prompt", "")
                trigger_probability = active_config.get("trigger_probability", 0.1)
                no_reply_marker = active_config.get("no_reply_marker", "<NOREPLY>")
            except Exception as e:
                print(f"读取主动回复配置失败：{str(e)}")
                # 使用默认值
                active_reply_prompt = "\n\n[主动回复判断]\n请分析用户的最后一条消息，判断是否需要进行回复：\n1. 如果内容与你相关、需要你的参与，或者是一个开放性的问题，请正常回复\n2. 如果是纯闲聊内容且与你无关，或者是群成员之间的对话，请返回不回复标记\n\n注意：如果不需要回复，请在回复的开头必须包含标记 <NOREPLY>，其余内容随意\n如果需要回复，请直接回复内容，不要包含<NOREPLY>标记\n请以符合你角色的方式回复"
                trigger_probability = 0.1
                no_reply_marker = "<NOREPLY>"
            
            # 根据配置的概率触发AI回复
            if random.random() < trigger_probability:
                print("主动回复模式：触发AI自主回复判断")
                
                # 获取记忆内容
                print(f"主动回复模式：正在加载记忆内容 - 记忆键: {memory_key}")
                memory_content = get_memory_content(memory_key)
                print(f"主动回复模式：记忆内容加载完成，长度: {len(str(memory_content))} 字符")
                
                # 调用API生成回复
                current_model = get_current_model()
                user_id = str(event.user_id)
                group_id = str(event.group_id)
                try:
                    if current_model.startswith("gemini"):
                        # 为AI请求添加发信人标识
                        ai_input_msg = add_sender_identifier(event, raw_user_msg)
                        data = prepare_gemini_request(ai_input_msg, memory_content + active_reply_prompt, event)
                        headers = {"Content-Type": "application/json"}
                        # 动态获取Gemini配置
                        gemini_config = get_gemini_config()
                        response = requests.post(
                            gemini_config["url"],
                            json=data,
                            headers=headers,
                            proxies=get_proxies(),
                            timeout=30
                        )
                        response.raise_for_status()
                        response_data = response.json()
                        ai_reply = parse_gemini_response(response_data)
                    elif current_model.startswith("deepseek"):
                        # 为AI请求添加发信人标识
                        ai_input_msg = add_sender_identifier(event, raw_user_msg)
                        data = prepare_deepseek_request(ai_input_msg, memory_content + active_reply_prompt, event)
                        # 动态获取DeepSeek配置
                        deepseek_config = get_deepseek_config()
                        headers = {
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {deepseek_config['api_key']}"
                        }
                        response = requests.post(
                            deepseek_config["url"],
                            json=data,
                            headers=headers,
                            proxies=get_proxies(),
                            timeout=60  # 增加超时时间以应对网络延迟
                        )
                        response.raise_for_status()
                        response_data = response.json()
                        ai_reply = parse_deepseek_response(response_data)
                    
                    # 记录API交互日志（无论是否回复）
                    ai_logger.log_api_interaction(
                        user_id=user_id,
                        group_id=group_id,
                        model_name=current_model,
                        request_data=data,
                        response_data=response_data,
                        user_message=raw_user_msg,
                        ai_reply=ai_reply,
                        memory_content=memory_content
                    )
                    
                    # 检查AI回复是否包含不回复标记
                    if ai_reply and not ai_reply.startswith(no_reply_marker):
                        print(f"主动回复模式：AI决定回复消息 - {ai_reply[:30]}...")
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
                        else:
                            # 不分割，直接发送
                            await ai_chat.send(ai_reply)
                        
                        # 根据不同模型获取对应的参数
                        if current_model.startswith("gemini"):
                            # 获取Gemini配置和函数
                            gemini_config = get_gemini_config()
                            prepare_func = prepare_gemini_request
                            parse_func = parse_gemini_response
                            api_url = gemini_config["url"]
                            headers = {"Content-Type": "application/json"}
                        elif current_model.startswith("deepseek"):
                            # 获取DeepSeek配置和函数
                            deepseek_config = get_deepseek_config()
                            prepare_func = prepare_deepseek_request
                            parse_func = parse_deepseek_response
                            api_url = deepseek_config["url"]
                            headers = {
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {deepseek_config['api_key']}"
                            }
                        
                        # 更新记忆，添加AI回复，并传递所有必要的模型参数
                        await update_memory_chat(
                            event=event,
                            user_msg="",  # 用户消息已经添加过了
                            ai_reply=ai_reply,
                            split_parts=split_parts if split_parts else None,
                            current_model=current_model,
                            prepare_request=prepare_func,
                            parse_response=parse_func,
                            api_url=api_url,
                            headers=headers,
                            proxies=get_proxies()
                        )
                    else:
                        print(f"主动回复模式：AI判断不需要回复此消息 - {ai_reply[:30]}...")
                except Exception as e:
                    print(f"处理主动回复时出错：{str(e)}")
        
        # 正常结束处理流程
        await ai_chat.finish()
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
            # 动态获取Gemini配置
            gemini_config = get_gemini_config()
            response = requests.post(
                gemini_config["url"],
                json=data,
                headers=headers,
                proxies=get_proxies(),
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
            # 动态获取DeepSeek配置
            deepseek_config = get_deepseek_config()
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {deepseek_config['api_key']}"
            }
            response = requests.post(
                deepseek_config["url"],
                json=data,
                headers=headers,
                proxies=get_proxies(),
                timeout=60  # 增加超时时间以应对网络延迟
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
        
        # 根据不同模型获取对应的参数
        if current_model.startswith("gemini"):
            # 获取Gemini配置和函数
            gemini_config = get_gemini_config()
            prepare_func = prepare_gemini_request
            parse_func = parse_gemini_response
            api_url = gemini_config["url"]
            headers = {"Content-Type": "application/json"}
        elif current_model.startswith("deepseek"):
            # 获取DeepSeek配置和函数
            deepseek_config = get_deepseek_config()
            prepare_func = prepare_deepseek_request
            parse_func = parse_deepseek_response
            api_url = deepseek_config["url"]
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {deepseek_config['api_key']}"
            }
        
        # 更新记忆 - 使用兼容函数处理聊天记录更新，并传递所有必要的模型参数
        print("准备更新记忆...")
        await update_memory_chat(
            event=event,
            user_msg=raw_user_msg,
            ai_reply=ai_reply,
            split_parts=split_parts if split_parts else None,  # 传递分割后的消息部分
            current_model=current_model,
            prepare_request=prepare_func,
            parse_response=parse_func,
            api_url=api_url,
            headers=headers,
            proxies=get_proxies()
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
        # 提供更详细的超时提示
        await ai_chat.finish("与AI服务的连接超时，请检查网络连接后稍后再试～")
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