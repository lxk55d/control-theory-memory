#!/usr/bin/env python3
"""
PID 自适应控制器 — 记忆系统的第二回路

控制律：根据系统观测状态，自动调节遗忘控制器的参数。

控制论原理：
  e(t) = r(t) - y(t)    误差 = 期望状态 - 观测状态
  u(t) = Kp·e(t) + Ki·∫e(τ)dτ + Kd·de(t)/dt

被控参数：
  - base_forget_rate   → 整体遗忘速度
  - theta_vital        → 活跃门限
  - access_boost       → 访问脉冲增益

观测变量：
  - active_ratio       → 活跃记忆占比
  - dormant_ratio      → 休眠记忆占比
  - critical_ratio     → 低价值记忆占比
  - avg_retention      → 平均保留强度
  - memory_volatility  → 跨扫描的变化率

用法：
  python3 pid_controller.py <stats_json_or_file>
  或作为 forgetting_controller.py 的模块调用
"""

from error_alert import error_context, alert

#!/usr/bin/env python3
"""
PID 自适应控制器 — 记忆系统的第二回路

控制律：根据系统观测状态，自动调节遗忘控制器的参数。

控制论原理：
  e(t) = r(t) - y(t)    误差 = 期望状态 - 观测状态
  u(t) = Kp·e(t) + Ki·∫e(τ)dτ + Kd·de(t)/dt

被控参数：
  - base_forget_rate   → 整体遗忘速度
  - theta_vital        → 活跃门限
  - access_boost       → 访问脉冲增益

观测变量：
  - active_ratio       → 活跃记忆占比
  - dormant_ratio      → 休眠记忆占比
  - critical_ratio     → 低价值记忆占比
  - avg_retention      → 平均保留强度
  - memory_volatility  → 跨扫描的变化率

用法：
  python3 pid_controller.py <stats_json_or_file>
  或作为 forgetting_controller.py 的模块调用
"""

import json
import os
import math
import datetime
from pathlib import Path

from memcore import MEMORY_DIR, CONFIG_PATH, PID_STATE_PATH, HISTORY_PATH

# ─── 目标状态 ─────────────────────────────────────────────────────────────

TARGET_STATE = {
    "active_ratio": 0.40,       # 40% 活跃 — 核心知识区
    "dormant_ratio": 0.45,       # 45% 休眠 — 可检索但非焦点
    "critical_ratio": 0.10,      # 10% 低价值 — 应占少数
    "avg_retention": 0.65,       # 平均保留强度 0.65
    "memory_volatility": 0.05,   # 逐次波动 < 5%
}

# ─── PID 参数 ─────────────────────────────────────────────────────────────

PID_PARAMS = {
    # (Kp, Ki, Kd) 对不同的被控参数
    "base_forget_rate":  {"Kp": 0.005, "Ki": 0.001, "Kd": 0.002},
    "theta_vital":       {"Kp": 0.05,  "Ki": 0.01,  "Kd": 0.02},
    "access_boost":      {"Kp": 0.01,  "Ki": 0.002, "Kd": 0.005},
}

# 参数安全边界
PARAM_BOUNDS = {
    "base_forget_rate": (0.005, 0.10),
    "theta_vital":      (0.40, 0.95),
    "access_boost":     (0.02, 0.40),
}


# ─── 状态观测 ──────────────────────────────────────────────────────────────

