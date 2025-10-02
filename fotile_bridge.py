import httpx
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import socket
import os

class ProxyHandler(BaseHTTPRequestHandler):
    # 从环境变量中读取 TARGET_HOST
    # 如果环境变量不存在，使用默认地址
    TARGET_HOST = os.environ.get("TARGET_HOST", "101.37.40.179")
    MQTT_HOST = os.environ.get("SUPERVISOR_IP", "127.0.0.1")

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
        print("=== HTTP Request Start ===")
        print(f"{method} {path} HTTP/1.1")
        for key, value in headers.items():
            print(f"{key}: {value}")
        if body:
            try:
                print("\nRequest Body:")
                print(body.decode('utf-8'))
            except UnicodeDecodeError:
                print("<非文本数据>")
        print("=== HTTP Request End ===\n")

    # 打印响应日志
    def log_response_details(self, status_code, headers, body):
        print("=== HTTP Response Start ===")
        print(f"HTTP/1.1 {status_code}")
        for key, value in headers.items():
            print(f"{key}: {value}")
        if body:
            try:
                # 尝试格式化 JSON 输出
                data = json.loads(body.decode('utf-8'))
                print("\nResponse Body (JSON):")
                print(json.dumps(data, indent=2, ensure_ascii=False))
            except (UnicodeDecodeError, json.JSONDecodeError):
                print("\nResponse Body (Raw):")
                print(body.decode('utf-8', errors='replace'))
        print("=== HTTP Response End ===\n")

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        headers = {'Connection': 'close'}
        # 在准备将请求转发给真正的方太服务器
        # 其中 headers[key] = 'api.fotile.com' 至关重要。
        # 因为油烟机发出的请求的 Host 头是 api.fotile.com，
        # 但我们的代理服务器在转发时，httpx 库可能会自动将其改为目标 IP 地址。
        # 这里我们强制将 Host 头改回官方域名，
        # 确保方太的服务器能正确识别这个请求，认为它是一个合法的、来自正常客户端的请求。
        for key, value in self.headers.items():
            if key.lower() == 'host':
                headers[key] = 'api.fotile.com'
            else:
                headers[key] = value
        for key in list(headers.keys()):
            if key.lower() == 'user-agent':
                del headers[key]

        # 打印请求日志
        self.log_request_details("POST", self.path, headers, post_data)

        # 将请求转发给真正的方太服务器
        target_url = f"http://{self.TARGET_HOST}{self.path}"
        with httpx.Client(headers={}) as client:
            try:
                request = client.build_request('POST', target_url, content=post_data, headers=headers)

                unwanted_headers = ['user-agent', 'accept', 'accept-encoding']
                for key in unwanted_headers:
                    request.headers.pop(key, None)

                response = client.send(request, follow_redirects=False)

                # 核心拦截与篡改逻辑
                # 代码在这里设置了一个条件检查：
                # 如果请求的路径恰好是 /iot-mqttManager/routeService（抓包发现的，专门用来获取 MQTT 服务器信息的），
                # 那么就不直接返回原始响应。
                # 而是调用 self.modify_response() 函数对响应内容进行**“手术”**。
                # 如果请求的是任何其他路径，就直接使用 response.content，即原样转发。
                if self.path == "/iot-mqttManager/routeService":
                    content_to_send = self.modify_response(response.content)
                else:
                    content_to_send = response.content

                # 打印响应日志
                self.log_response_details(response.status_code, response.headers, content_to_send)

                # 这部分代码负责将处理过的响应（可能是原始的，也可能是被篡改过的）按照标准的 HTTP 格式，发送回最初发起请求的油烟机。
                # 油烟机收到这个响应后，它会完全相信这就是来自 api.fotile.com 官方的回复。
                # 当它解析 /iot-mqttManager/routeService 的响应时，就会拿到我们伪造的本地 MQTT 服务器 IP，并尝试与之建立连接。
                self.send_response(response.status_code)

                unwanted_response_headers = ['transfer-encoding', 'server', 'content-length']
                for key, value in response.headers.items():
                    if key.lower() not in unwanted_response_headers:
                        self.send_header(self.standardize_header_name(key), value)

                self.send_header('Content-Length', str(len(content_to_send)))
                self.end_headers()
                self.wfile.write(content_to_send)

            except Exception as e:
                self.send_error(500, f"Proxy error: {str(e)}")


    # 这个函数接收来自方太服务器的原始响应体 content。
    # 它尝试将响应体解析为 JSON 格式。
    # 然后检查 JSON 数据结构，如果发现其中包含了 "ip" 这个键（这表明响应里有服务器 IP 地址），
    # 就毫不犹豫地将它的值修改为我们自己局域网内 MQTT 服务器的 IP 地址 (192.168.1.194)。
    # 最后，将修改后的 JSON 数据重新编码并返回。
    # 如果解析失败或结构不匹配，就返回原始内容，确保程序的健壮性。

    def modify_response(self, content):
        try:
            data = json.loads(content.decode('utf-8'))
            if isinstance(data, list) and len(data) > 0 and "ip" in data[0]:
                print(f"Modifying MQTT IP from '{data[0]['ip']}' to '{self.MQTT_HOST}'")
                data[0]["ip"] = self.MQTT_HOST
            return json.dumps(data).encode('utf-8')
        except (json.JSONDecodeError, KeyError, IndexError):
            return content

def run_server():
    server_address = ('', 80)
    httpd = HTTPServer(server_address, ProxyHandler)
    httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
    print("代理服务器已在端口80启动...")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()