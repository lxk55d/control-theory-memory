#!/usr/bin/env python3
"""
记忆反思器（Memory Reflector）— 周级自动反思。

功能：
1. 矛盾检测：扫描所有记忆文件，找出端口/路径/配置冲突
2. 模式提炼：阅读本周会话日志，提炼工作模式与全局趋势
3. 健康评分：综合 PID 状态 + 矛盾数 + 记忆分布

运行方式：
  python3 memory_reflector.py              # 本周反思
  python3 memory_reflector.py --week 25     # 指定 ISO 周
  python3 memory_reflector.py --force       # 重新生成本周

输出：memory/reflect/YYYY-MM-DD-Www.md
"""

import json
import os
import re
import sys
import datetime
from pathlib import Path
from collections import defaultdict

SCRIPTS_DIR = os.path.expanduser("~/scripts")
sys.path.insert(0, SCRIPTS_DIR)

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
PROJECT_DIR = os.path.expanduser("~/.claude/projects/-home-lxk")
REFLECT_DIR = os.path.join(MEMORY_DIR, "reflect")
COMPOUNDS_DIR = os.path.join(MEMORY_DIR, "compounds")

# LLM API
API_URL = os.environ.get("LLM_API_URL", "http://127.0.0.1:15721/v1/messages")
API_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", "PROXY_MANAGED")
MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-flash")


def log(msg):
    print(f"  📝 {msg}", file=sys.stderr)


# ════════════════════════════════════════════════════════════════════
# LLM 调用
# ════════════════════════════════════════════════════════════════════

def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 2048) -> str | None:
    """调用 LLM API"""
    import urllib.request

    headers = {"Content-Type": "application/json"}
    if API_KEY and API_KEY != "PROXY_MANAGED":
        headers["x-api-key"] = API_KEY

    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(API_URL, data=data, headers=headers, method="POST")

    try:
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read())
        # Anthropic 格式
        for c in result.get("content", []):
            if c.get("type") == "text" and c.get("text", "").strip():
                return c["text"]
        # thinking 块降级
        for c in reversed(result.get("content", [])):
            if c.get("type") == "thinking" and c.get("thinking", "").strip():
                t = c["thinking"].strip()
                lines = [l for l in t.split("\n") if not re.match(r'^(我们|用户|指令|要求|看起来|需要理)', l)]
                return "\n".join(lines[-5:]) if lines else t[-300:]
        # OpenAI 兼容
        return result.get("choices", [{}])[0].get("message", {}).get("content", None)
    except Exception as e:
        print(f"  ⚠ LLM 调用失败: {e}", file=sys.stderr)
        return None


# ════════════════════════════════════════════════════════════════════
# 环节一：矛盾检测
# ════════════════════════════════════════════════════════════════════

def detect_contradictions(memories: list[dict]) -> list[dict]:
    """扫描所有记忆，检测冲突模式"""
    import memcore

    findings = []

    # 1. 端口号冲突
    port_map = defaultdict(list)  # port -> [(mem_name, context)]
    port_pattern = re.compile(r'(?:端口|port|:\s*)(\d{4,5})', re.IGNORECASE)

    for mem in memories:
        text = mem.get("body", "") + " " + mem.get("description", "")
        for m in port_pattern.finditer(text):
            port = m.group(1)
            context_before = text[max(0, m.start()-20):m.start()]
            port_map[port].append((mem["name"], context_before.strip()))

    for port, refs in port_map.items():
        if len(refs) > 1:
            names = list(set(r[0] for r in refs))
            if len(names) > 1:
                findings.append({
                    "type": "port_conflict",
                    "severity": "medium",
                    "detail": f"端口 {port} 出现在多条记忆中: {', '.join(names)}",
                    "sources": names,
                    "suggestion": f"确认数字 {port} 是否指代不同服务的端口，若是，标注服务名以避免混淆",
                })

    # 2. 路径冲突（同一路径在不同记忆里用途不同）
    path_map = defaultdict(list)
    path_pattern = re.compile(r'(/[\w/.\-]+)', re.IGNORECASE)

    for mem in memories:
        text = mem.get("body", "") + " " + mem.get("description", "")
        for m in path_pattern.finditer(text):
            p = m.group(1)
            if p.startswith("/home") or p in ("/dev/null",):
                continue
            if len(p) > 8:
                path_map[p].append(mem["name"])

    for path, refs in path_map.items():
        if len(refs) > 3:
            names = list(set(refs))
            if len(names) > 2:
                findings.append({
                    "type": "path_frequent",
                    "severity": "low",
                    "detail": f"路径 {path} 在 {len(names)} 条记忆中出现 ({', '.join(names[:4])})",
                    "sources": names,
                    "suggestion": "考虑提取为共享配置",
                })

    # 3. 从正文搜索明确的矛盾标记
    for i, m1 in enumerate(memories):
        for j, m2 in enumerate(memories):
            if j <= i:
                continue
            # 查找冲突断言模式
            conflicts = _find_text_conflicts(m1, m2)
            findings.extend(conflicts)

    return findings