def observe_memory_state(memories: list[dict]) -> dict:
    """
    从记忆列表中提取系统状态。

    输入: forgetting_controller 输出的 memories 列表
    输出: 系统状态字典
    """
    if not memories:
        return {
            "active_ratio": 0.0,
            "dormant_ratio": 0.0,
            "critical_ratio": 0.0,
            "avg_retention": 0.0,
            "total_memories": 0,
            "memory_volatility": 0.0,
        }

    total = len(memories)
    active = sum(1 for m in memories if m.get("classification") == "活跃")
    dormant = sum(1 for m in memories if m.get("classification") == "休眠")
    critical = sum(1 for m in memories if m.get("classification") == "低价值")

    avg_retention = sum(m.get("retention", 0) for m in memories) / total

    # 波动率：保留强度的标准差
    if total > 0:
        variance = sum((m.get("retention", 0) - avg_retention) ** 2 for m in memories) / total
        volatility = math.sqrt(variance)
    else:
        volatility = 0.0

    return {
        "active_ratio": round(active / total, 4),
        "dormant_ratio": round(dormant / total, 4),
        "critical_ratio": round(critical / total, 4),
        "avg_retention": round(avg_retention, 4),
        "total_memories": total,
        "memory_volatility": round(volatility, 4),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


# ─── 误差计算 ─────────────────────────────────────────────────────────────

def compute_error(observed: dict, target: dict = None) -> dict:
    """计算 e(t) = r(t) - y(t)"""
    if target is None:
        target = TARGET_STATE

    error = {}
    for key in ["active_ratio", "dormant_ratio", "critical_ratio", "avg_retention", "memory_volatility"]:
        obs_val = observed.get(key, 0.0)
        tgt_val = target.get(key, 0.0)
        error[key] = round(tgt_val - obs_val, 6)

    return error


# ─── PID 状态管理 ─────────────────────────────────────────────────────────

def load_pid_state() -> dict:  # 已迁移至 memcore.py
    """加载 PID 积分器状态"""
    path = Path(PID_STATE_PATH)
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception):
            pass
    return {
        "integral": {},          # ∫e(τ)dτ 累积
        "prev_error": {},        # e(t-1) 用于导数
        "last_update": None,
        "iteration": 0,
    }


def save_pid_state(state: dict):
    from memcore import save_pid_state as _sps
    _sps(state)


# ─── PID 控制律 ──────────────────────────────────────────────────────────

def apply_pid(
    error_name: str,
    current_error: float,
    pid_state: dict,
    pid_gains: dict,
    param_bounds: tuple,
    current_param_value: float,
    scale_n: int = 14,  # 参考记忆量，用于增益缩放
) -> float:
    """
    对单个参数应用 PID 控制律，带记忆量自适应缩放。

    u(t) = Kp·e(t) · N_ref/N_eff + Ki·∫e(τ)dτ + Kd·de(t)/dt

    N_eff = max(10, total_memories)，N_ref = 10（设计基准）
    记忆越多 → 单步调整量需要按比例放大才能产生相同的影响力
    """
    Kp = pid_gains["Kp"]
    Ki = pid_gains["Ki"]
    Kd = pid_gains["Kd"]

    # 自适应缩放：相对于 N_ref=10 的基准
    N_ref = 10.0
    N_eff = max(N_ref, float(scale_n))
    scale_factor = N_eff / N_ref

    # 比例项 (带缩放)
    P = Kp * current_error * scale_factor

    # 积分项 (带抗饱和)
    integral = pid_state["integral"].get(error_name, 0.0)
    integral += current_error
    # 抗饱和: 积分项限幅
    integral = max(-2.0, min(2.0, integral))
    I = Ki * integral

    # 微分项
    prev_error = pid_state["prev_error"].get(error_name, 0.0)
    derivative = current_error - prev_error
    D = Kd * derivative

    # 控制输出
    delta = P + I + D

    # 应用边界约束
    new_value = current_param_value + delta
    lo, hi = param_bounds
    if new_value < lo:
        new_value = lo
        # 积分器抗饱和: 输出饱和时停止积分
        integral = pid_state["integral"].get(error_name, 0.0) - current_error
    elif new_value > hi:
        new_value = hi
        integral = pid_state["integral"].get(error_name, 0.0) - current_error

    # 更新状态
    pid_state["integral"][error_name] = integral
    pid_state["prev_error"][error_name] = current_error

    return round(delta, 6), round(new_value, 6)


# ─── 控制器主逻辑 ─────────────────────────────────────────────────────────

