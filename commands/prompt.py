import json
import os
from typing import Dict, List, Optional
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment
from . import register_command
from ..utils.config import config_manager

# 初始化提示词配置文件
prompts_config = config_manager.load_config("prompts_config.json")
if "prompts" not in prompts_config:
    prompts_config["prompts"] = {}
    config_manager.save_config("prompts_config.json", prompts_config)
    
if "status" not in prompts_config:
    prompts_config["status"] = {}
    config_manager.save_config("prompts_config.json", prompts_config)

def load_prompts() -> Dict[str, str]:
    """从prompts_config.json加载提示词"""
    prompts_config = config_manager.load_config("prompts_config.json")
    return prompts_config.get("prompts", {})

# 保留独立的提示词状态加载/保存函数
def load_prompt_status(context: str = None) -> Dict[str, bool]:
    """
    从prompts_config.json加载提示词启用状态
    context: 聊天环境标识，None时返回所有环境的状态
    """
    prompts_config = config_manager.load_config("prompts_config.json")
    all_status = prompts_config.get("context_status", {})
    
    if context:
        # 返回指定环境的状态，如果不存在则初始化并返回默认值（全部启用）
        if context not in all_status:
            prompts = load_prompts()
            all_status[context] = {name: True for name in prompts.keys()}
            # 保存初始化的状态
            prompts_config["context_status"] = all_status
            config_manager.save_config("prompts_config.json", prompts_config)
        return all_status[context]
    else:
        return all_status

def save_prompt_status(status: Dict[str, bool], context: str = None) -> bool:
    """
    保存提示词状态到prompts_config.json
    context: 聊天环境标识，None时保存所有环境的状态
    """
    try:
        prompts_config = config_manager.load_config("prompts_config.json")
        if context:
            # 保存指定环境的状态
            all_status = prompts_config.get("context_status", {})
            all_status[context] = status
            prompts_config["context_status"] = all_status
        else:
            # 兼容旧版，保存到根级status（不推荐使用）
            prompts_config["status"] = status
        return config_manager.save_config("prompts_config.json", prompts_config)
    except Exception as e:
        print(f"保存提示词状态失败：{str(e)}")
        return False

def init_prompt_status():
    """初始化提示词配置"""
    prompts_config = config_manager.load_config("prompts_config.json")
    
    # 确保有prompts字段
    if "prompts" not in prompts_config:
        prompts_config["prompts"] = {}
        config_manager.save_config("prompts_config.json", prompts_config)
    
    # 确保有context_status字段
    if "context_status" not in prompts_config:
        prompts_config["context_status"] = {}
        config_manager.save_config("prompts_config.json", prompts_config)

init_prompt_status()


def save_prompts(prompts: Dict[str, str]) -> bool:
    """保存提示词到prompts_config.json（同步更新所有环境的状态）"""
    try:
        prompts_config = config_manager.load_config("prompts_config.json")
        prompts_config["prompts"] = prompts
        
        # 同步所有环境的状态（新增提示词默认启用）
        all_status = prompts_config.get("context_status", {})
        for context, status in all_status.items():
            for name in prompts:
                if name not in status:
                    status[name] = True
        prompts_config["context_status"] = all_status
        
        # 兼容旧版状态
        old_status = prompts_config.get("status", {})
        for name in prompts:
            if name not in old_status:
                old_status[name] = True
        prompts_config["status"] = old_status
        
        return config_manager.save_config("prompts_config.json", prompts_config)
    except Exception as e:
        print(f"保存提示词失败：{str(e)}")
        return False

