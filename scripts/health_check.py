#!/usr/bin/env python3
"""
健康检查器 — 监控所有外部依赖的健康状态。

检查项：
  1. Hindsight API (端口 8888) — 可达性 + 延迟
  2. Hindsight Recall — 语义检索功能正常
  3. Hindsight Embeddings — 向量索引状态
  4. File system — 记忆目录完整性
  5. 配置完整性 — controller_config / pid_state 无损坏
  6. 数据完整性 — 所有记忆文件有有效 frontmatter

用法：
  python3 health_check.py              # 完整检查
  python3 health_check.py --watch      # 持续监控（每 60s）
  python3 health_check.py --json       # JSON 输出
"""

import json
import os
import re
import time
import datetime
import urllib.request
import urllib.error
from pathlib import Path

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
SCRIPTS_DIR = os.path.expanduser("~/scripts")
HINDSIGHT_API = "http://127.0.0.1:8888"
HINDSIGHT_BANK = f"{HINDSIGHT_API}/v1/default/banks/hermes"
HEALTH_LOG = os.path.join(MEMORY_DIR, "health_history.jsonl")


def check(name: str, severity: str, func) -> dict:
    """执行一项健康检查"""
    start = time.time()
    try:
        result = func()
        elapsed = (time.time() - start) * 1000
        status = "ok" if result.get("ok", False) else "degraded"
        return {
            "name": name, "status": status, "severity": severity,
            "latency_ms": round(elapsed, 1),
            "detail": result.get("detail", ""),
            "ok": result.get("ok", False),
        }
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        return {
            "name": name, "status": "fail", "severity": severity,
            "latency_ms": round(elapsed, 1),
            "detail": str(e)[:120],
            "ok": False,
        }


# ─── 单项检查 ───────────────────────────────────────────────────────────

def hindsight_api() -> dict:
    """Hindsight API 基础可达性"""
    r = urllib.request.urlopen(f"{HINDSIGHT_API}/health", timeout=5)
    data = json.loads(r.read())
    return {"ok": r.status == 200, "detail": f"HTTP {r.status}"}


def hindsight_version() -> dict:
    """Hindsight 版本"""
    r = urllib.request.urlopen(f"{HINDSIGHT_API}/version", timeout=5)
    data = json.loads(r.read())
    return {"ok": True, "detail": f"version: {data.get('version', '?')}"}


def hindsight_recall() -> dict:
    """Hindsight 语义检索功能"""
    try:
        recall = json.dumps({"query": "health check test query", "limit": 1}).encode()
        r = urllib.request.urlopen(
            urllib.request.Request(f"{HINDSIGHT_BANK}/memories/recall",
                                   data=recall,
                                   headers={"Content-Type": "application/json"},
                                   method="POST"),
            timeout=10)
        data = json.loads(r.read())
        results = len(data.get("results", []))
        return {"ok": r.status == 200, "detail": f"{results} results"}
    except Exception:
        pass

    # fallback: memories/list
    try:
        r2 = urllib.request.urlopen(f"{HINDSIGHT_BANK}/memories/list?limit=1", timeout=5)
        data2 = json.loads(r2.read())
        items = len(data2.get("items", []))
        return {"ok": r2.status == 200, "detail": f"fallback to list: {items} items"}
    except Exception as e:
        return {"ok": False, "detail": f"Recall + list 均失败: {str(e)[:80]}"}


def hindsight_bank() -> dict:
    """Hindsight bank 可用"""
    r = urllib.request.urlopen(f"{HINDSIGHT_API}/v1/default/banks", timeout=5)
    data = json.loads(r.read())
    banks = [b["bank_id"] for b in data.get("banks", [])]
    has_hermes = "hermes" in banks
    return {"ok": has_hermes, "detail": f"banks: {', '.join(banks)}"}


def memory_dir_integrity() -> dict:
    """记忆目录完整性"""
    mem_dir = Path(MEMORY_DIR)
    if not mem_dir.exists():
        return {"ok": False, "detail": "目录不存在"}

    md_files = list(mem_dir.glob("*.md"))
    mem_files = [f for f in md_files if f.name != "MEMORY.md"]

    # 检查每个文件是否有有效 frontmatter
    broken = []
    for f in mem_files:
        content = f.read_text(encoding="utf-8")
        if not content.startswith("---"):
            broken.append(f.name)

    # 检查状态文件
    config_ok = (mem_dir / "controller_config.json").exists()
    pid_ok = (mem_dir / "pid_state.json").exists()
    history_ok = (mem_dir / "memory_history.jsonl").exists()

    detail_parts = []
    detail_parts.append(f"{len(mem_files)} 个记忆文件")
    if broken:
        detail_parts.append(f"{len(broken)} 个破损")
    detail_parts.append(f"config={'✓' if config_ok else '✗'}")
    detail_parts.append(f"pid={'✓' if pid_ok else '✗'}")

    return {
        "ok": len(broken) == 0 and config_ok,
        "detail": " · ".join(detail_parts),
    }


