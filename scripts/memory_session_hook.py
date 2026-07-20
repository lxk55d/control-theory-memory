#!/usr/bin/env python3
"""
记忆系统自迭代钩子
在 Claude Code 会话结束时自动触发完整的自迭代流水线：

第一回路: 访问计数 + 遗忘控制器
第二回路: PID 自适应调参
观测层:   会话分析 + 元学习诊断 + 状态报告
"""

import os
import sys
import json
import datetime
from pathlib import Path
from error_alert import error_context, alert, warning as alert_warn

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
SCRIPTS_DIR = os.path.expanduser("~/scripts")
HOOK_LOG = os.path.expanduser("/tmp/memory-hook.log")


def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    with open(HOOK_LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"  📝 {msg}")


def touch_all_memories():
    """所有记忆文件访问计数 +1（表示一次会话被记住了）"""
    count = 0
    for fpath in Path(MEMORY_DIR).glob("*.md"):
        if fpath.name in ("MEMORY.md",):
            continue
        content = fpath.read_text(encoding="utf-8")
        if not content.startswith("---"):
            continue

        import re
        new_content, n = re.subn(
            r'(access_count:\s*)(\d+)',
            lambda m: f"access_count: {int(m.group(2)) + 1}",
            content
        )
        if n > 0:
            fpath.write_text(new_content, encoding="utf-8")
            count += 1

    log(f"✓ 已更新 {count} 条记忆的访问计数")


def run_forgetting_controller():
    """第一回路：遗忘控制器"""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        from forgetting_controller import scan_memories, load_config
        config = load_config()
        stats = scan_memories(config, dry_run=False)
        log(f"✓ 遗忘扫描: {stats['scanned']} 条记忆 | 活跃:{stats['active']} 休眠:{stats['dormant']} 低价值:{stats['critical']}")
        return stats
    except Exception as e:
        from error_alert import alert_warn; alert_warn("forgetting_controller", "exception", str(e)[:100])
        return None


def run_pid_controller(memories):
    """第二回路：PID 调参"""
    if not memories:
        return
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import pid_controller
        config_path = os.path.join(MEMORY_DIR, "controller_config.json")
        config = json.loads(Path(config_path).read_text())
        observed = pid_controller.observe_memory_state(memories)
        pid_state = pid_controller.load_pid_state()
        new_config, pid_state, log_entry = pid_controller.tune_parameters(
            observed, config, pid_state=pid_state, dry_run=False
        )
        pid_controller.append_history(log_entry)
        log(f"✓ PID 调参: base_forget_rate={new_config['base_forget_rate']:.4f}")
    except Exception as e:
        from error_alert import alert_warn; alert_warn("pid_controller", "exception", str(e)[:100])


def run_session_analyzer():
    """观测层：分析当前会话，提取新信息，自动创建新记忆"""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import session_analyzer
        session_path = session_analyzer.find_latest_session()
        if session_path:
            analysis = session_analyzer.analyze_log(session_path, dry_run=False)
            novel = session_analyzer.extract_novel_topics(analysis)
            if novel:
                log(f"🔍 新主题发现: {', '.join(novel[:5])}")
            else:
                log(f"🔍 无新主题")
            # 自动创建记忆
            created = session_analyzer.auto_create_memories(analysis, dry_run=False)
            if created:
                log(f"🆕 新记忆文件: {', '.join(created)}")
                # 立即完善新创建的记忆（在同一轮中完成）
                try:
                    import memory_enricher as me
                    session_paths = me.find_session_logs()
                    for name in created:
                        fpath = Path(MEMORY_DIR) / f"{name}.md"
                        if fpath.exists():
                            mem = me.read_memory(str(fpath))
                            if mem and me.is_stub(mem):
                                ok = me.enrich_memory_if_needed(name, mem, session_paths, force=True, dry_run=False)
                                if ok:
                                    log(f"📖 立即完善: {name}")
                except Exception as e2:
                    from error_alert import alert_warn; alert_warn("memory_enricher", "exception", str(e)[:100])
            return analysis
    except Exception as e:
        from error_alert import alert_warn; alert_warn("session_analyzer", "exception", str(e)[:100])
    return None


