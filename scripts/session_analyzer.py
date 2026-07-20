#!/usr/bin/env python3
"""
会话分析器 — 读取 Claude Code 会话日志，自动提取关键信息：
- 讨论的主题（从用户消息提取关键词）
- 创建/修改的文件
- 使用的主要工具
- 可记忆的内容

用于 Stop 钩子，让系统在每次会话后自我发现值得记住的东西。

用法: python3 session_analyzer.py [--dry-run]
"""

import json
import os
import re
import datetime
from pathlib import Path
from collections import Counter

PROJECT_DIR = os.path.expanduser("~/.claude/projects/-home-lxk")
MEMORY_DIR = os.path.join(PROJECT_DIR, "memory")
ANALYSIS_LOG = os.path.expanduser("/tmp/session-analysis.jsonl")

# ─── 停用词（过滤高频无意义词） ─────
STOP_WORDS = {
    '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
    '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着',
    '没有', '看', '好', '自己', '这', '他', '她', '它', '们', '那', '把',
    '吧', '吗', '啊', '呢', '哦', '嗯', '哈', '对', '让', '用', '能',
    '可以', '还是', '因为', '所以', '如果', '但是', '而且', '虽然', '然后',
    '这个', '那个', '什么', '怎么', '怎样', '为什么', '如何', '应该',
    '需要', '知道', '觉得', '做', '想', '说', '问', '叫', '让', '给',
    'get', 'make', 'like', 'just', 'really', 'actually', 'basically',
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'is', 'it', 'as', 'be', 'are', 'was', 'were', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'can', 'shall', 'this', 'that', 'these',
    'those', 'my', 'me', 'your', 'you', 'we', 'our', 'us', 'they', 'them',
    'their', 'some', 'any', 'all', 'each', 'every', 'both', 'no', 'not',
    'very', 'too', 'much', 'more', 'most', 'such', 'only', 'own', 'same',
}


def find_latest_session() -> Path | None:
    """找到最新的会话日志文件"""
    project = Path(PROJECT_DIR)
    jsonl_files = sorted(project.glob("*.jsonl"), key=os.path.getmtime, reverse=True)
    if not jsonl_files:
        # 也检查旧格式
        for d in project.iterdir():
            if d.is_dir():
                for f in d.glob("*.jsonl"):
                    jsonl_files.append(f)
        jsonl_files.sort(key=os.path.getmtime, reverse=True)
    return jsonl_files[0] if jsonl_files else None


