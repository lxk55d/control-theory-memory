#!/usr/bin/env python3
"""
系统状态生成器 — 将记忆系统的当前状态写入 CLAUDE.md。

这样下一轮会话开始就能感知到：
- 记忆数量与分布（含 L0/L2 层级）
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

# L0 记忆（在精简 MEMORY.md 中可见的高信号记忆）
L0_NAMES = {
    "user-profile", "workspace-quant", "scripts-toolset",
    "sharefolder-data", "docker-services",
}


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


def load_history(n: int = 10) -> list[dict]:
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
    """扫描 memory/ 目录统计记忆分布，区分 L0/L2"""
    memory_dir = Path(MEMORY_DIR)
    total = 0
    active = 0
    dormant = 0
    critical = 0
    high_retention = 0
    l0_count = 0
    l2_count = 0

    for fpath in memory_dir.glob("*.md"):
        if fpath.name == "MEMORY.md":
            continue
        content = fpath.read_text(encoding="utf-8")
        if not content.startswith("---"):
            continue
        total += 1

        # 判断 L0/L2
        name = ""
        import re
        m_name = re.search(r'name:\s*(.+)', content)
        if m_name:
            name = m_name.group(1).strip()
        if name and name in L0_NAMES:
            l0_count += 1
        else:
            l2_count += 1

        # 提取 retention
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
        "l0": l0_count,
        "l2": l2_count,
    }


def compute_system_health(mem: dict, config: dict, pid: dict) -> tuple[str, list]:
    """诊断系统健康状态，返回 (status_label, [observations])"""
    obs = []

    if mem["total"] == 0:
        return "empty", ["无记忆文件 — 系统尚未初始化"]

    # 记忆分布诊断
    active_ratio = mem["active"] / mem["total"] if mem["total"] > 0 else 0
    l0_ratio = mem["l0"] / mem["total"] if mem["total"] > 0 else 0
    if active_ratio > 0.80 and mem["total"] > 5:
        obs.append(f"活跃比例偏高 ({active_ratio:.0%}) — PID 正在调大遗忘率")
    elif active_ratio < 0.20 and mem["total"] > 5:
        obs.append(f"活跃比例偏低 ({active_ratio:.0%}) — 可能需要降低遗忘率")

    # 层级分布诊断
    if l0_ratio < 0.2 and mem["total"] > 5:
        obs.append(f"L0 占比偏低 ({l0_ratio:.0%}) — 可考虑提升部分记忆信号强度")
    elif mem["l2"] > 20:
        obs.append(f"L2 记忆过多 ({mem['l2']}) — 建议运行记忆回收器")

    # PID 收敛诊断
    pid_iter = pid.get("iteration", 0)
    if pid_iter >= 10:
        obs.append(f"PID 第 {pid_iter} 轮 — 系统趋近收敛")
    elif pid_iter >= 3:
        obs.append(f"PID 第 {pid_iter} 轮 — 仍在收敛中")
    elif pid_iter > 0:
        obs.append(f"PID 第 {pid_iter} 轮 — 刚刚开始迭代")

    fr = config.get("base_forget_rate", 0)
    if fr > 0.08:
        obs.append(f"遗忘率较高 ({fr:.3f}) — 适合高速变化的知识环境")
    elif fr < 0.02:
        obs.append(f"遗忘率较低 ({fr:.3f}) — 适合稳定知识体系")

    # 从记忆分布推断系统阶段
    total = mem["total"]
    if total == 0:
        return "empty", obs
    if total < 5:
        return "initializing", obs
    if total > 20 or (((mem.get("high_retention", 0) / total) < 0.3) if total > 0 else False):
        return "growing", obs
    if pid_iter >= 15:
        return "stable", obs

    return "converging", obs


def ensure_claude_md_markers():
    """确保 CLAUDE.md 存在且包含状态块标记"""
    path = Path(CLAUDE_MD_PATH)
    if not path.parent.exists():
        path.parent.mkdir(parents=True)
    if not path.exists():
        path.write_text("# 项目记忆系统\n\n<!-- MEMORY_SYSTEM_STATUS_START -->\n<!-- MEMORY_SYSTEM_STATUS_END -->\n")
        return

    content = path.read_text()
    if "<!-- MEMORY_SYSTEM_STATUS_START -->" not in content:
        content += "\n<!-- MEMORY_SYSTEM_STATUS_START -->\n<!-- MEMORY_SYSTEM_STATUS_END -->\n"
        path.write_text(content)


def generate_status_block() -> str:
    """生成状态 Markdown 块"""
    config = load_controller_config()
    pid = load_pid_state()
    history = load_history(5)
    mem = count_memories()

    status_label, observations = compute_system_health(mem, config, pid)

    lines = []
    lines.append(f"## 🧠 记忆系统状态 [{status_label}]")
    lines.append("")
    lines.append("### 记忆分布")
    total = mem["total"]
    lines.append(f"**{total}** 条记忆 (L0={mem['l0']} L2={mem['l2']})")
    bar_len = 20
    fill = int((mem["active"] / max(1, total)) * bar_len)
    lines.append(f"`{'█' * fill}{'░' * (bar_len - fill)}`")
    lines.append("")
    lines.append("### 控制参数")
    lines.append(f"| 参数 | 值 | PID 迭代 |")
    lines.append(f"|---|---|---|")
    lines.append(f"| base_forget_rate | `{config.get('base_forget_rate', '?')}` | 第 {pid.get('iteration', '?')} 轮 |")
    lines.append(f"| theta_vital | `{config.get('theta_vital', '?')}` | 目标活跃 ~40% |")
    lines.append(f"| access_boost | `{config.get('access_boost', '?')}` | |")
    lines.append(f"| theta_dormant | `{config.get('theta_dormant', '?')}` | 休眠门限 |")
    lines.append("")
    lines.append("### 最近调节")
    lines.append(f"| # | 时间 | Δ遗忘率 | Δ活跃门限 | 活跃 | 休眠 |")
    lines.append(f"|---|---|---|---|---|---|")
    for h in history:
        it = h.get("iteration", "?")
        ts = h.get("timestamp", "")
        try:
            delta = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(ts)).total_seconds()
            ago = f"{int(delta // 3600)}h ago" if delta < 86400 else f"{int(delta // 86400)}d ago"
        except Exception:
            ago = ts[:16] if ts else "?"
        obs = h.get("observed", {})
        act = h.get("action", {})
        fr_act = act.get("base_forget_rate", {})
        tv_act = act.get("theta_vital", {})
        old_fr = fr_act.get("old", "?")
        new_fr = fr_act.get("new", "?")
        old_tv = tv_act.get("old", "?")
        new_tv = tv_act.get("new", "?")
        ar = f"{obs.get('active_ratio', 0)*100:.0f}%" if obs.get("active_ratio") is not None else "?"
        dr = f"{obs.get('dormant_ratio', 0)*100:.0f}%" if obs.get("dormant_ratio") is not None else "?"
        lines.append(f"| {it} | {ago} | `{old_fr}` → `{new_fr}` | `{old_tv}` → `{new_tv}` | {ar} | {dr} |")

    lines.append("")
    lines.append("### 诊断")
    for o in observations:
        lines.append(f"- {o}")
    lines.append("")

    # 知识空白
    evo_gaps_path = os.path.join(MEMORY_DIR, "knowledge_gaps.jsonl")
    if os.path.exists(evo_gaps_path):
        try:
            gaps_lines = open(evo_gaps_path).read().strip().split("\n")
            if gaps_lines:
                last_gap = json.loads(gaps_lines[-1])
                gaps = last_gap.get("gaps", [])
                high_gaps = [g for g in gaps if g.get("priority") == "high"]
                if high_gaps:
                    top_gap = high_gaps[0]
                    lines.append(f"### 💡 系统想问你")
                    lines.append(f"")
                    lines.append(f"> 我发现 **{top_gap.get('topic', '?')}** 是你经常提到的，但我还没有为此建立记忆。你想让我记录一些关于它的信息吗？")
                    lines.append("")
        except Exception:
            pass

    # 健康检查
    try:
        from health_check import run_all
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            report_dict = run_all()
        checks = report_dict.get("checks", [])
        lines.append(f"### 🔬 依赖健康")
        for c in checks:
            icon = "✅" if c.get("ok") else ("⚠️" if c.get("status") == "degraded" else "❌")
            lines.append(f"- {icon} {c['name']}: {c.get('detail', '')[:60]}")
    except Exception:
        pass

    from datetime import timezone
    utc_now = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"")
    lines.append(f"> 自动更新于 {utc_now}")

    return "\n".join(lines)


def update_claude_md(status_block: str):
    """将状态块写入 CLAUDE.md"""
    ensure_claude_md_markers()
    path = Path(CLAUDE_MD_PATH)
    content = path.read_text()
    import re

    new_content = re.sub(
        r'<!-- MEMORY_SYSTEM_STATUS_START -->.*?<!-- MEMORY_SYSTEM_STATUS_END -->',
        f'<!-- MEMORY_SYSTEM_STATUS_START -->\n{status_block}\n<!-- MEMORY_SYSTEM_STATUS_END -->',
        content,
        flags=re.DOTALL,
    )

    path.write_text(new_content, encoding="utf-8")


def main():
    block = generate_status_block()
    print(block)
    update_claude_md(block)
    print("\n✅ 状态已写入 CLAUDE.md")


if __name__ == "__main__":
    main()
