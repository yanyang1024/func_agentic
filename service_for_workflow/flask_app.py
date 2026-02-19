"""
Flask Web应用 - 智能对话工作流系统
不依赖Gradio，使用原生HTML/CSS/JavaScript
"""
from flask import Flask, render_template, request, jsonify
from typing import Dict, Any
import asyncio

from workflow_mock import workflow_service, WorkflowStatus
from session_manager import session_manager, Session
from async_processor import async_processor


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'


# ============================================
# 异步工作流回调
# ============================================

async def workflow_callback(session_id: str, result: Dict[str, Any]):
    """工作流状态回调"""
    session = session_manager.get_session(session_id)
    if not session:
        return

    # 根据状态添加消息
    if result["status"] == WorkflowStatus.INTERRUPT:
        session.waiting_for_input = True
        session.add_message("assistant", result["message"])
    elif result["status"] == WorkflowStatus.SUCCESS:
        session.waiting_for_input = False
        session.add_message("assistant", result["message"], result.get("visualization_url"))
    elif result["status"] == WorkflowStatus.FAIL:
        session.waiting_for_input = False
        session.add_message("assistant", result["message"])


# ============================================
# 路由处理
# ============================================

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/session', methods=['GET', 'POST'])
def handle_session():
    """创建或获取会话"""
    if request.method == 'POST':
        # 创建新会话
        session = session_manager.create_session()
        return jsonify({
            'success': True,
            'session_id': session.session_id,
            'message': '会话已创建'
        })
    else:
        # 获取当前会话
        sessions = session_manager.get_all_sessions()
        if not sessions:
            session = session_manager.create_session()
        else:
            session = sessions[-1]

        return jsonify({
            'success': True,
            'session_id': session.session_id,
            'message_count': len(session.messages),
            'waiting_for_input': session.waiting_for_input,
            'current_run_id': session.current_run_id
        })


@app.route('/api/messages', methods=['GET'])
def get_messages():
    """获取对话消息"""
    sessions = session_manager.get_all_sessions()
    if not sessions:
        return jsonify({'success': True, 'messages': []})

    session = sessions[-1]

    # 格式化消息
    messages = []
    for msg in session.messages:
        message = {
            'role': msg.role,
            'content': msg.content,
            'timestamp': msg.timestamp.isoformat()
        }
        if msg.visualization_url:
            message['visualization_url'] = msg.visualization_url
        messages.append(message)

    return jsonify({
        'success': True,
        'messages': messages,
        'session_id': session.session_id
    })


@app.route('/api/send', methods=['POST'])
def send_message():
    """发送用户消息"""
    data = request.get_json()
    user_message = data.get('message', '').strip()

    if not user_message:
        return jsonify({
            'success': False,
            'error': '消息不能为空'
        }), 400

    # 获取或创建会话
    sessions = session_manager.get_all_sessions()
    session = sessions[-1] if sessions else session_manager.create_session()

    # 添加用户消息
    session.add_message("user", user_message)

    # 判断是新对话还是中断响应
    if session.waiting_for_input and session.current_run_id:
        # 重启工作流
        run_id = workflow_service.restart_workflow(user_message, session.current_run_id)
        session.waiting_for_input = False
    else:
        # 启动新工作流
        run_id = workflow_service.start_workflow(user_message)

    session.current_run_id = run_id

    # 提交异步任务
    async_processor.submit_task(
        session_id=session.session_id,
        run_id=run_id,
        status_callback=workflow_callback
    )

    return jsonify({
        'success': True,
        'run_id': run_id,
        'message': '消息已发送，工作流正在处理'
    })


@app.route('/api/refresh', methods=['POST'])
def refresh_status():
    """刷新状态"""
    sessions = session_manager.get_all_sessions()
    if not sessions:
        return jsonify({
            'success': False,
            'error': '无活动会话'
        }), 404

    session = sessions[-1]

    # 获取最新消息
    messages = []
    reference_info = None

    for msg in session.messages:
        message = {
            'role': msg.role,
            'content': msg.content,
            'timestamp': msg.timestamp.isoformat()
        }
        if msg.visualization_url:
            message['visualization_url'] = msg.visualization_url
            reference_info = msg.visualization_url
        messages.append(message)

    return jsonify({
        'success': True,
        'messages': messages,
        'reference_info': reference_info,
        'session_id': session.session_id,
        'waiting_for_input': session.waiting_for_input,
        'current_run_id': session.current_run_id
    })


@app.route('/api/clear', methods=['POST'])
def clear_chat():
    """清空对话"""
    session = session_manager.create_session()

    return jsonify({
        'success': True,
        'session_id': session.session_id,
        'message': '对话已清空'
    })


@app.route('/api/status', methods=['GET'])
def get_status():
    """获取系统状态"""
    sessions = session_manager.get_all_sessions()

    return jsonify({
        'success': True,
        'active_sessions': len(sessions),
        'active_tasks': async_processor.get_active_tasks_count()
    })


# ============================================
# 错误处理
# ============================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': '未找到'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': '服务器内部错误'}), 500


# ============================================
# 启动应用
# ============================================

def main():
    """主函数"""
    print("=" * 70)
    print("🚀 Flask智能对话工作流系统启动中...")
    print("=" * 70)
    print(f"📍 服务地址: http://0.0.0.0:5000")
    print(f"📊 活跃会话: {len(session_manager.get_all_sessions())}")
    print(f"⚙️  活跃任务: {async_processor.get_active_tasks_count()}")
    print("=" * 70)

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )


if __name__ == '__main__':
    main()