def analyze_log(session_path: Path, dry_run: bool = False) -> dict:
    """分析会话日志，提取关键信息"""
    print(f"📄 分析会话: {session_path.name}")

    try:
        lines = session_path.read_text(encoding="utf-8").strip().split("\n")
    except Exception as e:
        print(f"⚠ 读取失败: {e}")
        return {"status": "error", "error": str(e)}

    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    # ── 1. 收集用户消息文本 ──
    user_messages = []
    assistant_texts = []
    files_read = set()
    files_written = set()
    tools_used = Counter()
    topics = Counter()

    for e in entries:
        msg = e.get("message", {})
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            if isinstance(content, str):
                user_messages.append(content)
            elif isinstance(content, list):
                texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                user_messages.extend(texts)

        elif role == "assistant" and isinstance(content, list):
            for c in content:
                if isinstance(c, dict):
                    if c.get("type") == "text":
                        assistant_texts.append(c.get("text", ""))
                    elif c.get("type") == "tool_use":
                        tools_used[c.get("name", "?")] += 1
                        inp = c.get("input", {})
                        if "file_path" in inp and isinstance(inp["file_path"], str):
                            path = inp["file_path"]
                            if c["name"] in ("Write", "Edit"):
                                files_written.add(path)
                            elif c["name"] == "Read":
                                files_read.add(path)

        # 工具结果中的文件操作
        tr = e.get("toolUseResult")
        if tr and isinstance(tr, dict):
            tool_name = e.get("message", {}).get("content", "")
            pass  # 工具结果通常不直接包含文件路径

    # ── 2. 提取关键词（用户消息 + assistant 文本） ──
    all_text = " ".join(user_messages) + " " + " ".join(assistant_texts)
    # 中文分词（简单按字符和常见双字词）
    words = re.findall(r'[一-鿿]{2,6}|[a-zA-Z][a-zA-Z0-9_\-.]{2,}', all_text)
    for w in words:
        w_lower = w.lower().strip("-_.")
        if w_lower not in STOP_WORDS and len(w_lower) >= 2:
            topics[w_lower] += 1

    # ── 3. 提取明显的主题短语（"做XX","说XX","用XX" 等动词+名词结构） ──
    # 使用简单启发式：连续出现的汉字

    # ── 4. 计算会话统计 ──
    duration = 0
    for e in entries:
        if e.get("type") == "message" and "timestamp" in e:
            # 粗略估算
            pass

    # 找到第一和最后一个时间戳
    timestamps = []
    for e in entries:
        ts = e.get("timestamp")
        if ts:
            try:
                timestamps.append(datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")))
            except Exception:
                pass

    duration_min = 0
    if len(timestamps) >= 2:
        duration_min = round((max(timestamps) - min(timestamps)).total_seconds() / 60, 1)

    # ── 5. 提取"可记忆"的内容 ──
    # 规则：用户消息中的长文本（>50字符）且包含非对话性内容
    memorable = []
    for msg in user_messages:
        msg = msg.strip()
        if len(msg) > 50 and not msg.startswith("{") and not msg.startswith("```"):
            # 看是否包含代码或技术内容
            has_code = bool(re.search(r'(def |class |function|import|const |let |var |```)', msg))
            has_question = msg.endswith("?") or msg.endswith("？")
            memorable.append({
                "text": msg[:200],
                "has_code": has_code,
                "is_question": has_question,
                "length": len(msg),
            })

    # 去重并取前5条
    seen = set()
    unique_memorable = []
    for m in memorable:
        key = m["text"][:60]
        if key not in seen:
            seen.add(key)
            unique_memorable.append(m)
    memorable = unique_memorable[:5]

    # ── 汇总 ──
    result = {
        "session_id": session_path.stem,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "stats": {
            "total_entries": len(entries),
            "user_messages": len(user_messages),
            "duration_min": duration_min,
            "tools_used": dict(tools_used.most_common(10)),
            "files_read": len(files_read),
            "files_written": len(files_written),
        },
        "top_topics": [w for w, c in topics.most_common(15) if c >= 2],
        "files_created_or_modified": sorted(files_written)[:20],
        "files_read": sorted(files_read)[:10],
        "memorable_snippets": memorable,
        "all_user_text_preview": " ".join(user_messages)[:1000],
    }

    # ── 打印 ──
    print(f"  会话: {duration_min} 分钟, {len(user_messages)} 条用户消息")
    print(f"  工具: {', '.join(f'{k}({v})' for k,v in Counter(result['stats']['tools_used']).most_common(5))}")
    print(f"  文件: +{len(files_written)} 写 / {len(files_read)} 读")
    print(f"  主题: {'|'.join(result['top_topics'][:8])}")
    if memorable:
        print(f"  可记忆内容: {len(memorable)} 条")

    if not dry_run:
        # 追加到分析日志
        with open(ANALYSIS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

    return result

    import memcore as _mc

def extract_novel_topics(analysis: dict) -> list[str]:
    """检测会话中是否有新的主题词未在现有记忆中出现"""
    import memcore as _mc
    existing_names = {m["name"].lower() for m in _mc.read_all_memories() if m.get("name")}
    existing_keywords = set()
    for m in _mc.read_all_memories():
        desc = m.get("description", "")
        import re
        for w in re.findall(r"[一-鿿]{2,6}|[a-zA-Z][a-zA-Z0-9_\-.]{2,}", desc):
            existing_keywords.add(w.lower())
        name = m.get("name", "")
        for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_\-.]{2,}", name):
            existing_keywords.add(w.lower())

    novel = []
    for topic in analysis.get("top_topics", []):
        if topic.lower() not in existing_keywords:
            novel.append(topic)
    return novel
    import memcore as _mc
    existing_names = {m["name"].lower() for m in _mc.read_all_memories() if m.get("name")}
    existing_keywords = set()
    for m in _mc.read_all_memories():
        desc = m.get("description", "")
        import re
        for w in re.findall(r"[一-鿿]{2,6}|[a-zA-Z][a-zA-Z0-9_\-.]{2,}", desc):
            existing_keywords.add(w.lower())
        name = m.get("name", "")
        for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_\-.]{2,}", name):
            existing_keywords.add(w.lower())
    for topic in analysis.get("top_topics", []):
        if topic.lower() not in existing_keywords:
            novel.append(topic)

    return novel


