#!/usr/bin/env python3
"""
系统状态生成器 — 将记忆系统的当前状态写入 CLAUDE.md。

这样下一轮会话开始就能感知到：
- 记忆数量与分布
- PID 控制参数
- 系统健康状态（是否收敛）
- 知识空白（进化层输出）

用法：
  python3 generate_status.py
  或由 forgetting_controller.py / memory_session_hook.py 自动调用
"""

import json
import os
import datetime
from pathlib import Path

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
PROJECT_DIR = os.path.expanduser("~/.claude/projects/-home-lxk")
CONFIG_PATH = os.path.join(MEMORY_DIR, "controller_config.json")
PID_STATE_PATH = os.path.join(MEMORY_DIR, "pid_state.json")
HISTORY_PATH = os.path.join(MEMORY_DIR, "memory_history.jsonl")
CLAUDE_MD_PATH = os.path.join(PROJECT_DIR, "CLAUDE.md")


def load_controller_config() -> dict:
    path = Path(CONFIG_PATH)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


def load_pid_state() -> dict:
    path = Path(PID_STATE_PATH)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


def load_history(n: int = 10) -> list:
    path = Path(HISTORY_PATH)
    if not path.exists():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    return entries[-n:]


def count_memories() -> dict:
    """扫描 memory/ 目录统计记忆分布"""
    memory_dir = Path(MEMORY_DIR)
    total = 0
    active = 0
    dormant = 0
    critical = 0
    high_retention = 0

    for fpath in memory_dir.glob("*.md"):
        if fpath.name == "MEMORY.md":
            continue
        content = fpath.read_text(encoding="utf-8")
        if not content.startswith("---"):
            continue
        total += 1

        # 提取 retention 和 classification
        import re
        m = re.search(r'retention_strength:\s*([\d.]+)', content)
        if m:
            r = float(m.group(1))
            if r >= 0.8:
                active += 1
            elif r >= 0.4:
                dormant += 1
            else:
                critical += 1
            if r > 0.85:
                high_retention += 1

    return {
        "total": total,
        "active": active,
        "dormant": dormant,
        "critical": critical,
        "high_retention": high_retention,
    }


def compute_system_health(mem: dict, config: dict, pid: dict) -> tuple[str, list]:
    """诊断系统健康状态，返回 (status_label, [observations])"""
    obs = []

    if mem["total"] == 0:
        return "empty", ["无记忆文件 — 系统尚未初始化"]

    # 记忆分布诊断
    active_ratio = mem["active"] / mem["total"] if mem["total"] > 0 else 0
    if active_ratio > 0.80 and mem["total"] > 5:
        obs.append(f"活跃比例偏高 ({active_ratio:.0%}) — PID 正在调大遗忘率")
    elif active_ratio < 0.20 and mem["total"] > 5:
        obs.append(f"活跃比例偏低 ({active_ratio:.0%}) — 可能需要降低遗忘率")

    # PID 收敛诊断
    pid_iter = pid.get("iteration", 0)
    if pid_iter >= 10:
        obs.append(f"PID 已运行 {pid_iter} 轮 — 参数应已接近收敛")
    elif pid_iter >= 3:
        obs.append(f"PID 第 {pid_iter} 轮 — 仍在收敛中")
    elif pid_iter > 0:
        obs.append(f"PID 刚启动 (第 {pid_iter} 轮)")

    # 遗忘率诊断
    fr = config.get("base_forget_rate", 0.03)
    if fr > 0.07:
        obs.append(f"遗忘率较高 ({fr:.3f}) — 适合高速变化的知识环境")
    elif fr < 0.01:
        obs.append(f"遗忘率极低 ({fr:.3f}) — 大部分记忆保持活跃")

    # 综合判断
    if pid_iter >= 5 and active_ratio < 0.60 and active_ratio > 0.15:
        return "stable", obs
    elif pid_iter >= 3:
        return "converging", obs
    else:
        return "initializing", obs


def format_timedelta(ts_str: str) -> str:
    """格式化时间差为人可读的字符串"""
    try:
        dt = datetime.datetime.fromisoformat(ts_str)
        now = datetime.datetime.now(datetime.timezone.utc)
        # 处理时区
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        delta = now - dt
        days = delta.days
        hours = delta.seconds // 3600
        if days > 0:
            return f"{days}d {hours}h ago"
        elif hours > 0:
            return f"{hours}h ago"
        else:
            return f"{delta.seconds // 60}m ago"
    except Exception:
        return "unknown"