@register_command(
    command=["创建提示词", "prompt create"],
    description="创建新的提示词预设",
    usage="\\创建提示词 名称 内容 或 \\prompt create 名称 内容（如：\\创建提示词 助手 你是一个乐于助人的助手）"
)
async def handle_create_prompt(event: MessageEvent, command_text: str) -> bool:
    """处理 \创建提示词 指令"""
    try:
        # 解析格式：\创建提示词 名称 内容 或 \prompt create 名称 内容
        # 去除命令开头的反斜杠
        command_str = command_text[1:].strip()
        
        if command_str.startswith("prompt create"):
            # English command
            parts = command_str[13:].strip().split(" ", 1)
        else:
            # Chinese command
            if command_str.startswith("创建提示词"):
                # 处理 "创建提示词 名称 内容" 格式
                name_and_content = command_str[5:].strip()
                parts = name_and_content.split(" ", 1)
            else:
                # 处理其他可能的命令前缀格式
                parts = command_str.split(" ", 1)
                if len(parts) >= 1:
                    parts = parts[1].split(" ", 1)  # 再次分割以获取名称和内容
        
        if len(parts) < 2:
            raise ValueError("缺少提示词内容")
            
        name = parts[0].strip()
        content = parts[1].strip()
        
        if not name or not content:
            raise ValueError("提示词名称或内容不能为空")
        
        prompts = load_prompts()
        if name in prompts:
            bot = get_bot()
            await bot.send(event, f"提示词 `{name}` 已存在！")
            return True
        
        prompts[name] = content
        if save_prompts(prompts):
            bot = get_bot()
            await bot.send(event, f"已创建提示词 `{name}`")
        else:
            bot = get_bot()
            await bot.send(event, f"创建提示词 `{name}` 失败（存储错误）")
        return True
    except ValueError:
        bot = get_bot()
        await bot.send(event, "格式错误！正确格式：\\创建提示词 名称 内容（如 \\创建提示词 助手 你是一个乐于助人的助手）")
        return True

@register_command(
    command=["删除提示词", "prompt delete"],
    description="删除指定提示词",
    usage="\\删除提示词 名称 或 \\prompt delete 名称（如：\\删除提示词 助手）"
)
async def handle_delete_prompt(event: MessageEvent, command_text: str) -> bool:
    """处理 \删除提示词 指令"""
    try:
        # 解析格式：\删除提示词 名称 或 \prompt delete 名称
        # 去除命令开头的反斜杠
        command_str = command_text[1:].strip()
        
        if command_str.startswith("prompt delete"):
            # English command
            name = command_str[13:].strip()
        else:
            # Chinese command
            if command_str.startswith("删除提示词"):
                # 处理 "删除提示词 名称" 格式
                name = command_str[5:].strip()
            else:
                # 处理其他可能的命令前缀格式
                try:
                    _, name = command_str.split(" ", 1)
                    name = name.strip()
                except ValueError:
                    # 如果分割失败，尝试将剩余部分作为名称
                    name = command_str
        
        if not name:
            raise ValueError("提示词名称不能为空")
        
        prompts = load_prompts()
        if name not in prompts:
            bot = get_bot()
            await bot.send(event, f"提示词 `{name}` 不存在！")
            return True
        
        del prompts[name]
        if save_prompts(prompts):
            # 直接从配置文件加载和修改所有环境的状态，更高效
            prompts_config = config_manager.load_config("prompts_config.json")
            
            # 处理所有聊天环境的状态
            if "context_status" in prompts_config:
                for context, status in prompts_config["context_status"].items():
                    if name in status:
                        del status[name]
                # 保存更新后的配置
                config_manager.save_config("prompts_config.json", prompts_config)
            
            # 兼容旧版，删除根级status中的记录
            if "status" in prompts_config and name in prompts_config["status"]:
                del prompts_config["status"][name]
                config_manager.save_config("prompts_config.json", prompts_config)
            
            bot = get_bot()
            await bot.send(event, f"已删除提示词 `{name}`（所有聊天环境的状态已同步更新）")
        else:
            bot = get_bot()
            await bot.send(event, f"删除提示词 `{name}` 失败（存储错误）")
        return True
    except ValueError:
        bot = get_bot()
        await bot.send(event, "格式错误！正确格式：\\删除提示词 名称（如 \\删除提示词 助手）")
        return True