def tune_parameters(
    observed: dict,
    config: dict,
    pid_state: dict = None,
    dry_run: bool = False,
) -> tuple[dict, dict, list]:
    """
    PID 调参主入口。

    输入:
      observed — observe_memory_state() 的输出
      config   — 当前配置
      pid_state — PID 积分器状态 (如不传则自动加载)
      dry_run  — 预览模式

    输出:
      (new_config, new_pid_state, log_entries)
    """
    if pid_state is None:
        pid_state = load_pid_state()

    pid_state["iteration"] += 1
    pid_state["last_update"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    new_config = dict(config)
    error = compute_error(observed)
    log = []

    print(f"\n  ┌─ PID 自适应控制 (第 {pid_state['iteration']} 轮) ──────────────")
    print(f"  │ 观测状态:")
    print(f"  │   活跃: {observed['active_ratio']:.1%}  |  休眠: {observed['dormant_ratio']:.1%}  |  低价值: {observed['critical_ratio']:.1%}")
    print(f"  │   平均保留: {observed['avg_retention']:.3f}  |  波动率: {observed['memory_volatility']:.3f}")
    print(f"  │ 误差信号:")
    for key, val in error.items():
        sign = "+" if val >= 0 else ""
        print(f"  │   e_{key} = {sign}{val:.4f}")

    # ── 控制 base_forget_rate ──
    # 活跃比例太高 → 遗忘不够快 → 提高遗忘率 (反向控制)
    # 活跃比例太低 → 遗忘太快 → 降低遗忘率
    scale_n = observed.get("total_memories", 14)
    delta_fr, new_fr = apply_pid(
        "base_forget_rate",
        -error["active_ratio"],     # 反向控制: 活跃太高 → 增大遗忘率
        pid_state,
        PID_PARAMS["base_forget_rate"],
        PARAM_BOUNDS["base_forget_rate"],
        config["base_forget_rate"],
        scale_n=scale_n,
    )
    new_config["base_forget_rate"] = new_fr

    # ── 控制 theta_vital ──
    # 误差: 活跃比例太高 → 门限太松 → 提高门限
    delta_th, new_th = apply_pid(
        "theta_vital",
        -error["active_ratio"],     # 反向控制活跃门限
        pid_state,
        PID_PARAMS["theta_vital"],
        PARAM_BOUNDS["theta_vital"],
        config["theta_vital"],
        scale_n=scale_n,
    )
    new_config["theta_vital"] = new_th

    # ── 控制 access_boost ──
    # 误差: memory_volatility 太高 (记忆变化剧烈) → 降低访问脉冲
    delta_ab, new_ab = apply_pid(
        "access_boost",
        -error["memory_volatility"],  # 波动率作为误差
        pid_state,
        PID_PARAMS["access_boost"],
        PARAM_BOUNDS["access_boost"],
        config["access_boost"],
        scale_n=scale_n,
    )
    new_config["access_boost"] = new_ab

    # ── 自适应边界：当参数逼近边界时自动放宽 ──
    if not dry_run:
        bounds_updated = False
        # 使用模块级 PARAM_BOUNDS 的副本
        current_bounds = dict(PARAM_BOUNDS)

        # 遗忘率接近上限 → 放宽上界
        if new_fr >= PARAM_BOUNDS["base_forget_rate"][1] * 0.95:
            lo, hi = PARAM_BOUNDS["base_forget_rate"]
            new_hi = min(hi * 1.5, 0.20)
            current_bounds["base_forget_rate"] = (lo, round(new_hi, 4))
            print(f"  │ ⚡ 遗忘率逼近上界 ({new_fr:.4f} ≈ {hi})，放宽至 {new_hi:.4f}")
            bounds_updated = True

        # 活跃门限接近上限 → 放宽上界
        if new_th >= PARAM_BOUNDS["theta_vital"][1] * 0.97:
            lo, hi = PARAM_BOUNDS["theta_vital"]
            new_hi = min(hi * 1.03, 0.99)
            current_bounds["theta_vital"] = (lo, round(new_hi, 4))
            print(f"  │ ⚡ 活跃门限逼近上限 ({new_th:.4f})，放宽至 {new_hi:.4f}")
            bounds_updated = True

        if bounds_updated:
            bounds_path = os.path.join(os.path.dirname(CONFIG_PATH), "param_bounds.json")
            with open(bounds_path, "w") as f:
                json.dump({k: list(v) for k, v in current_bounds.items()}, f, indent=2)
            print(f"  │ ✓ 边界已放宽 → {bounds_path}")
            # 更新模块级 PARAM_BOUNDS
            PARAM_BOUNDS.clear()
            PARAM_BOUNDS.update(current_bounds)

    print(f"  │")
    print(f"  │ 控制动作:")
    print(f"  │   base_forget_rate: {config['base_forget_rate']:.4f} → {new_fr:.4f}  (Δ={delta_fr:+.4f})")
    print(f"  │   theta_vital:      {config['theta_vital']:.4f} → {new_th:.4f}  (Δ={delta_th:+.4f})")
    print(f"  │   access_boost:     {config['access_boost']:.4f} → {new_ab:.4f}  (Δ={delta_ab:+.4f})")

    if dry_run:
        print(f"  │ [DRY RUN] 未写入")
    else:
        # 写入新配置
        with open(CONFIG_PATH, "w") as f:
            json.dump(new_config, f, indent=2, ensure_ascii=False)
        print(f"  │ ✓ 配置已更新 → {CONFIG_PATH}")

    # 保存 PID 状态
    if not dry_run:
        save_pid_state(pid_state)

    print(f"  └────────────────────────────────────────────")

    # 日志条目
    log_entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "iteration": pid_state["iteration"],
        "observed": observed,
        "error": error,
        "action": {
            "base_forget_rate": {"old": config["base_forget_rate"], "new": new_fr},
            "theta_vital": {"old": config["theta_vital"], "new": new_th},
            "access_boost": {"old": config["access_boost"], "new": new_ab},
        },
    }

    return new_config, pid_state, log_entry


