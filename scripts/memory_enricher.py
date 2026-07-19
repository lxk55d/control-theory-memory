#!/usr/bin/env python3
"""
记忆完善引擎 — 自动从会话日志中提取信息来丰富记忆文件。

功能：
1. 检测低 consolidation 的 stub 记忆（新创建的占位符）
2. 从会话日志中提取关于该主题的讨论片段
3. 更新记忆文件的 description 和正文内容
4. 提升 consolidation_level（表示已被"巩固"）

用法：python3 memory_enricher.py [--dry-run]
"""

import json
import os
import re
import datetime
from pathlib import Path
from collections import Counter, defaultdict

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
PROJECT_DIR = os.path.expanduser("~/.claude/projects/-home-lxk")
ENRICH_LOG = os.path.expanduser("/tmp/memory-enrich.log")


# ─── 读取记忆文件 ────────────────────────────────────────────────────────

def read_memory(path: str) -> dict | None:
    """读取记忆文件的 frontmatter + body"""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except:
        return None
    if not text.startswith("---"):
        return None

    parts = text.split("---", 2)
    if len(parts) < 3:
        return None

    fm_text = parts[1].strip()
    body = parts[2].strip()

    # 简单解析 frontmatter
    fm = {}
    for line in fm_text.split("\n"):
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()

    return {
        "frontmatter": fm,
        "body": body,
        "full_text": text,
        "path": path,
    }


def classify_memory(mem: dict) -> str:
    """分类：stub（自动创建未完善）/ normal（已完善）"""
    fm = mem["frontmatter"]
    consolidation = float(fm.get("consolidation_level", 0))
    desc = fm.get("description", "")
    is_auto = "自动" in mem.get("body", "") or "待后续会话完善" in mem.get("body", "")
    if is_auto and consolidation < 0.50:
        return "stub"
    return "normal"


def is_stub(mem: dict) -> bool:
    return classify_memory(mem) == "stub"


# ─── 从会话日志提取主题信息 ──────────────────────────────────────────────

def find_session_logs() -> list[str]:
    """找到所有会话日志文件"""
    logs = sorted(Path(PROJECT_DIR).glob("*.jsonl"), key=os.path.getmtime, reverse=True)
    return [str(p) for p in logs]


def extract_topic_context(topic: str, session_paths: list[str], max_snippets: int = 5) -> list[str]:
    """从会话日志中提取与某个主题相关的文本片段"""
    snippets = []
    topic_lower = topic.lower()

    for sp in session_paths:
        try:
            lines = open(sp, encoding="utf-8").read().split("\n")
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
                    elif isinstance(c, dict) and c.get("type") == "tool_use":
                        # 提取 tool_use input 中的命令内容
                        inp = c.get("input", {})
                        inp_str = json.dumps(inp, ensure_ascii=False)
                        text += inp_str + " "

            if topic_lower in text.lower():
                # 提取包含主题的句子片段
                sentences = re.split(r'[。！？\n.]', text)
                for sent in sentences:
                    if topic_lower in sent.lower() and len(sent) > 15:
                        snippets.append(sent.strip()[:300])
                        if len(snippets) >= max_snippets:
                            break
                if len(snippets) >= max_snippets:
                    break

    # 去重
    seen = set()
    unique = []
    for s in snippets:
        key = s[:60]
        if key not in seen:
            seen.add(key)
            unique.append(s)

    return unique[:max_snippets]


def find_sessions_since(ts_iso: str, session_paths: list[str]) -> list[str]:
    """找到某个时间戳之后的会话日志（用于增量追加）"""
    try:
        cutoff = datetime.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    except:
        return session_paths

    recent = []
    for sp in session_paths:
        try:
            mtime = os.path.getmtime(sp)
            if datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc) > cutoff:
                recent.append(sp)
        except:
            pass
    return recent if recent else session_paths


def extract_topic_details(topic: str, session_paths: list[str]) -> dict:
    """从会话中提取关于某个主题的详细信息"""
    details = {
        "mentioned_files": [],
        "key_commands": [],
        "context_snippets": [],
    }

    topic_lower = topic.lower()

    for sp in session_paths:
        try:
            lines = open(sp, encoding="utf-8").read().split("\n")
        except:
            continue

        for line in lines:
            try:
                e = json.loads(line)
            except:
                continue

            msg = e.get("message", {})
            content = msg.get("content", "")
            if not isinstance(content, list):
                continue

            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    inp = c.get("input", {})
                    inp_str = json.dumps(inp, ensure_ascii=False)
                    if topic_lower in inp_str.lower():
                        if "command" in inp:
                            cmd = inp["command"][:200]
                            if cmd not in details["key_commands"]:
                                details["key_commands"].append(cmd)
                        if "file_path" in inp:
                            fp = inp["file_path"]
                            if fp not in details["mentioned_files"]:
                                details["mentioned_files"].append(fp)

                elif isinstance(c, dict) and c.get("type") == "text":
                    text = c.get("text", "")
                    if topic_lower in text.lower() and len(text) > 20:
                        details["context_snippets"].append(text[:300])

    return details


def find_sessions_since(ts_iso: str, session_paths: list[str]) -> list[str]:
    """找到某个时间戳之后的会话日志"""
    try:
        cutoff = datetime.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    except:
        return session_paths
    recent = []
    for sp in session_paths:
        try:
            mtime = os.path.getmtime(sp)
            if datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc) > cutoff:
                recent.append(sp)
        except:
            pass
    return recent if recent else session_paths


