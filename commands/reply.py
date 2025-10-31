from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent
from ..utils.config import config_manager
from . import register_command
from .__init__ import is_admin

def get_status_key(event: MessageEvent) -> str:
    if event.message_type == "private":
        return f"user_{event.user_id}"
    else:
        return f"group_{event.group_id}"

@register_command(
    command=["回复状态", "reply status"],
    description="设置当前聊天场景的回复状态",
    usage="\\回复状态 on/off/admin 或 \\reply status on/off/admin"
)
async def handle_reply_status(event: MessageEvent, command_text: str) -> bool:
    key = get_status_key(event)
    
    # 解析命令参数
    command_str = command_text[1:].strip()
    if command_str.startswith("回复状态"):
        params = command_str[4:].strip().lower()
    elif command_str.startswith("reply status"):
        params = command_str[12:].strip().lower()
    else:
        # 获取当前状态并显示帮助信息
        current_status = config_manager.get_value("config.json", f"reply_status.{key}", "on")
        await get_bot().send(event, 
                           f"当前回复状态：{current_status}\n" 
                           f"使用格式：\\回复状态 on/off/admin 或 \\reply status on/off/admin\n" 
                           f"on：处理所有消息\n" 
                           f"admin：仅处理管理员消息\n" 
                           f"off：不处理任何消息")
        return True
    
    # 根据参数设置状态
    if params in ["on", "admin", "off"]:
        if config_manager.set_value("config.json", f"reply_status.{key}", params):
            status_text = {
                "on": "已开启处理所有消息",
                "admin": "已设置为仅处理管理员消息",
                "off": "已关闭回复功能"
            }
            await get_bot().send(event, status_text[params], at_sender=True)
    else:
        await get_bot().send(event, "参数错误！请使用：on/admin/off")
    return True

@register_command(
    command=["开启回复", "reply on"],
    description="开启当前聊天场景的回复功能（处理所有消息）",
    usage="\\开启回复 或 \\reply on"
)
async def handle_enable_reply(event: MessageEvent, _: str) -> bool:
    key = get_status_key(event)
    if config_manager.set_value("config.json", f"reply_status.{key}", "on"):
        await get_bot().send(event, "已开启处理所有消息", at_sender=True)
    return True

@register_command(
    command=["关闭回复", "reply off"],
    description="关闭当前聊天场景的回复功能",
    usage="\\关闭回复 或 \\reply off"
)
async def handle_disable_reply(event: MessageEvent, _: str) -> bool:
    key = get_status_key(event)
    if config_manager.set_value("config.json", f"reply_status.{key}", "off"):
        await get_bot().send(event, "已关闭回复功能", at_sender=True)
    return True

@register_command(
    command=["只回复管理员", "reply admin_only"],
    description="设置当前聊天场景只回复管理员消息",
    usage="\\只回复管理员 或 \\reply admin_only"
)
async def handle_admin_only_reply(event: MessageEvent, _: str) -> bool:
    key = get_status_key(event)
    if config_manager.set_value("config.json", f"reply_status.{key}", "admin"):
        await get_bot().send(event, "已设置为仅处理管理员消息", at_sender=True)
    return True

def is_reply_enabled(event: MessageEvent) -> bool:
    key = get_status_key(event)
    # 使用配置管理器获取回复状态，默认为on
    reply_status = config_manager.get_value("config.json", f"reply_status.{key}", "on")
    
    # 根据不同状态进行处理
    if reply_status == "off":
        return False
    elif reply_status == "admin":
        # 仅管理员消息才处理
        return is_admin(str(event.user_id))
    else:  # reply_status == "on" 或其他未知值默认处理所有消息
        return True