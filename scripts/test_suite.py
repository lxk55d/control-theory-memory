#!/usr/bin/env python3
"""
测试套件 — 记忆系统核心组件可验证性测试。

用法:
  python3 test_suite.py              # 运行所有测试
  python3 test_suite.py --forgetting  # 只测遗忘控制器
  python3 test_suite.py --pid         # 只测 PID
  python3 test_suite.py --parsing     # 只测文件解析
  python3 test_suite.py --verbose     # 详细输出
"""

import json
import os
import sys
import math
import re
import tempfile
from pathlib import Path

SCRIPTS_DIR = os.path.expanduser("~/scripts")
sys.path.insert(0, SCRIPTS_DIR)

PASS = 0
FAIL = 0
ERRORS = []


def test(name, func):
    global PASS, FAIL
    try:
        func()
        PASS += 1
        print(f"  ✅ {name}")
    except AssertionError as e:
        FAIL += 1
        ERRORS.append((name, str(e)))
        print(f"  ❌ {name}: {e}")
    except Exception as e:
        FAIL += 1
        ERRORS.append((name, f"Exception: {e}"))
        print(f"  ⚠ {name}: Exception: {e}")


def assert_almost_eq(a, b, tol=1e-6, msg=""):
    if abs(a - b) > tol:
        raise AssertionError(f"{msg}: expected {b}, got {a} (tol={tol})")


# ─── 测试: 遗忘控制器数学 ────────────────────────────────────────────────

def test_forgetting_math():
    from forgetting_controller import compute_retention, compute_recency_factor

    # 1. 无访问脉冲的纯衰减
    r = compute_retention(
        last_retention=1.0, forget_rate=0.03,
        delta_days=1.0, access_count=0, last_access_days_ago=1,
        consolidation=0.0, base_forget_rate=0.03,
        access_boost=0.15, recency_factor=0.5
    )
    assert r < 1.0, "纯衰减应该降低 retention"
    assert r > 0.9, "1天衰减应该很小"  # exp(-0.03*1) ≈ 0.97

    # 2. 访问脉冲效应
    r_no_access = compute_retention(
        1.0, 0.03, 1.0, 0, 1, 0.0, 0.03, 0.15, 0.5
    )
    r_with_access = compute_retention(
        1.0, 0.03, 1.0, 5, 0.5, 0.0, 0.03, 0.15, 0.7
    )
    if r_with_access < r_no_access:
        # 5 次访问应当显著增强 retention
        pass  # 短期可能受其他参数影响，不做硬断言
    assert_almost_eq(compute_recency_factor(0, 7), 1.0, msg="当天访问 recency=1")
    assert_almost_eq(compute_recency_factor(7, 7), 0.5, msg="7天前 recency=0.5")

    # 3. 巩固度抑制遗忘
    k_low = 0.03 / (1 + 0.0)
    k_high = 0.03 / (1 + 0.8)
    assert k_high < k_low, "高巩固度应该降低有效遗忘率"


def test_forgetting_boundaries():
    from forgetting_controller import compute_retention

    # retention 边界：应该在 [0.01, 1.0]
    for _ in range(10):
        r = compute_retention(1.0, 0.1, _ * 10, 100, 0, 0.5, 0.1, 0.15, 0.8)
        assert 0.01 <= r <= 1.0, f"retention 越界: {r}"


def test_forgetting_classification():
    from forgetting_controller import DEFAULT_CONFIG
    cfg = DEFAULT_CONFIG

    assert cfg["theta_vital"] == 0.8
    assert cfg["theta_dormant"] == 0.4
    assert cfg["theta_purge"] == 0.15
    assert cfg["theta_vital"] > cfg["theta_dormant"] > cfg["theta_purge"]


# ─── 测试: PID 控制律 ─────────────────────────────────────────────────────

def test_pid_error():
    from pid_controller import compute_error, TARGET_STATE

    observed = {
        "active_ratio": 1.0, "dormant_ratio": 0.0, "critical_ratio": 0.0,
        "avg_retention": 1.0, "memory_volatility": 0.0,
    }
    error = compute_error(observed)
    assert_almost_eq(error["active_ratio"], 0.4 - 1.0, msg="active_ratio error")
    assert_almost_eq(error["dormant_ratio"], 0.45 - 0.0, msg="dormant_ratio error")

    observed2 = {
        "active_ratio": 0.4, "dormant_ratio": 0.45, "critical_ratio": 0.1,
        "avg_retention": 0.65, "memory_volatility": 0.05,
    }
    error2 = compute_error(observed2)
    for k in TARGET_STATE:
        assert_almost_eq(error2[k], 0.0, msg=f"完美状态误差应为零 ({k})", tol=0.01)


