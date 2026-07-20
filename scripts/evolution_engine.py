#!/usr/bin/env python3
"""
进化层：知识空白检测器

检测系统"不知道什么":
1. 高频话题无对应记忆文件 → 缺失知识
2. 用户反复询问但未建立记忆 → 应知未知
3. 对话中隐含结构断裂 → 孤立知识簇
4. 记忆类型分布失衡 → 知识种类偏科

用法: python3 evolution_engine.py --detect
"""

import json
import os
import re
import datetime
from pathlib import Path
from collections import Counter

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
PROJECT_DIR = os.path.expanduser("~/.claude/projects/-home-lxk")
GAPS_LOG = os.path.join(MEMORY_DIR, "knowledge_gaps.jsonl")

STOP_WORDS = {
    'the','and','for','are','was','but','not','you','can','has','had','get','etc',
    'use','this','that','with','from','have','been','what','when','where','which',
    'their','them','node','json','html','http','file','home','bash','all','d','c',
    'v','w','x','y','z','http','https','api','src','bin','org','url','div','span',
    'key','val','int','str','def','class','true','false','none','self','return',
    'import','from','elif','else','if','for','in','not','and','or','is','are',
    'was','were','been','being','have','has','had','do','does','did','will',
    'would','could','should','may','might','shall','can','need','must','let',
    'var','const','new','function','async','await','export','module','require',
    'cd','ls','rm','mv','cp','mkdir','rmdir','chmod','chown','grep','echo',
    'cat','head','tail','less','more','sort','uniq','wc','find','du','df',
}


# ─── 1. 读取已有记忆概念 ───────────────────────────────────────────────────

def load_existing_concepts() -> set:
    """从记忆文件中提取所有已有概念"""
    concepts = set()
    for fpath in Path(MEMORY_DIR).glob("*.md"):
        if fpath.name == "MEMORY.md":
            continue
        content = fpath.read_text(encoding="utf-8")
        nm = re.search(r'name:\s*(.+)', content)
        if nm:
            concepts.add(nm.group(1).strip().lower())

        parts = content.split("---", 2)
        body = parts[2] if len(parts) >= 3 else ""
        for w in re.findall(r'[一-鿿]{3,6}|[a-zA-Z][a-zA-Z0-9_\-.]{3,}', body.lower()):
            if w not in STOP_WORDS:
                concepts.add(w)
    return concepts


def load_all_memory_names() -> set:
    """只返回记忆文件名（不包含 body 中的散词）"""
    names = set()
    for fpath in Path(MEMORY_DIR).glob("*.md"):
        if fpath.name == "MEMORY_NAME":
            continue
        content = fpath.read_text(encoding="utf-8")
        nm = re.search(r'name:\s*(.+)', content)
        if nm:
            names.add(nm.group(1).strip())
    return names


# ─── 2. 从会话日志检测空白 ─────────────────────────────────────────────────

def find_gaps_from_sessions(existing: set, existing_names: set) -> list[dict]:
    """从会话日志中检测知识空白"""
    gaps = []
    topic_freq = Counter()
    question_topics = Counter()

    session_logs = list(Path(PROJECT_DIR).glob("*.jsonl"))

    for sl_path in session_logs:
        try:
            lines = sl_path.read_text().split("\n")
        except:
            continue
        for line in lines:
            try:
                e = json.loads(line)
            except:
                continue
            msg = e.get("message", {})
            content = msg.get("content", "")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        text += c.get("text", "") + " "

            # 统计话题频率
            for w in re.findall(r'[一-鿿]{3,6}|[a-zA-Z][a-zA-Z0-9_\-.]{3,}', text.lower()):
                if w not in STOP_WORDS:
                    topic_freq[w] += 1

            # 检测用户问句
            if "?" in text or "？" in text or "吗" in text or "什么" in text:
                for w in re.findall(r'[一-鿿]{3,6}|[a-zA-Z][a-zA-Z0-9_\-.]{3,}', text.lower()):
                    if w not in existing and w not in STOP_WORDS and topic_freq[w] > 1:
                        question_topics[w] += 1

    # 高频话题 → 知识空白
    for w, c in topic_freq.most_common(40):
        if c >= 10 and w not in existing and len(w) >= 3:
            gaps.append(dict(
                type="high_frequency_topic",
                topic=w, frequency=c,
                reason=f"话题 '{w}' 在会话中出现了 {c} 次，但没有对应的记忆文件",
                priority="high" if c >= 15 else "medium",
                suggested_type="reference" if c < 20 else "project",
            ))

    # 用户问过的 → 应知未知
    for w, c in question_topics.most_common(15):
        if c >= 3:
            # 检查是否已作为高频话题添加
            if not any(g["topic"] == w for g in gaps):
                gaps.append(dict(
                    type="asked_but_no_memory",
                    topic=w, frequency=c,
                    reason=f"用户问过 '{w}' {c} 次，但没有记忆文件来回答",
                    priority="high" if c >= 8 else "medium",
                    suggested_type="reference",
                ))

    return gaps


