from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent
from ..utils.config import config_manager
from . import register_command

def get_status_key(event: MessageEvent) -> str:
    if event.message_type == "private":
        return f"user_{event.user_id}"
    else:
        return f"group_{event.group_id}"

@register_command(
    command=["开启回复", "reply on"],
    description="开启当前聊天场景的回复功能",
    usage="\开启回复 或 \reply on"
)
async def handle_enable_reply(event: MessageEvent, _: str) -> bool:
    key = get_status_key(event)
    # 使用配置管理器更新回复状态
    if config_manager.set_value("config.json", f"reply_status.{key}", True):
        await get_bot().send(event, "已开启回复功能～", at_sender=True)
    return True

@register_command(
    command=["关闭回复", "reply off"],
    description="关闭当前聊天场景的回复功能",
    usage="\关闭回复 或 \reply off"
)
async def handle_disable_reply(event: MessageEvent, _: str) -> bool:
    key = get_status_key(event)
    # 使用配置管理器更新回复状态
    if config_manager.set_value("config.json", f"reply_status.{key}", False):
        await get_bot().send(event, "已关闭回复功能～", at_sender=True)
    return True

def is_reply_enabled(event: MessageEvent) -> bool:
    key = get_status_key(event)
    # 使用配置管理器获取回复状态，默认启用
    return config_manager.get_value("config.json", f"reply_status.{key}", True)