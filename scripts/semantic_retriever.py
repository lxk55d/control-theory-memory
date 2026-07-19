#!/usr/bin/env python3
"""
语义检索器 — 基于 Hindsight Recall API 的真正语义搜索。

使用 hindsight 的 bge-small-zh-1.5 做向量嵌入，glm-4-flash 做语义排序。
支持按标签过滤、限定搜索范围。

用法：
  python3 semantic_retriever.py "查询语句"
  python3 semantic_retriever.py "查询语句" --limit 5 --filter control-memory
"""

import json
import os
import sys
import urllib.request
import urllib.error

HINDSIGHT_API = "http://127.0.0.1:8888/v1/default/banks/hermes"


def recall(query: str, limit: int = 5, tag_filter: str = None) -> list[dict]:
    """
    语义检索 — 通过 Hindsight Recall API。

    参数:
      query: 自然语言查询
      limit: 返回条数
      tag_filter: 可选，只返回包含该标签的结果
    """
    payload = {"query": query, "limit": limit * 3}  # 多取一些，方便后过滤
    data = json.dumps(payload).encode()

    req = urllib.request.Request(
        f"{HINDSIGHT_API}/memories/recall",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        results = json.loads(resp.read()).get("results", [])
    except Exception as e:
        print(f"⚠ 检索失败: {e}", file=sys.stderr)
        return []

    # 后处理
    processed = []
    for r in results:
        text = r.get("text", "")
        score = r.get("scores", {}).get("final", 0.0)
        tags = r.get("tags", [])
        mem_id = r.get("id", "")

        # 标签过滤
        if tag_filter and tag_filter not in tags:
            continue

        # 提取记忆来源
        is_control = "控制论记忆" in text
        memory_name = ""
        if is_control:
            import re as re2
            m = re2.search(r'控制论记忆\]\s*([^:]+)', text)
            if m:
                memory_name = m.group(1).strip()

        processed.append({
            "id": mem_id,
            "text": text,
            "score": round(score, 4),
            "tags": tags,
            "is_control_memory": is_control,
            "memory_name": memory_name,
        })

    # 按分数排序取 top
    processed.sort(key=lambda x: x["score"], reverse=True)
    return processed[:limit]


def format_results(results: list[dict], show_all: bool = False) -> str:
    """格式化检索结果为可读文本"""
    if not results:
        return "（无结果）"

    lines = []
    for i, r in enumerate(results):
        icon = "📖" if r["is_control_memory"] else "📝"
        tag_str = ", ".join(r["tags"][:3]) if r["tags"] else ""
        score_bar = "█" * int(min(r["score"], 1.5) * 10) + "░" * (15 - int(min(r["score"], 1.5) * 10))
        lines.append(f"{icon} [{r['score']:.3f}] {score_bar}")
        lines.append(f"   {r['text'][:200]}")
        if show_all and tag_str:
            lines.append(f"   标签: {tag_str}")
        lines.append("")

    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="语义检索 — 基于 Hindsight Recall API")
    parser.add_argument("query", nargs="?", help="查询语句")
    parser.add_argument("--limit", type=int, default=5, help="返回条数")
    parser.add_argument("--filter", type=str, default="control-memory", help="标签过滤")
    parser.add_argument("--all", action="store_true", help="显示全部结果，不过滤标签")
    parser.add_argument("--verbose", action="store_true", help="显示详细信息")

    args = parser.parse_args()

    if not args.query and not sys.stdin.isatty():
        args.query = sys.stdin.read().strip()
    if not args.query:
        parser.print_help()
        sys.exit(1)

    tag_filter = None if args.all else args.filter
    results = recall(args.query, limit=args.limit, tag_filter=tag_filter)

    print(f"\n🔍 '{args.query}' ({len(results)} 条结果)")
    print("=" * 60)
    print(format_results(results, show_all=args.verbose))

    if results:
        control_count = sum(1 for r in results if r["is_control_memory"])
        print(f"  其中 {control_count} 条来自控制论记忆系统")


if __name__ == "__main__":
    main()
