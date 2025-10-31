import os
import json
from datetime import datetime
from typing import Dict, Any

class AIChatLogger:
    """AI聊天日志记录器"""
    
    def __init__(self, base_dir: str):
        """初始化日志记录器
        
        Args:
            base_dir: 日志文件基础目录
        """
        self.log_dir = os.path.join(base_dir, "logs")
        os.makedirs(self.log_dir, exist_ok=True)
    
    def _get_log_file_path(self) -> str:
        """获取当日日志文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"ai_chat_{today}.jsonl")
    
    def log_api_interaction(
        self,
        user_id: str,
        group_id: str = None,
        model_name: str = None,
        request_data: Dict[str, Any] = None,
        response_data: Dict[str, Any] = None,
        user_message: str = None,
        ai_reply: str = None,
        memory_content: str = None,
        error: str = None
    ) -> None:
        """记录API交互日志
        
        Args:
            user_id: 用户ID
            group_id: 群组ID（可选）
            model_name: 模型名称
            request_data: 发送给API的原始请求数据
            response_data: 从API接收的原始响应数据
            user_message: 用户发送的消息
            ai_reply: AI回复的消息
            memory_content: 发送给AI的记忆内容
            error: 错误信息（如有）
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "group_id": group_id,
            "model_name": model_name,
            "user_message": user_message,
            "ai_reply": ai_reply,
            "memory_content": memory_content,
            "error": error
        }
        
        # 记录请求和响应数据（但限制大小以避免日志文件过大）
        if request_data:
            # 对于大型请求，只记录部分关键信息
            if isinstance(request_data, dict):
                log_entry["request_summary"] = {
                    "type": "api_request",
                    "has_system_prompt": "system" in str(request_data).lower(),
                    "has_messages": "messages" in request_data or "contents" in request_data,
                    "request_size": len(str(request_data))
                }
        
        if response_data:
            # 对于响应，也只记录关键信息
            log_entry["response_summary"] = {
                "type": "api_response",
                "has_error": "error" in response_data,
                "has_content": "choices" in response_data or "candidates" in response_data,
                "response_size": len(str(response_data))
            }
        
        # 将完整的请求和响应保存到单独的文件（可选，用于调试）
        if request_data and response_data:
            self._save_full_interaction(user_id, request_data, response_data)
        
        # 写入日志文件
        try:
            with open(self._get_log_file_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            # 如果日志写入失败，打印错误但不中断程序
            print(f"写入日志失败: {str(e)}")
    
    def _save_full_interaction(self, user_id: str, request_data: Dict[str, Any], response_data: Dict[str, Any]) -> None:
        """保存完整的交互数据到单独文件（用于调试）"""
        debug_dir = os.path.join(self.log_dir, "debug")
        os.makedirs(debug_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = os.path.join(debug_dir, f"interaction_{user_id}_{timestamp}.json")
        
        full_data = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "request": request_data,
            "response": response_data
        }
        
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(full_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存完整交互日志失败: {str(e)}")
    
    def log_message(self, message: str, level: str = "info") -> None:
        """记录一般日志消息
        
        Args:
            message: 日志消息
            level: 日志级别 (info, warning, error)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message
        }
        
        try:
            with open(self._get_log_file_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"写入日志失败: {str(e)}")

# 创建全局日志器实例
logger = None

def get_logger(data_dir: str = None) -> AIChatLogger:
    """获取日志器实例（单例模式）"""
    global logger
    if logger is None:
        from .config import config_manager
        actual_data_dir = data_dir or config_manager.get_data_dir()
        logger = AIChatLogger(actual_data_dir)
    return logger