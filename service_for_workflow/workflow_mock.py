"""
工作流服务模拟 - 支持动态状态转换
后续替换为实际工作流服务
"""
import time
from typing import Dict, Any, List
from enum import Enum


class WorkflowStatus(Enum):
    """工作流状态"""
    PROCESSING = "processing"  # 处理中
    INTERRUPT = "interrupt"     # 中断（需要更多信息）
    SUCCESS = "success"       # 成功
    FAIL = "fail"             # 失败


class WorkflowService:
    """工作流服务（模拟）- 支持动态状态转换"""

    def __init__(self):
        self._counter = 0
        # 维护每个 run_id 的状态信息
        self._workflow_states: Dict[str, Dict[str, Any]] = {}

    def start_workflow(self, user_input: str) -> str:
        """启动工作流"""
        self._counter += 1
        run_id = f"run_{self._counter}_{int(time.time())}"
        print(f"[Workflow] 启动: {run_id}, 输入: {user_input}")

        # 初始化工作流状态
        run_num = int(run_id.split('_')[1])
        self._workflow_states[run_id] = {
            'run_num': run_num,
            'query_count': 0,
            'status': WorkflowStatus.PROCESSING,
            'progress_nodes': [
                "数据加载",
                "预处理",
                "特征提取",
                "模型推理",
                "结果生成"
            ],
            'current_step': 0
        }

        return run_id

    def get_workflow_info(self, run_id: str) -> Dict[str, Any]:
        """
        获取工作流信息 - 支持动态状态转换

        状态转换规则：
        - 第 1-3 次查询返回 processing（带中间节点信息）
        - 第 4 �查询根据 run_id 模块决定最终状态
        """
        if run_id not in self._workflow_states:
            # 兼容旧版本：如果 run_id 不在状态中，使用旧逻辑
            return self._get_legacy_workflow_info(run_id)

        state = self._workflow_states[run_id]
        state['query_count'] += 1
        query_count = state['query_count']

        # 第 1-3 次查询返回 processing 状态
        if query_count <= 3:
            state['current_step'] = query_count - 1
            progress_info = self.get_processing_progress(run_id)
            return {
                "run_id": run_id,
                "status": WorkflowStatus.PROCESSING,
                "message": "正在处理中...",
                "visualization_url": None,
                "progress_info": progress_info
            }

        # 第 4 次查询决定最终状态
        run_num = state['run_num']

        if run_num % 3 == 0:
            # 中断
            state['status'] = WorkflowStatus.INTERRUPT
            return {
                "run_id": run_id,
                "status": WorkflowStatus.INTERRUPT,
                "message": "需要更多信息：请提供数据范围和时间周期",
                "visualization_url": None,
                "interrupt_info": {"question": "请提供数据范围和时间周期"}
            }
        elif run_num % 3 == 1:
            # 成功
            state['status'] = WorkflowStatus.SUCCESS
            return {
                "run_id": run_id,
                "status": WorkflowStatus.SUCCESS,
                "message": "分析完成！数据显示过去一个月增长了25%，主要来自产品A和B。",
                "visualization_url": f"https://example.com/chart/{run_id}",
                "progress_info": None
            }
        else:
            # 失败
            state['status'] = WorkflowStatus.FAIL
            return {
                "run_id": run_id,
                "status": WorkflowStatus.FAIL,
                "message": "处理失败：系统内部错误",
                "visualization_url": None,
                "progress_info": None
            }

    def _get_legacy_workflow_info(self, run_id: str) -> Dict[str, Any]:
        """兼容旧版本的工作流信息获取"""
        try:
            run_num = int(run_id.split('_')[1])
        except:
            run_num = 0

        if run_num % 3 == 0:
            return {
                "run_id": run_id,
                "status": WorkflowStatus.INTERRUPT,
                "message": "需要更多信息：请提供数据范围和时间周期",
                "visualization_url": None,
                "interrupt_info": {"question": "请提供数据范围和时间周期"}
            }
        elif run_num % 3 == 1:
            return {
                "run_id": run_id,
                "status": WorkflowStatus.SUCCESS,
                "message": "分析完成！数据显示过去一个月增长了25%，主要来自产品A和B。",
                "visualization_url": f"https://example.com/chart/{run_id}",
                "progress_info": None
            }
        else:
            return {
                "run_id": run_id,
                "status": WorkflowStatus.FAIL,
                "message": "处理失败：系统内部错误",
                "visualization_url": None,
                "progress_info": None
            }

    def get_processing_progress(self, run_id: str) -> Dict[str, Any]:
        """
        获取处理进度信息

        Args:
            run_id: 工作流运行 ID

        Returns:
            进度信息字典
        """
        if run_id not in self._workflow_states:
            return {
                "current_step": 0,
                "total_steps": 5,
                "nodes": ["数据加载", "预处理", "特征提取", "模型推理", "结果生成"],
                "percentage": 0
            }

        state = self._workflow_states[run_id]
        current_step = state['current_step']
        nodes = state['progress_nodes']
        total_steps = len(nodes)

        return {
            "current_step": current_step,
            "current_node": nodes[current_step] if current_step < total_steps else "完成",
            "total_steps": total_steps,
            "nodes": nodes,
            "percentage": int((current_step / total_steps) * 100),
            "status": f"正在执行: {nodes[current_step] if current_step < total_steps else '完成'}"
        }

    def restart_workflow(self, user_input: str, run_id: str) -> str:
        """重启工作流"""
        new_counter = int(run_id.split('_')[1]) + 1000
        new_run_id = f"run_{new_counter}_{int(time.time())}"
        print(f"[[Workflow] 重启: {new_run_id}, 原run: {run_id}")

        # 初始化新工作流状态
        self._workflow_states[new_run_id] = {
            'run_num': new_counter,
            'query_count': 0,
            'status': WorkflowStatus.PROCESSING,
            'progress_nodes': [
                "数据加载",
                "预处理",
                "特征提取",
                "模型推理",
                "结果生成"
            ],
            'current_step': 0
        }

        return new_run_id


# 全局实例
workflow_service = WorkflowService()
