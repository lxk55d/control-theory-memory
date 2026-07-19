#!/usr/bin/env python3
"""
规模压力测试 — 合成大量记忆验证系统行为。

生成 N 条合成记忆文件，运行完整流水线，测量：
1. 遗忘控制器扫描时间 (O(n) 验证)
2. PID 收敛行为 (O(1) 验证)
3. 文件 IO 吞吐
4. 总体流水线耗时

用法：
  python3 scale_test.py --generate 100    # 生成 100 条测试记忆
  python3 scale_test.py --run             # 在当前规模下运行
  python3 scale_test.py --clean           # 清理测试记忆
  python3 scale_test.py --full 50 100 500 # 全流程: 生成 → 测试 → 清理
"""

import json
import os
import re
import sys
import time
import datetime
from pathlib import Path

SCRIPTS_DIR = os.path.expanduser("~/scripts")
MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
sys.path.insert(0, SCRIPTS_DIR)


# ─── 合成记忆生成 ────────────────────────────────────────────────────────

def generate_synthetic(count: int, prefix: str = "perf-test") -> int:
    """生成 N 条合成记忆文件"""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    created = 0
    for i in range(count):
        name = f"{prefix}-{i:06d}"
        # 随机分类主题，使分布更真实
        themes = [
            f"Performance test memory #{i}",
            f"Synthetic data point for scaling analysis ({i})",
            f"Benchmark entry #{i} — system behavior under load",
        ]
        theme = themes[i % len(themes)]
        consolidation = round(0.3 + (i % 5) * 0.1, 2)
        retention = round(0.5 + (i % 10) * 0.05, 2)
        access = (i // 10) % 20

        content = f"""---
name: {name}
description: {theme}
metadata:
  node_type: memory
  type: reference
  created: {now}
  modified: {now}
  access_count: {access}
  last_accessed: {now}
  retention_strength: {retention}
  consolidation_level: {consolidation}
  forget_rate: 0.03
  centrality: 0.15
  last_checked: {now}
---

自动生成的性能测试记忆 #{i}。

主题: {theme}
访问次数: {access}
巩固度: {consolidation}
"""

        fpath = Path(MEMORY_DIR) / f"{name}.md"
        if not fpath.exists():
            fpath.write_text(content, encoding="utf-8")
            created += 1

    total = len([f for f in Path(MEMORY_DIR).glob(f"{prefix}-*.md")])
    print(f"  ✅ 生成 {created} 新 / 共 {total} 条 '{prefix}' 记忆")
    return total


def clean_synthetic(prefix: str = "perf-test") -> int:
    """清理合成记忆"""
    removed = 0
    for f in Path(MEMORY_DIR).glob(f"{prefix}-*.md"):
        f.unlink()
        removed += 1
    print(f"  🗑 清理 {removed} 条合成记忆")
    return removed


# ─── 压力测试 ────────────────────────────────────────────────────────────

def benchmark_forgetting() -> dict:
    """测量遗忘控制器"""
    from forgetting_controller import scan_memories, load_config
    config = load_config()

    # warmup
    scan_memories(config, dry_run=True)

    # timed run
    t0 = time.time()
    stats = scan_memories(config, dry_run=True)
    elapsed = (time.time() - t0) * 1000
    count = stats.get("scanned", 0)

    return {
        "time_ms": round(elapsed, 2),
        "count": count,
        "active": stats.get("active", 0),
        "dormant": stats.get("dormant", 0),
        "critical": stats.get("critical", 0),
    }


def benchmark_pid() -> dict:
    """测量 PID 调参"""
    from forgetting_controller import scan_memories, load_config
    from pid_controller import observe_memory_state, tune_parameters
    config = load_config()
    stats = scan_memories(config, dry_run=True)
    memories = stats.get("memories", [])
    observed = observe_memory_state(memories)

    # warmup
    tune_parameters(observed, config, dry_run=True)

    # timed run
    t0 = time.time()
    new_config, pid_state, log_entry = tune_parameters(observed, config, dry_run=True)
    elapsed = (time.time() - t0) * 1000

    return {
        "time_ms": round(elapsed, 2),
        "memories": observed["total_memories"],
    }


def benchmark_file_io() -> dict:
    """测量文件 I/O"""
    mem_files = [f for f in Path(MEMORY_DIR).glob("*.md") if f.name != "MEMORY.md"]
    count = len(mem_files)

    if count == 0:
        return {"time_ms": 0, "count": 0}

    # 顺序读取
    t0 = time.time()
    for f in mem_files:
        f.read_text()
    read_ms = (time.time() - t0) * 1000

    # 列出目录
    t0 = time.time()
    list(Path(MEMORY_DIR).glob("*.md"))
    ls_ms = (time.time() - t0) * 1000

    return {
        "read_ms": round(read_ms, 2),
        "ls_ms": round(ls_ms, 2),
        "count": count,
    }


def run_full_benchmark() -> dict:
    """运行所有基准测试"""
    print(f"\n{'='*60}")
    print(f"  性能基准测试")
    print(f"{'='*60}")

    io = benchmark_file_io()
    print(f"\n💾 文件 I/O ({io['count']} 文件):")
    print(f"  顺序读取: {io['read_ms']:.2f}ms")
    print(f"  目录列出: {io['ls_ms']:.2f}ms")

    fc = benchmark_forgetting()
    print(f"\n⚙️  遗忘控制器 ({fc['count']} 条):")
    print(f"  耗时:    {fc['time_ms']:.2f}ms")
    print(f"  分布:   {fc['active']}活跃/{fc['dormant']}休眠/{fc['critical']}低价值")

    pid = benchmark_pid()
    print(f"\n🎛 PID 调参 ({pid['memories']} 条):")
    print(f"  耗时: {pid['time_ms']:.2f}ms")

    total = round(io.get("read_ms", 0) + fc["time_ms"] + pid["time_ms"], 2)
    print(f"\n📊 总耗时: {total:.2f}ms")

    return {
        "file_io": io,
        "forgetting_controller": fc,
        "pid": pid,
        "total_ms": total,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


# ─── 规模扫描 ────────────────────────────────────────────────────────────

def scan_sizes(sizes: list[int], prefix: str = "perf-test"):
    """在多个规模下运行测试"""
    print(f"{'='*60}")
    print(f"  规模扫描: {', '.join(str(s) for s in sizes)}")
    print(f"{'='*60}")

    results = []

    for n in sizes:
        print(f"\n--- 规模 {n} 条 ---")
        generate_synthetic(n, prefix=prefix)

        result = run_full_benchmark()
        result["target_size"] = n
        results.append(result)

        clean_synthetic(prefix=prefix)

    # 汇总表
    print(f"\n{'='*60}")
    print(f"  规模扫描汇总")
    print(f"{'='*60}")
    print(f"  {'规模':>6s} | {'文件IO':>8s} | {'遗忘控制':>8s} | {'PID':>6s} | {'总计':>8s} | {'吞吐(条/s)':>10s}")
    print(f"  {'-'*6} | {'-'*8} | {'-'*8} | {'-'*6} | {'-'*8} | {'-'*10}")
    for r in results:
        io = r["file_io"]["read_ms"]
        fc = r["forgetting_controller"]["time_ms"]
        pid = r["pid"]["time_ms"]
        total = r["total_ms"]
        count = r["forgetting_controller"]["count"]
        throughput = count / (total / 1000) if total > 0 else float('inf')
        print(f"  {count:6d} | {io:7.1f}ms | {fc:7.1f}ms | {pid:5.1f}ms | {total:7.1f}ms | {throughput:9.0f}")

    return results


# ─── 主入口 ──────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if "--generate" in args:
        idx = args.index("--generate")
        count = int(args[idx + 1]) if idx + 1 < len(args) else 100
        generate_synthetic(count)
        return

    if "--clean" in args:
        prefix = "perf-test"
        if "--prefix" in args:
            idx = args.index("--prefix")
            prefix = args[idx + 1] if idx + 1 < len(args) else prefix
        clean_synthetic(prefix)
        return

    if "--full" in args:
        idx = args.index("--full")
        sizes = [int(a) for a in args[idx + 1:] if a.isdigit()] or [50, 100, 500]
        scan_sizes(sizes)
        clean_synthetic()
        return

    # 默认：运行一次基准
    run_full_benchmark()


if __name__ == "__main__":
    main()
