# AI聊天插件日志功能说明

本插件实现了详细的日志记录功能，用于记录发送给AI的原始信息和从AI接收到的原始信息，方便用户检查和调试。

## 日志文件位置

日志文件默认保存在插件的 `data/logs/` 目录下：

```
data/
└── logs/
    ├── ai_chat_YYYY-MM-DD.jsonl        # 每日的主要日志文件
    └── debug/                          # 调试用的完整交互日志目录
        └── interaction_用户ID_时间戳.json  # 完整的API交互数据
```

## 日志内容说明

### 1. 每日主要日志文件 (ai_chat_YYYY-MM-DD.jsonl)

这是一个JSON Lines格式的文件，每条记录包含以下信息：

- `timestamp`: 日志记录时间（ISO格式）
- `user_id`: 用户ID
- `group_id`: 群组ID（如果在群聊中）
- `model_name`: 使用的AI模型名称
- `user_message`: 用户发送的消息
- `ai_reply`: AI回复的消息
- `memory_content`: 发送给AI的记忆内容
- `request_summary`: 请求摘要信息（包含请求大小和关键结构）
- `response_summary`: 响应摘要信息
- `error`: 错误信息（如有）

### 2. 调试用完整交互日志 (interaction_用户ID_时间戳.json)

这个文件包含完整的API交互数据，用于详细调试：

- `timestamp`: 交互时间
- `user_id`: 用户ID
- `request`: 发送给API的完整请求数据（**包含所有提示词、分割提示词和记忆内容**）
- `response`: 从API接收的完整响应数据

> **重要提示**：这里的`request`字段包含了**所有发送给AI的原始信息**，包括：
> - 前缀提示词（通过`get_all_prompts()`获取）
> - 分割提示词（如果启用）
> - 记忆内容
> - 带有<新消息>标签的用户消息
> 
> 这正是您需要的完整调试信息！

## 查看日志的方法

### 方法一：直接查看日志文件

使用文本编辑器（如VS Code、Notepad++等）直接打开日志文件查看。对于JSON格式的日志，建议使用支持语法高亮和格式化的编辑器。

### 方法二：使用日志分析工具

对于大量日志数据，可以使用专门的日志分析工具，如：
- [jq](https://stedolan.github.io/jq/) - 命令行JSON处理工具
- [Logstash + Kibana](https://www.elastic.co/elastic-stack/) - 企业级日志分析解决方案

### 方法三：编写简单脚本分析日志

可以编写Python脚本快速分析日志内容。特别是用于查看完整的请求数据：

```python
import json
import os

# 读取完整的调试日志，查看所有发送给AI的信息
def analyze_full_requests(debug_dir="data/logs/debug"):
    if not os.path.exists(debug_dir):
        print(f"调试日志目录不存在: {debug_dir}")
        return
    
    # 获取最新的10个调试日志文件
    log_files = sorted([f for f in os.listdir(debug_dir) if f.startswith("interaction_")], 
                      reverse=True)[:10]
    
    for log_file in log_files:
        file_path = os.path.join(debug_dir, log_file)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
                print(f"\n=== 日志文件: {log_file} ===")
                print(f"时间: {data.get('timestamp')}")
                print(f"用户ID: {data.get('user_id')}")
                
                # 分析请求数据
                request = data.get('request', {})
                if 'contents' in request:  # Gemini格式
                    print("\n=== 完整发送给AI的内容 (Gemini) ===")
                    contents = request.get('contents', [])
                    for content in contents:
                        if 'parts' in content:
                            for part in content.get('parts', []):
                                if 'text' in part:
                                    print(part['text'])
                elif 'messages' in request:  # DeepSeek格式
                    print("\n=== 完整发送给AI的内容 (DeepSeek) ===")
                    messages = request.get('messages', [])
                    for message in messages:
                        print(f"角色: {message.get('role')}")
                        print(f"内容:\n{message.get('content')}\n")
                
        except Exception as e:
            print(f"读取日志文件 {log_file} 失败: {str(e)}")

# 运行分析
analyze_full_requests()
```

运行此脚本将显示最近的完整请求数据，包括所有发送给AI的提示词、分割提示词、记忆内容和用户消息。

## 日志管理

### 日志轮转

日志按日期自动轮转，每天生成一个新的日志文件。对于大型机器人，建议定期归档或清理旧日志文件。

### 日志大小控制

为了避免日志文件过大影响性能：
1. 主要日志文件只记录请求和响应的摘要信息
2. 完整的交互数据只保存在debug目录下的单独文件中
3. 建议定期清理debug目录中的旧文件

### 确保记录所有请求数据

当前实现已经确保：
- `prepare_gemini_request` 和 `prepare_deepseek_request` 函数会将**所有提示词、分割提示词、记忆内容和用户消息**组合成完整的请求数据
- 这些完整的请求数据会被保存到debug目录下的交互日志文件中
- 您可以通过查看这些日志文件，获取发送给AI的所有原始信息，用于调试目的

## 隐私注意事项

日志文件可能包含用户的隐私信息，请妥善保管：
1. 不要将日志文件上传到公共代码仓库
2. 在分享日志用于调试时，建议先匿名化敏感信息
3. 定期清理不再需要的日志文件

## 常见问题解答

### Q: 为什么有些交互没有记录到debug目录？
A: Debug目录只保存完整的API交互，当请求或响应失败时，可能不会生成完整的交互日志。

### Q: 如何查看完整的发送给AI的内容？
A: 查看 `data/logs/debug/` 目录下的 `interaction_*.json` 文件，这些文件包含了完整的请求数据，包括所有提示词、分割提示词和记忆内容。

### Q: 如何禁用日志功能？
A: 目前没有直接的配置项禁用日志功能。如需临时禁用，可以修改`utils/logger.py`中的`log_api_interaction`方法，在方法开始处直接返回。

### Q: 日志文件太大怎么办？
A: 可以定期归档或删除旧的日志文件，特别是debug目录下的完整交互日志。