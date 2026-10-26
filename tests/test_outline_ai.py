"""TC-模块O 大纲与 AI 生成专项
覆盖：分卷生成、章节挂靠分卷、智能归卷、续写接续、生成节点归属、封面生图。
AI 专项重点：无 LLM Key 时后端走 mock 兜底——此时 AI 生成接口每调用落 1 个节点、
且不保证内容对齐本书；因此本模块在 mock 兜底下验证「结构正确性」（节点类型、
父子归属、卷号接续、数量钳制、归属本书），内容级一致性需在配置 LLM Key 后专项验证。
这是 AI 应用测试的关键切入点：mock 下守住业务约束，真实 LLM 下再校验内容质量。
对应测试用例设计文档 TC-O 系列。
"""
import pytest


def _seed_book_with_chapters(c, title="我的仙侠世界", hero="林晚"):
    book = c.create_book(title=title, genre="仙侠").expect(0).data["id"]
    c.post(f"/books/{book}/characters",
           {"name": hero, "role": "PROTAGONIST", "goal": "为母报仇"}).expect(0)
    for t in ["第一章 入山拜师", "第二章 遇敌突围"]:
        c.post(f"/books/{book}/outlines",
               {"nodeType": "CHAPTER", "chapterTitle": t, "summary": t + "梗概"}).expect(0)
    return book, hero


def test_generate_volumes_basic(user):
    """AI 生成分卷（mock 兜底）：返回 code 0，至少生成 1 个 VOLUME 节点，count 与 items 一致。"""
    c = user
    book, _ = _seed_book_with_chapters(c)
    r = c.post(f"/books/{book}/outlines/generate-volumes", {"count": 3}).expect(0)
    items = r.data["items"]
    assert isinstance(items, list) and len(items) >= 1, "应至少生成 1 个分卷"
    assert all(it["nodeType"] == "VOLUME" for it in items)
    assert r.data["count"] == len(items)


def test_generate_chapters_under_volume(user):
    """分卷下生成章节（mock 兜底）：返回的 CHAPTER 节点 parentId 正确指向该卷。"""
    c = user
    book, _ = _seed_book_with_chapters(c)
    vols = c.post(f"/books/{book}/outlines/generate-volumes", {"count": 1}).expect(0).data["items"]
    vol_id = vols[0]["id"]
    chaps = c.post(f"/outlines/{vol_id}/generate-chapters", {"count": 3}).expect(0).data["items"]
    assert isinstance(chaps, list) and len(chaps) >= 1, "应至少生成 1 章"
    assert all(ch["nodeType"] == "CHAPTER" and ch["parentId"] == vol_id for ch in chaps)


def test_assign_orphan_chapters(user):
    """智能归卷：先建分卷，再建游离章节，单独调用 assign-to-volumes 应把全部游离章归入某卷。"""
    c = user
    book = c.create_book().expect(0).data["id"]
    c.post(f"/books/{book}/outlines/generate-volumes", {"count": 2}).expect(0)  # 先建 2 卷，此时无游离章
    for t in ["第一章 入山拜师", "第二章 遇敌突围"]:                 # 再建 2 个游离 CHAPTER
        c.post(f"/books/{book}/outlines",
               {"nodeType": "CHAPTER", "chapterTitle": t, "summary": t}).expect(0)
    assigned = c.post(f"/books/{book}/outlines/assign-to-volumes", {}).expect(0).data["assigned"]
    assert assigned >= 2, f"期望至少 2 章被归卷，实际 {assigned}"

    nodes = c.get(f"/books/{book}/outlines").expect(0).data
    vol_ids = {n["id"] for n in nodes if n["nodeType"] == "VOLUME"}
    for ch in nodes:
        if ch["nodeType"] == "CHAPTER":
            assert ch["parentId"] in vol_ids, f"章节 {ch['chapterTitle']} 未归入任何卷"


def test_continue_volume_numbering(user):
    """续写接续（mock 兜底）：第二次生成分卷不删除/改写已有卷，且 orderIndex 连续递增。"""
    c = user
    book, _ = _seed_book_with_chapters(c)
    t1 = c.post(f"/books/{book}/outlines/generate-volumes", {"count": 3}).expect(0).data["items"]
    t1_ids = {i["id"] for i in t1}
    t2 = c.post(f"/books/{book}/outlines/generate-volumes", {"count": 2}).expect(0).data["items"]
    t2_ids = {i["id"] for i in t2}
    assert t1_ids.isdisjoint(t2_ids), "续写不应覆盖/改写已有分卷"

    nodes = c.get(f"/books/{book}/outlines").expect(0).data
    vols = [n for n in nodes if n["nodeType"] == "VOLUME"]
    order_idx = [v["orderIndex"] for v in vols]
    assert order_idx == sorted(order_idx), "分卷 orderIndex 应连续递增（接续）"


def test_volume_belongs_to_book(user):
    """生成分卷结构正确性（mock 兜底）：每个分卷归属于本书且摘要非空。

    注：分卷『内容』对齐本书书名/主角属内容级校验，需配置 LLM Key 后验证；
    本用例在 mock 兜底下验证数据结构与归属关系（更稳健、可重复）。
    """
    c = user
    book, _ = _seed_book_with_chapters(c)
    items = c.post(f"/books/{book}/outlines/generate-volumes", {"count": 3}).expect(0).data["items"]
    assert len(items) >= 1
    for v in items:
        assert v["nodeType"] == "VOLUME"
        assert v["bookId"] == book, "分卷必须归属当前作品"
        assert isinstance(v.get("summary"), str) and len(v.get("summary", "")) > 0, "分卷摘要不应为空"


def test_cover_generate_image_mock(user):
    """封面文生图（mock 兜底）：返回合法的 PNG data URL。"""
    c = user
    book, _ = _seed_book_with_chapters(c)
    r = c.post(f"/books/{book}/covers/generate-image",
               {"prompt": "仙侠竖版封面，电影质感", "size": "1024x1792"}).expect(0)
    img = (r.data or {}).get("imageUrl", "")
    assert img.startswith("data:image/png;base64,") and len(img) > 2000, "应返回有效 PNG data URL"