def _find_text_conflicts(m1: dict, m2: dict) -> list[dict]:
    """查找两条记忆之间的文本级冲突"""
    results = []
    b1 = m1.get("body", "").lower()
    b2 = m2.get("body", "").lower()

    # 版本冲突（"用 Python 3.10" vs "用 Python 3.12"）
    version_matches_1 = set(re.findall(r'(python|node|npm|docker\s*compose)\s*[:\s]*(\d[\d.]*)', b1))
    version_matches_2 = set(re.findall(r'(python|node|npm|docker\s*compose)\s*[:\s]*(\d[\d.]*)', b2))

    for (tool1, ver1) in version_matches_1:
        for (tool2, ver2) in version_matches_2:
            if tool1 == tool2 and ver1 != ver2:
                results.append({
                    "type": "version_conflict",
                    "severity": "high",
                    "detail": f"{tool1.capitalize()} 版本冲突: '{ver1}' (在 {m1['name']}) vs '{ver2}' (在 {m2['name']})",
                    "sources": [m1["name"], m2["name"]],
                    "suggestion": "确认实际使用的版本并统一记忆",
                })

    return results


# ════════════════════════════════════════════════════════════════════
# 环节二：模式提炼
# ════════════════════════════════════════════════════════════════════

def get_recent_sessions(days: int = 7) -> str:
    """读取最近的会话日志摘要"""
    import memcore
    session_paths = memcore.find_session_logs(PROJECT_DIR)
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    snippets = []

    for sp in session_paths:
        try:
            mtime = os.path.getmtime(sp)
            if datetime.datetime.fromtimestamp(mtime) < cutoff:
                continue
        except Exception:
            continue

        try:
            lines = Path(sp).read_text(encoding="utf-8").split("\n")
        except Exception:
            continue

        user_msgs = []
        tools_used = set()
        for line in lines:
            try:
                entry = json.loads(line)
            except Exception:
                continue
            msg = entry.get("message", {})
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            user_msgs.append(c["text"][:200])
                elif isinstance(content, str):
                    user_msgs.append(content[:200])
            if msg.get("role") == "assistant":
                for c in (msg.get("content", []) if isinstance(msg.get("content"), list) else []):
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        tools_used.add(c.get("name", "?"))

        if user_msgs or tools_used:
            fname = sp.name[:20]
            topics = ", ".join(user_msgs[:3])
            tools = ", ".join(sorted(tools_used)[:5])
            snippets.append(f"会话 {fname}:\n  主题: {topics[:200]}\n  工具: {tools}\n")

    return "\n".join(snippets[:15]) if snippets else "（近 7 天无活跃会话）"


def get_pid_history_summary() -> str:
    """获取 PID 调参历史摘要"""
    import memcore
    entries = memcore.read_history(10)
    if not entries:
        return "（无历史）"
    lines = []
    for e in entries:
        ts = e.get("timestamp", "?")[:19]
        obs = e.get("observed", {})
        act = e.get("action", {})
        fr = act.get("base_forget_rate", {})
        lines.append(f"  {ts} iteration={e.get('iteration','?')} "
                     f"active={obs.get('active_ratio',0)*100:.0f}% "
                     f"dormant={obs.get('dormant_ratio',0)*100:.0f}% "
                     f"forget_rate: {fr.get('old','?')}→{fr.get('new','?')}")
    return "\n".join(lines[:8])


def generate_pattern_insight(memories: list[dict], contradictions: list, sessions_text: str) -> str | None:
    """调用 LLM 生成周级模式洞察"""
    # 构建所有 L0 记忆的正文
    mem_text = ""
    for m in memories:
        name = m.get("name", "?")
        body = m.get("body", "").strip()[:800]
        desc = m.get("description", "")
        if body:
            mem_text += f"\n## {name}\n{desc}\n{body}\n"

    # 矛盾简表
    conflict_text = ""
    for c in contradictions[:5]:
        conflict_text += f"  - [{c['severity']}] {c['detail'][:120]}\n"
    if not conflict_text:
        conflict_text = "  - 未检测到明显矛盾\n"

    system_prompt = """你是一个记忆系统的"周反思分析器"。你的任务是从本周的工作会话和记忆内容中提取模式。

输出结构：
1. **本周主题漂移**：用户的工作焦点是否移动？（60字内）
2. **跨领域连接**：哪些知识域有意外交叉？（60字内）
3. **系统性缺失**：系统整体缺什么类型的知识？（60字内）
4. **矛盾警告**：需要立即关注的一致性冲突（如有）
5. **一条建议**：下周最值得做的一件事

保持简洁，不超过 500 tokens。用中文。"""

    user_prompt = f"""以下是本周数据和记忆内容，请进行周反思分析。

## 本周会话摘要
{sessions_text[:1500]}

## PID 调参历史（上周变迁）
{get_pid_history_summary()[:800]}

## 当前记忆正文（高信号）
{mem_text[:2500]}

## 检测到的矛盾
{conflict_text}

请输出周反思分析。"""

    print("  📡 调用 LLM 进行模式提炼...", file=sys.stderr)
    return call_llm(system_prompt, user_prompt)


