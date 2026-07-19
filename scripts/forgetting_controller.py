#!python3
"""
遗忘控制器 — 记忆系统的第一回路（运行控制层）

基于工程控制论：d(retention)/dt = -k·retention + access_signal(t)

功能：
  1. 为每条记忆计算 Ebbinghaus 衰减
  2. 按保留强度分为三级：活跃 / 休眠 / 低价值
  3. 更新记忆文件的 retention_strength 和 consolidation_level
  4. 触发 PID 自适应调参（第二回路）

用法：
  python3 forgetting_controller.py [--dry-run] [--no-pid]
      --dry-run  只分析不修改
      --no-pid   跳过 PID 调参
"""

from error_alert import error_context, alert

import os
import re
import sys
import math
import json
import time
import datetime
from pathlib import Path
from typing import Optional

# ─── 配置 ────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    # 衰减模型参数
    "base_forget_rate": 0.03,           # 基础遗忘率 k0
    "consolidation_boost": 0.5,          # 巩固度对遗忘率的抑制系数
    "access_boost": 0.15,                # 每次访问对 retention 的脉冲增量
    "recency_halflife_days": 7,          # 访问频率衰减的半衰期（天）

    # 门控阈值
    "theta_vital": 0.8,                  # ≥ 0.8 → 活跃
    "theta_dormant": 0.4,                # < 0.8 & ≥ 0.4 → 休眠
    "theta_purge": 0.15,                 # < 0.4 & ≥ 0.15 → 低价值
    "centrality_floor": 0.05,            # 净化所需的 centrality 下界

    # 初始值
    "initial_retention": 0.9,            # 新记忆的初始保留强度
    "initial_consolidation": 0.3,        # 新记忆的初始巩固度
    "default_forget_rate": 0.03,
    "default_centrality": 0.1,

    # 调度
    "scan_interval_hours": 24,           # 建议的扫描间隔
    "archive_threshold_days": 90,        # 无访问即归档
}

from memcore import MEMORY_DIR, CONFIG_PATH


# ─── 核心模型 ────────────────────────────────────────────────────────────

def compute_retention(
    last_retention: float,
    forget_rate: float,
    delta_days: float,
    access_count: int,
    last_access_days_ago: float,
    consolidation: float,
    base_forget_rate: float,
    access_boost: float,
    recency_factor: float,
) -> float:
    """
    连续衰减 + 脉冲访问模型。

    d(retention)/dt = -k·retention + access_signal(t)

    其中:
      k = base_forget_rate / (1 + consolidation)   ← 巩固抑制遗忘
      access_signal(t) = Σ δ(t - t_i) · access_boost

    连续解: retention(t) = retention(0)·exp(-k·t) + boost·exp(-k·(t - t_access))

    这里用离散近似:
      retention_new = retention_old · exp(-k · Δt)  +  访问脉冲 · recency_factor
    """
    effective_k = forget_rate / (1 + consolidation)

    # 纯衰减项
    decayed = last_retention * math.exp(-effective_k * delta_days)

    # 访问脉冲项（recency_factor = 近期访问的额外提升）
    # 最近访问越多、越近，脉冲越强
    access_pulse = access_count * (access_boost * recency_factor) * (1 / (1 + last_access_days_ago * 0.1))

    # 组合
    new_retention = decayed + access_pulse

    # 有界性保证（核心记忆不归零）
    return max(0.01, min(1.0, new_retention))


def compute_recency_factor(last_access_days_ago: float, halflife_days: float = 7) -> float:
    """半衰期衰减：最近访问过 → 因子高；很久没访问 → 因子趋近于 0"""
    return 0.5 ** (last_access_days_ago / halflife_days)


def compute_centrality(links_count: int, inbound_links: int) -> float:
    """简化 PageRank：更多链接 = 更高 centrality"""
    raw = (links_count * 0.3 + inbound_links * 0.7) * 0.1
    return min(1.0, max(0.001, raw))


# ─── 文件 I/O ────────────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 frontmatter — 委托至 memcore"""
    from memcore import parse_frontmatter as _pf; return _pf(content)
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    fm_text = parts[1].strip()
    body = parts[2].strip()

    # 简单 YAML-like 解析（只处理我们需要的字段）
    metadata = {}
    current_key = None
    current_dict = {}
    stack = [metadata]

    for line in fm_text.split("\n"):
        # 缩进的嵌套字段
        if line.startswith("  ") or line.startswith("\t"):
            stripped = line.strip()
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if current_dict is not None:
                    current_dict[key] = _parse_value(val)
            continue

        current_dict = stack[-1]
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()

            # 嵌套开始
            if val == "":
                new_dict = {}
                current_dict[key] = new_dict
                stack.append(new_dict)
                current_dict = new_dict
            else:
                current_dict[key] = _parse_value(val)
                stack = stack[:1]  # reset to top

    return metadata, body


