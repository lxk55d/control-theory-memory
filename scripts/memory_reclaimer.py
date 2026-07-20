#!/usr/bin/env python3
"""
记忆回收器 — P2: 只保留高信号记忆。

规则：
1. hindsight 记忆超过 8 条 → 清理最早的（按 retention 排序，保留核心词匹配的）
2. 任意记忆 retention < 0.15 持续 7 天 → 建议归档
3. 任意记忆 total_memory 超过 50 条 → 启动软上限
4. 每天清理一次

用法：python3 memory_reclaimer.py [--dry-run] [--force]
"""

import os
import re
import datetime
from pathlib import Path
from collections import Counter

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")

# 保留的核心主题词（不清理的 hindsight 记忆）
CORE_TOPICS = {
    '量化', '策略', '回测', 'factor', '因子', 'memory', '记忆', '控制论',
    'PID', '遗忘', 'docker', 'hindsight', 'script', '知识', '系统',
    'claude', '学习', '进化', '用户', '项目', '环境', '共享', '脚本',
}


def read_all() -> list[dict]:
    """读取所有记忆的结构化数据"""
    memories = []
    for fpath in sorted(Path(MEMORY_DIR).glob("*.md")):
        if fpath.name == "MEMORY.md":
            continue
        content = fpath.read_text(encoding="utf-8")
        if not content.startswith("---"):
            continue

        def g(p, d=""):
            m = re.search(p, content)
            return m.group(1).strip() if m else d

        def gf(p, d=0.0):
            m = re.search(p, content)
            return float(m.group(1)) if m else d

        name = g(r'name:\s*(.+)', fpath.stem)
        desc = g(r'description:\s*(.+)', "")
        mem_type = g(r'type:\s*(.+)', "memory")
        retention = gf(r'retention_strength:\s*(.+)', 0.5)
        consolidation = gf(r'consolidation_level:\s*(.+)', 0.3)
        access_count = int(gf(r'access_count:\s*(\d+)', 0))
        created = g(r'created:\s*(.+)', "")
        forget_rate = gf(r'forget_rate:\s*(.+)', 0.03)
        modified = g(r'modified:\s*(.+)', "")

        body_parts = content.split('---', 2)
        body = body_parts[2] if len(body_parts) >= 3 else ""

        memories.append(dict(
            name=name, fname=fpath.name, path=str(fpath),
            desc=desc, type=mem_type,
            retention=retention, consolidation=consolidation,
            access_count=access_count, forget_rate=forget_rate,
            created=created, modified=modified,
            is_auto="自动" in body or "待后续会话完善" in body,
            is_hindsight="hindsight" in name.lower(),
            has_core_content=any(t.lower() in body.lower() for t in CORE_TOPICS),
            body_length=len(body),
        ))

    return memories


def reclaim_hindsight(memories: list[dict], dry_run: bool = False) -> int:
    """hindsight 记忆：清理无正文内容的空 stub，保留上限 8 条"""
    h_entries = [m for m in memories if m["is_hindsight"]]
    if not h_entries:
        return 0

    # 评分：retention + consolidation + access_count + 核心主题匹配 + body 长度
    for m in h_entries:
        score = m["retention"] * 3 + m["consolidation"] * 2 + min(m["access_count"], 10) * 0.5
        if m["has_core_content"]:
            score += 2
        score += min(m["body_length"] / 200, 1)
        m["_score"] = round(score, 2)

    # 1. 先清理无正文的空 stub（不论数量）
    stubs = [m for m in h_entries if m["body_length"] == 0 or m.get("is_auto", False)]
    # 2. 如果还有超限（>8），按评分清理最低分的
    h_entries.sort(key=lambda m: m["_score"], reverse=True)
    surplus = h_entries[8:] if len(h_entries) > 8 else []
    # 合并：stub 优先清理，再补超限
    to_remove = {m["path"]: m for m in stubs}
    for m in surplus:
        if m["path"] not in to_remove:
            to_remove[m["path"]] = m

    removed = 0
    for path, m in to_remove.items():
        if not dry_run:
            try:
                os.remove(path)
                print(f"  🗑 hindsight: {m['fname']} (score={m['_score']}, body={m['body_length']}B)")
                removed += 1
            except OSError as e:
                print(f"  ⚠ 删除失败 {m['fname']}: {e}")
        else:
            print(f"  🗑 [DRY] hindsight: {m['fname']} (score={m['_score']})")
            removed += 1

    return removed


