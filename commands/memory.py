import os
import os
import json
import asyncio
import requests  
from datetime import datetime
from typing import Dict, List, Callable, Optional
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent
from . import register_command, is_admin
from ..utils.config import config_manager

# 记忆存储路径
DATA_DIR = config_manager.get_data_dir()
MEMORY_DIR = os.path.join(DATA_DIR, "memories")
USER_MEMORY_DIR = os.path.join(MEMORY_DIR, "users")
GROUP_MEMORY_DIR = os.path.join(MEMORY_DIR, "groups")

# 确保数据目录存在并检查权限
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(USER_MEMORY_DIR, exist_ok=True)
os.makedirs(GROUP_MEMORY_DIR, exist_ok=True)
for dir_name in ["users", "groups"]:
    dir_path = os.path.join(MEMORY_DIR, dir_name)
    if not os.access(dir_path, os.W_OK):
        print(f"警告：目录 {dir_path} 无写入权限，记忆无法保存！")


# 记忆数据结构
MEMORY_STRUCT = {
    "summary": "",  # AI总结的历史信息
    "history": [],  # 最近聊天记录
    "last_summary_time": 0  # 上次总结时间戳
}

# 并发控制锁
memory_locks = {}  # {key: asyncio.Lock()}

def calculate_effective_length(history: List[Dict]) -> int:
    """计算历史记录中的有效信息长度（去掉标记信息性质的内容）"""
    total_length = 0
    for item in history:
        # 只计算实际内容部分，去掉标记性信息
        content = item['content']
        total_length += len(content)
    return total_length

def get_memory_key(event: MessageEvent) -> str:
    """获取记忆存储的唯一键"""
    if event.message_type == "private":
        return f"user_{event.user_id}"
    else:
        return f"group_{event.group_id}"

def get_memory_path(key: str) -> str:
    """获取记忆文件路径"""
    prefix, id = key.split("_", 1)
    path = os.path.join(MEMORY_DIR, prefix + "s", f"{id}.json")
    # 新增日志：验证路径是否正确
    print(f"记忆文件路径：{path}")  # 测试时查看控制台输出
    return path

def load_memory(key: str) -> Dict:
    """加载记忆数据（纯文件操作，无外部函数依赖）"""
    path = get_memory_path(key)
    if not os.path.exists(path):
        return MEMORY_STRUCT.copy()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"加载记忆失败: {str(e)}")
        return MEMORY_STRUCT.copy()

