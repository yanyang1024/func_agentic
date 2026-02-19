"""
工作流服务模拟 - 简化版
后续替换为实际工作流服务
"""
import time
from typing import Dict, Any
from enum import Enum


class WorkflowStatus(Enum):
    """工作流状态"""
    INTERRUPT = "interrupt"
    SUCCESS = "success"
    FAIL = "fail"


class WorkflowService:
    """工作流服务（模拟）"""

    def __init__(self):
        self._counter = 0

    def start_workflow(self, user_input: str) -> str:
        """启动工作流"""
        self._counter += 1
        run_id = f"run_{self._counter}_{int(time.time())}"
        print(f"[Workflow] 启动: {run_id}, 输入: {user_input}")
        return run_id

    def get_workflow_info(self, run_id: str) -> Dict[str, Any]:
        """获取工作流信息"""
        run_num = int(run_id.split('_')[1])

        # 模拟不同状态
        if run_num % 3 == 0:
            # 中断
            return {
                "run_id": run_id,
                "status": WorkflowStatus.INTERRUPT,
                "message": "需要更多信息：请提供数据范围和时间周期",
                "visualization_url": None,
                "interrupt_info": {"question": "请提供数据范围和时间周期"}
            }
        elif run_num % 3 == 1:
            # 成功
            return {
                "run_id": run_id,
                "status": WorkflowStatus.SUCCESS,
                "message": "分析完成！数据显示过去一个月增长了25%，主要来自产品A和B。",
                "visualization_url": f"https://example.com/chart/{run_id}"
            }
        else:
            # 失败
            return {
                "run_id": run_id,
                "status": WorkflowStatus.FAIL,
                "message": "处理失败：系统内部错误",
                "visualization_url": None
            }

    def restart_workflow(self, user_input: str, run_id: str) -> str:
        """重启工作流"""
        new_counter = int(run_id.split('_')[1]) + 1000
        new_run_id = f"run_{new_counter}_{int(time.time())}"
        print(f"[Workflow] 重启: {new_run_id}, 原run: {run_id}")
        return new_run_id


# 全局实例
workflow_service = WorkflowService()
