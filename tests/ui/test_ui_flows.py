"""
TC-模块U  Web UI 端到端自动化（Playwright）
覆盖：登录页渲染、登录失败、登录成功、UI 注册成功、注册表单校验、
新建作品弹窗流、大纲视图渲染 + AI 生成分卷、协作面板渲染。
依赖：本地已启动 vite 开发服务器(5174，带 /api 代理) 与 后端(8081)。
运行：pytest tests/ui/test_ui_flows.py --base-url=http://localhost:5174
（base-url 也可通过环境变量 UI_BASE_URL 指定，默认 http://localhost:5174）
对应测试用例设计文档 TC-U 系列。

注意：antd 会在相邻中文字符间插入空格（如「创建账号」→「创 建 账 号」），
因此所有中文文本/按钮定位一律走「容忍空格的正则匹配」(_btn / _txt / text=/.../)，
避免精确文本匹配失配导致的误报。
"""
import os
import sys
import re
import json
import random
import string

import pytest
from playwright.sync_api import sync_playwright

# 复用接口层客户端做「注册/建书」前置与 localStorage 注入
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from client import Client  # noqa: E402

DEFAULT_BASE = os.environ.get("UI_BASE_URL", "http://localhost:5174")


def _rx(s: str) -> "re.Pattern":
    """把字符串转成正则，容忍 antd 在相邻 CJK 间插入的空格。"""
    return re.compile(r"\s*".join(re.escape(c) for c in s))


def _btn(page, s: str):
    """按（容忍空格的）文本定位 antd 按钮。"""
    return page.get_by_role("button", name=_rx(s))


def _txt(page, s: str):
    """按（容忍空格的）文本定位普通元素。"""
    return page.get_by_text(_rx(s))


def _rand(n=8):
    return "".join(random.choices(string.digits, k=n))


def _seed_user_book(need_book=True):
    """通过接口注册一个随机用户，可选建一本书，返回登录态所需数据。"""
    c = Client()
    uname = "ui_" + _rand()
    pwd = "Test@1234"
    r = c.post("/auth/register", {"username": uname, "password": pwd, "email": uname + "@q.com"})
    assert r.ok, f"注册失败: {r.message}"
    d = r.data
    seed = {
        "username": uname,
        "password": pwd,
        "token": d.get("token"),
        "user_id": d.get("id"),
        "displayName": d.get("displayName") or uname,
        "book_id": None,
        "book_title": None,
    }
    if need_book:
        rb = Client(token=d.get("token")).post(
            "/books",
            {"title": "UI测试书_" + _rand(), "genre": "玄幻", "description": "ui", "targetWords": 100000},
        )
        assert rb.ok, f"建书失败: {rb.message}"
        seed["book_id"] = rb.data["id"]
        seed["book_title"] = rb.data["title"]
    return seed


def _auth_script(seed, with_book=True):
    """构造注入 localStorage 的初始化脚本（绕过登录态、直接进入已登录+选中某书）。"""
    books = []
    if with_book and seed["book_id"]:
        books = [{"id": seed["book_id"], "title": seed["book_title"]}]
    data = {
        "nwb_token": seed["token"],
        "nwb_user": json.dumps(
            {"id": seed["user_id"], "username": seed["username"], "displayName": seed["displayName"]},
            ensure_ascii=False,
        ),
        "nw-book-store": json.dumps(
            {"state": {"currentBookId": seed["book_id"] if with_book else None, "books": books}, "version": 0},
            ensure_ascii=False,
        ),
    }
    return "Object.entries(%s).forEach(([k,v]) => localStorage.setItem(k, v));" % json.dumps(data, ensure_ascii=False)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def ctx(browser):
    context = browser.new_context(base_url=DEFAULT_BASE)
    yield context
    context.close()


@pytest.fixture
def page(ctx):
    pg = ctx.new_page()
    pg.set_default_timeout(15000)
    yield pg
    pg.close()


# ---------------- 1. 登录页渲染 ----------------
def test_login_page_renders(page):
    """登录页应渲染品牌、登录 Tab、用户名/密码输入框与登录按钮。"""
    page.goto("/login")
    page.get_by_text(_rx("AI 小说生成工作台")).first.wait_for(state="visible", timeout=10000)
    assert page.get_by_placeholder("用户名").is_visible()
    assert page.get_by_placeholder("密码").is_visible()
    # 登录 tab 下的主按钮（antd type="primary"）；显式等待可见，规避 headless 入场动画偶发卡
    login_btn = page.locator("button.ant-btn-primary").first
    login_btn.wait_for(state="visible", timeout=10000)
    assert login_btn.is_visible()
    assert _txt(page, "注册").first.is_visible()


# ---------------- 2. 登录失败（错误密码） ----------------
def test_login_failure_wrong_password(page, ctx):
    """错误密码登录：应停留在登录页并提示错误（HTTP 200 + code!=0，前端拦截器弹错）。"""
    seed = _seed_user_book(need_book=False)
    page.goto("/login")
    page.get_by_placeholder("用户名").fill(seed["username"])
    page.get_by_placeholder("密码").fill("WrongPass@1")
    page.locator("button.ant-btn-primary").click()  # 登录主按钮
    # 登录失败不跳转，仍在登录页
    page.wait_for_timeout(1500)
    assert "login" in page.url, f"登录失败后仍跳转，url={page.url}"
    # 前端拦截器应弹出了错误提示
    assert page.locator(".ant-message-notice").count() >= 1, "未出现错误提示 toast"


