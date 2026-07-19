#!/usr/bin/env python3
"""
Hindsight text-prefix stripper + tag extractor

用法:
  hindsight_strip.py recall <query> [budget]
  hindsight_strip.py recall <query> [budget] --ids-only
  hindsight_strip.py parse <text>     # 单条文本解析
  hindsight_strip.py stats            # 全库 prefix 覆盖率统计

输出:
  recall 模式: 直接打印干净 fact (无 prefix) + 提取出的 topic/ttl
  parse  模式: 打印解析结果 dict
  stats  模式: 打印全库 prefix 覆盖率
"""
import sys
import json
import re
import requests
from typing import Optional

HOST = "http://localhost:8888"
BANK = "hermes"

TOPIC_PATTERN = re.compile(r'\[topic:(business|infra|dev_tools|code|reflection|research)\]')
TTL_PATTERN = re.compile(r'\[ttl:(permanent|30d|7d|1d)\]')
COMBINED_PREFIX = re.compile(
    r'^\[topic:(?:business|infra|dev_tools|code|reflection|research)\]\s*'
    r'\[ttl:(?:permanent|30d|7d|1d)\]\s*'
)


def parse_fact(text: str) -> dict:
    """从 fact text 里抽 topic/ttl, 返回 stripped 文本和 tags"""
    m_topic = TOPIC_PATTERN.search(text)
    m_ttl = TTL_PATTERN.search(text)
    topic = m_topic.group(1) if m_topic else None
    ttl = m_ttl.group(1) if m_ttl else None
    # strip 掉开头的 [topic:X] [ttl:Y] 前缀
    stripped = COMBINED_PREFIX.sub('', text, count=1)
    return {
        "topic": topic,
        "ttl": ttl,
        "stripped": stripped,
        "has_prefix": bool(topic and ttl),
    }


def recall(query: str, budget: str = "mid", ids_only: bool = False):
    """调用 Hindsight recall, 输出干净结果"""
    r = requests.post(
        f"{HOST}/v1/default/banks/{BANK}/memories/recall",
        json={"query": query, "budget": budget, "max_tokens": 2048},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    # results 是 list,不是 dict{facts: [...]}
    facts = data.get("results", [])
    if not isinstance(facts, list):
        facts = []
    if not facts:
        print(f"[no facts for query={query!r}]")
        return

    n_prefix = 0
    for i, f in enumerate(facts, 1):
        text = f.get("text", "")
        parsed = parse_fact(text)
        if parsed["has_prefix"]:
            n_prefix += 1
        if ids_only:
            print(f"[{i:2}] {f.get('id', '')[:8]} topic={parsed['topic']} ttl={parsed['ttl']}")
        else:
            print(f"\n[{i:2}] topic={parsed['topic']} ttl={parsed['ttl']}")
            print(f"    {parsed['stripped'][:200]}")
    print(f"\n--- {n_prefix}/{len(facts)} facts have prefix ---")


def stats():
    """全库 prefix 覆盖率统计"""
    r = requests.get(f"{HOST}/v1/default/banks/{BANK}/memories/list",
                     params={"limit": 500, "offset": 0}, timeout=15)
    r.raise_for_status()
    items = r.json().get("items", [])

    # 分页拉全 - 最多 10 页
    total = r.json().get("total", len(items))
    if total > 500:
        for off in range(500, min(total, 5000), 500):
            r2 = requests.get(f"{HOST}/v1/default/banks/{BANK}/memories/list",
                              params={"limit": 500, "offset": off}, timeout=15)
            items.extend(r2.json().get("items", []))

    topic_dist = {}
    ttl_dist = {}
    no_prefix = 0
    with_prefix = 0
    for it in items:
        parsed = parse_fact(it.get("text", ""))
        if parsed["has_prefix"]:
            with_prefix += 1
            topic_dist[parsed["topic"]] = topic_dist.get(parsed["topic"], 0) + 1
            ttl_dist[parsed["ttl"]] = ttl_dist.get(parsed["ttl"], 0) + 1
        else:
            no_prefix += 1

    print(f"=== Hindsight bank prefix coverage ===")
    print(f"Total nodes sampled: {len(items)}")
    print(f"With prefix:    {with_prefix} ({with_prefix/len(items)*100:.1f}%)")
    print(f"Without prefix: {no_prefix} ({no_prefix/len(items)*100:.1f}%)")
    print(f"\nTopic distribution (prefixed only):")
    for k, v in sorted(topic_dist.items(), key=lambda x: -x[1]):
        print(f"  {k:12} {v:4}")
    print(f"\nTTL distribution (prefixed only):")
    for k, v in sorted(ttl_dist.items(), key=lambda x: -x[1]):
        print(f"  {k:10} {v:4}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "parse":
        text = sys.argv[2] if len(sys.argv) > 2 else input("text: ")
        print(json.dumps(parse_fact(text), ensure_ascii=False, indent=2))
    elif cmd == "recall":
        q = sys.argv[2]
        budget = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] in ("low", "mid", "high") else "mid"
        ids = "--ids-only" in sys.argv
        recall(q, budget, ids)
    elif cmd == "stats":
        stats()
    else:
        print(f"unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
