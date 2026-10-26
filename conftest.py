"""pytest 夹具：提供干净的用户/作品上下文，保证用例互相隔离、可重复执行。

设计要点（测试工程素养体现）：
  - 每个用例用随机用户名注册独立账号，避免数据污染；
  - 跨用户/越权用例用 fixture 同时产出 owner 与 attacker 两个 token；
  - 所有新建数据挂在当前测试用户名下，天然隔离。
"""
import os
import sys

import pytest

# 把项目根目录加入 sys.path，使 tests/ 下的用例能 `from client import Client`
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client import Client


@pytest.fixture
def base_url():
    return "http://localhost:8081/api"


@pytest.fixture
def anon():
    """未携带 token 的匿名客户端（用于鉴权/越权用例）"""
    return Client()


@pytest.fixture
def user():
    """已注册并登录的普通用户客户端"""
    c = Client()
    _, username = c.register()
    c.login(username)
    return c


@pytest.fixture
def owner_book():
    """返回一个 (client, book_id) 元组：已登录用户 + 其名下一本书"""
    c = Client()
    _, username = c.register()
    c.login(username)
    resp = c.create_book()
    resp.expect(0)
    return c, resp.data["id"]


@pytest.fixture
def two_users():
    """返回 (owner_client, attacker_client, book_id)：owner 名下一本书，attacker 是另一个人"""
    owner = Client()
    _, o_name = owner.register()
    owner.login(o_name)
    book = owner.create_book().expect(0).data["id"]

    attacker = Client()
    _, a_name = attacker.register()
    attacker.login(a_name)
    return owner, attacker, book