# ---------------- 3. 登录成功 ----------------
def test_login_success(page, ctx):
    """正确凭据登录：跳转工作台，渲染品牌侧栏与欢迎语。"""
    seed = _seed_user_book(need_book=False)
    page.goto("/login")
    page.get_by_placeholder("用户名").fill(seed["username"])
    page.get_by_placeholder("密码").fill(seed["password"])
    page.locator("button.ant-btn-primary").click()  # 登录主按钮
    page.wait_for_url("**/")
    assert _txt(page, "你好，创作者").first.is_visible()
    assert _txt(page, "AI 小说工作台").first.is_visible()


# ---------------- 4. UI 注册成功（自动登录） ----------------
def test_register_success_via_ui(page, ctx):
    """注册 Tab 提交合法信息：自动登录并跳转工作台。"""
    uname = "ui_reg_" + _rand()
    page.goto("/login")
    _txt(page, "注册").first.click()
    page.get_by_placeholder("别人怎么称呼你").fill("UI测试昵称")
    page.get_by_placeholder("用户名").fill(uname)
    page.get_by_placeholder("密码").fill("Test@1234")
    _btn(page, "创建账号").click()
    page.wait_for_url("**/")
    assert _txt(page, "你好，创作者").first.is_visible(), "注册后未自动登录跳转"


# ---------------- 5. 注册表单校验 ----------------
def test_register_validation(page, ctx):
    """非法输入（用户名过短、密码过短）：内联报错且不提交。"""
    page.goto("/login")
    _txt(page, "注册").first.click()
    page.get_by_placeholder("别人怎么称呼你").fill("短")
    page.get_by_placeholder("用户名").fill("ab")          # 长度 3-20 → 太短
    page.get_by_placeholder("密码").fill("123")           # 至少 6 位 → 太短
    _btn(page, "创建账号").click()
    page.get_by_text(_rx("长度 3-20 个字符")).first.wait_for(state="visible", timeout=10000)
    assert _txt(page, "至少 6 位").first.is_visible()
    # 未离开登录页（注册 Tab 仍在）
    assert "login" in page.url


# ---------------- 6. 新建作品弹窗流 ----------------
def test_create_book_flow(page, ctx):
    """无书用户通过头部作品选择器新建作品：弹窗填写 → 创建 → 书架/选择器出现新书。"""
    seed = _seed_user_book(need_book=False)  # 故意无书，验证“新建”入口
    ctx.add_init_script(script=_auth_script(seed, with_book=False))
    title = "UI新建书_" + _rand()
    page.goto("/")
    # 头部 BookPicker 无书时显示“暂无作品” → 点击打开下拉 → 新建作品…
    page.get_by_text(_rx("暂无作品")).first.wait_for(state="visible", timeout=10000)
    _txt(page, "暂无作品").first.click()
    page.get_by_role("menuitem", name=_rx("新建作品…")).click()
    page.get_by_text(_rx("新建作品")).first.wait_for(state="visible", timeout=10000)
    page.get_by_placeholder("例如：星海征途").fill(title)
    _btn(page, "创建").click()
    # 创建成功后新书名应出现在页面（选择器/书架）；书名含动态串，用 _rx 容忍 antd 间距
    _txt(page, title).first.wait_for(state="visible", timeout=10000)
    assert _txt(page, title).count() >= 1


# ---------------- 7. 大纲视图渲染 + AI 生成分卷 ----------------
def test_outline_render_and_generate_volume(page, ctx):
    """进入大纲视图：标题与生成按钮渲染；点击 AI 生成分卷 → 模态 → 开始生成 → 出现卷节点。"""
    seed = _seed_user_book(need_book=True)
    ctx.add_init_script(script=_auth_script(seed, with_book=True))
    page.goto("/outline")
    page.get_by_text(_rx("一键大纲生成器")).first.wait_for(state="visible", timeout=10000)
    # owner 可写：AI 生成分卷大纲按钮可见（真实按钮名，非“一键生成大纲”）
    gen_btn = _btn(page, "AI 生成分卷大纲")
    gen_btn.first.wait_for(state="visible", timeout=10000)
    assert gen_btn.first.is_visible()
    # 触发 AI 生成分卷大纲
    gen_btn.first.click()
    page.get_by_text(_rx("AI 生成分卷大纲")).first.wait_for(state="visible", timeout=10000)
    _btn(page, "开始生成").first.click()  # 卷规划模态的「开始生成」
    # mock 兜底下生成 1 个分卷节点（卷 tag），等待树渲染
    page.wait_for_selector(".ant-tag:has-text('卷')", timeout=12000)
    assert page.locator(".ant-tag").filter(has_text="卷").count() >= 1


# ---------------- 8. 协作面板渲染（owner 视角） ----------------
def test_collaboration_page_renders(page, ctx):
    """owner 进入协作面板：标题含书名·协作，渲染邀请码区与协作者列表。"""
    seed = _seed_user_book(need_book=True)
    ctx.add_init_script(script=_auth_script(seed, with_book=True))
    page.goto(f"/books/{seed['book_id']}/collaboration")
    page.get_by_text(_rx(f"{seed['book_title']} · 协作")).first.wait_for(state="visible", timeout=10000)
    assert _txt(page, "邀请码").first.is_visible()
    assert _txt(page, "协作者").first.is_visible()