def save_memory(key: str, data: Dict) -> bool:
    """保存记忆数据（纯文件操作，无外部函数依赖）"""
    try:
        path = get_memory_path(key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存记忆失败: {str(e)}")
        return False

# 新增：记忆提示词管理相关指令
@register_command(
    command=["memory prompt", "记忆提示词"],
    description="管理记忆相关的提示词（仅管理员）",
    usage="\\memory prompt [操作] [参数]\n操作: create/edit/show/delete/list\n例如：\\memory prompt create summary 总结提示词内容"
)
async def handle_memory_prompt(event: MessageEvent, command_text: str) -> bool:
    """处理记忆提示词相关指令"""
    user_id = str(event.user_id)
    if not is_admin(user_id):
        await get_bot().send(event, "无权限执行此操作（仅管理员可管理记忆提示词）")
        return True
    
    # 解析格式：\memory prompt 操作 [参数]
    # 去除命令开头的反斜杠
    command_str = command_text[1:].strip()
    
    # 提取操作类型
    if command_str.startswith("memory prompt"):
        parts = command_str[13:].strip().split(" ", 1)
    elif command_str.startswith("记忆提示词"):
        parts = command_str[5:].strip().split(" ", 1)
    else:
        # 兼容其他格式
        _, remaining = command_str.split(" ", 1)
        parts = remaining.strip().split(" ", 1)
    
    if not parts or not parts[0]:
        await get_bot().send(event, "使用方式：\\memory prompt [操作] [参数]\n操作: create/edit/show/delete/list")
        return True
    
    action = parts[0].lower()
    params = parts[1].strip() if len(parts) > 1 else ""
    
    # 记忆提示词类型
    memory_prompt_types = ["summary", "history"]
    
    # 加载或初始化记忆提示词配置
    memory_prompts = config_manager.get_value("memory_prompts.json", {}, default={})
    
    if action == "create" or action == "edit":
        # 创建或编辑提示词
        try:
            prompt_type, content = params.split(" ", 1)
            if prompt_type not in memory_prompt_types:
                    await get_bot().send(event, f"无效的提示词类型！支持的类型：{', '.join(memory_prompt_types)}")
                    return True
            
            memory_prompts[prompt_type] = content
            if config_manager.set_value("memory_prompts.json", memory_prompts):
                await get_bot().send(event, f"已{'创建' if action == 'create' else '编辑'}记忆提示词 `{prompt_type}`")
            else:
                await get_bot().send(event, f"{'创建' if action == 'create' else '编辑'}记忆提示词失败（存储错误）")
        except ValueError:
            await get_bot().send(event, f"格式错误！正确格式：\\memory prompt {action} 类型 内容")
    
    elif action == "show":
        # 显示提示词
        prompt_type = params.strip()
        if not prompt_type:
            # 显示所有提示词
            if not memory_prompts:
                await get_bot().send(event, "当前没有任何记忆提示词")
            else:
                prompt_list = []
                for ptype, content in memory_prompts.items():
                    prompt_list.append(f"【{ptype}】\n{content[:100]}{'...' if len(content) > 100 else ''}")
                await get_bot().send(event, "记忆提示词列表：\n" + "\n\n".join(prompt_list))
        elif prompt_type in memory_prompts:
            await get_bot().send(event, f"【{prompt_type}】\n{memory_prompts[prompt_type]}")
        else:
            await get_bot().send(event, f"记忆提示词 `{prompt_type}` 不存在！")
    
    elif action == "delete":
        # 删除提示词
        prompt_type = params.strip()
        if not prompt_type:
            await get_bot().send(event, "请指定要删除的提示词类型")
        elif prompt_type not in memory_prompts:
            await get_bot().send(event, f"记忆提示词 `{prompt_type}` 不存在！")
        else:
            del memory_prompts[prompt_type]
            if config_manager.set_value("memory_prompts.json", memory_prompts):
                await get_bot().send(event, f"已删除记忆提示词 `{prompt_type}`")
            else:
                await get_bot().send(event, "删除记忆提示词失败（存储错误）")
    
    elif action == "list":
        # 列出所有提示词类型
        if not memory_prompts:
            await get_bot().send(event, "当前没有任何记忆提示词")
        else:
            prompt_list = []
            for idx, ptype in enumerate(memory_prompts.keys(), 1):
                prompt_list.append(f"{idx}. {ptype}")
            await get_bot().send(event, "记忆提示词类型列表：\n" + "\n".join(prompt_list) + "\n\n使用 \\memory prompt show 类型 查看详情")
    
    else:
        await get_bot().send(event, f"未知的操作：{action}\n支持的操作：create/edit/show/delete/list")
    
    return True

async def generate_summary(
    history: List[Dict],
    current_model: str,
    prepare_request: Callable,
    parse_response: Callable,
    api_url: str,
    headers: Dict,
    proxies: Dict,
    event: Optional[MessageEvent] = None,
    timeout: int = 15,
    history_summary: str = ""  # 添加历史总结参数
) -> str:
    """调用AI生成聊天记录总结（通过参数注入避免循环依赖）"""
    if not history:
        return ""
    
    # 构建总结提示词
    # 解析role字段，提取用户信息
    messages_text = "\n".join([
        f"{parse_role_info(item['role'])}: {item['content']}"
        for item in history
    ])
    
    # 获取按聊天环境启用的提示词
    from .prompt import get_all_prompts
    enabled_prompts = get_all_prompts(event) if event else ""
    
    # 构建最终提示词：先添加已启用的提示词，再添加总结提示词和聊天内容
    prompt_parts = []
    if enabled_prompts:
        prompt_parts.append(enabled_prompts)
    
    # 修改总结提示词，强调要结合之前的总结和当前信息
    enhanced_summary_prompt = """
请你作为一个专业的对话记录分析者，根据以下聊天记录生成一份简洁而全面的总结。

分析要求：
1. 识别并总结关键话题和讨论内容
2. 记录每个用户的主要偏好和关注点
3. 语言简洁明了，不超过600字

请基于所有提供的信息生成一份高质量的总结。
"""
    
    prompt_parts.append(enhanced_summary_prompt)
    
    # 如果有历史总结，添加到提示词中
    if history_summary:
        prompt_parts.append(f"历史总结：\n{history_summary}")
    
    prompt_parts.append("最新聊天记录：")
    prompt_parts.append(messages_text)
    
    prompt = "\n\n".join(prompt_parts)
    
    try:
        # 创建一个专门用于总结的请求准备函数，确保不包含消息分割提示词
        def prepare_summary_request(prompt_text: str) -> dict:
            # 直接构建请求数据，不包含分割提示词
            if "gemini" in current_model.lower():
                # Gemini请求格式
                return {
                    "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
                    "generationConfig": {
                        "maxOutputTokens": 2048,
                        "temperature": 0.7,
                        "topP": 0.95
                    }
                }
            else:
                # Deepseek请求格式
                return {
                    "model": current_model,
                    "messages": [{"role": "user", "content": prompt_text}],
                    "max_tokens": 2048,
                    "temperature": 0.7,
                    "top_p": 0.95
                }
        
        data = prepare_summary_request(prompt)
        response = await asyncio.to_thread(
            requests.post,
            api_url,
            json=data,
            headers=headers,
            proxies=proxies,
            timeout=timeout
        )
        response.raise_for_status()
        # 使用注入的响应解析函数
        return parse_response(response.json())
    except Exception as e:
        print(f"生成总结失败: {str(e)}")
        return ""

async def update_memory(
    event: MessageEvent,
    content: str,
    role: str = "user",  # 新增role参数，默认为"user"
    # 注入模型相关依赖
    current_model: str = None,
    prepare_request: Callable = None,
    parse_response: Callable = None,
    api_url: str = None,
    headers: Dict = None,
    proxies: Dict = None
):
    """更新记忆（通过参数注入外部依赖）
    
    Args:
        event: MessageEvent - 消息事件
        content: str - 消息内容
        role: str - 消息角色，可选值："user" 或 "ai"
        current_model: str - 当前使用的模型
        prepare_request: Callable - 请求准备函数
        parse_response: Callable - 响应解析函数
        api_url: str - API URL
        headers: Dict - 请求头
        proxies: Dict - 代理配置
    """
    key = get_memory_key(event)
    
    # 获取锁防止并发问题
    if key not in memory_locks:
        memory_locks[key] = asyncio.Lock()
    async with memory_locks[key]:
        memory = load_memory(key)
        
        # 添加新消息到历史记录
        now = datetime.now().timestamp()
        
        # 根据role确定消息角色
        if role.lower() == "user":
            # 在role字段同时存储QQ号和昵称
            user_id_str = str(event.user_id)
            nickname = getattr(event.sender, 'nickname', '未知用户')
            message_role = f"user_{user_id_str}_{nickname}"
        elif role.lower() == "ai":
            message_role = "ai"
        else:
            # 支持自定义角色
            message_role = role
        
        # 添加消息到历史记录
        memory["history"].append({
            "role": message_role,
            "content": content,
            "timestamp": now
        })
        
        # 计算有效信息长度（去掉标记信息性质的内容）
        effective_length = calculate_effective_length(memory["history"])
        
        # 添加日志记录当前状态，便于调试
        print(f"记忆更新状态 - 历史记录数: {len(memory['history'])}, 有效内容长度: {effective_length}")
        
        # 检查是否需要生成总结
        # 根据需求：历史记录超过120条 或 有效信息超过2000字时触发总结
        need_summary = (
            len(memory["history"]) >= 120 or
            effective_length >= 2000
        )
        
        # 添加日志记录是否需要总结
        print(f"是否需要生成总结: {need_summary}, 模型参数是否完整: {all([current_model, prepare_request, parse_response, api_url, headers])}")
        
        if need_summary and all([current_model, prepare_request, parse_response, api_url, headers]):
            # 构建用于总结的完整信息：结合之前的总结和现有历史记录
            full_history_for_summary = []
            
            # 如果有历史总结，添加到总结内容中
            if memory["summary"]:
                # 在generate_summary函数中会处理这个
                pass  # 我们将通过修改generate_summary的提示词来包含历史总结
            
            # 使用注入的参数调用总结生成，并传递event以获取按聊天环境启用的提示词
            # 传递历史总结，确保新总结能够基于之前的总结记录和现有信息
            new_summary = await generate_summary(
                memory["history"],
                current_model,
                prepare_request,
                parse_response,
                api_url,
                headers,
                proxies or {},
                event=event,
                history_summary=memory["summary"]  # 传递历史总结
            )
            
            # 合并总结：依照之前的总结记录和现有的所有信息进行总结
            memory["summary"] = new_summary  # 新总结已经包含了历史信息，直接替换
                
            # 删除历史聊天记录最远的80条（而不是之前的保留最近10条）
            if len(memory["history"]) > 80:
                memory["history"] = memory["history"][80:]  # 保留最新的记录
                
            memory["last_summary_time"] = now
        
        # 保存更新后的记忆
        save_memory(key, memory)

# 兼容函数，处理现有的调用逻辑
async def update_memory_chat(
    event: MessageEvent,
    user_msg: str,
    ai_reply: str,
    split_parts: List[str] = None,  # 分割后的AI回复部分
    # 注入模型相关依赖
    current_model: str = None,
    prepare_request: Callable = None,
    parse_response: Callable = None,
    api_url: str = None,
    headers: Dict = None,
    proxies: Dict = None
):
    """兼容原有的update_memory函数调用，用于聊天记录更新
    
    先添加用户消息，再添加AI消息（支持分割）
    """
    # 添加用户消息 - 只有当user_msg不为空时才添加
    if user_msg and user_msg.strip():
        await update_memory(
            event=event,
            content=user_msg,
            role="user",
            current_model=current_model,
            prepare_request=prepare_request,
            parse_response=parse_response,
            api_url=api_url,
            headers=headers,
            proxies=proxies
        )
    
    # 添加AI回复 - 根据是否分割选择不同的方式，且仅当ai_reply不为空时添加
    if ai_reply:
        if split_parts and len(split_parts) > 1:
            # 如果有分割的消息部分，为每个部分创建单独的AI记忆条目
            for index, part in enumerate(split_parts):
                # 第一个分割部分携带完整模型参数，以便可能触发自动总结
                # 后续部分不携带模型参数，避免重复检查和生成总结
                if index == 0:
                    await update_memory(
                        event=event,
                        content=part,
                        role="ai",
                        current_model=current_model,
                        prepare_request=prepare_request,
                        parse_response=parse_response,
                        api_url=api_url,
                        headers=headers,
                        proxies=proxies
                    )
                else:
                    await update_memory(
                        event=event,
                        content=part,
                        role="ai",
                        current_model=None,
                        prepare_request=None,
                        parse_response=None,
                        api_url=None,
                        headers=None,
                        proxies=None
                    )
        else:
            # 否则添加完整的AI回复
            await update_memory(
                event=event,
                content=ai_reply,
                role="ai",
                current_model=current_model,
                prepare_request=prepare_request,
                parse_response=parse_response,
                api_url=api_url,
                headers=headers,
                proxies=proxies
            )

def parse_role_info(role: str) -> str:
    """解析role字段，提取用户信息"""
    if role == "ai":
        return "AI"
    elif role.startswith("user_"):
        # 格式：user_qq号_昵称
        parts = role.split('_', 2)
        if len(parts) >= 3:
            qq = parts[1]
            nickname = parts[2]
            return f"用户[{qq}:{nickname}]"
        return "用户"
    return role

def get_memory_content(key: str) -> str:
    """获取用于AI调用的记忆内容（纯数据读取，无外部依赖）"""
    memory = load_memory(key)
    if not memory["summary"] and not memory["history"]:
        return ""
    
    content = []
    if memory["summary"]:
        content.append("[历史对话摘要]")
        content.append(memory["summary"])
    
    if memory["history"]:
        # 获取最大历史记录数配置
        max_history = config_manager.get_value("config.json", "max_history", 30)
        # 限制历史记录数量
        recent_history = memory["history"][-max_history*2:]  # 每个对话包含用户和AI两条消息
        
        # 将对话历史用<对话历史>标签包裹
        content.append("<对话历史>")
        for item in recent_history:
            content.append(f"{parse_role_info(item['role'])}: {item['content']}")
        content.append("</对话历史>")
    
    return "\n".join(content)

# 指令处理部分保持不变（仅依赖本地函数）
@register_command(
    command=["删除记忆", "memory delete"],
    description="删除当前场景的记忆（个人/群组）",
    usage="\\删除记忆 [范围] 或 \\memory delete [scope]（范围：personal/group，默认自动判断）"
)
async def handle_delete_memory(event: MessageEvent, command_text: str) -> bool:
    user_id = str(event.user_id)
    parts = command_text.split()
    scope = parts[1].lower() if len(parts) > 1 else None
    
    if event.message_type == "group" and (not scope or scope == "group"):
        if not is_admin(user_id):
            await get_bot().send(event, "删除群组记忆需要管理员权限")
            return True
    
    if scope == "personal":
        target_key = f"user_{event.user_id}"
    elif scope == "group" and event.message_type == "group":
        target_key = f"group_{event.group_id}"
    else:
        target_key = get_memory_key(event)
    
    path = get_memory_path(target_key)
    if os.path.exists(path):
        try:
            os.remove(path)
            await get_bot().send(event, f"已删除{'个人' if 'user_' in target_key else '群组'}记忆")
        except Exception as e:
            await get_bot().send(event, f"删除记忆失败: {str(e)}")
    else:
        await get_bot().send(event, "没有找到可删除的记忆")
    
    return True

@register_command(
    command=["查看记忆状态", "memory status"],
    description="查看当前场景的记忆状态",
    usage="\\查看记忆状态 或 \\memory status"
)
async def handle_show_memory_status(event: MessageEvent, _: str) -> bool:
    key = get_memory_key(event)
    memory = load_memory(key)
    
    status = [
        f"总结长度: {len(memory['summary'])}字",
        f"最近记录数: {len(memory['history'])//2}轮对话",
        f"上次总结: {datetime.fromtimestamp(memory['last_summary_time']).strftime('%Y-%m-%d %H:%M') if memory['last_summary_time'] else '未总结'}"
    ]
    
    await get_bot().send(event, f"当前{'个人' if 'user_' in key else '群组'}记忆状态:\n" + "\n".join(status))
    return True

@register_command(
    command=["记忆管理", "memory config"],
    description="配置AI记忆相关参数（仅管理员）",
    usage="\\记忆管理 [参数名] [参数值]\n例如：\\记忆管理 max_history 50"
)
async def handle_memory_config(event: MessageEvent, args: str) -> bool:
    user_id = str(event.user_id)
    if not is_admin(user_id):
        await get_bot().send(event, "无权限执行此操作（仅管理员可配置记忆参数）")
        return True

    # 获取参数
    parts = args.strip().split()
    if len(parts) < 2:
        # 显示当前配置
        max_history = config_manager.get_value("config.json", "max_history", 30)
        summary_threshold = config_manager.get_value("config.json", "summary_threshold", 50)
        summary_interval = config_manager.get_value("config.json", "summary_interval", 3600)
        
        reply = f"当前记忆配置:\n"
        reply += f"- 最大历史消息数: {max_history}\n"
        reply += f"- 触发总结阈值: {summary_threshold}\n"
        reply += f"- 总结间隔(秒): {summary_interval}\n"
        reply += "\n使用方式: \\记忆管理 [参数名] [参数值]"
        await get_bot().send(event, reply)
        return True
    
    param_name = parts[0].lower()
    param_value = " ".join(parts[1:])
    
    try:
        # 更新配置
        if param_name == "max_history":
            if config_manager.set_value("config.json", "max_history", int(param_value)):
                await get_bot().send(event, f"已更新记忆配置: {param_name} = {param_value}")
            else:
                await get_bot().send(event, "更新配置失败（存储错误）")
        elif param_name == "summary_threshold":
            if config_manager.set_value("config.json", "summary_threshold", int(param_value)):
                await get_bot().send(event, f"已更新记忆配置: {param_name} = {param_value}")
            else:
                await get_bot().send(event, "更新配置失败（存储错误）")
        elif param_name == "summary_interval":
            if config_manager.set_value("config.json", "summary_interval", int(param_value)):
                await get_bot().send(event, f"已更新记忆配置: {param_name} = {param_value}")
            else:
                await get_bot().send(event, "更新配置失败（存储错误）")
        else:
            await get_bot().send(event, f"未知的参数名: {param_name}")
    except ValueError:
        await get_bot().send(event, "参数值必须为数字")
    return True