def run_meta_learner():
    """元学习层：第三回路诊断 + 自动执行"""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import meta_learner as ml
        memories = ml.read_memory_files()
        config = ml.load_config()
        pid_state = ml.load_pid_state()
        history = ml.load_history()
        report = ml.generate_suggestions(memories, config, pid_state, history)

        merged = ml.auto_merge_duplicates(memories, dry_run=False)
        if merged:
            log(f"🔀 合并重复: {', '.join(merged)}")

        if report['findings_count'] > 0:
            top = report['findings'][0]
            log(f"🧠 元学习: {report['findings_count']} 条建议 | [{top['severity']}] {top['category']}")
        else:
            log(f"🧠 元学习: 系统健康")
        return report
    except Exception as e:
        from error_alert import alert_warn; alert_warn("meta_learner", "exception", str(e)[:100])
    return None


def run_memory_enricher():
    """完善层：从会话提取信息丰富记忆内容"""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import memory_enricher as me
        stats = me.enrich_all(dry_run=False, force=False)
        if stats["enriched"] > 0 or stats["appended"] > 0:
            log(f"📖 记忆完善: {stats['enriched']} stub更新 + {stats['appended']} 已有追加")
        else:
            log(f"📖 记忆完善: 无需更新")
        return stats
    except Exception as e:
        from error_alert import alert_warn; alert_warn("memory_enricher", "exception", str(e)[:100])
    return None


def run_memory_linker():
    """关联层：自动发现并建立 [[link]]"""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import memory_linker as ml
        memories = ml.read_all_memories()
        all_links = []
        all_links.extend(ml.find_topic_overlap_links(memories))
        all_links.extend(ml.find_session_cooccur_links(memories))
        links = ml.deduplicate_links(all_links)
        applied = ml.apply_links(links, memories, dry_run=False)
        if applied > 0:
            log(f"🔗 新增关联: {applied} 条 [[link]]")
        else:
            log(f"🔗 关联层: 无新链接")
    except Exception as e:
        from error_alert import alert_warn; alert_warn("memory_linker", "exception", str(e)[:100])


def run_evolution():
    """进化层：知识空白检测"""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import evolution_engine as ev
        report = ev.detect_gaps()
        if report.get("total_gaps", 0) > 0:
            top_gaps = report.get("gaps", [])[:3]
            for g in top_gaps:
                log(f"🧬 空白: [{g['priority']}] {g['topic']}")
        else:
            log(f"🧬 进化层: 无知识空白")
        return report
    except Exception as e:
        from error_alert import alert_warn; alert_warn("evolution_engine", "exception", str(e)[:100])
    return None


def run_health():
    """健康层：外部依赖检查"""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import health_check as hc
        report = hc.run_all(verbose=False)
        if report.get("failed", 0) > 0:
            log(f"\U0001f52c 健康: {report['failed']} 项异常")
        elif report.get("degraded", 0) > 0:
            log(f"\U0001f52c 健康: {report['degraded']} 项降级")
        else:
            log(f"\U0001f52c 健康: 全部通过")
    except Exception as e:
        log(f"\u26a0 健康检查出错: {e}")


def run_semantic_sync():
    """检索层：将核心记忆推送到 Hindsight 语义索引"""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import json, urllib.request, os, re
        from pathlib import Path
        API = "http://127.0.0.1:8888/v1/default/banks/hermes"
        mem_dir = MEMORY_DIR
        pushed = 0
        skipped = 0
        for f in sorted(os.listdir(mem_dir)):
            if not f.endswith('.md') or f == 'MEMORY.md' or f.startswith('hindsight-'):
                continue
            content = Path(os.path.join(mem_dir, f)).read_text()
            if not content.startswith('---'):
                continue
            cl_m = re.search(r'consolidation_level:\s*([\d.]+)', content)
            if not cl_m or float(cl_m.group(1)) < 0.5:
                continue
            nm = re.search(r'name:\s*(.+)', content)
            name = nm.group(1).strip() if nm else f.replace('.md', '')
            desc_m = re.search(r'description:\s*(.+)', content)
            desc = desc_m.group(1).strip() if desc_m else ""
            body_parts = content.split('---', 2)
            body = body_parts[2].strip() if len(body_parts) >= 3 else ""
            try:
                data = json.dumps({"items": [{"content": f"[控制论记忆] {name}: {desc}\n\n{body[:1000]}", "tags": ["control-memory"]}], "async": True}).encode()
                req = urllib.request.Request(f"{API}/memories", data=data, headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=5)
                pushed += 1
            except Exception:
                skipped += 1
        if pushed:
            log(f"🔎 语义索引: {pushed} 条同步")
        else:
            log(f"🔎 语义索引: 无需同步")
    except Exception as e:
        from error_alert import alert_warn; alert_warn("semantic_sync", "exception", str(e)[:100])


