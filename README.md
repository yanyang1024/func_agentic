# 项目使用教程与维护指南

## 目录

1. [项目概述](#项目概述)
2. [快速开始](#快速开始)
3. [代理服务器使用](#代理服务器使用)
4. [工作流系统使用](#工作流系统使用)
5. [开发架构说明](#开发架构说明)
6. [维护与故障排除](#维护与故障排除)
7. [二次开发指南](#二次开发指南)
8. [配置说明](#配置说明)

---

## 项目概述

本项目包含两个主要组件：

### 1. 代理服务器 (proxy_server.py)
- 统一的 HTTP 转发服务
- 支持同步和异步两种请求模式
- 使用 Redis 队列处理异步任务
- 提供 Dashboard 监控任务执行状态

### 2. 工作流系统 (service_for_workflow/)
- Flask Web 应用，提供智能对话对话界面
- 异步工作流处理支持
- 模拟工作流服务支持动态状态转换

---

## 快速开始

### 1. 环境准备

```bash
# 安装 Python 依赖
pip install flask fastapi uvicorn httpx redis

# 或安装项目依赖
pip install -r requirements.txt

# 确保 Redis 服务运行
# 使用 Docker
docker run -d -p 6379:6379 redis

# 或直接启动 Redis
redis-server --daemonize yes --port 6379
```

### 2. 启动服务

```bash
# 启动代理服务器
python3 proxy_server.py \
    --target-host <目标服务器IP> \
    --target-port 8000 \
    --listen-port 8080 \
    --redis-host localhost \
    --redis-port 6379

# 启动工作流系统
cd service_for_workflow
python3 flask_app.py
```

---

## 代理服务器使用

### 启动命令

```bash
# 基本用法
python3 proxy_server.py --target-host <C服务器IP> --target-port 8000 \
    --listen-port 8080 --redis-host localhost --redis-port 6379

# 查看帮助
python3 proxy_server.py --help
```

### 命令行参数

| 参数 | 说明 | 默认值 | 必需填 |
|------|------|--------|--------|
| `--target-host` | 目标服务器IP地址 | - | 是 |
| `--target-port` | 目标服务器端口 | 8000 | 否 |
| `--listen-host` | 监听地址 | 0.0.0.0 | 否 |
| `--listen-port` | 监听端口 | 8080 | 否 |
| `--redis-host` | Redis 主机地址 | localhost | 否 |
| `redis-port` | Redis 端口 | 6379 | 否 |
| `--redis-db` | Redis 数据库编号 | 0 | 否 |
| `--redis-password` | Redis 密码（可选） | None | 否 |

### API 端点

#### 根路径
- `GET /` - 服务根路径，返回服务信息
- `POST /api/{path:path}` - 转发请求到目标服务器
- `GET /task/{task_id}` - 查询异步任务状态
- `GET /dashboard` - Dashboard 页面
- `GET /api/tasks` - 获取任务列表（简化信息）
- `GET /api/task/{task_id}/detail` - 获取任务完整详情
- `GET /stats` - 统计信息

### 请求模式

#### 同步模式（async=false 或不指定）

```bash
curl -X POST http://localhost:8080/api/test \
    -H "Content-Type: application/json" \
    -d '{"async": false, "data": "test"}'

# 或省略 async 字段
curl -X POST http://localhost:8080/api/test \
    -H "Content-Type: application/json" \
    -d '{"data": "test"}'
```

#### 异步模式（async=true）

```bash
curl -X POST http://localhost:8080/api/test \
    -H "Content-Type: application/json" \
    -d '{"async": true, "data": "test"}'

# 返回: {"task_id": "xxx", "status": "pending"}
```

### 查询任务状态

```bash
# 查询任务状态
curl http://localhost:8080/task/{task_id}

# 获取任务完整详情
curl http://localhost:8080/api/task/{task_id}/detail
```

### 访问 Dashboard

浏览器打开: `http://localhost:8080/dashboard`

Dashboard 功能：
- 实时显示所有任务状态
- 按状态筛选（全部/待处理/进行中/已完成/失败）
- 点击任务查看完整详情
- 每 3 秒自动刷新

---

## 工作流系统使用

### 启动服务

```bash
cd service_for_workflow

pip install -r requirements_flask.txt
python3 flask_app.py

# 或使用启动脚本
./start_flask.sh
```

### 访问服务

浏览器打开: `http://localhost:5000`

### API 端点

- `GET /` - 主页
- `POST /api/session` - 创建会话
- `GET /api/session` - 获取当前会话
- `POST /api/send` - 发送消息
- `GET /api/messages` - 获取消息列表
- `POST /api/refresh` - 刷新状态
- `POST /api/clear` - 清空对话
- `GET /api/status` - 系统状态
- `GET /api/workflow/{run_id}/status` - 轮询工作流状态
- `POST /api/workflow/{run_id}/resume` - 恢复中断的工作流

### 工作流状态说明

工作流支持四种状态：

1. **processing（处理中）**
   - 显示加载动画和进度信息
   - 显示当前执行步骤（如：数据加载、预处理、特征提取等）
   - 右侧信息面板显示进度百分比
   - 每次查询更新进度

2. **interrupt（中断）**
   - 显示中断原因（如："需要更多信息：请提供数据范围和时间周期"）
   - 输入框等待用户补充信息

3. **success（成功）**
   - 显示工作流结果
   - 如果有可视化链接，显示可视化图表按钮

4. **fail（失败）**
   - 显示失败原因
   - 提供重试选项

### 对话交互逻辑

1. 发送消息
   - 用户输入消息，点击发送或按 Enter 键
   - 消息立即显示在对话区域

2. 处理中状态
   - 显示处理中动画（旋转的加载图标）
   - 显示进度信息（当前步骤、进度百分比）
   - 显示工作流进度卡片（右侧面板）
   - 每秒自动轮询更新状态

3. 中断处理
   - 工作流需要更多信息时自动中断
- 显示中断原因
- 输入框可用，用户补充信息后继续

4. 成功/失败
   - 显示处理结果
- 如果成功且有可视化链接，提供可视化入口

### 状态管理

- 右侧信息面板显示：
  - 会话 ID（截断显示）
  - 消息数量
  - 会话状态（就绪/等待补充信息）
  - 工作流 Run ID
  - 工作流状态
- 工作流进度卡片（处理中时显示）

---

## 开发架构说明

### 项目结构

```
doing_service_for_opagent/
├── proxy_server.py          # 统一的代理服务器
├── redis_manager.py         # Redis 管理模块
├── service_for_workflow/  # 工作流系统目录
│   ├── flask_app.py         # Flask 应用主文件
│   ├── workflow_mock.py     # 工作流模拟服务
│   ├── session_manager.py    # 会话管理器
│   ├── async_processor.py    # 异步任务处理器
│   ├── config.py           # 配置管理
│   ├── templates/            # HTML 模板
│   │   └── index.html
│   └── requirements_flask.txt
└── README.md              # 本文档
```

### 核心模块说明

#### redis_manager.py

Redis 管理模块，提供：

- `RedisManager` 类：管理 Redis 连接和操作
- `enqueue_task()`：将任务加入队列
- `get_task_status()`：获取任务状态
- `update_task_status()`：更新任务状态
- `get_all_tasks()`：获取所有任务
- `get_stats()`：获取统计信息
- `delete_task()`：删除任务
- `cleanup_old_tasks()`：清理旧任务

Redis 数据结构：
```
async_proxy:queue -> 任务队列
async_proxy:task:{task_id} -> 任务状态（Hash）
async_proxy:stats -> 统计信息（Hash）
```

#### proxy_server.py

统一的代理服务器，功能：

- 同步请求转发模式（async=false）
- 异步请求队列处理模式（async=true）
- Dashboard 监控
- 任务状态查询
- 统计信息

关键端点：
- `POST /api/{path}` - 转发请求
- `GET /task/{task_id}` - 查询任务状态
- `GET /dashboard` - Dashboard
- `GET /api/tasks` - 任务列表
- `GET /api/task/{task_id}/detail` - 任务详情
- `GET /stats` - 统计信息

#### workflow_mock.py

模拟工作流服务，支持：

- `WorkflowStatus` 枚举：PROCESSING, INTERRUPT, SUCCESS, FAIL
- `start_workflow()`：启动工作流
- `get_workflow_info()`：获取工作流信息（支持动态状态转换）
- `get_processing_progress()`：获取处理进度信息
- `restart_workflow()`：重启工作流

状态转换逻辑：
- 第 1-3 次查询返回 `processing` 状态
- 第 4 次查询根据 run_id 模块决定最终状态：
  - run_id % 3 == 0 → `interrupt`（中断）
  - run_id % 3 == 1 → `success`（成功）
  - run_id % 3 == 2 → `fail`（失败）

#### flask_app.py

Flask 应用，提供 REST API：

- 会话管理（创建/查询/删除）
- 消息管理（发送/获取）
- 工作流状态轮询
- 中断工作流恢复
- 系统状态查询

关键端点：
- `POST /api/send` - 发送消息
- `GET /api/workflow/{run_id}/status` - 轮询工作流状态
- POST /api/workflow/{run_id}/resume` - 恢复中断的工作流
- `POST /api/refresh` - 刷新状态
- `POST /api/clear` - 清空对话
- `POST /api/session` - 创建会话

#### index.html

前端页面，提供：

- 对话界面
- 实时状态更新
- 工作流进度显示
- 响应式设计

---

## 维护与故障排除

### 常见问题

#### 1. Redis 连接失败

**症状**：
```
ConnectionError: Error connecting to Redis
```

**解决方案**：
```bash
# 检查 Redis 服务状态
redis-cli ping

# 启动 Redis
redis-server --daemonize yes --port 6379

# 检查查 Redis 配置
redis-cli CONFIG GET bind
redis-cli CONFIG GET port
```

#### 2. 代理服务器端口被占用

**症状**：
```
OSError: [Errno 99] Address already in use
```

**解决方案**：
```bash
# 查找占用端口的进程
lsof -ti :8080

# 更改端口或终止进程
kill -9 <PID>
```

#### 3. 依赖缺失

**症状**：
```
ModuleNotFoundError: No module named 'redis'
```

**解决方案**：
```bash
pip install flask fastapi uvicorn httpx redis
```

#### 4. 任务状态不更新

**症状**：
Dashboard 中任务状态一直处于 pending 状态

**解决方案**：
```bash
# 检查 Redis 队列
redis-cli LRANGE async_proxy:queue 0 -10

# 检查工作线程状态
# 可以在 proxy_server.py 中添加日志输出
```

### 日志调试

```bash
# 查看代理服务器日志
# 启动时已显示

# 可以在代码中添加更多日志
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.debug(f"Processing task: {task_id}")
```

### 性能优化

#### Redis 连接池优化

```python
# 在 redis_manager.py 中已使用连接池
pool = redis.ConnectionPool(
    host=redis_host,
    port=redis_port,
    db=redis_db,
    password=redis_password,
    decode_responses=True,
    max_connections=10  # 最大连接数
)
```

#### 异步任务超时控制

```python
# 在 redis_manager.py 中设置了超时
with httpx.Client(timeout=600.0) as client:
    # 600 秒超时
```

---

## 二次开发指南

### 添加新的 API 端点

#### 在 proxy_server.py 中添加

```python
@app.get("/custom/endpoint")
async def custom_endpoint():
    """自定义端点"""
    return {"message": "Custom endpoint"}

@app.api_router.get("/api/custom")
async def custom_api_endpoint():
    """API 路由前缀端点"""
    return {"message": "Custom API endpoint"}
```

#### 在 flask_app.py 中添加

```python
@app.route('/api/custom', methods=['GET', 'POST'])
def custom_endpoint():
    """自定义端点"""
    return jsonify({
        "success": True,
        "data": "Custom data"
    })
```

### 修改工作流状态逻辑

编辑 `service_for_workflow/workflow_mock.py` 中的 `get_workflow_info` 方法：

```python
def get_workflow_info(self, run_id: str) -> Dict[str, Any]:
    # 添加你的状态逻辑
    if condition:
        return {...}
    else:
        return {...}
```

### 添加新的前端功能

编辑 `service_for_workflow/templates/index.html`：

```javascript
// 添加新的 JavaScript 函数
async function newFunction() {
    // 实现
    console.log("New function called");
}

// 添加 UI 元素和事件
```

### 扩展 Redis 数据结构

```python
# 在 redis_manager.py 中添加新的数据操作
def add_custom_data(self, task_id: str, data: Dict):
    """添加自定义数据到任务"""
    task_key = self.TASK_KEY_PREFIX + task_id
    self.redis.hset(task_key, "custom_data", json.dumps(data))
```

### 修改工作流进度节点

编辑 `service_for_workflow/workflow_mock.py` 中的 `_workflow_states` 初始化：

```python
self._workflow_states[run_id] = {
    ...
    'progress_nodes': [
        "步骤1",
        "步骤2",
        "步骤3",
        "步骤4",
        "步骤5"
    ]
}
```

---

## 配置说明

### 环境变量

```bash
# 可选：设置为环境变量
export TARGET_HOST="192.168.1.100"
export TARGET_PORT="8000"
export LISTEN_PORT="8080"
export REDIS_HOST="localhost"
export REDIS_PORT="6379"
```

### 配置文件

```python
# config.py 中可以添加
PROXY_CONFIG = {
    'request_timeout': 300,  # 请求超时（秒）
    'max_connections': 10,    # 最大连接数
    'cleanup_interval': 3600,    # 清理间隔（秒）
    'max_task_age_hours': 24,   # 最大任务保留时间（小时）
}
```

### 端口配置

| 服务 | 端口 | 说明 |
|------|------|------|
| 代理服务器 | 8080 | 可通过 --listen-port 修改 |
| 工作流系统 | 5000 | 需要修改 flask_app.py 中的 port 参数 |
| Redis | 6379 | 默认端口，可修改 |

### 安全配置

```python
# 生产环境建议：
# 1. 使用 HTTPS
# 2. 添加认证
# 3. 限制跨域
# 4. 添加速率限制
```

---

## 测试方法

### 单元测试

```bash
# 测试代理服务器
curl http://localhost:8080/
curl -X POST http://localhost:8080/api/test \
    -H "Content-Type: application/json" \
    -d '{"async": true, "test": "data"}'

# 测试工作流系统
curl http://localhost:5000/api/session
curl -X POST http://localhost:5000/api/send \
    -H "Content-Type: application/json" \
    -d '{"message": "测试消息"}'
```

### 集成测试

```bash
# 完整流程测试脚本
# 1. 启动所有服务
# 2. 发送测试消息
# 3. 轮询任务状态
# 4. 验证 Dashboard 显示
# 5. 模拟工作流各状态
```

### 性能测试

```bash
# 使用 ab 测试并发性能
ab -n 100 -c 10 http://localhost:8080/api/test

# 检查内存和 CPU 使用
top -p $(pgrep -f "proxy_server.py")

# Redis 性能
redis-cli INFO memory
redis-cli INFO cpu
```

---

## 总结

本项目提供了一个完整的异步工作流处理系统，包括：

1. **统一代理服务器** - 支持同步/异步请求模式
2. **工作流系统** - 智能对话界面，支持动态状态转换
3. **Redis 队列** - 可靠的任务队列管理
4. **Dashboard 监控** - 实时任务状态监控

关键特性：
- 同步/异步模式自动切换
- 工作流状态动态转换（processing → interrupt/success/fail）
- 实时进度显示和更新
- 完整的错误处理和日志记录
- 模块化设计，易于扩展

如需更多帮助，请参考各模块的内联文档或源代码注释。