@register_command(
    command=["查看提示词", "prompt show"],
    description="查看指定提示词详情",
    usage="\\查看提示词 名称 或 \\prompt show 名称（如：\\查看提示词 助手）"
)
async def handle_view_prompt(event: MessageEvent, command_text: str) -> bool:
    """处理 \查看提示词 指令"""
    try:
        # 解析格式：\查看提示词 名称 或 \prompt show 名称
        # 去除命令开头的反斜杠
        command_str = command_text[1:].strip()
        
        if command_str.startswith("prompt show"):
            # English command
            name = command_str[11:].strip()
        else:
            # Chinese command
            # 处理 "查看提示词 名称" 格式
            if command_str.startswith("查看提示词"):
                name = command_str[5:].strip()
            else:
                # 处理其他可能的命令前缀格式，增加错误处理
                try:
                    # 兼容原来的split方式
                    _, name = command_str.split(" ", 1)
                    name = name.strip()
                except ValueError:
                    # 如果分割失败，尝试将剩余部分作为名称
                    name = command_str
        
        if not name:
            raise ValueError("提示词名称不能为空")
        
        prompts = load_prompts()
        if name not in prompts:
            bot = get_bot()
            await bot.send(event, f"提示词 `{name}` 不存在！")
            return True
        
        # 获取当前聊天环境的状态
        context = get_chat_context(event)
        status = load_prompt_status(context)
        status_str = "✅ 启用" if status.get(name, True) else "❌ 禁用"
        
        # 显示当前环境信息
        if context.startswith("group_"):
            env_info = f"[群聊 {context[6:]}] "
        else:
            env_info = "[私聊] "
        
        bot = get_bot()
        await bot.send(event, f"{env_info}【{name}】[{status_str}]\n{prompts[name]}")
        return True
    except ValueError:
        bot = get_bot()
        await bot.send(event, "格式错误！正确格式：\\查看提示词 名称（如 \\查看提示词 助手）")
        return True

@register_command(
    command=["查看提示词列表", "prompt list"],
    description="显示所有提示词列表",
    usage="\\查看提示词列表 或 \\prompt list"
)
async def handle_list_prompts(event: MessageEvent, _: str) -> bool:
    """处理 \查看提示词列表 指令（新增：显示编号和当前环境的启用状态）"""
    prompts = load_prompts()
    if not prompts:
        bot = get_bot()
        await bot.send(event, "当前没有任何提示词预设")
        return True
    
    # 获取当前聊天环境的状态
    context = get_chat_context(event)
    status = load_prompt_status(context)
    
    # 显示当前环境信息
    if context.startswith("group_"):
        env_info = f"[群聊 {context[6:]}] "
    else:
        env_info = "[私聊] "
    
    # 生成带编号和状态的列表（按创建顺序排序，先创建的序号小）
    prompt_list = []
    for idx, (name, content) in enumerate(prompts.items(), 1):
        status_str = "✅ 启用" if status.get(name, True) else "❌ 禁用"
        prompt_list.append(f"{idx}. {name} [{status_str}]")
    
    bot = get_bot()
    await bot.send(event, f"{env_info}提示词列表：\n" + "\n".join(prompt_list) + 
                 "\n\n使用 \查看提示词 名称 查看详情")
    return True

# 新增：启用第X条提示词指令
@register_command(
    command=["启用第X条提示词", "prompt enable"],
    description="启用指定序号的提示词",
    usage="\\启用第X条提示词 X 或 \\prompt enable X（如：\\启用第X条提示词 1）"
)
async def handle_enable_prompt(event: MessageEvent, command_text: str) -> bool:
    try:
        # 解析命令文本，提取提示词索引
        command_str = command_text[1:].strip()  # 去除开头的反斜杠
        
        if command_str.startswith("prompt enable"):
            # 英文命令格式：prompt enable 索引
            index_str = command_str[13:].strip()
        else:
            # 中文命令格式：启用第X条提示词 索引
            if command_str.startswith("启用第X条提示词"):
                index_str = command_str[7:].strip()
            else:
                # 处理其他可能的命令前缀格式
                try:
                    # 尝试分割获取索引
                    parts = command_str.split(" ", 1)
                    if len(parts) < 2:
                        raise ValueError("缺少提示词索引")
                    index_str = parts[1].strip()
                except ValueError:
                    # 如果分割失败，尝试直接提取
                    index_str = command_str
        
        if not index_str:
            raise ValueError("缺少提示词索引")
        
        try:
            x = int(index_str)  # 转换为索引
            if x < 1:
                raise ValueError
        except ValueError:
            raise ValueError("索引必须是数字！正确格式：\启用第X条提示词 X（X为正整数）")
    except ValueError:
        bot = get_bot()
        await bot.send(event, "格式错误！正确格式：\\启用第X条提示词 X（X为正整数，如 \\启用第X条提示词 1）")
        return True
    
    prompts = load_prompts()
    if x > len(prompts):
        bot = get_bot()
        await bot.send(event, f"编号超出范围！当前只有 {len(prompts)} 条提示词")
        return True
    
    # 获取当前聊天环境
    context = get_chat_context(event)
    
    # 获取对应编号的提示词名称（按创建顺序）
    prompt_name = list(prompts.keys())[x-1]
    status = load_prompt_status(context)
    status[prompt_name] = True
    
    if save_prompt_status(status, context):
        # 显示当前环境信息
        if context.startswith("group_"):
            env_info = f"[群聊 {context[6:]}] "
        else:
            env_info = "[私聊] "
        
        bot = get_bot()
        await bot.send(event, f"{env_info}已启用第 {x} 条提示词：`{prompt_name}`")
    else:
        bot = get_bot()
        await bot.send(event, f"启用第 {x} 条提示词失败（存储错误）")
    return True