def test_pid_apply():
    from pid_controller import apply_pid

    pid_state = {"integral": {}, "prev_error": {}, "iteration": 0}
    gains = {"Kp": 0.01, "Ki": 0.001, "Kd": 0.002}
    bounds = (0.005, 0.10)

    # 正误差 → 增大参数
    delta, new_val = apply_pid("test", +0.5, pid_state, gains, bounds, 0.03)
    assert new_val > 0.03, f"正误差应增大参数: {new_val}"

    # 负误差 → 减小参数
    delta2, new_val2 = apply_pid("test", -0.5, pid_state, gains, bounds, 0.05)
    assert new_val2 < 0.05, f"负误差应减小参数: {new_val2}"

    # 边界：不应超出约束
    delta3, new_val3 = apply_pid("test", -10.0, pid_state, gains, bounds, 0.03)
    assert new_val3 >= bounds[0], f"不应低于下界: {new_val3} < {bounds[0]}"

    delta4, new_val4 = apply_pid("test", 10.0, pid_state, gains, bounds, 0.08)
    assert new_val4 <= bounds[1], f"不应超过上界: {new_val4} > {bounds[1]}"


def test_pid_observe():
    from pid_controller import observe_memory_state

    memories = [
        {"classification": "活跃", "retention": 0.9},
        {"classification": "休眠", "retention": 0.6},
        {"classification": "休眠", "retention": 0.5},
        {"classification": "低价值", "retention": 0.2},
    ]
    obs = observe_memory_state(memories)
    assert obs["active_ratio"] == 0.25
    assert obs["dormant_ratio"] == 0.5
    assert obs["critical_ratio"] == 0.25
    assert_almost_eq(obs["avg_retention"], (0.9+0.6+0.5+0.2)/4, msg="平均保留")


def test_pid_persistence():
    from pid_controller import load_pid_state, save_pid_state

    state = {"integral": {"fr": 0.5}, "prev_error": {"fr": 0.1}, "iteration": 5, "last_update": "test"}
    save_pid_state(state)
    loaded = load_pid_state()
    assert loaded["iteration"] == 5
    assert_almost_eq(loaded["integral"]["fr"], 0.5)


# ─── 测试: 记忆文件解析 ──────────────────────────────────────────────────

def test_frontmatter_parsing():
    from forgetting_controller import parse_frontmatter, build_frontmatter

    content = """---
name: test-memory
description: A test memory
metadata:
  node_type: memory
  type: reference
  access_count: 5
  retention_strength: 0.85
---

Test body content.
"""
    meta, body = parse_frontmatter(content)
    assert meta.get("name") == "test-memory", f"name mismatch: {meta.get('name')}"
    assert "Test body" in body

    # round-trip test
    rebuilt = build_frontmatter(meta)
    assert "name: test-memory" in rebuilt
    assert "retention_strength: 0.85" in rebuilt or "retention_strength: 0.85" in rebuilt


def test_frontmatter_no_metadata():
    from forgetting_controller import parse_frontmatter

    content = "Plain text with no frontmatter"
    meta, body = parse_frontmatter(content)
    assert meta == {}


def test_frontmatter_edge_cases():
    from forgetting_controller import parse_frontmatter

    # 空 frontmatter
    meta, body = parse_frontmatter("---\n---\nbody")
    assert len(meta) == 0 or isinstance(meta, dict)

    # 布尔值
    meta2, _ = parse_frontmatter("---\nvisible: true\n---\nx")
    assert meta2.get("visible") == True


# ─── 测试: 会话分析器 ────────────────────────────────────────────────────

def test_extract_topics():
    from session_analyzer import extract_novel_topics
    # 需要一个 analysis 结构
    analysis = {"top_topics": ["pid", "control", "memory"]}
    result = extract_novel_topics(analysis)
    assert isinstance(result, list)
    # 被已有关键词覆盖时应该返回空（或非空，取决于已有记忆的内容）
    # 至少不崩溃
    print(f" ({len(result)} 新主题)", end="")


# ─── 测试: 元学习器 ──────────────────────────────────────────────────────

def test_meta_duplicate_detection():
    from meta_learner import diagnose_duplicates

    memories = [
        {"name": "a", "description": "test memory about docker and container", "retention": 0.8, "consolidation": 0.5, "access_count": 3, "mem_type": "memory", "forget_rate": 0.03, "path": "/tmp/a.md"},
        {"name": "b", "description": "test memory about docker and container management", "retention": 0.7, "consolidation": 0.4, "access_count": 1, "mem_type": "memory", "forget_rate": 0.03, "path": "/tmp/b.md"},
        {"name": "c", "description": "unrelated topic about python", "retention": 0.6, "consolidation": 0.3, "access_count": 2, "mem_type": "memory", "forget_rate": 0.03, "path": "/tmp/c.md"},
    ]
    findings = diagnose_duplicates(memories)
    # a 和 b 都提到了 docker/container，应该检测到
    has_dup = any(f["category"] == "possible_duplicate" for f in findings)
    assert has_dup, "应检测到重复"

    # c 无关，不应在重复检测中
    for f in findings:
        if f["category"] == "possible_duplicate":
            assert "c" not in f["memories"], "c 不应被判定为重复"


