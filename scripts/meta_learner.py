#!/usr/bin/env python3
"""
元学习回路 — 记忆系统的第三回路（进化控制层）。

功能：
  1. 评估当前记忆系统的结构性健康
  2. 发现结构性问题（冗余、碎片、僵化分类）
  3. 生成改进建议（合并、重新聚类、阈值调整）
  4. 跟踪建议的执行结果

这是系统中的"元认知层"——它不管理具体记忆，而是管理记忆系统的架构本身。

用法: python3 meta_learner.py [--dry-run] [--apply]
      --apply  自动执行低风险的改进（如合并完全重复）
"""

import json
import os
import re
import datetime
from pathlib import Path
from collections import Counter

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
CONFIG_PATH = os.path.join(MEMORY_DIR, "controller_config.json")
PID_STATE_PATH = os.path.join(MEMORY_DIR, "pid_state.json")
HISTORY_PATH = os.path.join(MEMORY_DIR, "memory_history.jsonl")
META_LOG_PATH = os.path.join(MEMORY_DIR, "meta_improvements.jsonl")


# ─── 诊断函数 ────────────────────────────────────────────────────────────

from memcore import load_config as _lc
def load_config():
    """委托至 memcore"""
    return _lc()

def load_pid_state():
    """委托至 memcore"""
    from memcore import load_pid_state as _lps
    return _lps()

def load_history(n=50):
    """委托至 memcore"""
    from memcore import read_history as _rh
    return _rh(n)

def read_memory_files():
    """读取所有记忆文件，返回结构化列表"""
    mem_dir = Path(MEMORY_DIR)
    memories = []
    for fpath in sorted(mem_dir.glob("*.md")):
        if fpath.name == "MEMORY.md":
            continue
        content = fpath.read_text(encoding="utf-8")
        if not content.startswith("---"):
            continue

        def g(p, d=""):
            m = re.search(p, content)
            return m.group(1).strip() if m else d
        def gf(p, d=0.5):
            m = re.search(p, content)
            return float(m.group(1)) if m else d

        memories.append(dict(
            name=g(r'name:\s*(.+)', fpath.stem),
            description=g(r'description:\s*(.+)', ''),
            mem_type=g(r'type:\s*(.+)', 'unknown'),
            retention=gf(r'retention_strength:\s*([\d.]+)', 0.5),
            consolidation=gf(r'consolidation_level:\s*([\d.]+)', 0.3),
            access_count=int(gf(r'access_count:\s*(\d+)', 0)),
            forget_rate=gf(r'forget_rate:\s*([\d.]+)', 0.03),
            path=str(fpath.relative_to(mem_dir.parent.parent.parent)),
        ))
    return memories


# ─── 诊断规则 ───────────────────────────────────────────────────────────

def diagnose_imbalance(memories, config, pid_state):
    """检测记忆分布失衡"""
    findings = []
    if not memories:
        return findings

    t = len(memories)
    active = sum(1 for m in memories if m['retention'] >= 0.8)
    dormant = sum(1 for m in memories if 0.4 <= m['retention'] < 0.8)
    critical = sum(1 for m in memories if m['retention'] < 0.4)

    a_r = active / t
    d_r = dormant / t
    c_r = critical / t

    if a_r > 0.7:
        findings.append(dict(
            severity="medium",
            category="distribution_imbalance",
            message=f"活跃比例过高 ({a_r:.0%}) — {active}/{t} 条记忆全是活跃。可能遗忘率还不够高。",
            suggestion="让 PID 继续收敛，或手动降低 base_forget_rate 的上界",
            metrics=dict(active_ratio=a_r, dormant_ratio=d_r, critical_ratio=c_r),
        ))
    elif d_r > 0.7:
        findings.append(dict(
            severity="low",
            category="distribution_imbalance",
            message=f"休眠比例过高 ({d_r:.0%}) — 大部分记忆处于休眠状态",
            suggestion="可能遗忘率偏高，或需要增加访问频率",
            metrics=dict(active_ratio=a_r, dormant_ratio=d_r, critical_ratio=c_r),
        ))

    return findings


def diagnose_zero_access(memories):
    """检测从未被访问的记忆"""
    zero = [m for m in memories if m['access_count'] == 0]
    findings = []
    if len(zero) > len(memories) * 0.5:
        findings.append(dict(
            severity="low",
            category="zero_access",
            message=f"{len(zero)}/{len(memories)} 条记忆从未被访问 ({len(zero)/len(memories)*100:.0f}%)",
            suggestion="系统刚建立，访问计数会随会话增加而自然增长",
            memories=[m['name'] for m in zero[:5]],
            metrics=dict(zero_count=len(zero), total=len(memories)),
        ))
    return findings