def auto_create_memories(analysis: dict, dry_run: bool = False) -> list[str]:
    """当发现足够显著的新主题时，自动创建记忆文件"""
    novel = extract_novel_topics(analysis)
    user_text = analysis.get("all_user_text_preview", "")
    created = []
    created_stems = set()  # 本轮已创建的 stem（防止 batch 内重复）

    # 过滤：至少要出现 3 次才认为显著
    top_topics = analysis.get("top_topics", [])
    topic_to_count = {}
    for w in re.findall(r'[一-鿿]{2,6}|[a-zA-Z][a-zA-Z0-9_\-.]{2,}', user_text):
        wl = w.lower().strip("-_.")
        topic_to_count[wl] = topic_to_count.get(wl, 0) + 1

    # 已有文件的 stem 集合（用于去重）
    existing_stems = {p.stem.lower() for p in Path(MEMORY_DIR).glob("*.md") if p.name != "MEMORY.md"}

    for topic in novel[:3]:  # 每次最多创建 3 条
        # 统计 topic 在用户文本中出现的真实次数
        actual_count = topic_to_count.get(topic.lower(), 0)
        count = actual_count if actual_count >= 3 else 3  # 至少 3 次才创建
        if actual_count < 3:
            continue

        now = datetime.datetime.now(datetime.timezone.utc)
        ts = now.isoformat()

        # 生成安全的文件名 stem
        raw_stem = topic.lower().replace('.', '-').replace('_', '-').replace(' ', '-')
        raw_stem = re.sub(r'[^a-zA-Z0-9_-]', '', raw_stem)
        raw_stem = raw_stem.strip('-')
        while '--' in raw_stem:
            raw_stem = raw_stem.replace('--', '-')

        # 过滤太宽泛的主题（单个词且太短，容易命名冲突）
        if len(raw_stem) < 3:
            print(f"  ⏭ 主题 '{topic}' 太短，跳过")
            continue

        # 去重：检查是否与已有文件或本轮已创建的冲突
        if raw_stem in existing_stems or raw_stem in created_stems:
            print(f"  ⏭ {raw_stem}.md 已存在，跳过")
            continue

        created_stems.add(raw_stem)
        desc = f"从会话自动提取的主题：{topic}（出现 {count} 次）"

        content = f"""---
name: {topic.lower().replace(' ', '-')}
description: {desc}
metadata:
  node_type: memory
  type: reference
  created: {ts}
  modified: {ts}
  access_count: 1
  last_accessed: {ts}
  retention_strength: 0.70
  consolidation_level: 0.30
  forget_rate: 0.04
  centrality: 0.20
  last_checked: {ts}
---

自动创建的初始记忆。主题 **{topic}** 在会话中出现 {count} 次。

来源：会话分析器自动提取。
待后续会话完善内容。
"""

        fpath = Path(MEMORY_DIR) / f"{raw_stem}.md"
        if fpath.exists():
            continue

        if not dry_run:
            fpath.write_text(content, encoding="utf-8")
            created.append(raw_stem)
            print(f"  🆕 创建记忆: {raw_stem}.md ({topic})")
        else:
            print(f"  🆕 [DRY] 准备创建: {raw_stem}.md ({topic})")

    return created


def main():
    import sys
    dry_run = "--dry-run" in sys.argv

    session_path = find_latest_session()
    if not session_path:
        print("⚠ 未找到会话日志")
        return

    result = analyze_log(session_path, dry_run=dry_run)
    print(f"\n📝 分析结果: {result.get('status', 'ok')}")

    # 发现新主题
    novel = extract_novel_topics(result)
    if novel:
        print(f"🆕 潜在新主题: {', '.join(novel[:5])}")

    # 自动创建记忆（如果发现显著新主题）
    created = auto_create_memories(result, dry_run=dry_run)
    if created:
        print(f"  ✓ 创建 {len(created)} 条新记忆")
    else:
        print("  无需创建新记忆")

    return result


if __name__ == "__main__":
    main()
