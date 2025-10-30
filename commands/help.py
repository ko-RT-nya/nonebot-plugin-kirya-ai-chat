from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot import get_bot
from . import register_command, COMMAND_METADATA

# 每页显示指令数量
COMMANDS_PER_PAGE = 20

@register_command(
    command=["帮助", "help"],
    description="显示所有指令的帮助信息",
    usage="\\帮助 [页码] 或 \\help [页码]（如：\\帮助 2 或 \\help 2）"
)
async def handle_help(event: MessageEvent, command_text: str) -> bool:
    """处理帮助指令，支持分页显示"""
    # 解析页码
    parts = command_text.split()
    page = 1
    if len(parts) >= 2:
        try:
            page = max(1, int(parts[1]))
        except ValueError:
            pass

    # 获取所有指令并排序
    commands = sorted(COMMAND_METADATA.values(), key=lambda x: x["aliases"][1].lower())
    total = len(commands)
    total_pages = (total + COMMANDS_PER_PAGE - 1) // COMMANDS_PER_PAGE
    page = min(page, total_pages)  # 防止页码超出范围

    # 计算当前页指令
    start = (page - 1) * COMMANDS_PER_PAGE
    end = start + COMMANDS_PER_PAGE
    current_commands = commands[start:end]

    # 构建帮助信息
    help_msg = [f"📚 指令帮助（第 {page}/{total_pages} 页）"]
    for cmd in current_commands:
        aliases = "、".join([f"\\{a}" for a in cmd["aliases"]])
        help_msg.append(f"\n【指令】{aliases}")
        help_msg.append(f"【功能】{cmd['description']}")
        help_msg.append(f"【用法】{cmd['usage']}")

    # 添加翻页提示
    if total_pages > 1:
        help_msg.append(f"\n🔍 输入 \\帮助 [页码] 或 \\help [页码] 查看其他页（1-{total_pages}）")

    await get_bot().send(event, "\n".join(help_msg))
    return True