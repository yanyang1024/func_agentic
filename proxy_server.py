#!/usr/bin/env python3
"""
统一的HTTP转发服务 - 支持同步和异步模式

功能特性:
1. 同步转发模式 - 直接返回目标服务器响应 (async=false 或不指定)
2. 异步转发模式 - 通过 Redis 队列处理，返回任务 ID (async=true)
3. 任务状态查询 - 通过 /task/{task_id} 查询异步任务状态
4. Dashboard - 查看所有异步任务状态
5. 统计信息 - 服务器运行统计

使用方法:
    python3 proxy_server.py --target-host <C服务器IP> --target-port 8000 \
        --listen-port 8080 --redis-host localhost --redis-port 6379

示例:
    python3 proxy_server.py --target-host 192.168.1.100 --target-port 8000 \
        --listen-port 8080 --redis-host localhost --redis-port 6379

同步请求:
    curl -X POST http://localhost:8080/api/test \
        -H "Content-Type: application/json" \
        -d '{"async": false, "data": "test"}'

异步请求:
    curl -X POST http://localhost:8080/api/test \
        -H "Content-Type: application/json" \
        -d '{"async": true, "data": "test"}'
    # 返回: {"task_id": "xxx", "status": "pending"}

查询异步任务状态:
    curl http://localhost:8080/task/{task_id}

访问 Dashboard:
    浏览器打开 http://localhost:8080/dashboard
"""

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse
from contextlib import asynccontextmanager
import httpx
import argparse
import json
from typing import Dict, Optional, Any
from datetime import datetime
import uvicorn

from redis_manager import RedisManager


# ==================== 全局变量 ====================
redis_manager: Optional[RedisManager] = None
target_config = {}


# ==================== FastAPI应用 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global redis_manager

    # 初始化 Redis 管理器
    redis_manager = RedisManager(
        redis_host=target_config.get("redis_host", "localhost"),
        redis_port=target_config.get("redis_port", 6379),
        redis_db=target_config.get("redis_db", 0),
        redis_password=target_config.get("redis_password", None)
    )

    # 启动后台工作线程
    redis_manager.start_worker(
        target_config.get("target_host", "localhost"),
        target_config.get("target_port", 8000)
    )

    print(f"\n{'='*70}")
    print(f"统一转发服务已启动")
    print(f"{'='*70}")
    print(f"目标服务器: {target_config.get('target_host', 'localhost')}:{target_config.get('target_port', 8000)}")
    print(f"监听地址: {target_config.get('listen_host', '0.0.0.0')}:{target_config.get('listen_port', 8080)}")
    print(f"Redis 服务器: {target_config.get('redis_host', 'localhost')}:{target_config.get('redis_port', 6379)}")
    print(f"{'='*70}\n")

    yield  # 应用运行中

    # 关闭时清理
    print("\n统一转发服务正在关闭...")
    if redis_manager:
        redis_manager.stop_worker()
        redis_manager.close()


app = FastAPI(
    title="Unified Proxy Server",
    description="支持同步和异步模式的统一转发服务",
    version="3.0.0",
    lifespan=lifespan
)


# ==================== 辅助函数 ====================

