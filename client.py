"""笔尖 AI 小说生成工作台 —— 接口测试客户端（零三方依赖，仅用标准库）。

为什么不用 requests：本机测试环境为隔离的 managed venv，避免额外装包，
用 urllib 封装一个轻量客户端即可，语义与 requests 一致。

响应约定（来自后端 GlobalExceptionHandler / ApiResponse）：
  - 成功：HTTP 200，body={"code":0,"message":"success","data":...}
  - 业务异常（BizException，如 401/403/404）：HTTP 200，body={"code":401,...}
  - 参数校验失败（@Valid）：HTTP 400，body={"code":400,...}
因此「业务失败」一律看 body 的 code 字段，而非 HTTP 状态码。
"""
import json
import random
import string
import urllib.error
import urllib.request


class ApiError(Exception):
    def __init__(self, status, code, message, raw=None):
        self.status = status      # HTTP 状态码
        self.code = code          # body 里的业务 code
        self.message = message
        self.raw = raw
        super().__init__(f"[{status}/{code}] {message}")


class ApiResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body or {}
        self.code = self.body.get("code")
        self.message = self.body.get("message")
        self.data = self.body.get("data")

    @property
    def ok(self):
        """成功：HTTP 200 且业务 code == 0"""
        return self.status == 200 and self.code == 0

    def expect(self, code=0):
        """断言业务 code 等于期望（默认 0=成功）"""
        if self.code != code:
            raise ApiError(self.status, self.code, self.message, self.body)
        return self


class Client:
    def __init__(self, base="http://localhost:8081/api", token=None):
        self.base = base
        self.token = token

    def auth(self, token):
        self.token = token
        return self

    def _request(self, method, path, body=None, token=None):
        url = self.base + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        t = token if token is not None else self.token
        if t:
            headers["Authorization"] = "Bearer " + t
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return ApiResponse(resp.status, json.loads(resp.read().decode("utf-8")))
        except urllib.error.HTTPError as e:
            try:
                parsed = json.loads(e.read().decode("utf-8"))
            except Exception:
                parsed = {"code": e.code, "message": e.reason, "data": None}
            return ApiResponse(e.code, parsed)
        except urllib.error.URLError as e:
            raise ApiError(0, 0, f"无法连接后端 {url}: {e.reason}")

    # ---- 通用 verbs ----
    def get(self, path, token=None):
        return self._request("GET", path, token=token)

    def post(self, path, body=None, token=None):
        return self._request("POST", path, body=body, token=token)

    def put(self, path, body=None, token=None):
        return self._request("PUT", path, body=body, token=token)

    def delete(self, path, body=None, token=None):
        return self._request("DELETE", path, body=body, token=token)

    # ---- 业务便捷方法 ----
    @staticmethod
    def rand_user(prefix="tester"):
        n = "".join(random.choices(string.digits, k=6))
        return f"{prefix}_{n}"

    def register(self, username=None, password="Test@1234", display_name=None):
        username = username or self.rand_user()
        resp = self.post("/auth/register",
                         {"username": username, "password": password,
                          "displayName": display_name or username},
                         token=None)
        return resp, username

    def login(self, username, password="Test@1234"):
        resp = self.post("/auth/login", {"username": username, "password": password}, token=None)
        if resp.ok:
            self.token = (resp.data or {}).get("token")
        return resp

    def create_book(self, title="测试书", genre="玄幻", description="自动化测试书", **extra):
        body = {"title": title, "genre": genre, "description": description}
        body.update(extra)
        return self.post("/books", body)
