#!/usr/bin/env python3
"""
Redis 管理模块 - 用于管理异步任务队列和状态
"""
import redis
import json
import uuid
import time
import threading
import httpx
from typing import Dict, Any, Optional, List
from datetime import datetime


class RedisManager:
    """Redis 管理器 - 管理任务队列和状态"""

    # Redis 键前缀
    QUEUE_KEY = "async_proxy:queue"
    TASK_KEY_PREFIX = "async_proxy:task:"
    STATS_KEY = "async_proxy:stats"

    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379,
                 redis_db: int = 0, redis_password: Optional[str] = None):
        """
        初始化 Redis 管理器

        Args:
            redis_host: Redis 主机地址
            redis_port: Redis 端口
            redis_db: Redis 数据库编号
            redis_password: Redis 密码
        """
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.redis_password = redis_password

        # 创建 Redis 连接池
        self.pool = redis.ConnectionPool(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True
        )
        self.redis = redis.Redis(connection_pool=self.pool)

        # 后台工作线程
        self._worker_thread = None
        self._running = False
        self._target_host = None
        self._target_port = None

        # 初始化统计信息
        self._init_stats()

    def _init_stats(self):
        """初始化统计信息"""
        if not self.redis.exists(self.STATS_KEY):
            self.redis.hset(self.STATS_KEY, mapping={
                "total_tasks": "0",
                "completed_tasks": "0",
                "failed_tasks": "0",
                "active_tasks": "0"
            })

    def start_worker(self, target_host: str, target_port: int):
        """
        启动后台工作线程处理队列

        Args:
            target_host: 目标服务器主机
            target_port: 目标服务器端口
        """
        self._target_host = target_host
        self._target_port = target_port
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def stop_worker(self):
        """停止后台工作线程"""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def _worker_loop(self):
        """工作线程循环"""
        while self._running:
            try:
                # 从队列获取任务（阻塞超时 1 秒）
                task_data = self.redis.brpop(self.QUEUE_KEY, timeout=1)

                if task_data:
                    _, task_json = task_data
                    task_info = json.loads(task_json)
                    self._process_task(task_info)

            except Exception as e:
                print(f"Worker error: {e}")
                time.sleep(1)

    def _process_task(self, task_info: Dict[str, Any]):
        """
        处理单个任务

        Args:
            task_info: 任务信息
        """
        task_id = task_info.get("task_id")

        # 更新状态为处理中
        self.update_task_status(task_id, "processing")

        try:
            # 构建目标 URL
            target_url = f"http://{self._target_host}:{self._target_port}{task_info['path']}"

            # 发送请求
            with httpx.Client(timeout=600.0) as client:
                start_time = time.time()

                response = client.request(
                    method=task_info.get("method", "POST"),
                    url=target_url,
                    headers=task_info.get("headers", {}),
                    content=task_info.get("body")
                )

                elapsed_time = time.time() - start_time

                # 判断是否为长任务（超过 5 分钟）
                is_long_task = elapsed_time > 300

                # 处理响应
                try:
                    result_data = response.json()
                except:
                    result_data = {
                        "status_code": response.status_code,
                        "content": response.text[:1000]
                    }

                # 更新任务状态为完成
                self.update_task_status(
                    task_id,
                    "completed",
                    result=result_data,
                    request_info={
                        "method": task_info.get("method"),
                        "path": task_info['path'],
                        "elapsed_time": elapsed_time,
                        "is_long_task": is_long_task,
                        "status_code": response.status_code
                    }
                )

                # 更新统计
                self.redis.hincrby(self.STATS_KEY, "completed_tasks", 1)

        except Exception as e:
            # 任务失败
            self.update_task_status(
                task_id,
                "failed",
                error=str(e),
                request_info={
                    "method": task_info.get("method"),
                    "path": task_info.get('path')
                }
            )

            # 更新统计
            self.redis.hincrby(self.STATS_KEY, "failed_tasks", 1)

    def enqueue_task(self, method: str, path: str, headers: Dict[str, str],
                     body: Optional[bytes] = None, request_data: Optional[Dict] = None) -> str:
        """
        将任务加入队列

        Args:
            method: HTTP 方法
            path: 请求路径
            headers: 请求头
            body: 请求体
            request_data: 请求数据

        Returns:
            task_id: 任务 ID
        """
        # 生成任务 ID
        task_id = str(uuid.uuid4())

        # 创建任务状态
        task_status = {
            "task_id": task_id,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "result": None,
            "error": None,
            "request_info": None
        }

        # 存储任务状态
        self.redis.hset(self.TASK_KEY_PREFIX + task_id, mapping={
            "status": task_status["status"],
            "created_at": task_status["created_at"],
            "updated_at": task_status["updated_at"],
            "result": json.dumps(task_status["result"]) if task_status["result"] else "",
            "error": task_status["error"] if task_status["error"] else "",
            "request_info": json.dumps(task_status["request_info"]) if task_status["request_info"] else ""
        })

        # 创建任务信息
        task_info = {
            "task_id": task_id,
            "method": method,
            "path": path,
            "headers": headers,
            "body": body.hex() if body else None,
            "request_data": request_data or {}
        }

        # 将任务加入队列
        self.redis.rpush(self.QUEUE_KEY, json.dumps(task_info))

        #.更新统计
        self.redis.hincrby(self.STATS_KEY, "total_tasks", 1)

        return task_id

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务状态字典或 None
        """
        task_key = self.TASK_KEY_PREFIX + task_id

        if not self.redis.exists(task_key):
            return None

        task_data = self.redis.hgetall(task_key)

        result = json.loads(task_data.get("result", "null")) if task_data.get("result") else None
        error = task_data.get("error") if task_data.get("error") else None
        request_info = json.loads(task_data.get("request_info", "null")) if task_data.get("request_info") else None

        return {
            "task_id": task_id,
            "status": task_data.get("status"),
            "created_at": task_data.get("created_at"),
            "updated_at": task_data.get("updated_at"),
            "result": result,
            "error": error,
            "request_info": request_info
        }

    def update_task_status(self, task_id: str, status: str,
                          result: Optional[Dict] = None, error: Optional[str] = None,
                          request_info: Optional[Dict] = None):
        """
        更新任务状态

        Args:
            task_id: 任务 ID
            status: 新状态
            result: 结果数据
            error: 错误信息
            request_info: 请求信息
        """
        task_key = self.TASK_KEY_PREFIX + task_id

        if not self.redis.exists(task_key):
            return

        updates = {
            "status": status,
            "updated_at": datetime.now().isoformat()
        }

        if result is not None:
            updates["result"] = json.dumps(result)

        if error is not None:
            updates["error"] = error

        if request_info is not None:
            updates["request_info"] = json.dumps(request_info)

        self.redis.hset(task_key, mapping=updates)

    def get_all_tasks(self, status_filter: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取所有任务

        Args:
            status_filter: 状态过滤器（可选）
            limit: 返回数量限制

        Returns:
            任务列表
        """
        # 获取所有任务键
        task_keys = self.redis.keys(self.TASK_KEY_PREFIX + "*")

        tasks = []
        for task_key in task_keys:
            task_id = task_key.replace(self.TASK_KEY_PREFIX, "")
            task_status = self.get_task_status(task_id)

            if task_status:
                # 应用状态过滤器
                if status_filter and task_status.get("status") != status_filter:
                    continue
                tasks.append(task_status)

        # 按创建时间倒序排序
        tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        # 限制数量
        return tasks[:limit]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.redis.hgetall(self.STATS_KEY)
        return {
            "total_tasks": int(stats.get("total_tasks", 0)),
            "completed_tasks": int(stats.get("completed_tasks", 0)),
            "failed_tasks": int(stats.get("failed_tasks", 0)),
            "active_tasks": int(stats.get("active_tasks", 0)),
            "queue_size": self.redis.llen(self.QUEUE_KEY)
        }

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务

        Args:
            task_id: 任务 ID

        Returns:
            是否删除成功
        """
        task_key = self.TASK_KEY_PREFIX + task_id
        return self.redis.delete(task_key) > 0

    def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """
        清理旧任务

        Args:
            max_age_hours: 任务最大保留时间（小时）

        Returns:
            删除的任务数量
        """
        task_keys = self.redis.keys(self.TASK_KEY_PREFIX + "*")
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)

        deleted_count = 0

        for task_key in task_keys:
            task_status = self.get_task_status(task_key.replace(self.TASK_KEY_PREFIX, ""))

            if task_status:
                created_at = datetime.fromisoformat(task_status.get("created_at", ""))
                status = task_status.get("status", "")

                if created_at.timestamp() < cutoff_time and status in ["completed", "failed"]:
                    if self.delete_task(task_status.get["task_id"]):
                        deleted_count += 1

        return deleted_count

    def close(self):
        """关闭 Redis 连接"""
        self.redis.close()
        self.pool.disconnect()