# ════════════════════════════════════════════════════════════════════
# 环节三：健康评分
# ════════════════════════════════════════════════════════════════════

def compute_health_score(memories: list[dict], contradictions: list, config: dict, pid_state: dict) -> dict:
    """综合计算系统健康评分"""
    total = len(memories)
    if total == 0:
        return {"score": 1, "level": "critical", "issues": ["无记忆"]}

    scores = []
    details = []

    # 1. 记忆覆盖度 (0-3分)
    types = set(m.get("type") for m in memories if m.get("type"))
    type_score = min(3, len(types))
    scores.append(type_score)
    details.append(f"类型覆盖: {len(types)}/{3} ({type_score}/3)")

    # 2. 矛盾数量 (-1/个)
    conflict_penalty = len([c for c in contradictions if c["severity"] == "high"]) * 1.5
    conflict_penalty += len([c for c in contradictions if c["severity"] == "medium"]) * 0.5

    # 3. PID 收敛度 (0-2分)
    pid_iter = pid_state.get("iteration", 0)
    pid_score = min(2, pid_iter / 3)  # 超过 6 轮 = 满分
    scores.append(pid_score)
    details.append(f"PID 迭代: {pid_iter} 轮 ({pid_score:.1f}/2)")

    # 4. 记忆质量 (0-2分)
    high_cons = sum(1 for m in memories if m.get("consolidation", 0) >= 0.5)
    quality_score = min(2, high_cons / max(1, total) * 3)
    scores.append(quality_score)
    details.append(f"巩固度高: {high_cons}/{total} ({quality_score:.1f}/2)")

    # 5. 活跃分布 (0-1分)
    active_ratio = sum(1 for m in memories if m.get("retention", 0) >= config.get("theta_vital", 0.8)) / max(1, total)
    if 0.3 <= active_ratio <= 0.8:
        balance_score = 1
    elif 0.15 <= active_ratio <= 0.9:
        balance_score = 0.5
    else:
        balance_score = 0
    scores.append(balance_score)
    details.append(f"活跃比: {active_ratio:.0%} ({balance_score:.0f}/1)")

    base_score = sum(scores)  # 最高 8 分
    final_score = max(0, min(10, base_score - conflict_penalty))

    if final_score >= 7:
        level = "healthy"
    elif final_score >= 5:
        level = "fair"
    elif final_score >= 3:
        level = "degraded"
    else:
        level = "critical"

    issues = []
    if conflict_penalty > 0:
        high_c = len([c for c in contradictions if c["severity"] == "high"])
        issues.append(f"发现 {high_c} 处高优先级矛盾")
    if active_ratio > 0.9:
        issues.append("活跃比接近 100%，遗忘率可能需继续调高")
    if pid_iter < 3:
        issues.append("PID 刚刚开始迭代，系统尚未收敛")
    if high_cons / max(1, total) < 0.3:
        issues.append("大部分记忆巩固度偏低")

    return {
        "score": round(final_score, 1),
        "level": level,
        "details": details,
        "issues": issues,
    }


# ════════════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════════════