def _forward_sync_request(method: str, path: str, target_host: str,
                          target_port: int, headers: Dict[str, str],
                          body: Optional[bytes] = None) -> Dict[str, Any]:
    """
    同步转发请求

    Args:
        method: HTTP 方法
        path: 请求路径
        target_host: 目标主机
        target_port: 目标端口
        headers: 请求头
        body: 请求体

    Returns:
        响应数据
    """
    try:
        # 构建目标 URL
        target_url = f"http://{target_host}:{target_port}{path}"

        # 发送请求
        with httpx.Client(timeout=300.0) as client:
            response = client.request(
                method=method,
                url=target_url,
                headers=headers,
                content=body
            )

            # 处理响应
            try:
                result_data = response.json()
            except:
                result_data = {
                    "status_code": response.status_code,
                    "content": response.text
                }

            return {
                "success": True,
                "status_code": response.status_code,
                "result": result_data
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ==================== 路由处理 ====================

@app.get("/", summary="服务根路径")
async def root():
    """返回服务信息"""
    return {
        "service": "Unified Proxy Server",
        "version": "3.0.0",
        "status": "running",
        "features": [
            "同步请求转发",
            "异步请求队列处理",
            "任务状态查询",
            "Dashboard"
        ]
    }


@app.get("/stats", summary="获取统计信息")
async def get_stats():
    """获取服务统计信息"""
    if not redis_manager:
        raise HTTPException(status_code=503, detail="Redis 管理器未初始化")

    return redis_manager.get_stats()


@app.post("/api/{path:path}", summary="转发 POST 请求")
async def forward_post(path: str, request: Request):
    """
    转发 POST 请求到目标服务器

    请求体应包含 `async` 字段:
    - async=false 或不指定: 同步模式，直接返回目标服务器响应
    - async=true: 异步模式，返回 task_id，可通过 /task/{task_id} 查询状态
    """
    if not redis_manager:
        raise HTTPException(status_code=503, detail="Redis 管理器未初始化")

    try:
        # 读取请求体
        body = await request.body()
        body_text = body.decode('utf-8') if body else '{}'

        # 解析 JSON
        try:
            body_json = json.loads(body_text)
        except:
            body_json = {}

        # 判断是否异步
        is_async = body_json.get('async', False)

        # 构建请求头（过滤掉不需要的头）
        headers = dict(request.headers)
        skip_headers = {'host', 'connection', 'accept-encoding', 'content-length'}
        headers = {k: v for k, v in headers.items() if k.lower() not in skip_headers}

        if is_async:
            # 异步模式 - 将任务加入队列
            task_id = redis_manager.enqueue_task(
                method="POST",
                path=f"/api/{path}",
                headers=headers,
                body=body,
                request_data=body_json
            )

            return {
                "success": True,
                "task_id": task_id,
                "status": "pending",
                "message": f"任务已创建，ID: {task_id}。请使用 /task/{task_id} 查询状态。",
                "status_url": f"/task/{task_id}"
            }
        else:
            # 同步模式 - 直接转发请求
            result = _forward_sync_request(
                method="POST",
                path=f"/api/{path}",
                target_host=target_config.get("target_host", "localhost"),
                target_port=target_config.get("target_port", 8000),
                headers=headers,
                body=body
            )
            return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}")


@app.get("/api/{path:path}", summary="转发 GET 请求")
async def forward_get(path: str, request: Request):
    """转发 GET 请求到目标服务器（同步模式）"""
    if not redis_manager:
        raise HTTPException(status_code=503, detail="Redis 管理器未初始化")

    try:
        # 构建查询字符串
        query_string = request.url.query

        full_path = f"/api/{path}"
        if query_string:
            full_path += f"?{query_string}"

        # 构建请求头
        headers = dict(request.headers)
        skip_headers = {'host', 'connection', 'accept-encoding', 'content-length'}
        headers = {k: v for k, v in headers.items() if k.lower() not in skip_headers}

        # 同步转发
        result = _forward_sync_request(
            method="GET",
            path=full_path,
            target_host=target_config.get("target_host", "localhost"),
            target_port=target_config.get("target_port", 8000),
            headers=headers,
            body=None
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}")


