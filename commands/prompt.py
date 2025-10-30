# 保留原有的prompt状态独立管理逻辑（使用prompt_status.json）
import json
import os
from typing import Dict, List, Optional
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment
from . import register_command

# 提示词存储路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PROMPTS_FILE = os.path.join(DATA_DIR, "prompts.json")
PROMPT_STATUS_FILE = os.path.join(DATA_DIR, "prompt_status.json")  # 保留独立状态文件

os.makedirs(DATA_DIR, exist_ok=True)

# 初始化提示词文件
if not os.path.exists(PROMPTS_FILE):
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f, ensure_ascii=False, indent=2)

def load_prompts() -> Dict[str, str]:
    """从本地文件加载提示词"""
    try:
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

# 保留独立的提示词状态加载/保存函数
def load_prompt_status() -> Dict[str, bool]:
    """从独立文件加载提示词启用状态"""
    try:
        with open(PROMPT_STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_prompt_status(status: Dict[str, bool]) -> bool:
    """保存提示词状态到独立文件"""
    try:
        with open(PROMPT_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存提示词状态失败：{str(e)}")
        return False

def init_prompt_status():
    """初始化提示词状态（默认全部启用）"""
    prompts = load_prompts()
    if not os.path.exists(PROMPT_STATUS_FILE):
        status = {name: True for name in prompts.keys()}
        save_prompt_status(status)

init_prompt_status()


def save_prompts(prompts: Dict[str, str]) -> bool:
    """保存提示词到本地文件（新增：同步更新状态文件）"""
    try:
        with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
            json.dump(prompts, f, ensure_ascii=False, indent=2)
        
        # 同步状态文件（新增提示词默认启用）
        status = load_prompt_status()
        for name in prompts:
            if name not in status:
                status[name] = True
        save_prompt_status(status)
        return True
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
        # 解析格式：\创建提示词 名称 内容
        _, name_and_content = command_text.split(" ", 1)
        name, content = name_and_content.split(" ", 1)
        name = name.strip()
        content = content.strip()
        
        if not name or not content:
            raise ValueError
        
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
        # 解析格式：\删除提示词 名称
        _, name = command_text.split(" ", 1)
        name = name.strip()
        
        if not name:
            raise ValueError
        
        prompts = load_prompts()
        if name not in prompts:
            bot = get_bot()
            await bot.send(event, f"提示词 `{name}` 不存在！")
            return True
        
        del prompts[name]
        if save_prompts(prompts):
            # 删除后同步更新状态文件
            status = load_prompt_status()
            if name in status:
                del status[name]
                save_prompt_status(status)
            bot = get_bot()
            await bot.send(event, f"已删除提示词 `{name}`")
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
        # 解析格式：\查看提示词 名称
        _, name = command_text.split(" ", 1)
        name = name.strip()
        
        if not name:
            raise ValueError
        
        prompts = load_prompts()
        if name not in prompts:
            bot = get_bot()
            await bot.send(event, f"提示词 `{name}` 不存在！")
            return True
        
        status = load_prompt_status()
        status_str = "✅ 启用" if status.get(name, True) else "❌ 禁用"
        bot = get_bot()
        await bot.send(event, f"【{name}】[{status_str}]\n{prompts[name]}")
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
    """处理 \查看提示词列表 指令（新增：显示编号和启用状态）"""
    prompts = load_prompts()
    if not prompts:
        bot = get_bot()
        await bot.send(event, "当前没有任何提示词预设")
        return True
    
    status = load_prompt_status()
    # 生成带编号和状态的列表（按创建顺序排序，先创建的序号小）
    prompt_list = []
    for idx, (name, content) in enumerate(prompts.items(), 1):
        status_str = "✅ 启用" if status.get(name, True) else "❌ 禁用"
        prompt_list.append(f"{idx}. {name} [{status_str}]")
    
    bot = get_bot()
    await bot.send(event, f"提示词列表：\n" + "\n".join(prompt_list) + 
                 "\n\n使用 \\查看提示词 名称 查看详情")
    return True

# 新增：启用第X条提示词指令
@register_command(
    command=["启用第X条提示词", "prompt enable"],
    description="启用指定序号的提示词",
    usage="\\启用第X条提示词 X 或 \\prompt enable X（如：\\启用第X条提示词 1）"
)
async def handle_enable_prompt(event: MessageEvent, command_text: str) -> bool:
    try:
        _, x_str = command_text.split(" ", 1)
        x = int(x_str.strip())
        if x < 1:
            raise ValueError
    except ValueError:
        bot = get_bot()
        await bot.send(event, "格式错误！正确格式：\\启用第X条提示词 X（X为正整数，如 \\启用第X条提示词 1）")
        return True
    
    prompts = load_prompts()
    if x > len(prompts):
        bot = get_bot()
        await bot.send(event, f"编号超出范围！当前只有 {len(prompts)} 条提示词")
        return True
    
    # 获取对应编号的提示词名称（按创建顺序）
    prompt_name = list(prompts.keys())[x-1]
    status = load_prompt_status()
    status[prompt_name] = True
    
    if save_prompt_status(status):
        bot = get_bot()
        await bot.send(event, f"已启用第 {x} 条提示词：`{prompt_name}`")
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
        _, x_str = command_text.split(" ", 1)
        x = int(x_str.strip())
        if x < 1:
            raise ValueError
    except ValueError:
        bot = get_bot()
        await bot.send(event, "格式错误！正确格式：\\禁用第X条提示词 X（X为正整数，如 \\禁用第X条提示词 1）")
        return True
    
    prompts = load_prompts()
    if x > len(prompts):
        bot = get_bot()
        await bot.send(event, f"编号超出范围！当前只有 {len(prompts)} 条提示词")
        return True
    
    # 获取对应编号的提示词名称（按创建顺序）
    prompt_name = list(prompts.keys())[x-1]
    status = load_prompt_status()
    status[prompt_name] = False
    
    if save_prompt_status(status):
        bot = get_bot()
        await bot.send(event, f"已禁用第 {x} 条提示词：`{prompt_name}`")
    else:
        bot = get_bot()
        await bot.send(event, f"禁用第 {x} 条提示词失败（存储错误）")
    return True

def get_all_prompts() -> str:
    """获取所有启用的提示词（修改：只返回启用状态的提示词）"""
    prompts = load_prompts()
    status = load_prompt_status()
    if not prompts:
        return ""
    
    # 只拼接启用的提示词
    enabled_prompts = [
        f"【{name}】{content}" 
        for name, content in prompts.items() 
        if status.get(name, True)
    ]
    return "\n\n".join(enabled_prompts)