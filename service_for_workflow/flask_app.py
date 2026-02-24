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
    """
    工作流状态回调 - 处理新的工作流数据结构

    Args:
        session_id: 会话ID
        result: 工作流查询结果，包含:
            - runId: str
            - status: str (processing/interrupted/success/fail)
            - nodes: Dict[str, NodeInfo]
            - steps: List[str]
            - costMs: int
            - output: Any
            - (interrupted) msg: str
            - (interrupted) lastInterruptedNodeId: str
            - (fail) error: str
    """
    session = session_manager.get_session(session_id)
    if not session:
        return

    status = result.get("status", "")

    # 根据状态添加消息
    if status == "processing":
        session.waiting_for_input = False
        # 从节点信息中提取进度
        nodes = result.get("nodes", {})
        steps = result.get("steps", [])

        # 计算进度
        completed_count = sum(1 for node_id in steps if nodes.get(node_id, {}).get("status") == "success")
        processing_count = sum(1 for node_id in steps if nodes.get(node_id, {}).get("status") == "processing")
        total_count = len(steps)

        current_step = completed_count + processing_count
        percentage = int((current_step / total_count) * 100) if total_count > 0 else 0

        # 找到当前正在处理的节点
        current_node_info = "正在处理工作流..."
        for node_id in steps:
            node_info = nodes.get(node_id, {})
            if node_info.get("status") == "processing":
                node_type = node_info.get("nodeType", "flow")
                current_node_info = f"正在执行节点: {node_type} ({current_step}/{total_count})"
                break

        message = f"{current_node_info} ({percentage}%)"
        session.add_message("assistant", message)

    elif status == "interrupted":
        session.waiting_for_input = True
        # 使用 msg 字段作为中断消息
        msg = result.get("msg", "工作流被中断，需要更多信息")
        session.add_message("assistant", msg)

    elif status == "success":
        session.waiting_for_input = False
        # 从 output 字段提取结果
        output = result.get("output", {})
        if isinstance(output, dict):
            message = output.get("summary", "工作流执行完成")
            # 可以添加更多详细信息
            details = output.get("details", {})
            if details:
                message += f"\n\n详细信息：\n{format_dict_to_text(details)}"
        else:
            message = str(output) if output else "工作流执行完成"

        # 检查是否有可视化链接
        visualization_url = None
        if isinstance(output, dict):
            # 检查最后一个节点的输出
            nodes = result.get("nodes", {})
            steps = result.get("steps", [])
            if steps:
                last_node = nodes.get(steps[-1], {})
                last_output = last_node.get("output", {})
                if isinstance(last_output, dict):
                    visualization_url = last_output.get("chart_url")

        session.add_message("assistant", message, visualization_url)

    elif status == "fail":
        session.waiting_for_input = False
        # 使用 error 字段作为失败原因
        error_msg = result.get("error", "工作流执行失败")
        session.add_message("assistant", f"❌ {error_msg}")


def format_dict_to_text(d: Dict[str, Any], indent: int = 0) -> str:
    """将字典格式化为文本"""
    lines = []
    prefix = "  " * indent
    for key, value in d.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.append(format_dict_to_text(value, indent + 1))
        elif isinstance(value, list):
            lines.append(f"{prefix}{key}: {', '.join(str(v) for v in value)}")
        else:
            lines.append(f"{prefix}{key}: {value}")
    return "\n".join(lines)


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
        # 中断后恢复：创建新的工作流实例（模拟恢复）
        run_id = workflow_service.start_workflow(user_message)
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


@app.route('/api/workflow/<run_id>/status', methods=['GET'])
def get_workflow_status(run_id: str):
    """
    轮询工作流状态 - 返回新的数据结构

    Args:
        run_id: 工作流运行 ID

    Returns:
        工作流状态信息（包含节点详情）
    """
    try:
        workflow_info = workflow_service.get_workflow_info(run_id)

        # 直接返回工作流信息，添加 success 标记
        response = {
            'success': True,
            **workflow_info
        }

        # 为前端添加额外的友好信息
        status = workflow_info.get('status', '')
        nodes = workflow_info.get('nodes', {})
        steps = workflow_info.get('steps', [])

        if status == 'processing':
            # 计算进度信息
            completed_count = sum(1 for node_id in steps if nodes.get(node_id, {}).get("status") == "success")
            processing_count = sum(1 for node_id in steps if nodes.get(node_id, {}).get("status") == "processing")
            total_count = len(steps)
            current_step = completed_count + processing_count
            percentage = int((current_step / total_count) * 100) if total_count > 0 else 0

            response['progress_info'] = {
                'current_step': current_step,
                'total_steps': total_count,
                'percentage': percentage,
                'nodes': [nodes.get(node_id, {}).get('nodeType', 'unknown') for node_id in steps],
                'current_node': nodes.get(steps[current_step - 1], {}).get('nodeType', 'unknown') if current_step > 0 else 'unknown'
            }

        elif status == 'interrupted':
            # 中断状态
            response['message'] = workflow_info.get('msg', '工作流被中断')
            interrupted_node_id = workflow_info.get('lastInterruptedNodeId', '')
            if interrupted_node_id and interrupted_node_id in nodes:
                interrupted_node = nodes[interrupted_node_id]
                response['interrupt_info'] = {
                    'node_type': interrupted_node.get('nodeType', 'unknown'),
                    'node_id': interrupted_node_id
                }

        elif status == 'success':
            # 成功状态 - 提取友好消息
            output = workflow_info.get('output', {})
            if isinstance(output, dict):
                response['message'] = output.get('summary', '工作流执行完成')

                # 检查可视化链接
                if steps:
                    last_node = nodes.get(steps[-1], {})
                    last_output = last_node.get('output', {})
                    if isinstance(last_output, dict) and 'chart_url' in last_output:
                        response['visualization_url'] = last_output['chart_url']
            else:
                response['message'] = str(output) if output else '工作流执行完成'

        elif status == 'fail':
            # 失败状态
            response['message'] = workflow_info.get('error', '工作流执行失败')

        return jsonify(response)

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/workflow/<run_id>/resume', methods=['POST'])
def resume_workflow(run_id: str):
    """
    恢复中断的工作流 - 创建新的工作流实例

    实际API可能通过提供补充信息来恢复中断的工作流
    这里我们创建一个新的工作流实例

    Args:
        run_id: 被中断的工作流运行 ID

    Returns:
        新的工作流运行 ID
    """
    data = request.get_json()
    user_input = data.get('input', '').strip()

    if not user_input:
        return jsonify({
            'success': False,
            'error': '输入不能为空'
        }), 400

    try:
        # 创建新的工作流实例（模拟恢复）
        new_run_id = workflow_service.start_workflow(user_input)

        # 获取当前会话并更新
        sessions = session_manager.get_all_sessions()
        if sessions:
            session = sessions[-1]
            session.current_run_id = new_run_id
            session.waiting_for_input = False

            # 提交异步任务
            async_processor.submit_task(
                session_id=session.session_id,
                run_id=new_run_id,
                status_callback=workflow_callback
            )

        return jsonify({
            'success': True,
            'new_run_id': new_run_id,
            'message': '工作流已恢复'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


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
