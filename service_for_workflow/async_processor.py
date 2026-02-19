"""
异步任务处理器 - 简化版
"""
import asyncio
import threading
from typing import Dict, Optional, Callable, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from workflow_mock import workflow_service, WorkflowStatus
from session_manager import Session, session_manager


class AsyncProcessor:
    """异步处理器"""

    def __init__(self, max_workers: int = 10):
        self._tasks: Dict[str, Dict] = {}
        self._task_counter = 0
        self._lock = threading.Lock()
        self._loop = None
        self._start_event_loop()

    def _start_event_loop(self):
        """启动事件循环线程"""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        threading.Thread(target=run_loop, daemon=True).start()

    async def _run_task(self, task_id: str, session_id: str, run_id: str, callback: Optional[Callable]):
        """运行异步任务"""
        try:
            print(f"[AsyncProcessor] 开始任务: {task_id}, run_id: {run_id}")
            await asyncio.sleep(2)  # 模拟工作流执行

            # 获取工作流结果
            result = workflow_service.get_workflow_info(run_id)
            print(f"[AsyncProcessor] 完成任务: {task_id}, 状态: {result['status']}")

            # 更新任务状态
            with self._lock:
                if task_id in self._tasks:
                    self._tasks[task_id]['completed'] = True
                    self._tasks[task_id]['result'] = result

            # 执行回调
            if callback:
                await callback(session_id, result)

        except Exception as e:
            print(f"[AsyncProcessor] 任务异常: {task_id}, 错误: {str(e)}")
            error_result = {
                "run_id": run_id,
                "status": WorkflowStatus.FAIL,
                "message": f"处理异常: {str(e)}",
                "visualization_url": None
            }
            with self._lock:
                if task_id in self._tasks:
                    self._tasks[task_id]['completed'] = True
                    self._tasks[task_id]['result'] = error_result

            if callback:
                await callback(session_id, error_result)

    def submit_task(self, session_id: str, run_id: str, status_callback: Optional[Callable] = None) -> str:
        """提交异步任务"""
        with self._lock:
            self._task_counter += 1
            task_id = f"task_{self._task_counter}_{int(datetime.now().timestamp())}"

            self._tasks[task_id] = {
                'task_id': task_id,
                'session_id': session_id,
                'run_id': run_id,
                'completed': False,
                'result': None
            }

        # 在事件循环中运行任务
        asyncio.run_coroutine_threadsafe(
            self._run_task(task_id, session_id, run_id, status_callback),
            self._loop
        )

        return task_id

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        with self._lock:
            return self._tasks.get(task_id)

    def get_active_tasks_count(self) -> int:
        """获取活跃任务数"""
        with self._lock:
            return sum(1 for t in self._tasks.values() if not t['completed'])


# 全局实例
async_processor = AsyncProcessor()
