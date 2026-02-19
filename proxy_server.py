#!/usr/bin/env python3
"""
简单的HTTP转发服务
用于将请求从B服务器转发到C服务器

使用方法:
    python3 proxy_server.py --target-host <C服务器IP> --target-port 8000 --listen-port 8080

示例:
    python3 proxy_server.py --target-host 192.168.1.100 --target-port 8000 --listen-port 8080
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import socket
import argparse
import sys
from typing import Tuple


class ProxyHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP请求转发处理器"""

    # 目标服务器配置（类变量，由服务器启动时设置）
    target_host = None
    target_port = None

    def log_message(self, format: str, *args):
        """自定义日志格式"""
        sys.stderr.write(f"[Proxy] {self.log_date_time_string()} - {format % args}\n")

    def _forward_request(self) -> Tuple[bytes, int, dict]:
        """
        转发请求到目标服务器

        Returns:
            (response_body, status_code, response_headers)
        """
        try:
            # 解析请求URL
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            query = parsed_path.query

            # 构建目标URL
            if query:
                target_url = f"http://{self.target_host}:{self.target_port}{path}?{query}"
            else:
                target_url = f"http://{self.target_host}:{self.target_port}{path}"

            # 获取请求体（如果有）
            content_length = int(self.headers.get('Content-Length', 0))
            request_body = self.rfile.read(content_length) if content_length > 0 else None

            # 发送请求到目标服务器
            import urllib.request
            req = urllib.request.Request(target_url, data=request_body, method=self.command)

            # 复制原始请求头（过滤掉一些不需要的头）
            skip_headers = {'host', 'connection', 'accept-encoding', 'content-length'}
            for header, value in self.headers.items():
                if header.lower() not in skip_headers:
                    req.add_header(header, value)

            # 执行请求
            with urllib.request.urlopen(req, timeout=30) as response:
                response_body = response.read()
                status_code = response.status

                # 收集响应头
                response_headers = {}
                skip_response_headers = {'connection', 'transfer-encoding', 'content-encoding'}
                for header, value in response.headers.items():
                    if header.lower() not in skip_response_headers:
                        response_headers[header] = value

                return response_body, status_code, response_headers

        except urllib.error.HTTPError as e:
            # HTTP错误（如404, 500等）
            error_body = e.read() if e.fp else b''
            return error_body, e.code, {}
        except urllib.error.URLError as e:
            # 连接错误
            error_msg = f"Proxy Error: Cannot connect to target server {self.target_host}:{self.target_port}\nReason: {e.reason}"
            return error_msg.encode('utf-8'), 502, {'Content-Type': 'text/plain'}
        except socket.timeout:
            error_msg = f"Proxy Error: Target server timeout"
            return error_msg.encode('utf-8'), 504, {'Content-Type': 'text/plain'}
        except Exception as e:
            error_msg = f"Proxy Error: {str(e)}"
            return error_msg.encode('utf-8'), 500, {'Content-Type': 'text/plain'}

    def do_GET(self):
        """处理GET请求"""
        response_body, status_code, response_headers = self._forward_request()

        # 发送响应
        self.send_response(status_code)
        for header, value in response_headers.items():
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(response_body)

    def do_POST(self):
        """处理POST请求"""
        response_body, status_code, response_headers = self._forward_request()

        # 发送响应
        self.send_response(status_code)
        for header, value in response_headers.items():
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(response_body)

    def do_PUT(self):
        """处理PUT请求"""
        response_body, status_code, response_headers = self._forward_request()

        # 发送响应
        self.send_response(status_code)
        for header, value in response_headers.items():
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(response_body)

    def do_DELETE(self):
        """处理DELETE请求"""
        response_body, status_code, response_headers = self._forward_request()

        # 发送响应
        self.send_response(status_code)
        for header, value in response_headers.items():
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(response_body)

    def do_OPTIONS(self):
        """处理OPTIONS请求（用于CORS预检）"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()


def run_proxy_server(listen_host: str, listen_port: int, target_host: str, target_port: int):
    """
    启动代理服务器

    Args:
        listen_host: 监听地址（通常是0.0.0.0）
        listen_port: 监听端口
        target_host: 目标服务器IP（C服务器）
        target_port: 目标服务器端口（通常是8000）
    """
    # 设置目标服务器配置
    ProxyHTTPRequestHandler.target_host = target_host
    ProxyHTTPRequestHandler.target_port = target_port

    # 创建服务器
    server_address = (listen_host, listen_port)
    httpd = HTTPServer(server_address, ProxyHTTPRequestHandler)

    print("=" * 70)
    print("HTTP转发服务已启动")
    print("=" * 70)
    print(f"监听地址: {listen_host}:{listen_port}")
    print(f"目标地址: {target_host}:{target_port}")
    print(f"\n使用方式:")
    print(f"  A服务器访问: http://{listen_host}:{listen_port}/api/function1")
    print(f"  将被转发到:   http://{target_host}:{target_port}/api/function1")
    print("\n按 Ctrl+C 停止服务")
    print("=" * 70)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n服务器已停止")
        httpd.shutdown()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='HTTP转发服务 - 将请求转发到目标服务器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 转发到C服务器的8000端口，B服务器监听8080端口
  python3 proxy_server.py --target-host 192.168.1.100 --target-port 8000 --listen-port 8080

  # 只指定必需参数，使用默认监听端口
  python3 proxy_server.py --target-host 192.168.1.100
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
        help='监听地址（默认: 0.0.0.0，允许所有IP访问）'
    )

    parser.add_argument(
        '--listen-port',
        type=int,
        default=8080,
        help='监听端口（默认: 8080）'
    )

    args = parser.parse_args()

    # 启动服务器
    run_proxy_server(
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        target_host=args.target_host,
        target_port=args.target_port
    )


if __name__ == "__main__":
    main()
