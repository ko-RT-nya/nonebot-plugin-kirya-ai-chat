import os
import json
import asyncio
import requests  
from datetime import datetime
from typing import Dict, List, Optional, Callable
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent
from . import register_command, is_admin

# 从外部配置导入路径信息（避免硬编码）
from ..utils.config import DATA_DIR
MEMORY_DIR = os.path.join(DATA_DIR, "memories")
os.makedirs(os.path.join(MEMORY_DIR, "users"), exist_ok=True)
os.makedirs(os.path.join(MEMORY_DIR, "groups"), exist_ok=True)
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

async def generate_summary(
    history: List[Dict],
    current_model: str,
    prepare_request: Callable,
    parse_response: Callable,
    api_url: str,
    headers: Dict,
    proxies: Dict,
    timeout: int = 15
) -> str:
    """调用AI生成聊天记录总结（通过参数注入避免循环依赖）"""
    if not history:
        return ""
    
    # 构建总结提示词
    messages_text = "\n".join([
        f"{'用户' if item['role'] == 'user' else 'AI'}: {item['content']}"
        for item in history
    ])
    prompt = f"请用简洁的语言总结以下聊天记录的核心信息（不超过600字），保留关键话题和用户偏好：\n{messages_text}"
    
    try:
        # 使用注入的请求准备函数
        data = prepare_request(prompt)
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
    user_msg: str,
    ai_reply: str,
    # 注入模型相关依赖
    current_model: str,
    prepare_request: Callable,
    parse_response: Callable,
    api_url: str,
    headers: Dict,
    proxies: Dict
):
    """更新记忆（通过参数注入外部依赖）"""
    key = get_memory_key(event)
    
    # 获取锁防止并发问题
    if key not in memory_locks:
        memory_locks[key] = asyncio.Lock()
    async with memory_locks[key]:
        memory = load_memory(key)
        
        # 添加新消息到历史记录
        now = datetime.now().timestamp()
        memory["history"].append({
            "role": "user",
            "content": user_msg,
            "timestamp": now
        })
        memory["history"].append({
            "role": "ai",
            "content": ai_reply,
            "timestamp": now
        })
        
        # 检查是否需要生成总结（60条记录或24小时）
        need_summary = (
            len(memory["history"]) >= 60 or
            (now - memory["last_summary_time"] > 86400 and memory["history"])
        )
        
        if need_summary:
            # 使用注入的参数调用总结生成
            new_summary = await generate_summary(
                memory["history"],
                current_model,
                prepare_request,
                parse_response,
                api_url,
                headers,
                proxies
            )
            # 合并总结
            if memory["summary"]:
                memory["summary"] = f"{memory['summary']}\n\n{new_summary}"
            else:
                memory["summary"] = new_summary
            # 保留最近10条记录作为上下文
            memory["history"] = memory["history"][-10:] if len(memory["history"]) > 10 else []
            memory["last_summary_time"] = now
        
        # 保存更新后的记忆
        save_memory(key, memory)

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
        content.append("\n[最近对话]")
        for item in memory["history"]:
            content.append(f"{'用户' if item['role'] == 'user' else 'AI'}: {item['content']}")
    
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