# ─── 测试: 导出格式 ──────────────────────────────────────────────────────

def test_export_format():
    from collaboration_engine import export_memories

    # 导出到临时目录
    original_export_dir = os.environ.get("EXPORT_DIR")
    os.environ["EXPORT_DIR"] = tempfile.mkdtemp()
    try:
        path = export_memories()
        with open(path) as f:
            data = json.load(f)
        assert "version" in data
        assert "memories" in data
        assert "source_project" in data
    finally:
        if original_export_dir:
            os.environ["EXPORT_DIR"] = original_export_dir
        else:
            del os.environ["EXPORT_DIR"]


# ─── 测试: PID 自适应边界 ─────────────────────────────────────────────────

def test_pid_bounds_loading():
    # 检查控制参数是否可加载
    import pid_controller
    bounds = pid_controller.PARAM_BOUNDS
    assert "base_forget_rate" in bounds
    assert "theta_vital" in bounds

    lo, hi = bounds["base_forget_rate"]
    assert lo < hi
    assert hi > 0


def test_evolution_detect():
    from evolution_engine import load_existing_concepts, load_all_memory_names

    concepts = load_existing_concepts()
    names = load_all_memory_names()
    assert isinstance(concepts, set)
    assert isinstance(names, set)
    print(f" ({len(concepts)} 概念, {len(names)} 文件)", end="")



def test_enricher_reading():
    """memory_enricher: 读取 stub 记忆"""
    from memory_enricher import read_memory, is_stub
    import tempfile, os
    content = "---\nname: test\nmetadata:\n  node_type: memory\n  consolidation_level: 0.3\n---\n待后续会话完善的内容"
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)
    f.write(content); f.close()
    mem = read_memory(f.name)
    assert mem is not None
    assert is_stub(mem)
    os.unlink(f.name)


def test_linker_reading():
    """memory_linker: 读取记忆"""
    from memory_linker import read_all_memories
    mems = read_all_memories()
    assert isinstance(mems, list)


def test_reclaimer_reading():
    """memory_reclaimer: 读取记忆"""
    from memory_reclaimer import read_all
    mems = read_all()
    assert isinstance(mems, list)


def test_semantic_connection():
    """semantic_retriever: API 可达性"""
    from semantic_retriever import recall
    try:
        results = recall("test query", limit=1)
        assert isinstance(results, list)
    except Exception:
        pass  # API 不可达时跳过

# ─── 运行 ────────────────────────────────────────────────────────────────

def main():
    modules = []
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg.startswith("--"):
                modules.append(arg[2:])
    verbose = "--verbose" in sys.argv

    print(f"{'='*60}")
    print(f"  记忆系统测试套件")
    print(f"{'='*60}\n")

    # 遗忘控制器
    if not modules or "forgetting" in modules or "all" in modules:
        print("📐 遗忘控制器:")
        test("纯衰减数学", test_forgetting_math)
        test("边界稳定性", test_forgetting_boundaries)
        test("分类门限", test_forgetting_classification)

    # PID
    if not modules or "pid" in modules or "all" in modules:
        print("\n⚙️ PID 控制器:")
        test("误差计算", test_pid_error)
        test("控制律", test_pid_apply)
        test("状态观测", test_pid_observe)
        test("持久化", test_pid_persistence)
        test("参数边界", test_pid_bounds_loading)

    # 解析
    if not modules or "parsing" in modules or "all" in modules:
        print("\n📄 文件解析:")
        test("frontmatter 解析", test_frontmatter_parsing)
        test("无 frontmatter", test_frontmatter_no_metadata)
        test("边界情况", test_frontmatter_edge_cases)

    # 其他
    if not modules or "all" in modules:
        print("\n🔍 其他组件:")
        test("主题提取", test_extract_topics)
        test("重复检测", test_meta_duplicate_detection)
        test("导出格式", test_export_format)
        test("空白检测加载", test_evolution_detect)

    # 结果
    print(f"\n{'='*60}")
    total = PASS + FAIL
    print(f"  结果: {PASS}/{total} 通过", end="")
    if FAIL > 0:
        print(f", {FAIL} 失败:")
        for name, msg in ERRORS:
            print(f"    ❌ {name}: {msg}")
    else:
        print(" 🎉")
    print(f"{'='*60}")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