# ─── 3. 结构断裂检测 ───────────────────────────────────────────────────────

def find_structural_gaps(memories: list[dict]) -> list[dict]:
    """检测知识结构的断裂"""
    gaps = []
    name_set = {m["name"] for m in memories}

    # 引用断裂：记忆中有 [[link]] 指向不存在的文件
    for m in memories:
        broken = []
        for ref in m.get("refs", []):
            if ref not in name_set:
                broken.append(ref)
        if broken:
            gaps.append(dict(
                type="broken_reference",
                topic=", ".join(broken[:3]),
                reason=f"'{m['name']}' 引用了不存在的记忆: {', '.join(broken[:3])}",
                priority="low",
                suggested_type="reference",
            ))

    # 类型偏科
    type_counts = Counter(m.get("type", "unknown") for m in memories)
    if len(type_counts) >= 2:
        max_type = type_counts.most_common(1)[0]
        min_type = type_counts.most_common()[-1]
        if max_type[1] > 3 * min_type[1] and min_type[1] == 1:
            gaps.append(dict(
                type="type_imbalance",
                topic=f"类型'{min_type[0]}'偏少",
                reason=f"记忆类型分布严重不均: {dict(type_counts)}",
                priority="low",
                suggested_type=min_type[0],
            ))

    return gaps


# ─── 4. 会话日志中缺失的关键上下文 ─────────────────────────────────────────

def find_context_gaps(existing_names: set) -> list[dict]:
    """检测缺失的关键上下文"""
    gaps = []

    # 基于已知信息的反向推断
    # 规则：如果一个记忆描述了项目结构但没有对应的代码仓库说明 → 缺失
    # 规则：如果用户提到某个工具但没有使用记录 → 未使用但存在

    # 这些规则需要领域知识，目前保持轻量
    # 后续可扩展：检查文件名在系统中的存在性
    return gaps


# ─── 5. 汇总与排名 ────────────────────────────────────────────────────────

def rank_gaps(gaps: list[dict]) -> list[dict]:
    """按优先级排序"""
    priority_order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: priority_order.get(g.get("priority", "low"), 9))
    return gaps


def generate_gap_report(gaps: list[dict]) -> str:
    """生成结构化的空白报告块，嵌入 CLAUDE.md 用"""
    lines = []
    lines.append("## 🔍 知识空白检测")
    lines.append("")
    lines.append(f"发现 {len(gaps)} 个知识空白")
    lines.append("")

    for i, gap in enumerate(gaps[:5]):  # 最多 5 条
        icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        lines.append(f"{icon.get(gap.get('priority','low'), '•')} **{gap['topic']}** — {gap['reason']}")

    if len(gaps) > 5:
        lines.append(f"- ...还有 {len(gaps) - 5} 条")

    lines.append("")
    lines.append("> 知识空白 = 系统注意到这些话题反复出现但没有对应的记忆文件。")
    return "\n".join(lines)


# ─── 6. 主入口 ────────────────────────────────────────────────────────────

def detect_gaps() -> dict:
    """运行所有空白检测规则"""
    existing = load_existing_concepts()
    existing_names = load_all_memory_names()

    print(f"📖 已有概念: {len(existing)} 个, 记忆文件: {len(existing_names)} 个")

    gaps = []
    gaps.extend(find_gaps_from_sessions(existing, existing_names))
    gaps.extend(find_structural_gaps([]))  # 需要记忆列表，稍后补
    gaps.extend(find_context_gaps(existing_names))

    gaps = rank_gaps(gaps)

    print(f"🔍 发现 {len(gaps)} 个知识空白")
    for g in gaps[:8]:
        icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        print(f"  {icon.get(g['priority'],'•')} [{g['priority']}] {g['topic']}: {g['reason'][:80]}")

    report = dict(
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        total_gaps=len(gaps),
        gaps=gaps[:10],  # 只保存最重要的 10 条
    )

    # 追加到日志
    Path(GAPS_LOG).parent.mkdir(parents=True, exist_ok=True)
    with open(GAPS_LOG, "a") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")

    # 自动创建存根：仅在非流水线调用时自动创建
    if os.environ.get("AUTO_CREATE_GAPS", "").lower() in ("1", "true", "yes"):
        auto_created = auto_create_gap_memories(gaps, existing_names)
        if auto_created:
            print(f"  🆕 自动创建记忆: {', '.join(auto_created)}")

    return report


