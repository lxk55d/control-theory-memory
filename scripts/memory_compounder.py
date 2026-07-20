#!/usr/bin/env python3
"""
记忆压缩器（Memory Compounder）— 月度全局摘要生成。

受 ai-agent-memory 的 memory-compounding.py 启发：
从高信号记忆文件中提取关键点与跨领域模式，综合生成月度摘要。

每周/每月自动执行：
  python3 memory_compounder.py       # 生成本月摘要
  python3 memory_compounder.py --all  # 重新生成所有缺失的月度摘要

输出：memory/compounds/YYYY-MM.md
"""

import json
import os
import re
import sys
import datetime
from pathlib import Path

SCRIPTS_DIR = os.path.expanduser("~/scripts")
sys.path.insert(0, SCRIPTS_DIR)

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
COMPOUNDS_DIR = os.path.join(MEMORY_DIR, "compounds")

# 高信号记忆（L0），也是摘要的主要素材
HIGH_SIGNAL_NAMES = {
    "user-profile", "workspace-quant", "scripts-toolset",
    "sharefolder-data", "docker-services",
}

# LLM API — 使用本地的 proxy 端点（Anthropic 兼容）
API_URL = os.environ.get("LLM_API_URL", "http://127.0.0.1:15721/v1/messages")
API_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", "PROXY_MANAGED")
MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-flash")


def load_memories() -> list[dict]:
    """读取所有记忆文件，返回结构化列表"""
    import memcore
    return memcore.read_all_memories()


def call_llm(system_prompt: str, user_prompt: str) -> str | None:
    """调用 LLM API 生成摘要"""
    import urllib.request

    headers = {"Content-Type": "application/json"}
    if API_KEY and API_KEY != "PROXY_MANAGED":
        headers["x-api-key"] = API_KEY

    payload = {
        "model": MODEL,
        "max_tokens": 2048,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        API_URL, data=data, headers=headers, method="POST"
    )

    try:
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read())
        # Anthropic 格式：找第一个 text 块
        for c in result.get("content", []):
            if c.get("type") == "text" and c.get("text", "").strip():
                return c["text"]
        # 如果全是 thinking 块，返回最后一个 thinking（降级方案）
        for c in reversed(result.get("content", [])):
            if c.get("type") == "thinking" and c.get("thinking", "").strip():
                thinking = c["thinking"].strip()
                # 截取 thinking 末尾的实际回答部分
                import re as re_mod
                # 去掉思考过程前缀
                lines = thinking.split("\n")
                body_lines = [l for l in lines if not re_mod.match(r'^(我们|用户|指令|要求|看起来|需要理)', l)]
                if body_lines:
                    return "\n".join(body_lines[-5:])
                return thinking[-300:]
        # OpenAI 兼容格式
        return result.get("choices", [{}])[0].get("message", {}).get("content", None)
    except Exception as e:
        print(f"  ⚠ LLM 调用失败: {e}", file=sys.stderr)
        return None


def generate_summary(memories: list[dict], year: int, month: int) -> str | None:
    """调用 LLM 生成月度综合摘要"""
    now = datetime.datetime.now()

    # 收集高信号记忆的内容
    source_memories = []
    for m in memories:
        name = m.get("name", "")
        if name not in HIGH_SIGNAL_NAMES:
            continue
        desc = m.get("description", "")
        body = m.get("body", "").strip()
        if not body:
            continue
        source_memories.append({
            "name": name,
            "description": desc,
            "type": m.get("type", ""),
            "retention": m.get("retention", 0),
            "consolidation": m.get("consolidation", 0),
            "body": body[:1500],  # 截断，控制 token
        })

    if not source_memories:
        print("  ⏭ 无有效素材（所有记忆正文为空）", file=sys.stderr)
        return None

    # 构建素材文本
    sources_text = ""
    for s in source_memories:
        sources_text += f"\n## {s['name']}\n"
        sources_text += f"描述: {s['description']}\n"
        sources_text += f"类型: {s['type']} | 保留: {s['retention']:.2f} | 巩固: {s['consolidation']:.2f}\n\n"
        sources_text += s['body'][:1000] + "\n"

    system_prompt = """你是一个记忆系统的"全局综合器"。你的任务是从多个独立的记忆文件中提取跨领域的关键模式和洞察。

要求：
1. 不要逐条复述记忆内容
2. 找出连接点：哪些知识领域之间有交叉？
3. 识别知识弱项：系统缺少什么类型的信息？
4. 给出 2-3 条针对记忆系统的改进建议
5. 语言简洁，用中文输出

输出格式：Markdown，以月度摘要标题开头，不超过 600 tokens。"""

    user_prompt = f"""以下是 {year} 年 {month} 月记忆系统中高信号记忆的内容，请综合提炼全局洞察：

{sources_text}

请从全局视角分析这些记忆反映了什么模式、有什么交叉点、系统还缺什么。"""

    print(f"  📡 调用 LLM 生成 {year}-{month:02d} 摘要...", file=sys.stderr)
    result = call_llm(system_prompt, user_prompt)

    if not result:
        print("  ❌ 摘要生成失败", file=sys.stderr)
        return None

    # 包装为正式格式
    header = f"# 记忆月度综合 — {year}年{month}月\n\n"
    header += f"> 自动生成于 {now.strftime('%Y-%m-%d %H:%M')} | 素材: {len(source_memories)} 条高信号记忆\n\n"
    header += "---\n\n"
    return header + result.strip()