# ─── 历史记录 ─────────────────────────────────────────────────────────────

def append_history(log_entry: dict):
    """追加 PID 执行历史到 jsonl 文件"""
    path = Path(HISTORY_PATH)
    with open(path, "a") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


def read_history(n: int = 20) -> list[dict]:
    from memcore import read_history as _rh
    return _rh(n)


# ─── 报告生成 ─────────────────────────────────────────────────────────────

def generate_report(memories: list[dict], observed: dict, config: dict, history: list[dict]) -> str:
    """生成系统状态报告文本"""
    lines = []
    def P(v): lines.append(v)

    P("╔══════════════════════════════════════════════════╗")
    P("║     记忆系统状态报告                             ║")
    P("╠══════════════════════════════════════════════════╣")
    P(f"║  时间: {observed.get('timestamp', 'N/A')}")
    P(f"║  记忆总数: {observed['total_memories']}")
    P("╠══════════════════════════════════════════════════╣")
    P("║  分布:")
    P(f"║    活跃:    {observed['active_ratio']:.1%}     (目标: {TARGET_STATE['active_ratio']:.0%})")
    P(f"║    休眠:    {observed['dormant_ratio']:.1%}    (目标: {TARGET_STATE['dormant_ratio']:.0%})")
    P(f"║    低价值:  {observed['critical_ratio']:.1%}    (目标: {TARGET_STATE['critical_ratio']:.0%})")
    P(f"║    平均保留: {observed['avg_retention']:.3f}   (目标: {TARGET_STATE['avg_retention']:.2f})")
    P("╠══════════════════════════════════════════════════╣")
    P("║  当前参数:")
    P(f"║    base_forget_rate = {config['base_forget_rate']:.4f}")
    P(f"║    theta_vital      = {config['theta_vital']:.4f}")
    P(f"║    access_boost     = {config['access_boost']:.4f}")
    P(f"║    theta_dormant    = {config['theta_dormant']:.4f}")
    P("╠══════════════════════════════════════════════════╣")
    P("║  PID 调节历史 (最近 5 次):")
    for entry in history[-5:]:
        ts = entry.get("timestamp", "")[-8:]  # HH:MM:SS
        errs = entry.get("error", {})
        P(f"║    [{ts}] e_active={errs.get('active_ratio',0):+.3f}  e_dormant={errs.get('dormant_ratio',0):+.3f}")
    P("╚══════════════════════════════════════════════════╝")

    return "\n".join(lines)


# ─── CLI 入口 ─────────────────────────────────────────────────────────────

def main():
    import sys
    dry_run = "--dry-run" in sys.argv

    # 从文件读 stats
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        with open(sys.argv[1]) as f:
            stats = json.load(f)
    else:
        # 从 stdin 读
        stats = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}

    memories = stats.get("memories", [])
    if not memories:
        # 尝试从文件读取
        from forgetting_controller import scan_memories
        config_path = CONFIG_PATH
        config = json.load(open(config_path)) if os.path.exists(config_path) else {}
        scan_result = scan_memories(config, dry_run=True)
        memories = scan_result.get("memories", [])

    config_path = Path(CONFIG_PATH)
    config = json.loads(config_path.read_text()) if config_path.exists() else {}

    observed = observe_memory_state(memories)
    new_config, pid_state, log_entry = tune_parameters(observed, config, dry_run=dry_run)

    if not dry_run:
        append_history(log_entry)

    history = read_history()
    report = generate_report(memories, observed, new_config, history)
    print(f"\n{report}\n")

    return {
        "observed": observed,
        "config": new_config,
        "log": log_entry,
    }


if __name__ == "__main__":
    main()
