import httpx
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import socket
import os
import logging
import sys

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("fotile-proxy")

class ProxyHandler(BaseHTTPRequestHandler):
    TARGET_HOST = os.environ.get("TARGET_HOST", "api.fotile.com")
    MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
    TARGET_SCHEME = os.environ.get("TARGET_SCHEME", "https").lower()
    UPSTREAM_IP   = os.environ.get("UPSTREAM_IP", "").strip()
    TIMEOUT       = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)
    # 将 BaseHTTPRequestHandler 的默认访问日志重定向到我们的 logger
    def log_message(self, fmt, *args):
        logger.info("%s - " + fmt, self.address_string(), *args)
    def build_target_url(self):
        host = self.UPSTREAM_IP if self.UPSTREAM_IP else self.TARGET_HOST
        return f"{self.TARGET_SCHEME}://{host}{self.path}"
    def standardize_header_name(self, name):
        standards = {
            'date': 'Date',
            'content-length': 'Content-Length',
            'set-cookie': 'Set-Cookie',
            'content-type': 'Content-Type',
            'x-frame-options': 'X-Frame-Options',
        }
        return standards.get(name.lower(), name.title())

    def send_response(self, code, message=None):
        self.send_response_only(code, message)

    # 打印请求日志
    def log_request_details(self, method, path, headers, body):
        logger.debug("=== HTTP Request Start ===")
        logger.debug("%s %s HTTP/1.1", method, path)
        for key, value in headers.items():
            logger.debug("%s: %s", key, value)
        if body:
            try:
                logger.debug("Request Body:\n%s", body.decode('utf-8'))
            except UnicodeDecodeError:
                logger.warning("Request Body: <非文本数据>")
        logger.debug("=== HTTP Request End ===")

    # 打印响应日志
    def log_response_details(self, status_code, headers, body):
        logger.debug("=== HTTP Response Start ===")
        logger.debug("HTTP/1.1 %s", status_code)
        for key, value in headers.items():
            logger.debug("%s: %s", key, value)
        if body:
            try:
                data = json.loads(body.decode('utf-8'))
                logger.debug("Response Body (JSON):\n%s", json.dumps(data, indent=2, ensure_ascii=False))
            except (UnicodeDecodeError, json.JSONDecodeError):
                logger.warning("Response Body (Raw):\n%s", body.decode('utf-8', errors='replace'))
        logger.debug("=== HTTP Response End ===")

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        headers = {'Connection': 'close'}
        # 将 Host 头改回官方域名，确保方太的服务器能正确识别这个请求。
        for key, value in self.headers.items():
            if key.lower() == 'host':
                headers[key] = self.TARGET_HOST
            else:
                headers[key] = value
        for key in list(headers.keys()):
            if key.lower() == 'user-agent':
                del headers[key]

        # 打印请求日志
        logger.info("Client IP: %s", self.client_address[0])
        self.log_request_details("POST", self.path, headers, post_data)

        # 将请求转发给真正的方太服务器
        target_url = self.build_target_url()
        verify_tls = not (self.TARGET_SCHEME == "https" and (self.UPSTREAM_IP or self.TARGET_HOST.replace('.', '').isdigit()))
        with httpx.Client(timeout=self.TIMEOUT, verify=verify_tls, headers={}) as client:
            try:
                request = client.build_request('POST', target_url, content=post_data, headers=headers)
                unwanted_headers = ['user-agent', 'accept', 'accept-encoding']
                for key in unwanted_headers:
                    request.headers.pop(key, None)

                response = client.send(request, follow_redirects=False)

                # 如果请求的路径恰好是 /iot-mqttManager/routeService，调用 self.modify_response() 函数对响应内容进行IP地址内容改写。
                # 如果请求的是任何其他路径，就直接使用 response.content，即原样转发。
                if self.path == "/iot-mqttManager/routeService":
                    content_to_send = self.modify_response(response.content)
                else:
                    content_to_send = response.content

                # 发送回最初发起请求的油烟机。
                self.send_response(response.status_code)

                unwanted_response_headers = ['transfer-encoding', 'server', 'content-length']
                for key, value in response.headers.items():
                    if key.lower() not in unwanted_response_headers:
                        self.send_header(self.standardize_header_name(key), value)

                self.send_header('Content-Length', str(len(content_to_send)))
                self.end_headers()
                self.wfile.write(content_to_send)

                self.log_response_details(response.status_code, response.headers, content_to_send)
            except httpx.ConnectTimeout:
                logger.exception("Proxy error: connect timeout -> %s", target_url)
                self.send_error(500, "Proxy error: timed out")
            except Exception as e:
                logger.exception("Proxy error: %s", e)
                self.send_error(500, f"Proxy error: {e}")

    # 检查 JSON 数据结构，包含了 "ip" 这个键，改为局域网内MQTT服务器的IP地址。
    def modify_response(self, content):
        try:
            data = json.loads(content.decode('utf-8'))
            if isinstance(data, list) and len(data) > 0 and "ip" in data[0]:
                old_ip = data[0]['ip']
                if old_ip != self.MQTT_HOST:
                    logger.info("Modifying MQTT IP from '%s' to '%s'", old_ip, self.MQTT_HOST)
                    data[0]["ip"] = self.MQTT_HOST
            return json.dumps(data).encode('utf-8')
        except (json.JSONDecodeError, KeyError, IndexError, UnicodeDecodeError):
            return content

def run_server():
    server_address = ('', 80)
    httpd = HTTPServer(server_address, ProxyHandler)
    httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
    logger.info("代理服务器已在端口80启动...")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()