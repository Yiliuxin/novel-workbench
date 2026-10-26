"""TC-模块S 安全与访问控制（越权/角色矩阵/注入）
覆盖：跨用户越权访问（IDOR）、仅所有者操作、只读角色禁止写入、协作加入链路、
      以及特殊字符/注入输入不引发服务端异常。
对应测试用例设计文档 TC-S 系列（安全专项）。
"""
import pytest


def test_cross_user_read_forbidden(two_users):
    """IDOR 基础：B 用户读取 A 用户的私有作品应被拒绝（403）。"""
    owner, attacker, bid = two_users
    r = attacker.get(f"/books/{bid}")
    assert r.code == 403, f"越权读应 403, 实际 {r.code}"


def test_cross_user_delete_forbidden(two_users):
    """仅所有者可删书：非所有者删除他人作品应 403。"""
    owner, attacker, bid = two_users
    r = attacker.delete(f"/books/{bid}")
    assert r.code == 403, f"越权删应 403, 实际 {r.code}"


def test_non_member_write_forbidden(two_users):
    """非成员在他人作品下写入大纲应 403（写权限门槛）。"""
    owner, attacker, bid = two_users
    r = attacker.post(f"/books/{bid}/outlines",
                      {"nodeType": "CHAPTER", "chapterTitle": "x", "summary": "y"})
    assert r.code == 403, f"非成员写应 403, 实际 {r.code}"


def test_collaboration_join_then_write(two_users):
    """正向协作链路：owner 取邀请码 → attacker 加入 → attacker 获得写权限。
    验证多租户隔离在「被授权后」正确放开。"""
    owner, attacker, bid = two_users
    code = owner.get(f"/books/{bid}/invite-code").expect(0).data["inviteCode"]
    join = attacker.post("/books/join", {"inviteCode": code})
    assert join.ok, f"加入应成功: {join.message}"

    # 加入后 attacker 应能读取该书
    assert attacker.get(f"/books/{bid}").ok
    # 加入后 attacker（EDITOR）应能写入大纲
    w = attacker.post(f"/books/{bid}/outlines",
                      {"nodeType": "CHAPTER", "chapterTitle": "合作章节", "summary": "梗概"})
    assert w.ok, f"协作成员写应成功: {w.message}"


def test_viewer_role_read_only(two_users):
    """角色矩阵：把协作者降为 VIEWER 后，读成功、写被拒（403）。"""
    owner, attacker, bid = two_users
    code = owner.get(f"/books/{bid}/invite-code").expect(0).data["inviteCode"]
    attacker.post("/books/join", {"inviteCode": code}).expect(0)

    # 找到 attacker 的成员 id 并改为 VIEWER
    members = owner.get(f"/books/{bid}/members").expect(0).data
    member = next(m for m in members if m["userId"] != (owner.get("/auth/me").data["id"] if False else None))
    # 用 inviteCode 加入者即 attacker；按 userId 过滤更稳：
    # 简化：取第一个非 owner 的成员
    target = next((m for m in members if m.get("role") == "EDITOR"), members[0])
    owner.put(f"/books/{bid}/members/{target['id']}/role", {"role": "VIEWER"}).expect(0)

    # VIEWER 可读取
    assert attacker.get(f"/books/{bid}").ok
    # VIEWER 不可写入（只读角色）
    w = attacker.post(f"/books/{bid}/outlines",
                      {"nodeType": "CHAPTER", "chapterTitle": "越权写", "summary": "x"})
    assert w.code == 403, f"VIEWER 写应 403, 实际 {w.code}"


def test_non_owner_change_role_forbidden(two_users):
    """越权管理：非 owner 修改成员角色应 403。"""
    owner, attacker, bid = two_users
    code = owner.get(f"/books/{bid}/invite-code").expect(0).data["inviteCode"]
    attacker.post("/books/join", {"inviteCode": code}).expect(0)
    members = owner.get(f"/books/{bid}/members").expect(0).data
    target = next((m for m in members if m.get("role") == "EDITOR"), members[0])
    # attacker 不是 owner，尝试改角色
    r = attacker.put(f"/books/{bid}/members/{target['id']}/role", {"role": "VIEWER"})
    assert r.code == 403, f"非 owner 改角色应 403, 实际 {r.code}"


@pytest.mark.parametrize("evil", [
    "<script>alert(1)</script>",          # 存储型 XSS 探针
    "'; DROP TABLE book; --",             # SQL 注入探针
    "../../etc/passwd",                   # 路径遍历探针
    "书名\u0000null",                      # 空字节探针
])
def test_special_char_title_not_crash(user, evil):
    """健壮性/安全：书名含特殊字符不应导致服务端 5xx，且应原样保存（转义由前端负责）。"""
    r = user.create_book(title=evil, genre="玄幻")
    assert r.status != 500, f"特殊字符导致服务端异常: {r.message}"
    if r.ok:
        got = user.get(f"/books/{r.data['id']}").data["title"]
        assert got == evil, "特殊字符应原样回显，不应被截断/转义在服务端"