def reflect(force: bool = False, iso_week: int | None = None) -> str | None:
    """执行一轮完整反思"""
    import memcore

    now = datetime.datetime.now()
    year = now.isoformat()[:4]
    week_num = iso_week or now.isocalendar()[1]
    monday = now - datetime.timedelta(days=now.weekday())
    date_str = monday.strftime("%Y-%m-%d")
    fname = f"{date_str}-W{week_num:02d}.md"
    fpath = os.path.join(REFLECT_DIR, fname)

    if os.path.exists(fpath) and not force:
        log(f"⏭ 本周 ({fname}) 已存在，跳过（使用 --force 重新生成）")
        return fpath

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  🪞 记忆反思 — {date_str} (Week {week_num})", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    # 加载数据
    memories = memcore.read_all_memories()
    config = memcore.load_config()
    pid_state = memcore.load_pid_state()
    log(f"已加载 {len(memories)} 条记忆")

    # 环节一：矛盾检测
    print(f"\n  🔍 环节一: 矛盾检测", file=sys.stderr)
    contradictions = detect_contradictions(memories)
    log(f"发现 {len(contradictions)} 处潜在冲突")
    for c in contradictions:
        icon = "🔴" if c["severity"] == "high" else ("🟡" if c["severity"] == "medium" else "⚪")
        print(f"  {icon} [{c['severity']}] {c['detail'][:100]}", file=sys.stderr)

    # 环节二：模式提炼
    print(f"\n  🧩 环节二: 模式提炼", file=sys.stderr)
    sessions_text = get_recent_sessions(days=7)
    insight = generate_pattern_insight(memories, contradictions, sessions_text)
    if insight:
        log(f"LLM 模式分析完成 ({len(insight)} 字符)")
    else:
        insight = "（LLM 模式分析不可用）"
        log("模式分析无结果")

    # 环节三：健康评分
    print(f"\n  💚 环节三: 健康评分", file=sys.stderr)
    health = compute_health_score(memories, contradictions, config, pid_state)

    level_icons = {"healthy": "✅", "fair": "🟡", "degraded": "⚠️", "critical": "🔴"}
    icon = level_icons.get(health["level"], "❓")
    print(f"  {icon} 健康评分: {health['score']}/10 ({health['level']})", file=sys.stderr)
    for issue in health["issues"]:
        print(f"     ⚠ {issue}", file=sys.stderr)

    # 组装输出
    output = _build_report(date_str, week_num, contradictions, insight, health, config, pid_state)

    # 写文件
    Path(REFLECT_DIR).mkdir(parents=True, exist_ok=True)
    Path(fpath).write_text(output, encoding="utf-8")
    print(f"\n  ✅ 反思写入: {fpath}", file=sys.stderr)

    return fpath


def _build_report(date_str: str, week_num: int, contradictions: list[dict],
                  insight: str, health: dict, config: dict, pid_state: dict) -> str:
    """组装反思报告 Markdown"""
    lines = []
    lines.append(f"# 周反思 — {date_str} (Week {week_num})")
    lines.append("")
    lines.append(f"> 自动生成 | 记忆数: {health['details'][0] if health['details'] else '?'} | 评分: {health['score']}/10 ({health['level']})")
    lines.append("")

    # 健康概览
    lines.append("## 💚 系统健康")
    lines.append(f"**健康评分**: {health['score']}/10 — **{health['level']}**")
    for d in health["details"]:
        lines.append(f"- {d}")
    if health["issues"]:
        lines.append("")
        lines.append("**待处理**:")
        for issue in health["issues"]:
            lines.append(f"- ⚠ {issue}")
    lines.append("")

    # 矛盾检测
    lines.append("## 🔍 矛盾检测")
    if contradictions:
        lines.append(f"发现 **{len(contradictions)}** 处潜在冲突:")
        for c in contradictions:
            icon = "🔴" if c["severity"] == "high" else ("🟡" if c["severity"] == "medium" else "⚪")
            lines.append(f"{icon} **[{c['severity']}]** {c['detail']}")
            lines.append(f"  💡 {c['suggestion']}")
            lines.append(f"  来源: {', '.join(c['sources'])}")
            lines.append("")
    else:
        lines.append("✅ 未检测到明显冲突")
    lines.append("")

    # 模式洞察
    lines.append("## 🧩 模式与洞察")
    if insight:
        lines.append(insight)
    else:
        lines.append("（本周无可用模式分析数据）")
    lines.append("")

    # PID 状态
    lines.append("## 📊 PID 控制状态")
    lines.append(f"- 遗忘率: {config.get('base_forget_rate', '?')}")
    lines.append(f"- 活跃门限: {config.get('theta_vital', '?')}")
    lines.append(f"- 访问增益: {config.get('access_boost', '?')}")
    lines.append(f"- 迭代次数: {pid_state.get('iteration', '?')}")
    lines.append("- 历史:")
    history_text = get_pid_history_summary()
    for h_line in history_text.split("\n")[:6]:
        lines.append(f"  {h_line}")
    if len(history_text.split("\n")) > 6:
        lines.append(f"  ... (共 {len(history_text.split('\n'))} 条)")
    lines.append("")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="记忆周反思器")
    parser.add_argument("--force", action="store_true", help="强制重新生成本周反思")
    parser.add_argument("--week", type=int, default=None, help="ISO 周数，默认本周")
    args = parser.parse_args()

    fpath = reflect(force=args.force, iso_week=args.week)

    if fpath and os.path.exists(fpath):
        print(f"\n📄 反思报告:", file=sys.stderr)
        content = Path(fpath).read_text()
        print(content[:500], file=sys.stderr)
        if len(content) > 500:
            print("...(省略)", file=sys.stderr)
        print(f"\n✅ 完成: {fpath}", file=sys.stderr)


if __name__ == "__main__":
    main()