def _parse_value(val: str):
    """解析 YAML-like 值"""
    val = val.strip()
    if val == "" or val is None:
        return None
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    if val.lower() == "null" or val.lower() == "~":
        return None
    # Number
    try:
        if "." in val:
            return float(val)
        return int(val)
    except ValueError:
        pass
    # String
    return val.strip("\"'")


def build_frontmatter(metadata: dict) -> str:
    """从元数据重建 frontmatter 字符串"""
    lines = ["---"]
    for key, val in metadata.items():
        if isinstance(val, dict):
            lines.append(f"{key}:")
            for k, v in val.items():
                lines.append(f"  {k}: {_format_value(v)}")
        else:
            lines.append(f"{key}: {_format_value(val)}")
    lines.append("---")
    return "\n".join(lines)


def _format_value(val) -> str:
    if isinstance(val, bool):
        return str(val).lower()
    if val is None:
        return "null"
    if isinstance(val, str):
        return val
    return str(val)


def read_memory_file(path: str) -> Optional[tuple[dict, str]]:
    """读取一个记忆文件，返回 (元数据, 正文)"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"  ⚠ 读取失败: {e}")
        return None

    metadata, body = parse_frontmatter(content)

    if not metadata:
        # 没有 frontmatter 的文件跳过
        return None

    return metadata, body


def write_memory_file(path: str, metadata: dict, body: str) -> bool:
    """写回记忆文件"""
    try:
        fm = build_frontmatter(metadata)
        content = f"{fm}\n\n{body}\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"  ⚠ 写入失败: {e}")
        return False


# ─── 遗忘调度器 ──────────────────────────────────────────────────────────

def load_config() -> dict:
    """加载配置，如果不存在则用默认值创建"""
    config_path = Path(CONFIG_PATH)
    if config_path.exists():
        try:
            with open(config_path) as f:
                return json.load(f)
        except Exception:
            pass

    # 写入默认配置
    with open(config_path, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    return dict(DEFAULT_CONFIG)


def scan_memories(config: dict, dry_run: bool = False) -> dict:
    """扫描所有记忆文件，计算衰减，执行遗忘调度"""

    memory_dir = Path(MEMORY_DIR)
    if not memory_dir.exists():
        print(f"✗ 记忆目录不存在: {MEMORY_DIR}")
        return {"status": "error", "message": "目录不存在"}

    now = datetime.datetime.now(datetime.timezone.utc)

    stats = {
        "scanned": 0,
        "active": 0,
        "dormant": 0,
        "critical": 0,
        "accessed_recently": 0,
        "archived": 0,
        "updated": 0,
        "errors": [],
        "memories": [],
    }

    print(f"\n{'='*60}")
    print(f"  遗忘控制器扫描 - {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    if dry_run:
        print(f"  🌵 DRY RUN — 不修改文件")
    print(f"{'='*60}\n")

    for fpath in sorted(memory_dir.glob("*.md")):
        if fpath.name == "MEMORY.md":
            continue

        result = read_memory_file(str(fpath))
        if result is None:
            continue

        metadata, body = result
        if not isinstance(metadata, dict) or "metadata" not in metadata:
            continue

        meta = metadata.get("metadata", {})
        if meta.get("node_type") != "memory":
            continue

        stats["scanned"] += 1
        name = metadata.get("name", fpath.stem)

        # ── 读取当前状态 ──
        created_raw = meta.get("created") or meta.get("modified") or now.isoformat()
        modified_raw = meta.get("modified") or now.isoformat()
        last_access_raw = meta.get("last_accessed") or created_raw
        access_count = int(meta.get("access_count", 0))

        retention = float(meta.get("retention_strength", config["initial_retention"]))
        consolidation = float(meta.get("consolidation_level", config["initial_consolidation"]))
        forget_rate = float(meta.get("forget_rate", config["default_forget_rate"]))

        # 计算时间差
        def parse_dt(s):
            try:
                return datetime.datetime.fromisoformat(s)
            except Exception:
                return now

        created_dt = parse_dt(created_raw)
        modified_dt = parse_dt(modified_raw)
        last_access_dt = parse_dt(last_access_raw)

        days_since_creation = (now - created_dt).total_seconds() / 86400
        days_since_mod = (now - modified_dt).total_seconds() / 86400
        days_since_access = (now - last_access_dt).total_seconds() / 86400

        # ── 计算衰减 ──
        recency_factor = compute_recency_factor(days_since_access, config["recency_halflife_days"])

        delta_days = max(0.01, days_since_mod if days_since_mod > 0 else days_since_creation)

        # 计算 centrality（从 metadata 读取，或默认）
        centrality = float(meta.get("centrality", config["default_centrality"]))

        new_retention = compute_retention(
            last_retention=retention,
            forget_rate=forget_rate,
            delta_days=delta_days,
            access_count=access_count,
            last_access_days_ago=days_since_access,
            consolidation=consolidation,
            base_forget_rate=config["base_forget_rate"],
            access_boost=config["access_boost"],
            recency_factor=recency_factor,
        )

        # ── 分类 ──
        if new_retention >= config["theta_vital"]:
            classification = "活跃"
            stats["active"] += 1
        elif new_retention >= config["theta_dormant"]:
            classification = "休眠"
            stats["dormant"] += 1
        else:
            classification = "低价值"
            stats["critical"] += 1

        if days_since_access < 1:
            stats["accessed_recently"] += 1

        # ── 执行控制 ──
        action = "保留"

        if classification == "低价值" and centrality < config["centrality_floor"]:
            if days_since_access > config["archive_threshold_days"]:
                action = "❗建议归档"
                stats["archived"] += 1

        # 更新 retention（非 dry-run）
        updated = False
        if not dry_run and abs(new_retention - retention) > 0.001:
            if "metadata" in metadata and isinstance(metadata["metadata"], dict):
                metadata["metadata"]["retention_strength"] = round(new_retention, 4)
                metadata["metadata"]["modified"] = now.isoformat()
                metadata["metadata"]["last_checked"] = now.isoformat()
                write_memory_file(str(fpath), metadata, body)
                updated = True
                stats["updated"] += 1

        # ── 显示 ──
        retention_bar = "█" * int(new_retention * 20) + "░" * (20 - int(new_retention * 20))

        # 使用 unicode 正确显示
        print(f"  [{classification}] {name}")
        print(f"    保留强度: {retention_bar} {new_retention:.3f}")
        print(f"    巩固度: {consolidation:.2f} | 访问: {access_count}次 | 中心度: {centrality:.3f}")
        print(f"    上次访问: {days_since_access:.0f}天前 | 决策: {action}")

        if updated:
            print(f"    ✓ 已更新")

        print()

        stats["memories"].append({
            "name": name,
            "classification": classification,
            "retention": round(new_retention, 4),
            "consolidation": consolidation,
            "access_count": access_count,
            "days_since_access": round(days_since_access, 1),
            "centrality": centrality,
            "action": action,
        })

    # ── 汇总 ──
    print(f"{'='*60}")
    print(f"  扫描完成")
    print(f"  记忆总数: {stats['scanned']}")
    print(f"  活跃: {stats['active']} | 休眠: {stats['dormant']} | 低价值: {stats['critical']}")
    print(f"  近期访问: {stats['accessed_recently']} | 建议归档: {stats['archived']}")
    print(f"  已更新元数据: {stats['updated']}")
    if dry_run:
        print(f"  本次为 dry run，未修改任何文件")
    print(f"{'='*60}\n")

    return stats


def update_access_count(name: str, memory_dir: str = MEMORY_DIR) -> bool:
    """当一条记忆被访问时，递增其访问计数（供外部调用）"""
    path = Path(memory_dir)
    for fpath in path.glob("*.md"):
        if fpath.name == "MEMORY.md":
            continue

        result = read_memory_file(str(fpath))
        if result is None:
            continue

        metadata, body = result
        if metadata.get("name") == name:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if "metadata" not in metadata:
                metadata["metadata"] = {}
            meta = metadata["metadata"]
            meta["access_count"] = int(meta.get("access_count", 0)) + 1
            meta["last_accessed"] = now
            meta["last_checked"] = now

            # 访问即巩固
            current_consolidation = float(meta.get("consolidation_level", 0.3))
            meta["consolidation_level"] = round(min(1.0, current_consolidation + 0.02), 4)

            write_memory_file(str(fpath), metadata, body)
            return True

    return False


# ─── 入口 ────────────────────────────────────────────────────────────────

def main():
    run_pid = "--no-pid" not in sys.argv
    dry_run = "--dry-run" in sys.argv

    config = load_config()

    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            alt_path = sys.argv[idx + 1]
            with open(alt_path) as f:
                config.update(json.load(f))

    stats = scan_memories(config, dry_run=dry_run)

    # 第二回路：PID 自适应控制
    if run_pid and stats.get("memories"):
        try:
            from pid_controller import tune_parameters, observe_memory_state, append_history, load_pid_state

            pid_state = load_pid_state()
            observed = observe_memory_state(stats["memories"])
            new_config, pid_state, log_entry = tune_parameters(
                observed, config, pid_state=pid_state, dry_run=dry_run
            )
            if not dry_run:
                append_history(log_entry)
        except ImportError:
            print("  (PID 控制器未安装，跳过自适应调参)")
        except Exception as e:
            print(f"  (PID 控制器异常: {e})")

    # 系统状态写入 CLAUDE.md
    if not dry_run and stats.get("scanned", 0) > 0:
        try:
            from generate_status import generate_status_block, update_claude_md
            block = generate_status_block()
            update_claude_md(block)
        except ImportError:
            pass
        except Exception as e:
            print(f"  (状态生成异常: {e})")

    # 输出 JSON 摘要到 stdout（方便管道或日志）
    summary = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scanned": stats["scanned"],
        "active": stats["active"],
        "dormant": stats["dormant"],
        "critical": stats["critical"],
        "archived": stats["archived"],
        "updated": stats["updated"],
        "dry_run": dry_run,
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