def auto_create_gap_memories(gaps: list[dict], existing_names: set) -> list[str]:
    """高频空白自动创建 stub 记忆"""
    if not gaps:
        return []

    # 读取历史中的高频主题
    from collections import Counter
    topic_counter = Counter()
    if os.path.exists(GAPS_LOG):
        try:
            with open(GAPS_LOG) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        for g in entry.get("gaps", []):
                            if g.get("priority") == "high":
                                topic_counter[g["topic"]] += 1
                    except Exception:
                        pass
        except Exception:
            pass

    created = []
    # 停用词表：太通用、无意义的高频词，不应自动创建记忆
    AUTO_CREATE_STOP_WORDS = {
        'lines', 'system', 'files', 'status', 'stub', 'round',
        'memory.md', 'code', 'server', 'host', 'source',
        'quality', 'claimcount', 'angle', 'home', 'error',
    }
    for g in gaps:
        if g.get("priority") != "high":
            continue
        topic = g["topic"]
        topic_lower = topic.lower().strip()
        # 停用词过滤
        if topic_lower in AUTO_CREATE_STOP_WORDS:
            continue
        # 安全过滤：topic 太通用或含非法字符则跳过
        if len(topic) < 3 or not re.match(r'^[\w一-鿿\-_.]+$', topic):
            continue
        if topic_lower in existing_names:
            continue
        # 检查是否在最近 3 次检测中都出现
        count = topic_counter.get(topic, 0)
        if count >= 3:
            fname = f"{topic.lower().replace(' ', '-').replace('.', '-')}.md"
            fpath = os.path.join(MEMORY_DIR, fname)
            if not os.path.exists(fpath):
                now = datetime.datetime.now(datetime.timezone.utc)
                content = f"""---
name: {topic}
description: 知识空白 — 自动创建的占位记忆（高频话题）
metadata:
  node_type: memory
  type: reference
  created: {now.isoformat()}
  modified: {now.isoformat()}
  access_count: 0
  last_accessed: {now.isoformat()}
  retention_strength: 0.9
  consolidation_level: 0.3
  forget_rate: 0.1
  centrality: 0.05
  last_checked: {now.isoformat()}
---

自动完善的占位记忆。关于 **{topic}** 的会话提取信息：

（待后续会话完善）
"""
                try:
                    Path(fpath).write_text(content, encoding="utf-8")
                    created.append(topic)
                    print(f"  🆕 知识空白 → 自动创建: {topic}")
                except Exception as e:
                    print(f"  ⚠ 创建失败 {topic}: {e}")

    return created


def format_for_claude(gaps: list[dict]) -> dict | None:
    """返回第一条高优先级空白（用于主动提问）"""
    for g in gaps:
        if g.get("priority") == "high":
            return g
    return None


def get_question_from_gap(gap: dict) -> str:
    """根据空白类型生成自然语言提问"""
    if not gap:
        return ""

    templates = {
        "high_frequency_topic": [
            f"我发现 **{gap['topic']}** 是你经常提到的，但我还没有为此建立记忆。你想让我记录一些关于它的信息吗？",
            f"关于 **{gap['topic']}**，它似乎在你的工作中很重要。有没有你想让我记住的关键信息？",
        ],
        "asked_but_no_memory": [
            f"你之前问过 **{gap['topic']}** 几次。需要我给你建立一个记忆文件来记录相关信息吗？",
            f"我注意到你对 **{gap['topic']}** 感兴趣。要不我把相关信息记录下来，以后随时可以查阅？",
        ],
    }

    tpls = templates.get(gap.get("type", ""), [f"**{gap['topic']}** 似乎是个重要的内容。要不要记录下来？"])
    return tpls[0] if tpls else ""


def main():
    import sys
    report = detect_gaps()
    print(f"\n📊 汇总: {report['total_gaps']} 个空白")

    top = format_for_claude(report.get("gaps", []))
    if top:
        print(f"\n💡 最需要填补: {top['topic']}")


if __name__ == "__main__":
    main()