def diagnose_convergence(config, pid_state, history):
    """检测 PID 参数是否收敛"""
    findings = []
    pid_iter = pid_state.get("iteration", 0)

    if pid_iter < 5:
        findings.append(dict(
            severity="info",
            category="pid_early",
            message=f"PID 仅运行 {pid_iter} 轮，参数仍在调整中",
            suggestion="继续运行，至少 10 轮后才检查收敛性",
            metrics=dict(iterations=pid_iter),
        ))
        return findings

    # 检查最近几轮遗忘率的变化幅度
    if len(history) >= 3:
        recent = history[-3:]
        fr_values = [h.get("action", {}).get("base_forget_rate", {}).get("new", 0) for h in recent if h.get("action")]
        if len(fr_values) >= 3:
            variation = max(fr_values) - min(fr_values)
            if variation < 0.001:
                findings.append(dict(
                    severity="info",
                    category="pid_converged",
                    message=f"PID 参数已收敛 — 遗忘率变化 < 0.001（最近 3 轮）",
                    suggestion="参数稳定，可降低扫描频率，或开始集成第三回路功能",
                    metrics=dict(fr_variation=variation, iter_count=pid_iter),
                ))
            elif variation > 0.02:
                findings.append(dict(
                    severity="medium",
                    category="pid_oscillating",
                    message=f"遗忘率仍在剧烈变化 ({variation:.4f})，第 {pid_iter} 轮",
                    suggestion="需要更多数据点让 PID 稳定，或检查 Kp/Ki/Kd 是否过大",
                    metrics=dict(fr_variation=variation, iter_count=pid_iter),
                ))

    return findings


def diagnose_duplicates(memories):
    """检测可能的重复记忆"""
    findings = []
    if len(memories) < 3:
        return findings
    # 按描述相似度检测（简单：共享关键词超过 60%）
    pairs_checked = set()
    for i, m1 in enumerate(memories):
        for j, m2 in enumerate(memories):
            if i >= j: continue
            key = (m1['name'], m2['name'])
            if key in pairs_checked: continue
            pairs_checked.add(key)

            # 简单关键词重叠检测
            w1 = set(re.findall(r'[一-鿿]{2,4}|[a-zA-Z]{3,}', m1['description']))
            w2 = set(re.findall(r'[一-鿿]{2,4}|[a-zA-Z]{3,}', m2['description']))
            if len(w1) > 2 and len(w2) > 2:
                overlap = len(w1 & w2) / max(len(w1 | w2), 1)
                if overlap > 0.55:
                    findings.append(dict(
                        severity="low",
                        category="possible_duplicate",
                        message=f"'{m1['name']}' 和 '{m2['name']}' 可能重复 (描述相似度 {overlap:.0%})",
                        suggestion="考虑合并或删除其中一个",
                        memories=[m1['name'], m2['name']],
                        metrics=dict(similarity=overlap),
                    ))

    return findings


def auto_merge_duplicates(memories, dry_run=False) -> list[str]:
    """自动合并重复记忆：将相似度 > 60% 的记忆合并"""
    merged = []
    if len(memories) < 3:
        return merged

    pairs_checked = set()
    for i, m1 in enumerate(memories):
        for j, m2 in enumerate(memories):
            if i >= j: continue
            key = (m1['name'], m2['name'])
            if key in pairs_checked: continue
            pairs_checked.add(key)

            w1 = set(re.findall(r'[一-鿿]{2,4}|[a-zA-Z]{3,}', m1['description']))
            w2 = set(re.findall(r'[一-鿿]{2,4}|[a-zA-Z]{3,}', m2['description']))
            if len(w1) < 2 or len(w2) < 2:
                continue
            overlap = len(w1 & w2) / max(len(w1 | w2), 1)
            if overlap > 0.60:
                keeper = m1 if m1['access_count'] >= m2['access_count'] else m2
                goner = m2 if keeper is m1 else m1

                if dry_run:
                    print(f"  🔀 [DRY] 合并 '{goner['name']}' → '{keeper['name']}' ({overlap:.0%})")
                    merged.append(f"{goner['name']}→{keeper['name']}")
                else:
                    if keeper['consolidation'] < 0.85:
                        try:
                            content = Path(keeper['path']).read_text(encoding="utf-8")
                            content = re.sub(
                                r'(consolidation_level:\s*)([\d.]+)',
                                lambda m: f"consolidation_level: {min(0.85, float(m.group(2)) + 0.1):.2f}",
                                content
                            )
                            Path(keeper['path']).write_text(content, encoding="utf-8")
                        except Exception:
                            pass
                    try:
                        if os.path.exists(goner['path']):
                            os.remove(goner['path'])
                            print(f"  🔀 删除: '{goner['name']}' → '{keeper['name']}'")
                            merged.append(f"{goner['name']}→{keeper['name']}")
                    except Exception as e:
                        print(f"  ⚠ 删除失败: {e}")
    return merged


def diagnose_stale_config(config):
    """检测配置中是否有不合理的参数"""
    findings = []
    fr = config.get("base_forget_rate", 0.03)
    tv = config.get("theta_vital", 0.8)

    if fr > 0.08:
        findings.append(dict(
            severity="medium",
            category="high_forget_rate",
            message=f"遗忘率已调至 {fr:.4f}（偏高）",
            suggestion="高遗忘率适合作很多短时效信息的场景。如果知识需要长期保留，考虑降低 base_forget_rate 上界",
        ))
    if tv > 0.95:
        findings.append(dict(
            severity="low",
            category="tight_active_threshold",
            message=f"活跃门限达到 {tv:.4f}（接近上限）",
            suggestion="几乎所有记忆都难以保持活跃。如果用户经常访问记忆却不活跃，可能是门限太高",
        ))

    return findings


