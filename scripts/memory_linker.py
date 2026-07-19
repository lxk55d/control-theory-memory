#!/usr/bin/env python3
"""
记忆关联器 — 自动发现记忆间的语义关联并建立 [[link]]。

方法：
1. 主题共现检测：同一主题词出现在两条记忆中 → 推荐关联
2. 会话共现检测：两条记忆在会话中被同时提及 → 推荐关联
3. 跨文件引用检测：一条记忆的内容中提到了另一条的名字 → 添加显式链接
4. 类型互补检测：同类型的记忆自动互补关联

用法：python3 memory_linker.py [--dry-run] [--apply]
      --apply  实际写入 [[link]] 到记忆文件
"""

import json
import os
import re
import datetime
from pathlib import Path
from collections import defaultdict, Counter

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
PROJECT_DIR = os.path.expanduser("~/.claude/projects/-home-lxk")


# ─── 读取数据 ────────────────────────────────────────────────────────────

def read_all_memories() -> list[dict]:
    """读取所有记忆文件的结构化数据"""
    memories = []
    for fpath in sorted(Path(MEMORY_DIR).glob("*.md")):
        if fpath.name == "MEMORY.md":
            continue
        content = fpath.read_text(encoding="utf-8")
        if not content.startswith("---"):
            continue

        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        fm_text = parts[1]
        body = parts[2].strip()

        def g(p, d=""):
            m = re.search(p, content)
            return m.group(1).strip() if m else d

        name = g(r'name:\s*(.+)', fpath.stem)
        desc = g(r'description:\s*(.+)', "")
        mtype = g(r'type:\s*(.+)', "unknown")

        # 已有 [[link]]
        existing_links = set(re.findall(r'\[\[(.+?)\]\]', body))

        # body 关键词
        body_words = set(re.findall(r'[一-鿿]{3,6}|[a-zA-Z]{3,}', body.lower()))

        memories.append(dict(
            name=name, desc=desc, type=mtype,
            body_words=body_words, existing_links=existing_links,
            body=body, path=str(fpath),
        ))

    return memories


def find_session_logs() -> list[str]:
    return sorted(Path(PROJECT_DIR).glob("*.jsonl"), key=os.path.getmtime, reverse=True)


# ─── 关联规则 ────────────────────────────────────────────────────────────

def find_topic_overlap_links(memories: list[dict]) -> list[dict]:
    """主题词重叠 → 推荐关联"""
    # 构建主题->记忆映射
    topic_memories = defaultdict(list)
    for m in memories:
        for w in m["body_words"]:
            topic_memories[w].append(m["name"])

    # 对每对记忆计算"共享主题词占比"
    pairs = {}
    for topic, names in topic_memories.items():
        if len(names) < 2:
            continue
        unique_names = list(set(names))
        for i, n1 in enumerate(unique_names):
            for j in range(i + 1, len(unique_names)):
                key = tuple(sorted([n1, unique_names[j]]))
                if key not in pairs:
                    pairs[key] = {"count": 0, "topics": set()}
                pairs[key]["count"] += 1
                if len(pairs[key]["topics"]) < 5:
                    pairs[key]["topics"].add(topic)

    # 转换为推荐列表
    links = []
    for (n1, n2), data in pairs.items():
        m1 = next(m for m in memories if m["name"] == n1)
        m2 = next(m for m in memories if m["name"] == n2)
        total_unique = len(m1["body_words"] | m2["body_words"])
        score = data["count"] / max(total_unique, 1) if total_unique > 0 else 0

        if score > 0.03 and data["count"] >= 2:
            links.append(dict(
                source=n1, target=n2,
                score=round(score, 3),
                shared_topics=list(data["topics"])[:5],
                method="topic_overlap",
            ))

    return links


def find_name_mention_links(memories: list[dict]) -> list[dict]:
    """一条记忆的 name 出现在另一条的 body/desc 中 → 推荐 link"""
    links = []
    name_index = {m["name"]: m for m in memories}

    for m in memories:
        body_lower = (m["body"] + " " + m["desc"]).lower()
        for target_name, target_mem in name_index.items():
            if target_name == m["name"]:
                continue
            if target_name.lower() in body_lower:
                # 但还没显式链接
                if target_name not in m["existing_links"]:
                    links.append(dict(
                        source=m["name"],
                        target=target_name,
                        score=0.9,
                        method="name_mention",
                    ))

    return links


def find_session_cooccur_links(memories: list[dict]) -> list[dict]:
    """会话共现 → 推荐关联"""
    name_index = {m["name"]: m for m in memories}
    cooccur = defaultdict(Counter)

    for slog in find_session_logs():
        try:
            lines = slog.read_text().split("\n")
        except:
            continue

        for line in lines:
            try:
                e = json.loads(line)
            except:
                continue
            msg = e.get("message", {})
            text = ""
            if isinstance(msg.get("content"), str):
                text = msg["content"]
            elif isinstance(msg.get("content"), list):
                for c in msg["content"]:
                    if isinstance(c, dict) and c.get("type") == "text":
                        text += c.get("text", "") + " "

            found = [n for n in name_index if n.lower() in text.lower()]
            for i, n1 in enumerate(found):
                for j in range(i + 1, min(i + 7, len(found))):
                    n2 = found[j]
                    if n1 != n2:
                        cooccur[n1][n2] += 1

    links = []
    for n1, targets in cooccur.items():
        for n2, count in targets.most_common(10):
            if count >= 3 and n2 not in name_index.get(n1, {}).get("existing_links", set()):
                links.append(dict(
                    source=n1, target=n2,
                    score=round(min(0.95, 0.3 + count * 0.05), 3),
                    method="session_cooccur",
                ))

    return links


