"""TC-模块B 作品（Book）CRUD 与生命周期
覆盖：创建/查询/更新/删除/归档/统计、不存在资源返回 404。
对应测试用例设计文档 TC-B 系列。
"""
import pytest


def test_create_book_success(user):
    r = user.create_book(title="我的仙侠世界", genre="仙侠", targetWords=100000)
    assert r.ok
    assert r.data["id"], "创建成功应返回作品 id"
    assert r.data["title"] == "我的仙侠世界"


def test_get_book_by_id(owner_book):
    c, bid = owner_book
    r = c.get(f"/books/{bid}")
    assert r.ok
    assert r.data["id"] == bid


def test_get_nonexistent_book_404(user):
    """访问不存在的作品，应返回 404（资源不存在）。"""
    r = user.get("/books/999999999")
    assert r.code == 404, f"期望 404, 实际 {r.code}"


def test_update_book(owner_book):
    c, bid = owner_book
    r = c.put(f"/books/{bid}", {"title": "改名后的书", "genre": "玄幻"})
    assert r.ok
    assert r.data["title"] == "改名后的书"


def test_archive_and_unarchive(owner_book):
    c, bid = owner_book
    assert c.put(f"/books/{bid}/archive").ok
    assert c.put(f"/books/{bid}/unarchive").ok


def test_delete_book(owner_book):
    c, bid = owner_book
    assert c.delete(f"/books/{bid}").ok
    # 删除后再次访问应 404
    assert c.get(f"/books/{bid}").code == 404


def test_book_stats(owner_book):
    c, bid = owner_book
    r = c.get(f"/books/{bid}/stats")
    assert r.ok
    assert isinstance(r.data, dict)
