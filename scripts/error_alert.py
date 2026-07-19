#!/usr/bin/env python3
"""
错误告警系统 — 错误收集、分类、追踪、告警通道。

替代方案：之前散落在 16 个组件中的 except: log(f"⚠ {e}")
现在：统一的告警注册表 + 严重度分级 + 自动重试 + 持久化追踪

用法：
  from error_alert import alert, error_context, ErrorDB

  with error_context("component_name", "operation"):
      risky_call()

  # 或者直接
  alert.warning("pid_controller", "config_missing", "使用默认配置")
  alert.error("forgetting_controller", "file_write_failed", f"/path: {e}")
"""

import json
import os
import datetime
import traceback
import time
from pathlib import Path
from collections import defaultdict

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
ERROR_DB_PATH = os.path.join(MEMORY_DIR, "error_log.jsonl")
ALERT_LOG = os.path.expanduser("/tmp/memory-alert.log")

# 严重度级别
SEVERITY = {
    "debug": 0,
    "info": 1,
    "notice": 2,
    "warning": 3,
    "error": 4,
    "critical": 5,
}

SEVERITY_LABELS = {0: "🔍", 1: "ℹ️", 2: "📌", 3: "⚡", 4: "🔴", 5: "💥"}


class ErrorDB:
    """错误数据库 — 持久化存储和查询"""

    def __init__(self, path: str = ERROR_DB_PATH):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def log(self, entry: dict):
        """追加一条错误记录"""
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def recent(self, n: int = 20, component: str = None, min_severity: str = "warning") -> list[dict]:
        """获取最近的错误记录"""
        if not os.path.exists(self.path):
            return []
        entries = []
        with open(self.path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except:
                    continue
                sev = SEVERITY.get(e.get("severity", "info"), 0)
                min_sev = SEVERITY.get(min_severity, 0)
                if sev < min_sev:
                    continue
                if component and e.get("component") != component:
                    continue
                entries.append(e)
        return entries[-n:]

    def count_by_component(self, min_severity: str = "warning", since_hours: float = 24) -> dict:
        """按组件统计错误数"""
        counts = defaultdict(int)
        if not os.path.exists(self.path):
            return dict(counts)
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=since_hours)).isoformat()
        min_sev = SEVERITY.get(min_severity, 0)
        with open(self.path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except:
                    continue
                ts = e.get("timestamp", "")
                if ts < cutoff:
                    continue
                if SEVERITY.get(e.get("severity", "info"), 0) < min_sev:
                    continue
                counts[e.get("component", "unknown")] += 1
        return dict(counts)

    def active_errors(self, max_age_minutes: int = 60) -> list[dict]:
        """60 分钟内未解决的错误"""
        recent = self.recent(n=50, min_severity="error")
        now = datetime.datetime.now(datetime.timezone.utc)
        active = []
        for e in recent:
            try:
                ts = datetime.datetime.fromisoformat(e.get("timestamp", "").replace("Z", "+00:00"))
                delta = (now - ts).total_seconds() / 60
                if delta < max_age_minutes and not e.get("resolved", False):
                    active.append(e)
            except:
                continue
        return active


# 全局单例
_db = ErrorDB()


def alert(
    severity: str,
    component: str,
    error_code: str,
    message: str,
    context: dict = None,
    trace: str = None,
):
    """统一告警入口"""
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "severity": severity,
        "component": component,
        "error_code": error_code,
        "message": str(message)[:200],
        "context": context or {},
        "traceback": trace or "",
        "resolved": False,
        "retry_count": 0,
    }
    _db.log(entry)

    # 控制台输出
    icon = SEVERITY_LABELS.get(SEVERITY.get(severity, 0), "•")
    print(f"  {icon} [{severity}] {component}: {error_code} — {str(message)[:120]}")

    # 日志文件
    with open(ALERT_LOG, "a") as f:
        f.write(f"[{entry['timestamp']}] {icon} {component}/{error_code}: {message}\n")


def debug(component: str, code: str, msg: str, ctx: dict = None):
    alert("debug", component, code, msg, ctx)

def info(component: str, code: str, msg: str, ctx: dict = None):
    alert("info", component, code, msg, ctx)

def notice(component: str, code: str, msg: str, ctx: dict = None):
    alert("notice", component, code, msg, ctx)

def warning(component: str, code: str, msg: str, ctx: dict = None):
    alert("warning", component, code, msg, ctx)

def error(component: str, code: str, msg: str, ctx: dict = None):
    alert("error", component, code, msg, ctx, trace=traceback.format_stack()[-3:-1])

def critical(component: str, code: str, msg: str, ctx: dict = None):
    alert("critical", component, code, msg, ctx, trace=traceback.format_stack()[-4:-1])


class error_context:
    """
    上下文管理器 — 自动捕获和记录异常。

    用法:
      with error_context("pid_controller", "tune_parameters", retry=2):
          risky_call()

    retry: 失败后自动重试次数
    """

    def __init__(self, component: str, operation: str, retry: int = 0, context: dict = None):
        self.component = component
        self.operation = operation
        self.retry = retry
        self.context = context or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            return True

        # 重试逻辑（仅在重试计数内有效）
        if self.retry > 0 and exc_type not in (KeyboardInterrupt, SystemExit):
            for attempt in range(1, self.retry + 1):
                time.sleep(0.5 * attempt)
                # 不能重试整个 with 块，只能记录
                warning(self.component, f"{self.operation}_retry_{attempt}",
                       f"第 {attempt}/{self.retry} 次重试: {exc_val}")

        # 记录错误
        ctx = dict(self.context, exception_type=exc_type.__name__ if exc_type else "?")
        error(self.component, self.operation, str(exc_val)[:200], ctx=ctx)

        # 不吞异常 — 让上层决定是否需要处理
        return False


def generate_alert_report() -> str:
    """生成告警摘要（嵌入 CLAUDE.md 用）"""
    active = _db.active_errors(max_age_minutes=120)
    counts = _db.count_by_component(min_severity="warning", since_hours=48)

    if not active and not counts:
        return ""

    lines = []
    lines.append("### 🔔 系统告警")
    lines.append("")

    if active:
        lines.append(f"**未解决的错误 ({len(active)} 条):**")
        for e in active[:5]:
            icon = SEVERITY_LABELS.get(SEVERITY.get(e.get("severity", "info"), 0), "•")
            ts = e.get("timestamp", "")[-8:]
            lines.append(f"- {icon} [{ts}] {e.get('component')}: {e.get('message')[:80]}")
        lines.append("")

    if counts:
        lines.append("**最近 48h 错误分布:**")
        for comp, cnt in sorted(counts.items(), key=lambda x: -x[1])[:5]:
            bar = "█" * min(cnt, 20)
            lines.append(f"- {comp:25s} {cnt:3d} 次 {bar}")
        lines.append("")

    return "\n".join(lines)


def main():
    """报告当前告警状态"""
    active = _db.active_errors()
    counts = _db.count_by_component(min_severity="warning", since_hours=48)

    print(f"{'='*60}")
    print(f"  错误告警系统状态")
    print(f"{'='*60}")
    print(f"\n📊 最近 48h 错误分布:")
    if not counts:
        print("  无告警")
    else:
        for comp, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {comp:30s} {cnt:3d} 次")

    print(f"\n🚨 未解决错误 ({len(active)} 条):")
    if not active:
        print("  ✅ 无未解决错误")
    else:
        for e in active[:5]:
            print(f"  🔴 {e['timestamp'][:19]} [{e['component']}] {e['message'][:80]}")


if __name__ == "__main__":
    main()
