# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project contains two main Python components:

1. **HTTP Proxy Servers** - Simple and enhanced HTTP forward proxies for request forwarding
2. **Workflow Management System** - Flask-based intelligent conversation system with async task processing

## Running the Applications

### Basic Proxy Server
```bash
python3 proxy_server.py --target-host <C_SERVER_IP> --target-port 8000 --listen-port 8080
python3 proxy_server.py --help  # View available options
```

### Enhanced Proxy Server
Requires dependencies: `pip install fastapi uvicorn httpx pydantic`
```bash
python3 enhanced_proxy_server.py --target-host <C_SERVER_IP> --target-port 8000 --listen-port 8080
python3 enhanced_proxy_server.py --help
```

The enhanced proxy provides:
- Async request processing with concurrency control
- Task queue management with `/task/{task_id}` status tracking
- `/stats` endpoint for server statistics
- Long task detection (>5 minutes) with dedicated tracking

### Flask Workflow System
```bash
cd service_for_workflow
pip install -r requirements_flask.txt
./start_flask.sh
# or manually:
python3 flask_app.py
```

## Architecture

### Service for Workflow Module (`service_for_workflow/`)

The Flask application is organized into several modules:

- **flask_app.py** - Main web application with API endpoints (`/api/session`, `/api/status`, etc.)
- **session_manager.py** - Thread-safe session management for storing conversation history
- **async_processor.py** - Async task execution using event loops and thread pools
- **workflow_mock.py** - Mock workflow service that simulates workflow states (INTERRUPT/SUCCESS/FAIL)
- **config.py** - Centralized configuration (ports, timeouts, limits)

Sessions contain conversation messages and can be queried, created, and deleted. The workflow system supports async callback mechanisms for workflow updates and handles interrupted workflows that can be resumed.

### Enhanced Proxy Architecture

The enhanced proxy uses FastAPI with Uvicorn for async HTTP handling. Key features:

- Task queue with configurable max concurrent requests
- Status tracking per task with start/end times and HTTP response metadata
- Cleanup functionality for completed tasks
- Request timeout handling

## Code Notes

- Most documentation and comments are in Chinese
- No formal build or linting configuration present
- Use `httpx` for async HTTP client operations in enhanced_proxy_server.py
