#!/usr/bin/env python3
"""
记忆系统核心库 — 公共基础设施。
剥离自 forgetting_controller.py / pid_controller.py / meta_learner.py 的重复代码。

包含：
- frontmatter 解析/构建
- 配置加载
- PID 状态持久化
- 历史记录管理
- 通用文件读取
"""

import json
import os
import re
import datetime
from pathlib import Path

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
CONFIG_PATH = os.path.join(MEMORY_DIR, "controller_config.json")
PID_STATE_PATH = os.path.join(MEMORY_DIR, "pid_state.json")
HISTORY_PATH = os.path.join(MEMORY_DIR, "memory_history.jsonl")


# ════════════════════════════════════════════════════════════════════
# frontmatter 解析
# ════════════════════════════════════════════════════════════════════

def parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 frontmatter，返回 (元数据, 正文)"""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    fm_text = parts[1].strip()
    body = parts[2].strip()
    metadata = {}
    stack = [metadata]
    current_dict = metadata
    for line in fm_text.split("\n"):
        if line.startswith("  ") or line.startswith("\t"):
            stripped = line.strip()
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                current_dict[key.strip()] = _parse_val(val.strip())
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if val == "":
                new_dict = {}
                current_dict[key] = new_dict
                stack.append(new_dict)
                current_dict = new_dict
            else:
                current_dict[key] = _parse_val(val)
                stack = stack[:1]
                current_dict = stack[0]
    return metadata, body


def _parse_val(val: str):
    if val.lower() in ("true",): return True
    if val.lower() in ("false",): return False
    if val.lower() in ("null", "~"): return None
    try:
        return float(val) if "." in val else int(val)
    except ValueError:
        pass
    return val.strip("\"'")


def build_frontmatter(metadata: dict) -> str:
    """从元数据重建 frontmatter 字符串"""
    lines = ["---"]
    for key, val in metadata.items():
        if isinstance(val, dict):
            lines.append(f"{key}:")
            for k, v in val.items():
                lines.append(f"  {k}: {v}")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# 记忆文件读取
# ════════════════════════════════════════════════════════════════════

def read_memory_file(path: str) -> dict | None:
    """读取一个记忆文件，返回结构化 dict"""
    try:
        content = Path(path).read_text(encoding="utf-8")
    except Exception:
        return None
    if not content.startswith("---"):
        return None
    fm, body = parse_frontmatter(content)
    if not fm:
        return None
    return {
        "frontmatter": fm,
        "body": body,
        "path": path,
        "name": fm.get("name", Path(path).stem),
        "fname": Path(path).name,
    }


def read_all_memories(memory_dir: str = None) -> list[dict]:
    """读取 memory_dir 下所有记忆文件"""
    mdir = Path(memory_dir or MEMORY_DIR)
    memories = []
    for fpath in sorted(mdir.glob("*.md")):
        if fpath.name == "MEMORY.md":
            continue
        mem = read_memory_file(str(fpath))
        if mem:
            # 提取额外字段 — 优先从 metadata 下读取，兼顾平铺结构
            fm = mem["frontmatter"]
            body = mem["body"]
            import re as rx

            # 辅助：从顶层或 metadata 下取值
            def _get(key: str, default):
                meta = fm.get("metadata", {}) or {}
                val = meta.get(key)
                if val is None:
                    val = fm.get(key)
                return val if val is not None else default

            mem["description"] = fm.get("description", "")
            mem["type"] = _get("type", "memory")
            mem["consolidation"] = float(_get("consolidation_level", 0.3))
            mem["retention"] = float(_get("retention_strength", 0.5))
            mem["access_count"] = int(_get("access_count", 0))
            mem["created"] = _get("created", "")
            mem["modified"] = _get("modified", "")
            mem["is_auto"] = "自动" in body or "待后续会话完善" in (fm.get("description", ""))
            mem["is_hindsight"] = mem["name"].lower().startswith("hindsight-")
            mem["body_length"] = len(body)
            memories.append(mem)
    return memories


# ════════════════════════════════════════════════════════════════════
# 配置加载
# ════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "base_forget_rate": 0.03,
    "consolidation_boost": 0.5,
    "access_boost": 0.15,
    "recency_halflife_days": 7,
    "theta_vital": 0.8,
    "theta_dormant": 0.4,
    "theta_purge": 0.15,
    "centrality_floor": 0.05,
    "initial_retention": 0.9,
    "initial_consolidation": 0.3,
    "default_forget_rate": 0.03,
    "default_centrality": 0.1,
    "scan_interval_hours": 24,
    "archive_threshold_days": 90,
}


def load_config(path: str = None) -> dict:
    """加载控制器配置"""
    cfg_path = Path(path or CONFIG_PATH)
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text())
        except Exception:
            pass
    Path(cfg_path.parent).mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False))
    return dict(DEFAULT_CONFIG)


def save_config(config: dict, path: str = None) -> bool:
    """保存控制器配置"""
    cfg_path = Path(path or CONFIG_PATH)
    try:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
        return True
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════════
# PID 状态管理
# ════════════════════════════════════════════════════════════════════

def load_pid_state(path: str = None) -> dict:
    p = Path(path or PID_STATE_PATH)
    if p.exists():
        try:
            state = json.loads(p.read_text())
            # 验证：如果迭代与 history 不匹配，以 history 为准
            try:
                hp = Path(path.replace("pid_state.json", "memory_history.jsonl") if path else HISTORY_PATH)
                if hp.exists():
                    max_iter = 0
                    with open(hp) as f:
                        for line in f:
                            try:
                                e = json.loads(line)
                                it = e.get("iteration")
                                if it is not None and isinstance(it, (int, float)):
                                    max_iter = max(max_iter, int(it))
                            except Exception:
                                pass
                    state_iter = state.get("iteration", 0)
                    if state_iter is not None and isinstance(state_iter, (int, float)):
                        state_iter = int(state_iter)
                    else:
                        state_iter = 0
                    if max_iter > state_iter:
                        state["iteration"] = max_iter
            except Exception:
                pass
            return state
        except Exception:
            pass
    return {"integral": {}, "prev_error": {}, "iteration": 0, "last_update": None}


def save_pid_state(state: dict, path: str = None):
    Path(path or PID_STATE_PATH).write_text(json.dumps(state, indent=2, ensure_ascii=False))


# ════════════════════════════════════════════════════════════════════
# 文件解析辅助函数（供各脚本统一调用）
# ════════════════════════════════════════════════════════════════════

def file_get(content: str, pattern: str, default: str = "") -> str:
    """从文件内容中用正则提取字符串字段，兼容 metadata 嵌套"""
    m = re.search(pattern, content)
    if m:
        return m.group(1).strip()
    return default


def file_float(content: str, pattern: str, default: float = 0.0) -> float:
    """从文件内容中用正则提取浮点数字段"""
    m = re.search(pattern, content)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return default


# ════════════════════════════════════════════════════════════════════
# 历史记录
# ════════════════════════════════════════════════════════════════════

def append_history(entry: dict, path: str = None):
    hp = Path(path or HISTORY_PATH)
    hp.parent.mkdir(parents=True, exist_ok=True)
    with open(hp, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_history(n: int = 20, path: str = None) -> list[dict]:
    hp = Path(path or HISTORY_PATH)
    if not hp.exists():
        return []
    entries = []
    with open(hp) as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    return entries[-n:]


# ════════════════════════════════════════════════════════════════════
# 会话日志
# ════════════════════════════════════════════════════════════════════

def find_session_logs(project_dir: str = None) -> list[Path]:
    """找到项目目录下的所有会话日志"""
    pdir = Path(project_dir or os.path.dirname(MEMORY_DIR))
    return sorted(pdir.glob("*.jsonl"), key=os.path.getmtime, reverse=True)
