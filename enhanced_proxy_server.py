#!/usr/bin/env python3
"""
增强型HTTP转发服务 - 支持高并发请求队列管理和长任务状态跟踪

功能特性:
1. 异步请求处理 - 提升并发性能
2. 请求队列管理 - 有序维护高并发请求
3. 长任务状态跟踪 - 超过5分钟的任务支持异步状态查询
4. 任务ID查询接口 - 实时查询任务执行状态

使用方法:
    python3 enhanced_proxy_server.py --target-host <C服务器IP> --target-port 8000 --listen-port 8080

示例:
    python3 enhanced_proxy_server.py --target-host 192.168.1.100 --target-port 8000 --listen-port 8080
"""

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from contextlib import asynccontextmanager
import httpx
import asyncio
import uuid
import time
import argparse
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
from pydantic import BaseModel
import uvicorn


# ==================== 配置模型 ====================

class TaskStatus(BaseModel):
    """任务状态模型"""
    task_id: str
    status: str  # pending, processing, completed, failed
    created_at: str
    updated_at: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    is_long_task: bool = False
    estimated_completion: Optional[str] = None


class TaskResponse(BaseModel):
    """任务响应模型"""
    success: bool
    task_id: Optional[str] = None
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ==================== 任务管理器 ====================

class TaskManager:
    """
    任务管理器 - 管理所有任务的队列和状态
    """

    # 长任务时间阈值（秒）
    LONG_TASK_THRESHOLD = 300  # 5分钟

    def __init__(self, max_concurrent: int = 10, max_queue_size: int = 100):
        """
        初始化任务管理器

        Args:
            max_concurrent: 最大并发任务数
            max_queue_size: 最大队列大小
        """
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size

        # 任务队列
        self.task_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)

        # 任务存储 - 按task_id存储任务状态
        self.tasks: Dict[str, TaskStatus] = {}

        # 信号量 - 控制并发数
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # 统计信息
        self.stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "long_tasks": 0,
            "current_queue_size": 0
        }

    async def create_task(self, request_data: Dict[str, Any], method: str, path: str,
                         headers: Dict[str, str], body: Optional[bytes] = None) -> str:
        """
        创建新任务并加入队列

        Args:
            request_data: 请求数据
            method: HTTP方法
            path: 请求路径
            headers: 请求头
            body: 请求体

        Returns:
            task_id: 任务ID
        """
        # 检查队列是否已满
        if self.task_queue.qsize() >= self.max_queue_size:
            raise HTTPException(
                status_code=503,
                detail=f"任务队列已满，当前队列大小: {self.max_queue_size}"
            )

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 创建任务状态
        task_status = TaskStatus(
            task_id=task_id,
            status="pending",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            is_long_task=False
        )

        # 存储任务
        self.tasks[task_id] = task_status

        # 创建任务信息
        task_info = {
            "task_id": task_id,
            "method": method,
            "path": path,
            "headers": headers,
            "body": body,
            "request_data": request_data,
            "created_at": time.time()
        }

        # 加入队列
        await self.task_queue.put(task_info)

        # 更新统计
        self.stats["total_tasks"] += 1
        self.stats["current_queue_size"] = self.task_queue.qsize()

        return task_id

    async def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """
        获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            TaskStatus对象或None
        """
        return self.tasks.get(task_id)

    async def process_task(self, task_info: Dict[str, Any], target_host: str, target_port: int):
        """
        处理单个任务（后台工作线程）

        Args:
            task_info: 任务信息
            target_host: 目标服务器主机
            target_port: 目标服务器端口
        """
        task_id = task_info["task_id"]
        task_status = self.tasks[task_id]

        try:
            # 获取信号量（控制并发）
            async with self.semaphore:
                # 更新状态为处理中
                task_status.status = "processing"
                task_status.updated_at = datetime.now().isoformat()

                # 构建目标URL
                target_url = f"http://{target_host}:{target_port}{task_info['path']}"

                # 发送请求
                async with httpx.AsyncClient(timeout=600.0) as client:  # 10分钟超时
                    start_time = time.time()

                    response = await client.request(
                        method=task_info["method"],
                        url=target_url,
                        headers=task_info["headers"],
                        content=task_info.get("body")
                    )

                    elapsed_time = time.time() - start_time

                    # 判断是否为长任务
                    if elapsed_time > self.LONG_TASK_THRESHOLD:
                        task_status.is_long_task = True
                        self.stats["long_tasks"] += 1

                    # 处理响应
                    try:
                        result_data = response.json()
                    except:
                        result_data = {
                            "status_code": response.status_code,
                            "content": response.text[:1000]  # 限制内容大小
                        }

                    # 更新任务状态
                    task_status.status = "completed"
                    task_status.updated_at = datetime.now().isoformat()
                    task_status.result = result_data

                    # 更新统计
                    self.stats["completed_tasks"] += 1

        except Exception as e:
            # 任务失败
            task_status.status = "failed"
            task_status.updated_at = datetime.now().isoformat()
            task_status.error = str(e)

            # 更新统计
            self.stats["failed_tasks"] += 1

    async def start_workers(self, target_host: str, target_port: int, num_workers: int = 5):
        """
        启动后台工作线程处理任务队列

        Args:
            target_host: 目标服务器主机
            target_port: 目标服务器端口
            num_workers: 工作线程数量
        """
        async def worker():
            while True:
                try:
                    # 从队列获取任务
                    task_info = await self.task_queue.get()

                    # 处理任务
                    await self.process_task(task_info, target_host, target_port)

                    # 标记任务完成
                    self.task_queue.task_done()

                    # 更新队列大小统计
                    self.stats["current_queue_size"] = self.task_queue.qsize()

                except Exception as e:
                    print(f"Worker error: {e}")
                    await asyncio.sleep(1)

        # 启动多个工作线程
        workers = [asyncio.create_task(worker()) for _ in range(num_workers)]
        await asyncio.gather(*workers)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            "max_concurrent": self.max_concurrent,
            "max_queue_size": self.max_queue_size,
            "active_tasks": self.max_concurrent - self.semaphore._value,
            "queue_size": self.task_queue.qsize()
        }

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """
        清理旧任务记录

        Args:
            max_age_hours: 任务最大保留时间（小时）
        """
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        tasks_to_remove = []

        for task_id, task_status in self.tasks.items():
            created_at = datetime.fromisoformat(task_status.created_at)
            if created_at < cutoff_time and task_status.status in ["completed", "failed"]:
                tasks_to_remove.append(task_id)

        for task_id in tasks_to_remove:
            del self.tasks[task_id]

        return len(tasks_to_remove)