@app.get("/task/{task_id}", summary="查询任务状态")
async def query_task_status(task_id: str):
    """
    查询异步任务执行状态

    Args:
        task_id: 任务 ID

    Returns:
        任务状态信息
    """
    if not redis_manager:
        raise HTTPException(status_code=503, detail="Redis 管理器未初始化")

    task_status = redis_manager.get_task_status(task_id)

    if not task_status:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    status = task_status.get("status", "unknown")

    if status == "completed":
        return {
            "success": True,
            "task_id": task_id,
            "status": status,
            "message": "任务执行完成",
            "result": task_status.get("result"),
            "data": {
                "created_at": task_status.get("created_at"),
                "updated_at": task_status.get("updated_at"),
                "request_info": task_status.get("request_info")
            }
        }
    elif status == "failed":
        return {
            "success": False,
            "task_id": task_id,
            "status": status,
            "message": "任务执行失败",
            "error": task_status.get("error"),
            "data": {
                "created_at": task_status.get("created_at"),
                "updated_at": task_status.get("updated_at"),
                "request_info": task_status.get("request_info")
            }
        }
    else:  # pending or processing
        return {
            "success": True,
            "task_id": task_id,
            "status": status,
            "message": f"任务正在{'处理中' if status == 'processing' else '等待中'}，请稍后查询",
            "data": {
                "created_at": task_status.get("created_at"),
                "updated_at": task_status.get("updated_at")
            }
        }


@app.get("/api/tasks", summary="获取任务列表")
async def list_tasks(status: Optional[str] = None, limit: int = 50):
    """
    获取任务列表（简化信息）

    Args:
        status: 过滤状态（pending, processing, completed, failed）
        limit: 返回数量限制

    Returns:
        任务列表
    """
    if not redis_manager:
        raise HTTPException(status_code=503, detail="Redis 管理器未初始化")

    tasks = redis_manager.get_all_tasks(status_filter=status, limit=limit)

    # 返回简化信息
    simplified_tasks = []
    for task in tasks:
        simplified_tasks.append({
            "task_id": task.get("task_id"),
            "status": task.get("status"),
            "created_at": task.get("created_at"),
            "updated_at": task.get("updated_at")
        })

    return {
        "count": len(simplified_tasks),
        "tasks": simplified_tasks
    }


@app.get("/api/task/{task_id}/detail", summary="获取任务完整详情")
async def get_task_detail(task_id: str):
    """
    获取任务的完整详情

    Args:
        task_id: 任务 ID

    Returns:
        任务完整详情
    """
    if not redis_manager:
        raise HTTPException(status_code=503, detail="Redis 管理器未初始化")

    task_status = redis_manager.get_task_status(task_id)

    if not task_status:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    return task_status


