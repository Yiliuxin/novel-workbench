"""TC-模块P 性能与并发专项
覆盖：并发生成、并发建书、单次生成时延 P95、中等规模大纲列表时延。
性能是 AI 写作平台上线前必测项（生成类接口耗时长、易在并发下出现 5xx/串号）。
对应测试用例设计文档 TC-P 系列（原规划项，现已落地）。
注意：需后端 + MySQL 运行时执行；无后端时仅做语法/收集校验。
"""
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from client import Client


def _worker_create_and_generate(base_book=False):
    """单个工作线程：注册->登录->(建书)->生成分卷，返回 (ok, elapsed_ms, code)。"""
    c = Client()
    _, username = c.register()
    c.login(username)
    if not base_book:
        book = c.create_book().expect(0).data["id"]
    else:
        book = base_book
    t0 = time.perf_counter()
    r = c.post(f"/books/{book}/outlines/generate-volumes", {"count": 1})
    elapsed = (time.perf_counter() - t0) * 1000
    return r.ok, elapsed, r.code


def test_concurrent_book_creation(user):
    """并发建书：20 个线程各自注册并建书，全部成功（无 5xx / 无重复冲突）。"""
    n = 20
    with ThreadPoolExecutor(max_workers=n) as ex:
        futures = [ex.submit(_worker_create_and_generate) for _ in range(n)]
        results = [f.result() for f in as_completed(futures)]
    ok_flags = [r[0] for r in results]
    assert all(ok_flags), f"并发建书存在失败：{results}"


def test_concurrent_volume_generation(user):
    """并发生成：10 个线程并发触发分卷生成，全部成功且服务不出现 5xx。"""
    n = 10
    with ThreadPoolExecutor(max_workers=n) as ex:
        futures = [ex.submit(_worker_create_and_generate) for _ in range(n)]
        results = [f.result() for f in as_completed(futures)]
    codes = [r[2] for r in results]
    assert all(c == 0 for c in codes), f"并发生成出现非 0 code：{codes}"


def test_single_generate_latency_p95(user):
    """时延 P95（mock 兜底）：单次分卷生成 P95 时延 < 3000ms。"""
    c = user
    book = c.create_book().expect(0).data["id"]
    samples = []
    for _ in range(10):
        t0 = time.perf_counter()
        c.post(f"/books/{book}/outlines/generate-volumes", {"count": 1}).expect(0)
        samples.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(samples, n=20)[18]  # 20 分位近似 P95
    assert p95 < 3000, f"P95 时延 {p95:.0f}ms 超阈值 3000ms"


def test_midscale_outline_list_latency(user):
    """中等规模树列表时延：用确定性 create 接口建 10 卷 + 每卷 3 章（共 40 节点），list < 1000ms。

    注：AI 生成接口在 mock 兜底下每调用仅落 1 个节点，无法保证精确数量；
    本用例改用确定性 create 接口构造精确规模的树，以真实衡量 list 接口时延。
    """
    c = user
    book = c.create_book().expect(0).data["id"]
    vol_ids = []
    for i in range(10):
        v = c.post(f"/books/{book}/outlines",
                   {"nodeType": "VOLUME", "chapterTitle": f"第{i+1}卷", "summary": "x"}).expect(0).data
        vol_ids.append(v["id"])
    for vid in vol_ids:
        for j in range(3):
            c.post(f"/books/{book}/outlines",
                   {"nodeType": "CHAPTER", "chapterTitle": f"章{j+1}", "parentId": vid, "summary": "y"}).expect(0)
    t0 = time.perf_counter()
    r = c.get(f"/books/{book}/outlines").expect(0)
    elapsed = (time.perf_counter() - t0) * 1000
    assert len(r.data) >= 40, f"应至少 40 节点，实际 {len(r.data)}"
    assert elapsed < 1000, f"列表时延 {elapsed:.0f}ms 超阈值 1000ms"