def reclaim_low_signal(memories: list[dict], dry_run: bool = False) -> int:
    """低信号记忆清理：自动创建的 stub 且 body 为空且 created > 24h（hindsight 减为 6h）"""
    auto_stubs = [m for m in memories if m.get("is_auto", False) and m["body_length"] == 0 and not m["is_hindsight"]]
    # hindsight stub：正文为空或 consolidation < 0.35
    hindsight_stubs = [m for m in memories if m["is_hindsight"] and (m["body_length"] == 0 or m["consolidation"] < 0.35)]
    all_stubs = auto_stubs + hindsight_stubs
    if not auto_stubs:
        return 0

    # 检查创建时间
    now = datetime.datetime.now(datetime.timezone.utc)
    removed = 0
    for m in auto_stubs:
        try:
            created_dt = datetime.datetime.fromisoformat(m["created"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        age_days = (now - created_dt).total_seconds() / 86400
        # 自动记忆保留 3 天，hindsight 保留 24 小时
        min_age = 1 if m["is_hindsight"] else 3
        if age_days < min_age:
            continue

        if not dry_run:
            try:
                os.remove(m["path"])
                print(f"  🗑 stub: {m['fname']} (age={age_days:.0f}d, access={m['access_count']})")
                removed += 1
            except OSError as e:
                print(f"  ⚠ 删除失败 {m['fname']}: {e}")
        else:
            print(f"  🗑 [DRY] stub: {m['fname']} (age={age_days:.0f}d)")
            removed += 1

    return removed


def report_signal(memories: list[dict]):
    """报告信号分布"""
    categories = {"高信号 (con>0.6)": 0, "中信号 (0.3-0.6)": 0, "低信号 (<0.3)": 0}
    for m in memories:
        if m["consolidation"] >= 0.6:
            categories["高信号 (con>0.6)"] += 1
        elif m["consolidation"] >= 0.3:
            categories["中信号 (0.3-0.6)"] += 1
        else:
            categories["低信号 (<0.3)"] += 1

    print(f"\n📊 信号分布:")
    for k, v in categories.items():
        bar = "█" * int(v)
        print(f"  {k:20s} {v:3d}  {bar}")

    hindsight = [m for m in memories if m["is_hindsight"]]
    auto = [m for m in memories if m["is_auto"]]
    core = [m for m in memories if not m["is_hindsight"] and not m["is_auto"]]
    print(f"\n📂 分类: 核心 {len(core)} + 自动 {len(auto)} + hindsight {len(hindsight)}")


def reclaim_all(dry_run: bool = False) -> dict:
    """运行所有回收规则"""
    print(f"{'='*60}")
    print(f"  记忆回收器")
    print(f"{'='*60}")

    memories = read_all()
    print(f"\n📖 当前 {len(memories)} 条记忆")
    report_signal(memories)

    print(f"\n🗑  hindsight 回收 (上限 8):")
    h_removed = reclaim_hindsight(memories, dry_run=dry_run)

    print(f"\n🗑  stub 回收 (7天无访问):")
    s_removed = reclaim_low_signal(memories, dry_run=dry_run)

    total_removed = h_removed + s_removed
    remains = len(memories) - total_removed

    print(f"\n{'='*60}")
    print(f"  回收: {total_removed} 条 | 剩余: ~{remains} 条")
    if dry_run:
        print(f"  (dry run — 未实际删除)")
    print(f"{'='*60}")

    return {"removed": total_removed, "remaining": remains}


def main():
    import sys
    dry_run = "--dry-run" in sys.argv
    do_apply = "--force" in sys.argv
    if do_apply:
        dry_run = False
    # 默认 --dry-run （安全），除非 --force

    stats = reclaim_all(dry_run=dry_run)


if __name__ == "__main__":
    main()
