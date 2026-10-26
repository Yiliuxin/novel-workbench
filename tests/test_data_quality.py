"""TC-模块D 数据质量专项
覆盖：大纲树结构完整性、卷号连续性、多语言/Emoji 字符编码保真、生成数量边界值。
数据质量是 AI 写作平台易翻车点（乱码、树断裂、越界生成）。
对应测试用例设计文档 TC-D 系列。
"""
import pytest


def test_outline_tree_integrity(user):
    """树完整性：每个 CHAPTER 的 parentId 要么为空（顶级），要么指向一个存在的 VOLUME。"""
    c = user
    book = c.create_book().expect(0).data["id"]
    c.post(f"/books/{book}/outlines/generate-volumes", {"count": 2}).expect(0)
    vols = c.get(f"/books/{book}/outlines").expect(0).data
    vol_ids = {n["id"] for n in vols if n["nodeType"] == "VOLUME"}
    for v in vols:
        if v["nodeType"] == "VOLUME":
            assert v["parentId"] in (None, 0), "卷应为顶级节点"
        if v["nodeType"] == "CHAPTER" and v.get("parentId"):
            assert v["parentId"] in vol_ids, "章节 parentId 必须指向存在的卷"


def test_chinese_and_emoji_preserved(user):
    """字符编码保真：中文 + Emoji 标题建大纲后能原样回显，无乱码/截断。"""
    c = user
    book = c.create_book().expect(0).data["id"]
    title = "序章·觉醒🔥【特别篇】"
    c.post(f"/books/{book}/outlines",
           {"nodeType": "CHAPTER", "chapterTitle": title, "summary": "测试编码"}).expect(0)
    nodes = c.get(f"/books/{book}/outlines").expect(0).data
    titles = [n["chapterTitle"] for n in nodes]
    assert title in titles, "中文/Emoji 应原样保存"


@pytest.mark.parametrize("count", [0, 1, 5, 100, -5])
def test_generate_volume_count_boundary(user, count):
    """边界值分析：生成分卷数量被服务端钳制在 [1,10]——任何输入都不应 5xx，且不超过上限。

    说明：后端对 count 做 Math.max(1, Math.min(10, count)) 钳制，故 0/负值/超大值
    均被收敛到 [1,10] 并成功返回，而非拒绝。本用例验证该钳制与下限/上限不变式。
    """
    c = user
    book = c.create_book().expect(0).data["id"]
    r = c.post(f"/books/{book}/outlines/generate-volumes", {"count": count})
    assert r.status != 500, f"count={count} 不应导致 5xx"
    assert r.ok, f"count={count} 应成功（服务端钳制），实际 {r.code}:{r.message}"
    n = r.data["count"]
    assert 1 <= n <= 10, f"分卷数应被钳制在 [1,10]，实际 {n}"


def test_generate_on_empty_book(user):
    """健壮性：空书（无任何章节/角色）直接生成分卷，不应崩溃且返回可用结构。"""
    c = user
    book = c.create_book().expect(0).data["id"]
    r = c.post(f"/books/{book}/outlines/generate-volumes", {"count": 2})
    assert r.status != 500
    if r.ok:
        assert isinstance(r.data["items"], list)
