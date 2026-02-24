# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project contains two independent Python systems for handling asynchronous HTTP requests and workflow management:

1. **HTTP Proxy Servers** - Request forwarding system with synchronous/asynchronous modes and Redis-based task queuing
2. **Workflow Management System** - Flask-based intelligent conversation interface with mock workflow processing

Both systems are designed for development/testing purposes and require Redis for async task management.

## Running the Applications

### Prerequisites

All systems require a running Redis server:

```bash
# Using Docker
docker run -d -p 6379:6379 redis

# Or directly
redis-server --daemonize yes --port 6379
```

### Proxy Server (Main)

The unified proxy server supports both synchronous and asynchronous request modes:

```bash
# Install dependencies
pip install fastapi uvicorn httpx redis

# Run the proxy
python3 proxy_server.py \
    --target-host <TARGET_SERVER_IP> \
    --target-port 8000 \
    --listen-port 8080 \
    --redis-host localhost \
    --redis-port 6379

# View all options
python3 proxy_server.py --help
```

**Key endpoints:**
- `POST /api/{path:path}` - Forward requests (add `{"async": true}` for async mode)
- `GET /task/{task_id}` - Query async task status
- `GET /dashboard` - Real-time task monitoring dashboard
- `GET /stats` - Server statistics

### Enhanced Proxy Server

Alternative proxy implementation with additional features:

```bash
python3 enhanced_proxy_server.py \
    --target-host <TARGET_SERVER_IP> \
    --target-port 8000 \
    --listen-port 8080
```

### Flask Workflow System

Interactive web interface for simulating workflow conversations:

```bash
cd service_for_workflow
pip install -r requirements_flask.txt
python3 flask_app.py
# or use: ./start_flask.sh
```

Access the interface at `http://localhost:5000`

## Architecture

### Proxy System Design

The proxy uses a **dual-mode architecture**:

```
Sync Mode:  Client → Proxy → Target Server → Immediate Response
Async Mode: Client → Proxy → Redis Queue → Background Worker → Target Server
                                      ↓
                              Task ID returned immediately
```

**Key components:**
- **`proxy_server.py`** - FastAPI application handling both sync/async forwarding
- **`redis_manager.py`** - Redis operations for task queuing and state management
- **Background workers** - Thread pool processing async tasks from Redis queue

**Redis data structures:**
- `async_proxy:queue` - Task queue (list)
- `async_proxy:task:{task_id}` - Task details (hash)
- `async_proxy:stats` - Server statistics (hash)

**Async request flow:**
1. Client sends request with `{"async": true}` in JSON body
2. Proxy generates task ID, queues to Redis, returns ID immediately
3. Background worker picks up task, forwards to target server
4. Worker updates task status in Redis (pending → completed/failed)
5. Client polls `/task/{task_id}` for status updates

### Workflow System Design

The Flask workflow system implements a **state machine pattern** with polling-based status updates:

```
User Input → Flask API → Session Manager → Async Processor → Workflow Mock
                      ↓                                    ↓
                 Session Storage                    State Transitions:
                                                      PROCESSING (1-3 polls)
                                                      → INTERRUPT (needs input)
                                                      → SUCCESS
                                                      → FAIL
```

**Module responsibilities:**

- **`flask_app.py`** - REST API endpoints (`/api/send`, `/api/workflow/{run_id}/status`, etc.)
- **`session_manager.py`** - Thread-safe in-memory session storage with conversation history
- **`async_processor.py`** - Event loop + thread pool for non-blocking workflow execution
- **`workflow_mock.py`** - Simulated workflow service with deterministic state transitions
- **`config.py`** - Centralized configuration for timeouts, limits, and UI settings

**Workflow state logic:**
- First 3 status polls return `PROCESSING` with progress increments
- 4th poll determines final state based on `run_id % 3`:
  - `0` → INTERRUPT (requires user input to resume)
  - `1` → SUCCESS (displays results)
  - `2` → FAIL (shows error)

**Session management:**
- Sessions stored in-memory with thread-safe locks
- Max 1000 sessions, 24-hour TTL (configurable in `config.py`)
- Each session contains message history and associated workflow run_id

## Configuration

### Proxy Server Configuration

All proxy settings are command-line arguments:

```bash
--target-host     # Target server IP (required)
--target-port     # Target server port (default: 8000)
--listen-port     # Proxy listening port (default: 8080)
--redis-host      # Redis host (default: localhost)
--redis-port      # Redis port (default: 6379)
--redis-db        # Redis database number (default: 0)
--redis-password  # Redis password (optional)
--max-concurrent  # Max concurrent async tasks (default: 10)
--queue-size      # Max task queue size (default: 100)
```

### Workflow System Configuration

Edit `service_for_workflow/config.py`:

```python
class Config:
    # Server
    GRADIO_SERVER_PORT = 7860

    # Async processing
    MAX_ASYNC_WORKERS = 10
    TASK_CLEANUP_INTERVAL_MINUTES = 30

    # Sessions
    SESSION_MAX_AGE_HOURS = 24
    MAX_SESSIONS = 1000

    # Workflows
    WORKFLOW_TIMEOUT_SECONDS = 300
    WORKFLOW_POLL_INTERVAL_SECONDS = 1

    # UI
    CHATBOT_HEIGHT = 500
    MAX_MESSAGE_LENGTH = 5000
```

## Development Notes

### Code Language

Most code comments, logs, and documentation (including this file) use Chinese. When adding new code or error messages, follow the existing pattern.

### Concurrency Patterns

**Proxy system:**
- Uses `threading.Semaphore` for concurrency limiting
- Background daemon threads for task processing
- Redis connection pooling via `redis.ConnectionPool`

**Workflow system:**
- `asyncio.new_event_loop()` in separate thread for async operations
- `concurrent.futures.ThreadPoolExecutor` for parallel task execution
- `threading.Lock` for session manager thread safety

### Error Handling

- Proxy: HTTP exceptions propagated to client, tasks marked as `failed` in Redis
- Workflow: State transitions include error states, frontend displays failure reasons
- Redis connection errors are logged but don't crash the application

### Testing

No formal test suite exists. Manual testing via:

```bash
# Test proxy sync mode
curl -X POST http://localhost:8080/api/test \
    -H "Content-Type: application/json" \
    -d '{"data": "test"}'

# Test proxy async mode
curl -X POST http://localhost:8080/api/test \
    -H "Content-Type: application/json" \
    -d '{"async": true, "data": "test"}'

# Test workflow system
curl -X POST http://localhost:5000/api/send \
    -H "Content-Type: application/json" \
    -d '{"message": "test message"}'
```

## Dependencies

**Core dependencies:**
- `fastapi` + `uvicorn` - Async web framework for proxy
- `flask` - Web framework for workflow system
- `redis` - Redis client for task queuing
- `httpx` - Async HTTP client for proxy forwarding

**Optional:**
- `gradio` - Alternative UI framework (mentioned but not actively used)

Install all dependencies:
```bash
pip install fastapi uvicorn httpx redis flask werkzeug
```