@app.get("/dashboard", summary="Dashboard 页面")
async def dashboard():
    """返回 Dashboard 页面"""
    dashboard_html = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>异步任务 Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
        }

        .header h1 {
            font-size: 32px;
            margin-bottom: 10px;
        }

        .header p {
            font-size: 16px;
            opacity: 0.9;
        }

        .content {
            padding: 20px;
        }

        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }

        .stat-card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }

        .stat-card .value {
            font-size: 32px;
            font-weight: bold;
            color: #667eea;
        }

        .stat-card .label {
            font-size: 14px;
            color: #666;
            margin-top: 4px;
        }

        .filters {
            display: flex;
            gap: 8px;
            margin-bottom: 16px;
            flex-wrap: wrap;
        }

        .filter-btn {
            padding: 8px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 20px;
            background: white;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 14px;
        }

        .filter-btn:hover {
            border-color: #667eea;
        }

        .filter-btn.active {
            background: #667eea;
            color: white;
            border-color: #667eea;
        }

        .task-list {
            display: grid;
            gap: 12px;
        }

        .task-item {
            background: #f8f9fa;
            padding: 16px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .task-item:hover {
            background: #e3f2fd;
            transform: translateX(4px);
        }

        .task-info {
            flex: 1;
        }

        .task-id {
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 4px;
        }

        .task-time {
            font-size: 12px;
            color: #999;
        }

        .task-status {
            padding: 6px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }

        .status-pending {
            background: #ffc107;
            color: white;
        }

        .status-processing {
            background: #2196f3;
            color: white;
        }

        .status-completed {
            background: #4caf50;
            color: white;
        }

        .status-failed {
            background: #f44336;
            color: white;
        }

        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }

        .modal.active {
            display: flex;
        }

        .modal-content {
            background: white;
            padding: 30px;
            border-radius: 16px;
            max-width: 800px;
            max-height: 80vh;
            overflow-y: auto;
            width: 90%;
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .modal-header h2 {
            font-size: 24px;
        }

        .close-btn {
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: #999;
        }

        .modal-body {
            font-family: monospace;
            font-size: 13px;
            white-space: pre-wrap;
            word-break: break-all;
            background: #f8f9fa;
            padding: 16px;
            border-radius: 8px;
        }

        .empty-state {
            text-align: center;
            padding: 60px;
            color: #999;
        }

        .refresh-btn {
            margin-left: auto;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 异步任务 Dashboard</h1>
            <p>实时查看异步任务执行状态</p>
        </div>

        <div class="content">
            <div class="stats">
                <div class="stat-card">
                    <div class="value" id="totalTasks">-</div>
                    <div class="label">总任务数</div>
                </div>
                <div class="stat-card">
                    <div class="value" id="activeTasks">-</div>
                    <div class="label">活跃任务</div>
                </div>
                <div class="stat-card">
                    <div class="value" id="completedTasks">-</div>
                    <div class="label">已完成</div>
                </div>
                <div class="stat-card">
                    <div class="value" id="failedTasks">-</div>
                    <div class="label">失败</div>
                </div>
            </div>

            <div class="filters">
                <button class="filter-btn active" data-filter="">全部</button>
                <button class="filter-btn" data-filter="pending">待处理</button>
                <button class="filter-btn" data-filter="processing">进行中</button>
                <button class="filter-btn" data-filter="completed">已完成</button>
                <button class="filter-btn" data-filter="failed">失败</button>
                <button class="filter-btn refresh-btn" onclick="refreshData()">🔄 刷新</button>
            </div>

            <div class="task-list" id="taskList">
                <div class="empty-state">加载中...</div>
            </div>
        </div>
    </div>

    <div class="modal" id="detailModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>任务详情</h2>
                <button class="close-btn" onclick="closeModal()">×</button>
            </div>
            <div class="modal-body" id="modalBody"></div>
        </div>
    </div>

    <script>
        let currentFilter = '';
        let refreshInterval = null;

        // 页面加载时初始化
        window.onload = function() {
            initFilters();
            refreshData();
            startAutoRefresh();
        };

        // 初始化过滤器
        function initFilters() {
            const buttons = document.querySelectorAll('.filter-btn:not(.refresh-btn)');
            buttons.forEach(btn => {
                btn.addEventListener('click', function() {
                    buttons.forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                    currentFilter = this.dataset.filter;
                    refreshData();
                });
            });
        }

        // 自动刷新
        function startAutoRefresh() {
            refreshInterval = setInterval(refreshData, 3000); // 每 3 秒刷新
        }

        // 刷新数据
        async function refreshData() {
            try {
                // 更新统计信息
                const statsResponse = await fetch('/stats');
                const stats = await statsResponse.json();

                document.getElementById('totalTasks').textContent = stats.total_tasks || 0;
                document.getElementById('activeTasks').textContent = stats.queue_size || 0;
                document.getElementById('completedTasks').textContent = stats.completed_tasks || 0;
                document.getElementById('failedTasks').textContent = stats.failed_tasks || 0;

                // 获取任务列表
                const url = currentFilter ? `/api/tasks?status=${currentFilter}` : '/api/tasks';
                const tasksResponse = await fetch(url);
                const tasksData = await tasksResponse.json();

                displayTasks(tasksData.tasks || []);

            } catch (error) {
                console.error('刷新数据失败:', error);
            }
        }

        // 显示任务列表
        function displayTasks(tasks) {
            const taskList = document.getElementById('taskList');

            if (tasks.length === 0) {
                taskList.innerHTML = '<div class="empty-state">暂无任务</div>';
                return;
            }

            taskList.innerHTML = tasks.map(task => `
                <div class="task-item" onclick="showTaskDetail('${task.task_id}')">
                    <div class="task-info">
                        <div class="task-id">${task.task_id.substring(0, 20)}...</div>
                        <div class="task-time">${formatTime(task.created_at)}</div>
                    </div>
                    <div class="task-status status-${task.status}">${getStatusLabel(task.status)}</div>
                </div>
            `).join('');
        }

        // 获取状态标签
        function getStatusLabel(status) {
            const labels = {
                'pending': '待处理',
                'processing': '进行中',
                'completed': '已完成',
                'failed': '失败'
            };
            return labels[status] || status;
        }

        // 格式化时间
        function formatTime(isoString) {
            const date = new Date(isoString);
            return date.toLocaleString('zh-CN');
        }

        // 显示任务详情
        async function showTaskDetail(taskId) {
            try {
                const response = await fetch(`/api/task/${taskId}/detail`);
                const data = await response.json();

                document.getElementById('modalBody').textContent = JSON.stringify(data, null, 2);
                document.getElementById('detailModal').classList.add('active');

            } catch (error) {
                console.error('获取任务详情失败:', error);
            }
        }

        // 关闭模态框
        function closeModal() {
            document.getElementById('detailModal').classList.remove('active');
        }

        // 点击模态框外部关闭
        document.getElementById('detailModal').addEventListener('click', function(e) {
            if (e.target === this) {
                closeModal();
            }
        });
    </script>
</body>
</html>
    """
    return HTMLResponse(content=dashboard_html)


# ==================== 服务器启动函数 ====================

def run_server(target_host: str, target_port: int,
               listen_host: str = "0.0.0.0", listen_port: int = 8080,
               redis_host: str = "localhost", redis_port: int = 6379,
               redis_db: int = 0, redis_password: Optional[str] = None):
    """
    启动统一转发服务器

    Args:
        target_host: 目标服务器IP
        target_port: 目标服务器端口
        listen_host: 监听地址
        listen_port: 监听端口
        redis_host: Redis 主机地址
        redis_port: Redis 端口
        redis_db: Redis 数据库编号
        redis_password: Redis 密码
    """
    global target_config

    # 设置配置
    target_config = {
        "target_host": target_host,
        "target_port": target_port,
        "listen_host": listen_host,
        "listen_port": listen_port,
        "redis_host": redis_host,
        "redis_port": redis_port,
        "redis_db": redis_db,
        "redis_password": redis_password
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
        description='统一HTTP转发服务 - 支持同步和异步模式',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法
  python3 proxy_server.py --target-host 192.168.1.100 --target-port 8000 \\
      --listen-port 8080 --redis-host localhost --redis-port 6379

  # 测试同步请求
  curl -X POST http://localhost:8080/api/test \\
      -H "Content-Type: application/json" \\
      -d '{"async": false, "data": "test"}'

  # 测试异步请求
  curl -X POST http://localhost:8080/api/test \\
      -H "Content-Type: application/json" \\
      -d '{"async": true, "data": "test"}'

  # 查询异步任务状态
  curl http://localhost:8080/task/{task_id}

  # 访问 Dashboard
  打开浏览器访问 http://localhost:8080/dashboard
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
        '--redis-host',
        default='localhost',
        help='Redis 主机地址（默认: localhost）'
    )

    parser.add_argument(
        '--redis-port',
        type=int,
        default=6379,
        help='Redis 端口（默认: 6379）'
    )

    parser.add_argument(
        '--redis-db',
        type=int,
        default=0,
        help='Redis 数据库编号（默认: 0）'
    )

    parser.add_argument(
        '--redis-password',
        help='Redis 密码（可选）'
    )

    args = parser.parse_args()

    # 启动服务器
    run_server(
        target_host=args.target_host,
        target_port=args.target_port,
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_db=args.redis_db,
        redis_password=args.redis_password
    )


if __name__ == "__main__":
    main()