def enrich_memory_if_needed(
    name: str, mem: dict, session_paths: list[str],
    force: bool = False, dry_run: bool = False,
) -> bool:
    """完善一条记忆。stub 替换正文；已有记忆追加 + 提升 consolidation"""
    topic = name.replace("-", " ").replace("_", " ")
    details = extract_topic_details(topic, session_paths)
    if not details["context_snippets"] and not details["key_commands"]:
        details = extract_topic_details(name, session_paths)
    sc = len(details["context_snippets"])
    cc = len(details["key_commands"])
    print(f"  \U0001f50d '{name}': {sc} 段 + {cc} 命令", end="")
    if sc == 0 and cc == 0 and not force:
        print(" \u2192 \u23ed \u65e0\u65b0\u4fe1\u606f")
        return False
    print(" \u2192 \u2705")
    is_stub = "\u5f85\u540e\u7eed\u4f1a\u8bdd\u5b8c\u5584" in mem["body"] or float(mem["frontmatter"].get("consolidation_level", 0)) < 0.50
    if is_stub:
        new_body = generate_enriched_body(topic, details, mem["body"])
        return update_memory(mem, new_body, dry_run=dry_run)
    else:
        fm = mem["frontmatter"]
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        old_cl = float(fm.get("consolidation_level", 0.5))
        fm["consolidation_level"] = str(round(min(1.0, old_cl + 0.05), 2))
        fm["modified"] = now
        lines = ["---"] + [f"{k}: {v}" for k, v in fm.items()] + ["---"]
        body = mem["body"]
        new_text = generate_enriched_body(topic, details, body)
        if not dry_run:
            Path(mem["path"]).write_text("\n".join(lines) + "\n\n" + new_text + "\n", encoding="utf-8")
            print(f"    \u2192 consolidation {old_cl}\u2192{fm['consolidation_level']}")
        return True


def generate_enriched_body(topic: str, details: dict, old_body: str) -> str:
    """生成丰富后的正文"""
    lines = []
    lines.append(f"自动完善记忆。主题 **{topic}** 的会话提取信息：")
    lines.append("")

    if details["context_snippets"]:
        lines.append("## 会话摘要")
        for s in details["context_snippets"][:3]:
            lines.append(f"- {s.strip()}")

    if details["key_commands"]:
        lines.append("")
        lines.append("## 相关操作")
        for cmd in details["key_commands"][:3]:
            lines.append(f"- `{cmd[:120]}...`" if len(cmd) > 120 else f"- `{cmd}`")

    if details["mentioned_files"]:
        lines.append("")
        lines.append("## 关联文件")
        for f in details["mentioned_files"][:5]:
            lines.append(f"- {f}")

    if not details["context_snippets"] and not details["key_commands"]:
        lines.append(old_body)

    return "\n".join(lines)


def update_memory(mem: dict, new_body: str, dry_run: bool = False) -> bool:
    """更新记忆文件的 consolidation_level 和正文"""
    fm = mem["frontmatter"]
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 更新 frontmatter
    fm["consolidation_level"] = "0.55"
    fm["modified"] = now
    # 如果 description 还是默认的，尝试丰富
    desc = fm.get("description", "")
    if "自动提取" in desc:
        fm["description"] = f"由会话日志自动完善的主题：{fm.get('name','?')}"

    # 重建 frontmatter 字符串
    fm_lines = ["---"]
    for k, v in fm.items():
        fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")

    new_full = "\n".join(fm_lines) + "\n\n" + new_body + "\n"

    if not dry_run:
        Path(mem["path"]).write_text(new_full, encoding="utf-8")
        print(f"  ✅ 完善: {Path(mem['path']).name}")
        return True
    else:
        print(f"  ✅ [DRY] 将完善: {Path(mem['path']).name}")
        return False


# ─── 主流程 ───────────────────────────────────────────────────────────────

def enrich_all(dry_run: bool = False, force: bool = False) -> dict:
    """扫描所有记忆文件，完善 stub 记忆 + 跨会话追加"""
    stats = {"scanned": 0, "stubs": 0, "enriched": 0, "appended": 0, "details": []}

    memory_dir = Path(MEMORY_DIR)
    memories = []
    for fpath in memory_dir.glob("*.md"):
        if fpath.name == "MEMORY.md":
            continue
        mem = read_memory(str(fpath))
        if mem:
            name = mem["frontmatter"].get("name", fpath.stem)
            memories.append((name, mem))

    stats["scanned"] = len(memories)
    stubs = [(n, m) for n, m in memories if is_stub(m)]

    if not stubs and not force:
        print("  ℹ️ 无 stub 记忆需要完善")
        return stats

    print(f"  📋 发现 {len(stubs)} 个 stub + {len(memories) - len(stubs)} 个已有记忆")
    session_paths = find_session_logs()

    # 完善所有记忆（stub + 有相关信息的老记忆）
    for name, mem in memories:
        ok = enrich_memory_if_needed(name, mem, session_paths, force=force, dry_run=dry_run)
        if ok:
            if is_stub(mem):
                stats["enriched"] += 1
            else:
                stats["appended"] += 1
            stats["details"].append({"name": name})

    print(f"  📊 完善统计: {stats['enriched']} stub更新 + {stats['appended']} 已有追加")
    return stats


def main():
    import sys
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    stats = enrich_all(dry_run=dry_run, force=force)
    print(f"\n✅ 记忆完善完成 (dry_run={dry_run}): {stats['enriched']} 条更新 + {stats['appended']} 追加")


if __name__ == "__main__":
    main()