# ==================== FastAPI应用 ====================
# 全局任务管理器实例
task_manager: Optional[TaskManager] = None
target_config = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理（兼容新版FastAPI）"""
    global task_manager

    # 启动时初始化
    max_concurrent = target_config.get("max_concurrent", 10)
    max_queue_size = target_config.get("max_queue_size", 100)
    num_workers = target_config.get("num_workers", 5)

    # 创建任务管理器
    task_manager = TaskManager(
        max_concurrent=max_concurrent,
        max_queue_size=max_queue_size
    )

    # 启动后台工作线程
    asyncio.create_task(
        task_manager.start_workers(
            target_config.get("target_host", "localhost"),
            target_config.get("target_port", 8000),
            num_workers
        )
    )

    print(f"\n{'='*70}")
    print(f"增强型转发服务已启动")
    print(f"{'='*70}")
    print(f"目标服务器: {target_config.get('target_host', 'localhost')}:{target_config.get('target_port', 8000)}")
    print(f"监听地址: {target_config.get('listen_host', '0.0.0.0')}:{target_config.get('listen_port', 8080)}")
    print(f"最大并发数: {max_concurrent}")
    print(f"最大队列大小: {max_queue_size}")
    print(f"工作线程数: {num_workers}")
    print(f"{'='*70}\n")

    yield  # 应用运行中

    # 关闭时清理（如果需要）
    print("\n增强型转发服务正在关闭...")


app = FastAPI(
    title="Enhanced Proxy Server",
    description="支持高并发队列管理和长任务状态跟踪的转发服务",
    version="2.0.0",
    lifespan=lifespan
)


@app.get("/", summary="服务根路径")
async def root():
    """返回服务信息"""
    return {
        "service": "Enhanced Proxy Server",
        "version": "2.0.0",
        "status": "running",
        "features": [
            "异步请求处理",
            "请求队列管理",
            "长任务状态跟踪",
            "任务ID查询"
        ]
    }


@app.get("/stats", summary="获取统计信息")
async def get_stats():
    """获取服务统计信息"""
    if not task_manager:
        raise HTTPException(status_code=503, detail="任务管理器未初始化")

    return task_manager.get_stats()


@app.post("/api/{path:path}", summary="转发POST请求")
async def forward_post(path: str, request: Request, background_tasks: BackgroundTasks):
    """
    转发POST请求到目标服务器

    如果任务预计超过5分钟，将返回task_id，可通过/task/{task_id}查询状态
    """
    if not task_manager:
        raise HTTPException(status_code=503, detail="任务管理器未初始化")

    try:
        # 读取请求体
        body = await request.body()

        # 构建请求头（过滤掉不需要的头）
        headers = dict(request.headers)
        skip_headers = {'host', 'connection', 'accept-encoding', 'content-length'}
        headers = {k: v for k, v in headers.items() if k.lower() not in skip_headers}

        # 创建任务
        task_id = await task_manager.create_task(
            request_data={},
            method="POST",
            path=f"/api/{path}",
            headers=headers,
            body=body
        )

        return TaskResponse(
            success=True,
            task_id=task_id,
            status="pending",
            message=f"任务已创建，ID: {task_id}。请使用 /task/{task_id} 查询状态。",
            data={"task_id": task_id, "status_url": f"/task/{task_id}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")


@app.get("/task/{task_id}", summary="查询任务状态")
async def query_task_status(task_id: str):
    """
    查询任务执行状态

    Args:
        task_id: 任务ID

    Returns:
        TaskResponse对象
    """
    if not task_manager:
        raise HTTPException(status_code=503, detail="任务管理器未初始化")

    task_status = await task_manager.get_task_status(task_id)

    if not task_status:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    # 根据任务状态返回不同响应
    if task_status.status == "completed":
        return TaskResponse(
            success=True,
            task_id=task_id,
            status=task_status.status,
            message="任务执行完成",
            result=task_status.result,
            data={
                "is_long_task": task_status.is_long_task,
                "created_at": task_status.created_at,
                "updated_at": task_status.updated_at
            }
        )
    elif task_status.status == "failed":
        return TaskResponse(
            success=False,
            task_id=task_id,
            status=task_status.status,
            message="任务执行失败",
            error=task_status.error,
            data={
                "created_at": task_status.created_at,
                "updated_at": task_status.updated_at
            }
        )
    else:  # pending or processing
        return TaskResponse(
            success=True,
            task_id=task_id,
            status=task_status.status,
            message=f"任务正在{task_status.status}中，请稍后查询",
            data={
                "is_long_task": task_status.is_long_task,
                "created_at": task_status.created_at,
                "updated_at": task_status.updated_at
            }
        )


@app.get("/tasks", summary="列出所有任务")
async def list_tasks(status: Optional[str] = None, limit: int = 50):
    """
    列出所有任务

    Args:
        status: 过滤状态（pending, processing, completed, failed）
        limit: 返回数量限制

    Returns:
        任务列表
    """
    if not task_manager:
        raise HTTPException(status_code=503, detail="任务管理器未初始化")

    tasks = list(task_manager.tasks.values())

    # 状态过滤
    if status:
        tasks = [t for t in tasks if t.status == status]

    # 按创建时间倒序排序
    tasks.sort(key=lambda x: x.created_at, reverse=True)

    # 限制数量
    tasks = tasks[:limit]

    return {
        "count": len(tasks),
        "tasks": [t.model_dump() for t in tasks]
    }


@app.post("/api/task/create", summary="创建任务")
async def create_task(request: Request):
    """
    创建新任务并转发到目标服务器

    请求体参数:
        path: 转发目标路径 (例如: "/api/users")
        params: 转发参数 (可选)
        method: HTTP方法 (默认: POST)
        body: 请求体内容 (可选)

    返回:
        task_id: 任务ID
    """
    if not task_manager:
        raise HTTPException(status_code=503, detail="任务管理器未初始化")

    try:
        data = await request.json()
    except:
        raise HTTPException(status_code=400, detail="请求体必须是JSON格式")

    path = data.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="缺少必需参数: path")

    method = data.get("method", "POST")
    params = data.get("params", {})
    body = data.get("body")

    import urllib.parse
    query_string = urllib.parse.urlencode(params) if params else ""

    full_path = f"{path}?{query_string}" if query_string else path

    headers = dict(request.headers)
    skip_headers = {'host', 'connection', 'accept-encoding', 'content-length'}
    headers = {k: v for k, v in headers.items() if k.lower() not in skip_headers}

    if body and isinstance(body, str):
        body = body.encode('utf-8')

    task_id = await task_manager.create_task(
        request_data=data,
        method=method,
        path=full_path,
        headers=headers,
        body=body
    )

    return TaskResponse(
        success=True,
        task_id=task_id,
        status="pending",
        message="任务创建成功",
        data={
            "task_id": task_id,
            "path": path,
            "method": method,
            "status_url": f"/task/{task_id}",
            "result_url": f"/api/task/{task_id}/result"
        }
    )


@app.get("/api/task/{task_id}/result", summary="获取任务完成结果")
async def get_task_result(task_id: str):
    """
    获取已完成任务的返回结果

    Args:
        task_id: 任务ID

    Returns:
        任务执行结果(result字段)
    """
    if not task_manager:
        raise HTTPException(status_code=503, detail="任务管理器未初始化")

    task_status = await task_manager.get_task_status(task_id)

    if not task_status:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    if task_status.status == "pending":
        return TaskResponse(
            success=True,
            task_id=task_id,
            status=task_status.status,
            message="任务等待中，尚未开始执行",
            data={
                "created_at": task_status.created_at,
                "status_url": f"/task/{task_id}"
            }
        )
    elif task_status.status == "processing":
        return TaskResponse(
            success=True,
            task_id=task_id,
            status=task_status.status,
            message="任务执行中，请稍后查询",
            data={
                "created_at": task_status.created_at,
                "status_url": f"/task/{task_id}"
            }
        )
    elif task_status.status == "failed":
        return TaskResponse(
            success=False,
            task_id=task_id,
            status=task_status.status,
            message="任务执行失败",
            error=task_status.error,
            data={
                "created_at": task_status.created_at,
                "updated_at": task_status.updated_at
            }
        )
    else:
        return TaskResponse(
            success=True,
            task_id=task_id,
            status=task_status.status,
            message="任务执行完成",
            result=task_status.result,
            data={
                "created_at": task_status.created_at,
                "updated_at": task_status.updated_at,
                "is_long_task": task_status.is_long_task
            }
        )


@app.delete("/tasks/cleanup", summary="清理旧任务")
async def cleanup_tasks(max_age_hours: int = 24):
    """
    清理超过指定时间的已完成或失败任务

    Args:
        max_age_hours: 任务最大保留时间（小时）

    Returns:
        清理结果
    """
    if not task_manager:
        raise HTTPException(status_code=503, detail="任务管理器未初始化")

    removed_count = task_manager.cleanup_old_tasks(max_age_hours)

    return {
        "success": True,
        "message": f"已清理 {removed_count} 个旧任务",
        "removed_count": removed_count
    }


# ==================== 服务器启动函数 ====================

def run_server(target_host: str, target_port: int,
               listen_host: str = "0.0.0.0", listen_port: int = 8080,
               max_concurrent: int = 10, max_queue_size: int = 100,
               num_workers: int = 5):
    """
    启动增强型转发服务器

    Args:
        target_host: 目标服务器IP
        target_port: 目标服务器端口
        listen_host: 监听地址
        listen_port: 监听端口
        max_concurrent: 最大并发任务数
        max_queue_size: 最大队列大小
        num_workers: 工作线程数量
    """
    global target_config

    # 设置配置
    target_config = {
        "target_host": target_host,
        "target_port": target_port,
        "listen_host": listen_host,
        "listen_port": listen_port,
        "max_concurrent": max_concurrent,
        "max_queue_size": max_queue_size,
        "num_workers": num_workers
    }

    # 启动服务器
    uvicorn.run(
        app,
        host=listen_host,
        port=listen_port,
        log_level="info",
        access_log=True
    )


# ==================== 主函数 ====================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='增强型HTTP转发服务 - 支持高并发队列管理和长任务状态跟踪',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法
  python3 enhanced_proxy_server.py --target-host 192.168.1.100 --target-port 8000 --listen-port 8080

  # 自定义并发参数
  python3 enhanced_proxy_server.py --target-host 192.168.1.100 --max-concurrent 20 --max-queue-size 200 --num-workers 10

  # 查看服务状态
  curl http://localhost:8080/stats

  # 查询任务状态
  curl http://localhost:8080/task/{task_id}

  # 列出所有任务
  curl http://localhost:8080/tasks
        """
    )

    parser.add_argument(
        '--target-host',
        required=True,
        help='目标服务器IP地址（C服务器）'
    )

    parser.add_argument(
        '--target-port',
        type=int,
        default=8000,
        help='目标服务器端口（默认: 8000）'
    )

    parser.add_argument(
        '--listen-host',
        default='0.0.0.0',
        help='监听地址（默认: 0.0.0.0）'
    )

    parser.add_argument(
        '--listen-port',
        type=int,
        default=8080,
        help='监听端口（默认: 8080）'
    )

    parser.add_argument(
        '--max-concurrent',
        type=int,
        default=10,
        help='最大并发任务数（默认: 10）'
    )

    parser.add_argument(
        '--max-queue-size',
        type=int,
        default=100,
        help='最大队列大小（默认: 100）'
    )

    parser.add_argument(
        '--num-workers',
        type=int,
        default=5,
        help='工作线程数量（默认: 5）'
    )

    args = parser.parse_args()

    # 启动服务器
    run_server(
        target_host=args.target_host,
        target_port=args.target_port,
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        max_concurrent=args.max_concurrent,
        max_queue_size=args.max_queue_size,
        num_workers=args.num_workers
    )


if __name__ == "__main__":
    main()
