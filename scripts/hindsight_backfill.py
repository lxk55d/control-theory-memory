#!/usr/bin/env python3
"""
Hindsight 历史节点 backfill 脚本

策略:
  1. 拉所有无 prefix 的 fact (text 不以 [topic: 开头)
  2. 分 batch (默认 10 条/批) 重新 retain 同内容
  3. Hindsight 的 v4 retain_mission 会让 LLM 重新打 prefix
  4. observations_mission 的 DEDUPLICATE 规则会自动合并重复 fact
  5. 完成后 stats 对比覆盖率

用法:
  hindsight_backfill.py --dry-run          # 看看有多少节点要 backfill
  hindsight_backfill.py --batch 10 --max 500   # 实际跑
  hindsight_backfill.py --batch 10 --max 500 --yes  # 跳过确认
"""
import requests
import time
import re
import argparse
import sys
from datetime import datetime

HOST = "http://localhost:8888"
BANK = "hermes"

TOPIC_PATTERN = re.compile(r'\[topic:(business|infra|dev_tools|code|reflection|research)\]')
TTL_PATTERN = re.compile(r'\[ttl:(permanent|30d|7d|1d)\]')


def list_all_facts(limit=500, max_total=10000):
    """分页拉所有 fact,带前缀过滤"""
    out = []
    offset = 0
    while len(out) < max_total:
        r = requests.get(
            f"{HOST}/v1/default/banks/{BANK}/memories/list",
            params={"limit": limit, "offset": offset},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        if not items:
            break
        out.extend(items)
        if data.get("total", 0) <= offset + len(items):
            break
        offset += limit
    return out


def has_prefix(text: str) -> bool:
    return bool(TOPIC_PATTERN.search(text) and TTL_PATTERN.search(text))


def needs_backfill(text: str) -> bool:
    return not has_prefix(text)


def retain_batch(items, batch_size=10, delay=3.0):
    """分小批 retain 旧 fact,触发 LLM 重新打 prefix"""
    total = len(items)
    success = 0
    failed = 0
    skipped = 0

    for i in range(0, total, batch_size):
        batch = items[i:i + batch_size]
        # 准备 payload
        retain_items = []
        for it in batch:
            text = it.get("text", "")
            # 去尾部 " | When: ... | Involving: ..." 等 LLM 加的元数据
            # 保留原始核心内容供 LLM 重新理解
            retain_items.append({
                "content": text[:1500],  # 截断避免超长
                "context": f"backfill:{it.get('id', '')[:8]}",
                "tags": [f"backfill:phase3_{datetime.now().strftime('%Y%m%d')}"]
            })
        payload = {"async": False, "items": retain_items}
        for retry in range(2):  # 失败重试 1 次
            try:
                r = requests.post(
                    f"{HOST}/v1/default/banks/{BANK}/memories",
                    json=payload,
                    timeout=60,
                )
                if r.status_code == 200:
                    success += len(batch)
                    print(f"  [{i+len(batch):4}/{total}] batch OK", flush=True)
                    break
                elif r.status_code == 500 and retry == 0:
                    print(f"  [{i+len(batch):4}/{total}] batch 500, retrying in 10s...", flush=True)
                    time.sleep(10)
                    continue
                else:
                    failed += len(batch)
                    print(f"  [{i+len(batch):4}/{total}] batch FAIL: {r.status_code} - {r.text[:100]}", flush=True)
                    break
            except Exception as e:
                if retry == 0:
                    print(f"  [{i+len(batch):4}/{total}] batch ERR, retrying: {e}", flush=True)
                    time.sleep(10)
                    continue
                failed += len(batch)
                print(f"  [{i+len(batch):4}/{total}] batch ERR final: {e}", flush=True)

        time.sleep(delay)

    return success, failed, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", type=int, default=10, help="items per batch (default 10)")
    ap.add_argument("--max", type=int, default=500, help="max items to backfill (default 500)")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between batches")
    ap.add_argument("--dry-run", action="store_true", help="just count, don't retain")
    ap.add_argument("--yes", action="store_true", help="skip confirmation")
    args = ap.parse_args()

    print(f"[{datetime.now():%H:%M:%S}] Loading all facts from {BANK} bank...")
    all_items = list_all_facts()
    print(f"  Total: {len(all_items)} facts")

    # 过滤: 已有 prefix 的不算
    needs = [it for it in all_items if needs_backfill(it.get("text", ""))]
    has = [it for it in all_items if has_prefix(it.get("text", ""))]
    print(f"  Already prefixed: {len(has)} ({len(has)/len(all_items)*100:.1f}%)")
    print(f"  Need backfill:    {len(needs)} ({len(needs)/len(all_items)*100:.1f}%)")

    if args.dry_run:
        print("\n[DRY-RUN] Would backfill up to", min(args.max, len(needs)), "items")
        return 0

    to_process = needs[:args.max]
    print(f"\nWill backfill {len(to_process)} items, batch_size={args.batch}, delay={args.delay}s")
    print(f"Estimated time: {len(to_process) // args.batch * (args.delay + 5):.0f}s "
          f"(~{len(to_process) // args.batch * (args.delay + 5) / 60:.1f} min)")

    if not args.yes:
        print("\nContinue? [y/N] ", end="")
        if input().strip().lower() != "y":
            print("Cancelled.")
            return 1

    print(f"\n[{datetime.now():%H:%M:%S}] Starting backfill...")
    s, f, sk = retain_batch(to_process, batch_size=args.batch, delay=args.delay)
    print(f"\n[{datetime.now():%H:%M:%S}] Done.")
    print(f"  Success: {s}")
    print(f"  Failed:  {f}")
    print(f"  Skipped: {sk}")

    # 跑一次 consolidation 让 DEDUPLICATE 规则生效
    print(f"\nTriggering consolidation to merge duplicates...")
    r = requests.post(
        f"{HOST}/v1/default/banks/{BANK}/consolidate",
        json={"scope": "all", "max_memories": 100},
        timeout=30,
    )
    print(f"  Consolidation: {r.status_code}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