def find_complementary_type_links(memories: list[dict]) -> list[dict]:
    """同类型 + 不同类型间的互补关联"""
    links = []
    for i, m1 in enumerate(memories):
        for j in range(i + 1, len(memories)):
            m2 = memories[j]
            # 不同类型互补
            if m1["type"] != m2["type"]:
                w1, w2 = m1["body_words"], m2["body_words"]
                overlap = len(w1 & w2)
                if overlap >= 2:
                    links.append(dict(
                        source=m1["name"], target=m2["name"],
                        score=round(0.4 + overlap * 0.05, 3),
                        method="type_complement",
                    ))
    return links


# ─── 去重与合并 ──────────────────────────────────────────────────────────

def deduplicate_links(links: list[dict]) -> list[dict]:
    """去重合并：同一条 link 取最高分 + 合并 method 来源"""
    best = {}

    for link in links:
        key = tuple(sorted([link["source"], link["target"]]))
        if key not in best or link["score"] > best[key]["score"]:
            best[key] = dict(link, key=key)
            best[key]["methods"] = [link["method"]]
        else:
            if link["method"] not in best[key].get("methods", []):
                best[key]["methods"] = best[key].get("methods", []) + [link["method"]]
            if link["score"] > best[key]["score"]:
                best[key]["score"] = link["score"]

    result = list(best.values())
    result.sort(key=lambda x: x["score"], reverse=True)
    return result


# ─── 写入链接 ────────────────────────────────────────────────────────────

def apply_links(links: list[dict], memories: list[dict], dry_run: bool = False) -> int:
    """将 [[link]] 写入记忆文件"""
    name_to_mem = {m["name"]: m for m in memories}
    applied = 0

    for link in links:
        source_name = link["source"]
        target_name = link["target"]

        mem = name_to_mem.get(source_name)
        if not mem:
            continue
        if target_name in mem["existing_links"]:
            continue

        link_text = f"[[{target_name}]]"
        new_body = mem["body"].rstrip() + f"\n- 参见 {link_text}"

        if not dry_run:
            content = Path(mem["path"]).read_text(encoding="utf-8")
            parts = content.split("---", 2)
            if len(parts) >= 3:
                new_content = f"{parts[0]}---{parts[1]}---{new_body}\n"
                Path(mem["path"]).write_text(new_content, encoding="utf-8")
                mem["existing_links"].add(target_name)
                applied += 1
                print(f"  🔗 {source_name:25s} → [[{target_name}]]  ({link['method']}, score={link['score']:.3f})")
        else:
            print(f"  🔗 [DRY] {source_name:25s} → [[{target_name}]]  ({link['method']}, score={link['score']:.3f})")
            applied += 1

    return applied


# ─── 主流程 ──────────────────────────────────────────────────────────────

def main():
    import sys
    dry_run = "--dry-run" in sys.argv
    do_apply = "--apply" in sys.argv
    if do_apply:
        dry_run = False
    if not dry_run and not do_apply:
        dry_run = True  # default: dry-run unless --apply

    print(f"{'='*60}")
    print(f"  记忆关联器 ({'应用' if do_apply else '预览'})")
    print(f"{'='*60}")

    memories = read_all_memories()
    print(f"\n📖 读取 {len(memories)} 条记忆")

    # 运行所有关联规则
    all_links = []
    all_links.extend(find_topic_overlap_links(memories))
    all_links.extend(find_name_mention_links(memories))
    all_links.extend(find_session_cooccur_links(memories))
    all_links.extend(find_complementary_type_links(memories))

    print(f"🔍 共发现 {len(all_links)} 条原始关联")

    # 去重合并
    links = deduplicate_links(all_links)
    print(f"📊 去重后: {len(links)} 条推荐关联\n")

    if not links:
        print("  无推荐关联。需要更多记忆文件才能产生有效关联。")
        return

    for link in links[:10]:
        methods = ", ".join(link.get("methods", [link["method"]]))
        print(f"  {link['score']:.3f}  {link['source']:25s}  ↔  {link['target']:25s}  [{methods}]")
        if "shared_topics" in link and link.get("shared_topics"):
            print(f"       共享词: {', '.join(link['shared_topics'][:4])}")

    if len(links) > 10:
        print(f"  ... 还有 {len(links) - 10} 条")

    if do_apply:
        applied = apply_links(links, memories, dry_run=False)
        print(f"\n✅ 已写入 {applied} 条 [[link]]")
    else:
        print(f"\n💡 使用 --apply 来实际写入这些链接")


if __name__ == "__main__":
    main()