# 新增：禁用第X条提示词指令
@register_command(
    command=["禁用第X条提示词", "prompt disable"],
    description="禁用指定序号的提示词",
    usage="\\禁用第X条提示词 X 或 \\prompt disable X（如：\\禁用第X条提示词 1）"
)
async def handle_disable_prompt(event: MessageEvent, command_text: str) -> bool:
    try:
        # 解析格式：\禁用第X条提示词 X 或 \prompt disable X
        # 去除命令开头的反斜杠
        command_str = command_text[1:].strip()
        
        if command_str.startswith("prompt disable"):
            # 英文命令格式：prompt disable 索引
            index_str = command_str[14:].strip()
        else:
            # 中文命令格式：禁用第X条提示词 索引
            if command_str.startswith("禁用第X条提示词"):
                index_str = command_str[7:].strip()
            else:
                # 处理其他可能的命令前缀格式
                try:
                    # 尝试分割获取索引
                    parts = command_str.split(" ", 1)
                    if len(parts) < 2:
                        raise ValueError("缺少提示词索引")
                    index_str = parts[1].strip()
                except ValueError:
                    # 如果分割失败，尝试直接提取
                    index_str = command_str
        
        if not index_str:
            raise ValueError("缺少提示词索引")
        
        try:
            x = int(index_str)  # 转换为索引
            if x < 1:
                raise ValueError
        except ValueError:
            raise ValueError("索引必须是数字！正确格式：\禁用第X条提示词 X（X为正整数）")
    except ValueError:
        bot = get_bot()
        await bot.send(event, "格式错误！正确格式：\\禁用第X条提示词 X（X为正整数，如 \\禁用第X条提示词 1）")
        return True
    
    prompts = load_prompts()
    if x > len(prompts):
        bot = get_bot()
        await bot.send(event, f"编号超出范围！当前只有 {len(prompts)} 条提示词")
        return True
    
    # 获取当前聊天环境
    context = get_chat_context(event)
    
    # 获取对应编号的提示词名称（按创建顺序）
    prompt_name = list(prompts.keys())[x-1]
    status = load_prompt_status(context)
    status[prompt_name] = False
    
    if save_prompt_status(status, context):
        # 显示当前环境信息
        if context.startswith("group_"):
            env_info = f"[群聊 {context[6:]}] "
        else:
            env_info = "[私聊] "
        
        bot = get_bot()
        await bot.send(event, f"{env_info}已禁用第 {x} 条提示词：`{prompt_name}`")
    else:
        bot = get_bot()
        await bot.send(event, f"禁用第 {x} 条提示词失败（存储错误）")
    return True

def get_chat_context(event: MessageEvent) -> str:
    """
    获取聊天环境的唯一标识
    群聊返回 group_{group_id}，私聊返回 private_{user_id}
    """
    if hasattr(event, 'group_id') and event.group_id:
        return f"group_{event.group_id}"
    else:
        return f"private_{event.user_id}"

def get_all_prompts(event: Optional[MessageEvent] = None) -> str:
    """获取所有提示词（用于主模块）"""
    prompts = load_prompts()
    if not prompts:
        return ""
    
    if event:
        # 有事件对象时，获取当前聊天环境的状态
        status = load_prompt_status(get_chat_context(event))
    else:
        # 没有事件对象时，使用默认状态（全部启用）
        status = {name: True for name in prompts.keys()}
    
    # 过滤出已启用的提示词，只返回内容，不包含提示词名称
    enabled_prompts = [
        content  # 只使用提示词内容，不包含名称
        for name, content in prompts.items() 
        if status.get(name, True)
    ]
    return "\n\n".join(enabled_prompts)