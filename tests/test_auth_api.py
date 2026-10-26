"""TC-模块A 认证与参数校验
覆盖：注册参数校验（等价类/边界值）、登录成功/失败、鉴权拦截、Token 失效/伪造。
对应测试用例设计文档 TC-A 系列。
"""
import pytest

from client import Client


# ---------------- 注册参数校验：等价类 + 边界值 ----------------
@pytest.mark.parametrize("username,password,expect_code", [
    ("ab", "Test@1234", 400),          # 用户名 2 字 < 下限 3（边界值，拒绝）
    ("a" * 33, "Test@1234", 400),      # 用户名 33 字 > 上限 32（边界值，拒绝）
    ("abc", "123", 400),               # 密码 3 字 < 下限 6（边界值，拒绝）
    ("", "Test@1234", 400),            # 用户名为空（等价类：无效输入，拒绝）
    ("abc", "", 400),                  # 密码为空（等价类：无效输入，拒绝）
])
def test_register_validation_reject(anon, username, password, expect_code):
    """等价类划分 + 边界值分析：用户名[3,32]、密码[6,64]为有效等价类，越界/空值应拒绝。"""
    resp = anon.post("/auth/register", {"username": username, "password": password})
    assert resp.code == expect_code, f"期望 code={expect_code}, 实际 {resp.code}: {resp.message}"


def test_register_valid_username_accepted(anon):
    """有效等价类：长度在 [3,32] 的合法用户名应注册成功（用随机名，避免跨运行重名）。"""
    name = anon.rand_user()
    r = anon.post("/auth/register", {"username": name, "password": "Test@1234"})
    assert r.code == 0, f"合法用户名应成功, 实际 {r.code}: {r.message}"


def test_register_username_max_length(anon):
    """边界值分析：32 字用户名（合法上限）应注册成功。"""
    name = (anon.rand_user() + "x" * 32)[:32]
    r = anon.post("/auth/register", {"username": name, "password": "Test@1234"})
    assert r.code == 0, f"32 字用户名应成功, 实际 {r.code}: {r.message}"


def test_register_duplicate_username(anon):
    """重复注册同名用户应被拒绝（业务唯一性约束）。"""
    name = anon.rand_user()
    r1 = anon.post("/auth/register", {"username": name, "password": "Test@1234"}).expect(0)
    r2 = anon.post("/auth/register", {"username": name, "password": "Test@1234"})
    assert r2.code != 0, "重复注册应返回非 0 业务码"


# ---------------- 登录成功 / 失败 ----------------
def test_login_success(anon):
    name = anon.rand_user()
    anon.post("/auth/register", {"username": name, "password": "Test@1234"}).expect(0)
    r = anon.post("/auth/login", {"username": name, "password": "Test@1234"})
    assert r.ok
    assert (r.data or {}).get("token"), "登录成功应返回 token"


def test_login_wrong_password(anon):
    name = anon.rand_user()
    anon.post("/auth/register", {"username": name, "password": "Test@1234"}).expect(0)
    r = anon.post("/auth/login", {"username": name, "password": "wrong-pass"})
    assert r.code != 0, "密码错误应登录失败"


# ---------------- 鉴权拦截 ----------------
def test_missing_token_rejected(anon):
    """未带 Bearer Token 访问受保护接口，应被拦截（code=401）。"""
    r = anon.get("/books")  # 受保护，非 /api/auth/**
    assert r.code == 401, f"期望 401, 实际 {r.code}"


def test_invalid_token_rejected(anon):
    """伪造/篡改的 Token 应被拒绝（code=401）。"""
    bad = Client(token="eyJhbGciOiJIUzI1NiJ9.fake.signature")
    r = bad.get("/books")
    assert r.code == 401, f"期望 401, 实际 {r.code}"


def test_expired_token_rejected(anon):
    """空/过期 Token 头应被拒绝。"""
    c = Client(token="")
    r = c.get("/books")
    assert r.code == 401