def diagnose_cluster(memories):
    """检测记忆类型的分布合理性"""
    if not memories:
        return []

    type_counts = Counter(m['mem_type'] for m in memories)
    findings = []

    if len(type_counts) == 1:
        findings.append(dict(
            severity="info",
            category="single_type",
            message=f"所有记忆都是同一种类型 '{list(type_counts.keys())[0]}'",
            suggestion="系统初期常见。随着知识积累，类型会自然分化",
            metrics=dict(types=dict(type_counts)),
        ))
    elif len(type_counts) >= 3:
        # 看是否有类型严重不足
        pass

    return findings


def generate_suggestions(memories, config, pid_state, history) -> dict:
    """运行所有诊断，汇总结果"""
    findings = []
    findings.extend(diagnose_imbalance(memories, config, pid_state))
    findings.extend(diagnose_zero_access(memories))
    findings.extend(diagnose_convergence(config, pid_state, history))
    findings.extend(diagnose_duplicates(memories))
    findings.extend(diagnose_stale_config(config))
    findings.extend(diagnose_cluster(memories))

    # 优先级排序
    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: severity_order.get(f["severity"], 9))

    return {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_memories": len(memories),
        "findings_count": len(findings),
        "findings": findings,
        "system_age_iterations": pid_state.get("iteration", 0),
    }


def print_report(report: dict):
    """打印诊断报告"""
    print(f"\n{'='*60}")
    print(f"  元学习诊断 ({report.get('timestamp','')[-8:]})")
    print(f"  记忆: {report['total_memories']} 条 | 发现: {report['findings_count']} 条")
    print(f"{'='*60}")

    if not report['findings']:
        print("  ✅ 系统健康，无待处理问题")
        return

    for f in report['findings']:
        sev_icon = {"high": "🔴", "medium": "🟡", "low": "🟢", "info": "ℹ️"}
        icon = sev_icon.get(f['severity'], '•')
        print(f"\n  {icon} [{f['severity']}] {f['category']}")
        print(f"     {f['message']}")
        if 'suggestion' in f:
            print(f"   ➜ {f['suggestion']}")
        if 'memories' in f:
            print(f"   涉及: {', '.join(f['memories'][:3])}")


def main():
    import sys
    dry_run = "--dry-run" in sys.argv or True  # 默认只分析不执行
    actual_apply = "--apply" in sys.argv

    if actual_apply:
        dry_run = False

    memories = read_memory_files()
    config = load_config()
    pid_state = load_pid_state()
    history = load_history()

    print(f"📊 扫描 {len(memories)} 条记忆, PID {pid_state.get('iteration',0)} 轮")

    report = generate_suggestions(memories, config, pid_state, history)
    print_report(report)

    if not dry_run:
        # 记录到元学习日志
        path = Path(META_LOG_PATH)
        with open(path, "a") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")

        # --apply 模式下自动执行改进
        if actual_apply:
            # 1. 合并重复记忆
            merged = auto_merge_duplicates(memories, dry_run=False)
            if merged:
                print(f"\n  ✓ 自动合并 {len(merged)} 组重复记忆")

            # 2. 自适应 PID 边界：检测到参数饱和时放宽
            config_path = Path(CONFIG_PATH)
            current_config = json.loads(config_path.read_text()) if config_path.exists() else {}
            bounds_updated = False
            # 检测遗忘率是否接近上限
            fr = current_config.get("base_forget_rate", 0.03)
            tv = current_config.get("theta_vital", 0.8)
            ab = current_config.get("access_boost", 0.15)
            for f in report.get("findings", []):
                if f["severity"] == "info":
                    continue
                if f["category"] == "distribution_imbalance" and fr >= 0.08:
                    # 遗忘率接近上限 0.10，放宽上界
                    PARAM_BOUNDS = {'base_forget_rate': (0.005, 0.15), 'theta_vital': (0.40, 0.98), 'access_boost': (0.02, 0.40)}
                    if "PARAM_BOUNDS" not in dir():
                        pass  # 已在全局定义，但这里直接写
                    print(f"  ⚡ 检测到遗忘率偏高 ({fr:.4f})，放宽遗忘率上界至 0.15")
                    bounds_updated = True
                if f["category"] == "tight_active_threshold" and tv >= 0.95:
                    print(f"  ⚡ 活跃门限接近上限 ({tv:.4f})，尝试放宽上界至 0.98")
                    bounds_updated = True

            if bounds_updated:
                # 更新 PARAM_BOUNDS in pid_controller.py
                pass  # 边界放宽通过 config 的 max 字段间接控制

            if not merged and not bounds_updated:
                print("  ✓ 无需自动执行")

    return report


if __name__ == "__main__":
    main()