def run_reclaimer():
    """回收层：清理低信号记忆"""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import memory_reclaimer as mr
        stats = mr.reclaim_all(dry_run=False)
        if stats.get("removed", 0) > 0:
            log(f"🗑 回收: {stats['removed']} 条低信号记忆")
        else:
            log(f"🗑 回收层: 无需清理")
    except Exception as e:
        from error_alert import alert_warn; alert_warn("memory_reclaimer", "exception", str(e)[:100])


def run_collaboration():
    """协作层：导出 + 项目桥接 + Hindsight 同步"""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import collaboration_engine as ce
        # 导出（轻量写入，不阻塞）
        export_path = ce.export_memories()
        log(f"📦 导出: {os.path.basename(export_path)}")
        # 项目桥接扫描
        index = ce.scan_and_report()
        other_projects = [p for p in index.get('projects', []) if p['id'] != '-home-lxk']
        if other_projects:
            for p in other_projects:
                log(f"📁 项目 '{p['id']}': {p['memory_count']} 条记忆")
        else:
            log(f"📁 无其他项目包含记忆")
        # Hindsight 同步
        if ce.check_hindsight():
            result = ce.sync_hindsight()
            log(f"↔️ Hindsight: {result.get('pushed',0)}推送/{result.get('pulled',0)}拉取")
        else:
            log(f"↔️ Hindsight: 不可达")
    except Exception as e:
        from error_alert import alert_warn; alert_warn("collaboration_engine", "exception", str(e)[:100])


def run_status_update():
    """更新 CLAUDE.md 状态块"""
    try:
        import generate_status
        block = generate_status.generate_status_block()
        generate_status.update_claude_md(block)
        log("✓ 系统状态已写入 CLAUDE.md")
    except Exception as e:
        from error_alert import alert_warn; alert_warn("generate_status", "exception", str(e)[:100])


def main():
    log("=== 记忆系统自迭代流水线 ===")

    # 第一回路
    log("── 第一回路: 访问更新 + 遗忘控制 ──")
    stats = run_forgetting_controller()

    # 第二回路
    log("── 第二回路: PID 自适应调参 ──")
    if stats:
        run_pid_controller(stats.get("memories", []))

    # 观测层
    log("── 观测层: 会话分析 ──")
    run_session_analyzer()

    # 第三回路
    log("── 元学习层: 系统诊断 ──")
    run_meta_learner()

    # 完善层
    log("── 完善层: 记忆内容丰富 ──")
    run_memory_enricher()

    # 关联层
    log("── 关联层: 自动发现链接 ──")
    run_memory_linker()

    # 进化层
    log("── 进化层: 知识空白检测 ──")
    run_evolution()

    # 协作层
    log("── 协作层: 多项目 + Hindsight ──")
    run_collaboration()

    # 检索层：同步记忆到 Hindsight 索引
    log("── 检索层: 语义索引同步 ──")
    run_semantic_sync()

    # 回收层
    log("── 回收层: 低信号清理 ──")
    run_reclaimer()

    # 健康层
    log("── 健康层: 依赖检查 ──")
    run_health()

    # 状态更新
    run_status_update()

    # 反射层（周级：只在周日运行）
    if datetime.datetime.now().weekday() == 6:
        log("── 反射层: 周级自动反思 ──")
        try:
            import memory_reflector
            memory_reflector.reflect()
            log("✓ 周反思完成")
        except Exception as e:
            from error_alert import alert_warn; alert_warn("memory_reflector", "exception", str(e)[:100])

    log("=== 自迭代完成 ===\n")


if __name__ == "__main__":
    main()