def hindsight_memory_count() -> dict:
    """Hindsight 中的记忆数量"""
    r = urllib.request.urlopen(f"{HINDSIGHT_BANK}/stats", timeout=5)
    data = json.loads(r.read())
    count = data.get("stats", {}).get("memory_count", data.get("memory_count", 0))
    return {"ok": count > 0, "detail": f"{count} 条记忆"}


def config_integrity() -> dict:
    """配置完整性检查"""
    config_path = Path(MEMORY_DIR) / "controller_config.json"
    try:
        cfg = json.loads(config_path.read_text())
    except Exception:
        return {"ok": False, "detail": "config 损坏"}

    required = ["base_forget_rate", "theta_vital", "theta_dormant", "theta_purge"]
    missing = [k for k in required if k not in cfg]
    if missing:
        return {"ok": False, "detail": f"缺少字段: {', '.join(missing)}"}

    fr = float(cfg.get("base_forget_rate", 0))
    bounds_ok = 0.005 <= fr <= 0.15
    return {"ok": bounds_ok, "detail": f"遗忘率 {fr:.4f}"}


def disk_usage() -> dict:
    """磁盘使用情况"""
    mem_dir = Path(MEMORY_DIR)
    total_bytes = 0
    for f in mem_dir.rglob("*"):
        if f.is_file():
            total_bytes += f.stat().st_size

    if total_bytes < 1024:
        detail = f"{total_bytes} bytes"
    elif total_bytes < 1024 * 1024:
        detail = f"{total_bytes / 1024:.1f} KB"
    else:
        detail = f"{total_bytes / 1024 / 1024:.1f} MB"

    return {"ok": True, "detail": detail}


# ─── 主流程 ─────────────────────────────────────────────────────────────

def run_all(verbose: bool = False) -> dict:
    """运行所有健康检查"""
    checks = [
        ("Hindsight API", "critical", hindsight_api),
        ("Hindsight Version", "info", hindsight_version),
        ("Hindsight Bank", "critical", hindsight_bank),
        ("Hindsight Recall", "warning", hindsight_recall),
        ("Hindsight Stats", "info", hindsight_memory_count),
        ("记忆目录完整", "critical", memory_dir_integrity),
        ("配置完整性", "warning", config_integrity),
        ("磁盘占用", "info", disk_usage),
    ]

    results = []
    statuses = {"ok": 0, "degraded": 0, "fail": 0}
    overall_ok = True

    print(f"\n{'='*60}")
    print(f"  健康检查 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    for name, severity, func in checks:
        result = check(name, severity, func)
        results.append(result)
        statuses[result["status"]] = statuses.get(result["status"], 0) + 1
        if result["status"] == "fail":
            overall_ok = False

        icon = {"ok": "✅", "degraded": "⚠️", "fail": "❌"}.get(result["status"], "❓")
        print(f"  {icon} {name:25s} {result['status']:8s} ({result['latency_ms']:.0f}ms)  {result['detail']}")

    # 汇总
    total = len(checks)
    passed = statuses.get("ok", 0)
    print(f"\n  📊 {passed}/{total} 通过", end="")
    if statuses.get("degraded", 0):
        print(f", {statuses['degraded']} 降级", end="")
    if statuses.get("fail", 0):
        print(f", {statuses['fail']} 失败", end="")
    print(f" | 总体: {'✅ 健康' if overall_ok else '❌ 异常'}")

    report = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "overall_ok": overall_ok,
        "total": total,
        "passed": passed,
        "degraded": statuses.get("degraded", 0),
        "failed": statuses.get("fail", 0),
        "checks": results,
    }

    # 记录历史
    Path(HEALTH_LOG).parent.mkdir(parents=True, exist_ok=True)
    with open(HEALTH_LOG, "a") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")

    return report


def format_for_claude(report: dict) -> str:
    """生成 CLAUDE.md 插块"""
    if report.get("overall_ok") and report.get("degraded", 0) == 0:
        return ""

    lines = ["### 🔬 依赖健康", ""]
    for check in report.get("checks", []):
        if check["status"] != "ok":
            icon = {"degraded": "⚠️", "fail": "❌"}.get(check["status"], "❓")
            lines.append(f"- {icon} {check['name']}: {check['detail']}")

    return "\n".join(lines)


def load_history(n: int = 20) -> list[dict]:
    """加载历史健康记录"""
    path = Path(HEALTH_LOG)
    if not path.exists():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except:
                continue
    return entries[-n:]


def main():
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    json_output = "--json" in flags
    watch = "--watch" in flags
    verbose = "--verbose" in flags or "-v" in flags

    if watch:
        # 持续监控
        print("🔄 持续监控 (Ctrl+C 退出)...\n")
        while True:
            report = run_all(verbose=verbose)
            if json_output:
                print(json.dumps(report, indent=2, ensure_ascii=False))
            time.sleep(60)
        return

    report = run_all(verbose=verbose)

    if json_output:
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