def save_summary(content: str, year: int, month: int) -> str | None:
    """保存摘要到 compounds/ 目录"""
    Path(COMPOUNDS_DIR).mkdir(parents=True, exist_ok=True)
    fname = f"{year}-{month:02d}.md"
    fpath = os.path.join(COMPOUNDS_DIR, fname)
    try:
        Path(fpath).write_text(content, encoding="utf-8")
        print(f"  ✅ 已保存: {fpath}", file=sys.stderr)
        return fpath
    except Exception as e:
        print(f"  ❌ 保存失败: {e}", file=sys.stderr)
        return None


def generate_all_missing(memories: list[dict]):
    """为所有缺失的月度生成摘要（从最早的记忆创建时间到上月）"""
    created_dates = []
    for m in memories:
        created = m.get("created", "")
        if created:
            try:
                dt = datetime.datetime.fromisoformat(created)
                created_dates.append(dt)
            except Exception:
                pass

    if not created_dates:
        earliest = datetime.datetime.now() - datetime.timedelta(days=60)
    else:
        earliest = min(created_dates)

    now = datetime.datetime.now()
    results = []

    y, m = earliest.year, earliest.month
    while (y < now.year) or (y == now.year and m <= now.month):
        fname = f"{y}-{m:02d}.md"
        fpath = os.path.join(COMPOUNDS_DIR, fname)
        if not os.path.exists(fpath):
            print(f"\n📋 生成 {y}-{m:02d}...", file=sys.stderr)
            content = generate_summary(memories, y, m)
            if content:
                saved = save_summary(content, y, m)
                if saved:
                    results.append(saved)
        # 下个月
        m += 1
        if m > 12:
            m = 1
            y += 1

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="记忆月度摘要生成器")
    parser.add_argument("--all", action="store_true", help="生成所有缺失的月度摘要（从最早记忆到上月）")
    parser.add_argument("--month", type=int, default=None, help="指定月份（1-12），默认本月")
    parser.add_argument("--year", type=int, default=None, help="指定年份，默认本年")
    args = parser.parse_args()

    now = datetime.datetime.now()
    year = args.year or now.year
    month = args.month or now.month

    print(f"🧠 记忆压缩器", file=sys.stderr)
    print(f"   输出目录: {COMPOUNDS_DIR}", file=sys.stderr)
    print(f"   素材: {len(HIGH_SIGNAL_NAMES)} 条高信号记忆\n", file=sys.stderr)

    memories = load_memories()

    if args.all:
        results = generate_all_missing(memories)
        print(f"\n✅ 共生成 {len(results)} 个月度摘要", file=sys.stderr)
    else:
        content = generate_summary(memories, year, month)
        if content:
            saved = save_summary(content, year, month)
            if saved:
                print(f"\n✅ 完成", file=sys.stderr)

    # 汇总
    Path(COMPOUNDS_DIR).mkdir(parents=True, exist_ok=True)
    existing = sorted(Path(COMPOUNDS_DIR).glob("*.md"))
    if existing:
        print(f"\n📚 compounds/ 目录现有 {len(existing)} 个月度摘要:", file=sys.stderr)
        for f in existing:
            size = len(f.read_text())
            print(f"   {f.name} ({size} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