def generate_status_block() -> str:
    """生成系统状态文本块（嵌入 CLAUDE.md 用）"""
    mem = count_memories()
    config = load_controller_config()
    pid_state = load_pid_state()
    history = load_history(5)

    health_label, health_obs = compute_system_health(mem, config, pid_state)

    lines = []

    # 状态头
    status_icon = {"stable": "✅", "converging": "🔄", "initializing": "⚙️", "empty": "⬜"}
    icon = status_icon.get(health_label, "❓")
    lines.append(f"## 🧠 记忆系统状态 [{icon} {health_label}]")
    lines.append("")

    # 记忆分布
    lines.append("### 记忆分布")
    if mem["total"] > 0:
        bars = []
        if mem["active"] > 0:
            bars.append(f"活跃 {mem['active']}")
        if mem["dormant"] > 0:
            bars.append(f"休眠 {mem['dormant']}")
        if mem["critical"] > 0:
            bars.append(f"低价值 {mem['critical']}")
        ratio_str = f"({mem['active']}/{mem['dormant']}/{mem['critical']})" if mem["total"] > 0 else ""
        lines.append(f"**{mem['total']}** 条记忆 {ratio_str}")
        progress = ""
        if mem["total"] > 0:
            a = int(mem["active"] / mem["total"] * 20)
            d = int(mem["dormant"] / mem["total"] * 20)
            progress = f"`{'█' * a}{'▓' * d}{'░' * (20 - a - d)}`"
        if progress:
            lines.append(progress)
    else:
        lines.append("*无记忆文件*")

    lines.append("")

    # 控制参数
    if config:
        lines.append("### 控制参数")
        ps = pid_state.get("iteration", 0)
        lines.append(f"| 参数 | 值 | PID 迭代 |")
        lines.append(f"|------|-----|---------|")
        lines.append(f"| base_forget_rate | `{config.get('base_forget_rate', 'N/A')}` | 第 {ps} 轮 |")
        lines.append(f"| theta_vital | `{config.get('theta_vital', 'N/A')}` | 目标活跃 ~40% |")
        lines.append(f"| access_boost | `{config.get('access_boost', 'N/A')}` | |")
        lines.append(f"| theta_dormant | `{config.get('theta_dormant', 'N/A')}` | 休眠门限 |")
        lines.append("")

    # 最近 PID 调节历史
    if history:
        lines.append("### 最近调节")
        lines.append("")
        lines.append("| # | 时间 | Δ遗忘率 | Δ活跃门限 | 活跃 | 休眠 |")
        lines.append("|---|------|---------|----------|------|------|")
        for i, entry in enumerate(history):
            ts = entry.get("timestamp", "")
            time_ago = format_timedelta(ts)
            action = entry.get("action", {})
            delta_fr = action.get("base_forget_rate", {}).get("new", "?")
            delta_th = action.get("theta_vital", {}).get("new", "?")
            obs = entry.get("observed", {})
            ar = obs.get("active_ratio", 0)
            dr = obs.get("dormant_ratio", 0)
            lines.append(f"| {entry.get('iteration', '?')} | {time_ago} | `{delta_fr}` | `{delta_th}` | {ar:.0%} | {dr:.0%} |")
        lines.append("")

    # 诊断与建议
    if health_obs:
        lines.append("### 诊断")
        for o in health_obs:
            lines.append(f"- {o}")
        lines.append("")

    # 进化层：知识空白主动提问
    try:
        import evolution_engine
        gaps = evolution_engine.detect_gaps()
        top_gap = evolution_engine.format_for_claude(gaps.get("gaps", []))
        if top_gap:
            question = evolution_engine.get_question_from_gap(top_gap)
            if question:
                lines.append("### 💡 系统想问你")
                lines.append("")
                lines.append(f"> {question}")
                lines.append("")
    except Exception:
        pass

    # 告警层：未解决错误
    try:
        from error_alert import ErrorDB
        _db = ErrorDB()
        active = _db.active_errors(max_age_minutes=120)
        if active:
            lines.append("### 🔔 系统告警")
            lines.append("")
            for e in active[:3]:
                icon_map = {"error": "🔴", "critical": "💥", "warning": "⚡"}
                icon = icon_map.get(e.get("severity", "info"), "•")
                ts = e.get("timestamp", "")[-8:]
                lines.append(f"- {icon} [{ts}] {e.get('component')}: {str(e.get('message', ''))[:80]}")
            lines.append("")
    except Exception:
        pass

    # 健康检查：外部依赖状态
    try:
        import health_check as hc
        report = hc.run_all(verbose=False)
        claude_block = hc.format_for_claude(report)
        if claude_block:
            lines.append(claude_block)
            lines.append("")
    except Exception:
        pass

    # 更新时间戳
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"> 自动更新于 {now}")

    return "\n".join(lines)


def update_claude_md(status_block: str) -> bool:
    """将状态块写入或更新 CLAUDE.md 中的标记区域"""
    path = Path(CLAUDE_MD_PATH)
    if not path.exists():
        return False

    content = path.read_text(encoding="utf-8")

    marker_start = "<!-- MEMORY_SYSTEM_STATUS_START -->"
    marker_end = "<!-- MEMORY_SYSTEM_STATUS_END -->"

    block_with_markers = f"{marker_start}\n{status_block}\n{marker_end}"

    if marker_start in content:
        # 替换已有状态块
        import re
        new_content = re.sub(
            f"{re.escape(marker_start)}.*?{re.escape(marker_end)}",
            block_with_markers,
            content,
            flags=re.DOTALL,
        )
    else:
        # 追加到文件末尾
        new_content = content.rstrip() + "\n\n" + block_with_markers + "\n"

    path.write_text(new_content, encoding="utf-8")
    return True


def main():
    status = generate_status_block()
    updated = update_claude_md(status)
    print(status)
    if updated:
        print(f"\n✓ 已写入 CLAUDE.md")
    return status


if __name__ == "__main__":
    main()
