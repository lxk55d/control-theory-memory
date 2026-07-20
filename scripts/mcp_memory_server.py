#!/usr/bin/env python3
"""
MCP Memory Server — 将记忆系统暴露为 MCP 工具接口。

让 Claude Code 在会话中直接搜索、查看、控制记忆系统。

使用：
  pip3 install mcp     # 依赖
  python3 mcp_memory_server.py   # 启动 (stdio transport)
"""

import json
import os
import sys
import re as re_module
from pathlib import Path

# 添加脚本目录
SCRIPTS_DIR = os.path.expanduser("~/scripts")
sys.path.insert(0, SCRIPTS_DIR)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("memory-system", instructions="""
记忆系统 MCP 服务器 — 管理基于文件的自调节记忆系统。
提供记忆搜索、查看、流水线触发、健康检查、知识空白检测等功能。
支持渐进式回忆：search_memories_index (L1) → get_memory_compact → get_memory (L2)。
所有记忆文件存储在 ~/.claude/projects/-home-lxk/memory/ 目录下。
""")

# ════════════════════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════════════════════

def _import(module_name: str):
    """导入 scripts 目录下的模块"""
    import importlib
    return importlib.import_module(module_name)


def _estimate_tokens(text: str) -> int:
    """粗略估算文本的 token 数（中英混合，中文 ~1.5 char/tok，英文 ~4 char/tok）"""
    import re
    chinese_chars = len(re.findall(r'[一-鿿]', text))
    ascii_chars = len(re.findall(r'[a-zA-Z0-9_\-.,!?;:()\[\]{}<>/\\@#$%^&*+=|~`\'\" \n\t]', text))
    return int(chinese_chars / 1.5 + ascii_chars / 4 + 5)


L0_NAMES = {
    "user-profile", "workspace-quant", "scripts-toolset",
    "sharefolder-data", "docker-services",
}


def _is_l0(mem: dict) -> bool:
    """判断是否属于 L0（在精简 MEMORY.md 中可见的高信号记忆）"""
    return mem.get("name", "") in L0_NAMES


def _layer_label(mem: dict) -> str:
    """返回层级标签"""
    return "L0" if _is_l0(mem) else "L2"


# ════════════════════════════════════════════════════════════════════
# MCP 工具
# ════════════════════════════════════════════════════════════════════


@mcp.tool()
def search_memories(query: str, limit: int = 10) -> str:
    """关键词搜索所有记忆文件的 frontmatter 和正文。
    返回匹配的记忆列表，包含名称、描述、保留强度、正文摘要。
    每条结果标注了读取完整内容的 token 成本。
    """
    memcore = _import("memcore")
    memories = memcore.read_all_memories()
    q = query.lower()
    results = []

    for mem in memories:
        name = mem.get("name", "")
        desc = mem.get("description", "")
        body = mem.get("body", "")

        score = 0
        if q in name.lower():
            score += 10
        if q in desc.lower():
            score += 5
        body_matches = body.lower().count(q)
        score += body_matches

        if score > 0:
            full_text = f"{name} {desc} {body}"
            token_estimate = _estimate_tokens(full_text)
            snippet = body[:300].replace("\n", " ")
            if len(body) > 300:
                snippet += "..."
            results.append({
                "name": name,
                "description": desc,
                "type": mem.get("type", ""),
                "retention": mem.get("retention", 0),
                "consolidation": mem.get("consolidation", 0),
                "score": score,
                "token_estimate": token_estimate,
                "snippet": snippet,
                "layer": _layer_label(mem),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:limit]

    if not results:
        return f"未找到包含 \"{query}\" 的记忆。"

    lines = [f"🔍 搜索 \"{query}\": 找到 {len(results)} 条结果\n"]
    for r in results:
        bar = "█" * int(r["retention"] * 20) + "░" * (20 - int(r["retention"] * 20))
        layer_tag = f"[{r['layer']}]" if r["layer"] != "L0" else ""
        lines.append(f"**{r['name']}** {layer_tag}— {r['description']}")
        lines.append(f"  📊 保留: {bar} {r['retention']:.3f} | 巩固: {r['consolidation']:.2f} | 类型: {r['type']} | 📄 ~{r['token_estimate']} tok")
        lines.append(f"  📝 {r['snippet'][:200]}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def search_memories_index(query: str = "", limit: int = 20) -> str:
    """按名称和描述搜索记忆索引（L1 层），只返回元数据不返回正文内容。
    这是渐进式回忆的中间层——比全量 MEMORY.md 索引更完整，但比 get_memory 节省 token。
    适合"浏览有什么"或"搜索哪个记忆文件可能包含我需要的信息"。
    每条结果标注了读取完整内容的 token 成本，方便按需取用。
    """
    memcore = _import("memcore")
    memories = memcore.read_all_memories()
    q = query.lower()

    results = []
    for mem in memories:
        name = mem.get("name", "")
        desc = mem.get("description", "")
        body = mem.get("body", "")
        full_text = f"{name} {desc} {body}"
        token_estimate = _estimate_tokens(full_text)

        score = 0
        if not q:
            score = 1  # 无查询时全部返回
        elif q in name.lower():
            score += 10
        elif q in desc.lower():
            score += 5
        elif q in body.lower():
            score += 1

        if score > 0:
            results.append({
                "name": name,
                "description": desc,
                "type": mem.get("type", ""),
                "retention": mem.get("retention", 0),
                "consolidation": mem.get("consolidation", 0),
                "access_count": mem.get("access_count", 0),
                "token_estimate": token_estimate,
                "layer": _layer_label(mem),
            })

    results.sort(key=lambda x: (0 if x["layer"] == "L0" else 1, -x["retention"], -x["access_count"]))
    results = results[:limit]

    if not results:
        return "（无匹配记忆）"

    l0_count = sum(1 for r in results if r["layer"] == "L0")
    l2_count = sum(1 for r in results if r["layer"] == "L2")

    lines = [f"📚 记忆索引 ({len(results)} 条: L0={l0_count} L2={l2_count})"]
    if q:
        lines[0] = f"🔍 搜索 \"{q}\": {len(results)} 条结果 (L0={l0_count} L2={l2_count})"
    lines.append("")

    for r in results:
        layer_badge = "⭐" if r["layer"] == "L0" else "  "
        bar = "█" * int(r["retention"] * 10) + "░" * (10 - int(r["retention"] * 10))
        lines.append(f"{layer_badge} **{r['name']}** [{r['type']}]")
        lines.append(f"   保留: {bar} {r['retention']:.2f} | 访问: {r['access_count']}次 | 读全: ~{r['token_estimate']} tok")
        lines.append(f"   {r.get('description', '')[:120]}")
        lines.append("")

    lines.append("💡 使用 `get_memory(name)` 读取完整内容，或 `get_memory_compact(name)` 获取压缩摘要。")

    return "\n".join(lines)


@mcp.tool()
def get_memory(name: str) -> str:
    """按名称读取一条记忆的完整内容（frontmatter 元数据 + 正文）。
    参数 name 是记忆文件的 name 字段（不含 .md 后缀）。
    这是 L2 层——完整读取，调用前注意 token 成本。
    """
    memcore = _import("memcore")
    mdir = memcore.MEMORY_DIR
    name_lower = name.lower()

    for fpath in sorted(Path(mdir).glob("*.md")):
        if fpath.name == "MEMORY.md":
            continue
        mem = memcore.read_memory_file(str(fpath))
        if mem and mem.get("name", "").lower() == name_lower:
            fm = mem.get("frontmatter", {})
            body = mem.get("body", "")

            full_text = f"{fm.get('name', name)} {fm.get('description', '')} {body}"
            token_cost = _estimate_tokens(full_text)

            meta = fm.get("metadata", {})
            lines = [f"# {fm.get('name', name)}", ""]
            lines.append(f"**描述**: {fm.get('description', '')}")
            lines.append(f"**类型**: {fm.get('type', '')}")
            lines.append(f"**读取成本**: ~{token_cost} tok")
            lines.append("")
            lines.append("**元数据**:")
            for k, v in meta.items():
                lines.append(f"  - {k}: {v}")
            lines.append("")
            lines.append("---")
            lines.append(body)
            return "\n".join(lines)

    # 尝试模糊匹配
    for fpath in sorted(Path(mdir).glob("*.md")):
        if fpath.name == "MEMORY.md":
            continue
        if name_lower in fpath.stem.lower():
            mem = memcore.read_memory_file(str(fpath))
            if mem:
                fm = mem.get("frontmatter", {})
                return f"找到近似匹配: `{fpath.stem}`（原名: {fm.get('name','?')}）\n使用 get_memory(\"{fpath.stem}\") 获取完整内容。"

    return f"未找到名为 \"{name}\" 的记忆。"


@mcp.tool()
def get_memory_compact(name: str) -> str:
    """获取一条记忆的压缩摘要（~100 tokens），适合快速预览内容。
    比 get_memory（完整读取）更节省 token，比 search_memories_index（纯元数据）更详细。
    分两步：先用此工具确认是否需要读取完整内容。
    """
    memcore = _import("memcore")
    mdir = memcore.MEMORY_DIR
    name_lower = name.lower()

    for fpath in sorted(Path(mdir).glob("*.md")):
        if fpath.name == "MEMORY.md":
            continue
        mem = memcore.read_memory_file(str(fpath))
        if mem and mem.get("name", "").lower() == name_lower:
            fm = mem.get("frontmatter", {})
            body = mem.get("body", "")
            meta = fm.get("metadata", {})

            # 构造压缩摘要
            desc = fm.get("description", "?")
            mem_type = fm.get("type", "?")
            retention = meta.get("retention_strength", "?")
            consolidation = meta.get("consolidation_level", "?")
            access_count = meta.get("access_count", 0)

            full_text = f"{fm.get('name', name)} {desc} {body}"
            full_cost = _estimate_tokens(full_text)

            # 正文压缩到 ~50 tokens
            body_compact = body[:400].replace("\n", " ")
            if len(body) > 400:
                body_compact += "..."

            lines = [
                f"📋 **{fm.get('name', name)}** — {desc}",
                f"   类型: {mem_type} | 保留: {retention} | 巩固: {consolidation} | 访问: {access_count}次",
                f"   完整读取: ~{full_cost} tok",
            ]
            if body.strip():
                lines.append(f"   概要: {body_compact[:300]}")
            else:
                lines.append(f"   ⏭ 正文为空（占位记忆）")

            return "\n".join(lines)

    # 模糊匹配
    for fpath in sorted(Path(mdir).glob("*.md")):
        if fpath.name == "MEMORY.md":
            continue
        if name_lower in fpath.stem.lower():
            mem = memcore.read_memory_file(str(fpath))
            if mem:
                fm = mem.get("frontmatter", {})
                return f"找到近似匹配: `{fpath.stem}`（原名: {fm.get('name','?')}）\n使用 get_memory_compact(\"{fpath.stem}\") 获取摘要。"

    return f"未找到名为 \"{name}\" 的记忆。"


@mcp.tool()
def list_memories(filter_type: str = "") -> str:
    """列出所有记忆文件，可选按类型筛选（memory|reference）。
    返回记忆名称、描述、保留强度、巩固度、分类、类型。
    """
    memcore = _import("memcore")
    memories = memcore.read_all_memories()

    if filter_type:
        memories = [m for m in memories if m.get("type", "") == filter_type]

    if not memories:
        return "（无记忆）" if not filter_type else f"未找到类型为 \"{filter_type}\" 的记忆。"

    # 统计
    total = len(memories)
    types = {}
    classifications = {"活跃": 0, "休眠": 0, "低价值": 0}

    lines = [f"📚 记忆总数: {total}", ""]

    for m in memories:
        ret = m.get("retention", 0)
        if ret >= 0.8:
            cls = "活跃"
        elif ret >= 0.4:
            cls = "休眠"
        else:
            cls = "低价值"
        classifications[cls] = classifications.get(cls, 0) + 1

        t = m.get("type", "?")
        types[t] = types.get(t, 0) + 1

        layer = _layer_label(m)
        layer_tag = f"[{layer}] " if layer == "L2" else ""

        bar = "█" * int(ret * 20) + "░" * (20 - int(ret * 20))
        lines.append(f"**{m['name']}** {layer_tag}")
        lines.append(f"  📊 {bar} {ret:.3f} | 巩固: {m.get('consolidation',0):.2f} | 访问: {m.get('access_count',0)}次 | 类型: {t}")
        lines.append(f"  {m.get('description','')[:100]}")

    lines.append("")
    lines.append(f"**概况**: 活跃={classifications['活跃']} 休眠={classifications['休眠']} 低价值={classifications['低价值']}")
    lines.append(f"**类型分布**: {', '.join(f'{k}={v}' for k, v in sorted(types.items()))}")

    return "\n".join(lines)


@mcp.tool()
def run_pipeline(stage: str = "all") -> str:
    """运行记忆系统自迭代流水线的一个或多个阶段。
    stage 参数：
    - "all" — 完整流水线（默认）
    - "forgetting" — 遗忘衰减扫描（第一回路）
    - "pid" — PID 自适应调参（第二回路）
    - "status" — 更新 CLAUDE.md 状态块
    """
    hook = _import("memory_session_hook")
    forgetting = _import("forgetting_controller")
    memcore = _import("memcore")

    if stage == "forgetting":
        config = memcore.load_config()
        stats = forgetting.scan_memories(config, dry_run=False)
        return (
            f"✅ 遗忘扫描完成\n"
            f"  扫描: {stats['scanned']} 条\n"
            f"  活跃: {stats['active']} | 休眠: {stats['dormant']} | 低价值: {stats['critical']}\n"
            f"  已更新: {stats['updated']} 条"
        )

    if stage == "pid":
        config = memcore.load_config()
        pid = _import("pid_controller")
        memories_list = memcore.read_all_memories()
        observed = pid.observe_memory_state(memories_list)
        pid_state = memcore.load_pid_state()
        new_config, new_pid_state, log_entry = pid.tune_parameters(
            observed, config, pid_state=pid_state, dry_run=False
        )
        memcore.append_history(log_entry)
        return (
            f"✅ PID 调参完成 (第 {new_pid_state.get('iteration', '?')} 轮)\n"
            f"  base_forget_rate: {new_config.get('base_forget_rate', '?')}\n"
            f"  theta_vital: {new_config.get('theta_vital', '?')}\n"
            f"  access_boost: {new_config.get('access_boost', '?')}"
        )

    if stage == "status":
        status = _import("generate_status")
        block = status.generate_status_block()
        status.update_claude_md(block)
        return "✅ CLAUDE.md 状态块已更新"

    if stage == "enrich":
        enricher = _import("memory_enricher")
        result = enricher.enrich_all(dry_run=False)
        return f"✅ 记忆完善完成: {result.get('enriched', 0)} stub + {result.get('appended', 0)} 已有追加"

    if stage == "meta":
        meta = _import("meta_learner")
        memories_list = meta.read_memory_files()
        config = meta.load_config()
        pid_state = meta.load_pid_state()
        history = meta.load_history(50)
        suggestions = meta.generate_suggestions(memories_list, config, pid_state, history)
        # 尝试合并
        merged = meta.auto_merge_duplicates(memories_list, dry_run=False)
        if suggestions:
            lines = [f"✅ 元学习诊断完成 ({len(suggestions)} 条建议)"]
            for s in suggestions[:10]:
                lines.append(f"  - [{s.get('severity','?')}] {s.get('diagnosis','')}")
            if merged:
                lines.append(f"  合并: {len(merged)} 组")
            return "\n".join(lines)
        return "✅ 元学习诊断完成，未发现问题"

    if stage == "health":
        return system_status()

    # "all" — 完整流水线
    hook.log = lambda msg: None  # 静默运行
    config = memcore.load_config()
    stats = forgetting.scan_memories(config, dry_run=False)
    if stats.get("memories"):
        pid = _import("pid_controller")
        observed = pid.observe_memory_state(stats["memories"])
        pid_state = memcore.load_pid_state()
        new_config, new_pid_state, log_entry = pid.tune_parameters(
            observed, config, pid_state=pid_state, dry_run=False
        )
        memcore.append_history(log_entry)
    status = _import("generate_status")
    block = status.generate_status_block()
    status.update_claude_md(block)
    return (
        f"✅ 完整流水线执行完毕\n"
        f"  遗忘扫描: {stats['scanned']} 条 (活跃={stats['active']} 休眠={stats['dormant']})\n"
        f"  PID: 第 {pid_state.get('iteration', '?')} 轮\n"
        f"  CLAUDE.md 状态已更新"
    )


@mcp.tool()
def system_status() -> str:
    """获取记忆系统的健康状态总览，包含：
    - 记忆分布统计
    - 控制参数当前值
    - 外部依赖健康检查
    """
    memcore = _import("memcore")
    memories = memcore.read_all_memories()
    config = memcore.load_config()
    pid_state = memcore.load_pid_state()
    history = memcore.read_history(5)

    total = len(memories)
    active = sum(1 for m in memories if m.get("retention", 0) >= config.get("theta_vital", 0.8))
    dormant = sum(1 for m in memories if config.get("theta_dormant", 0.4) <= m.get("retention", 0) < config.get("theta_vital", 0.8))
    critical = total - active - dormant
    l0_count = sum(1 for m in memories if _is_l0(m))

    lines = ["## 🧠 记忆系统状态", ""]
    lines.append(f"**记忆**: {total} 条 (活跃={active} 休眠={dormant} 低价值={critical})")
    lines.append(f"**层级**: L0={l0_count} L2={total - l0_count} | **遗忘率**: {config.get('base_forget_rate', '?')} | **活跃门限**: {config.get('theta_vital', '?')}")
    lines.append(f"**访问增益**: {config.get('access_boost', '?')} | **PID 迭代**: 第 {pid_state.get('iteration', '?')} 轮")
    lines.append("")

    # 最近历史
    if history:
        lines.append("**最近调节**:")
        for h in history[-3:]:
            ts = h.get("timestamp", "?")[:19]
            fr = h.get("action", {}).get("base_forget_rate", {})
            old_fr = fr.get("old", "?")
            new_fr = fr.get("new", "?")
            lines.append(f"  - {ts}: 遗忘率 {old_fr} → {new_fr}")

    # 健康检查
    try:
        hc = _import("health_check")
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            report_dict = hc.run_all()
        checks = report_dict.get("checks", [])
        ok_count = sum(1 for c in checks if c.get("ok"))
        total_count = len(checks)
        lines.append(f"\n**健康**: {ok_count}/{total_count} 通过")
        for c in checks:
            icon = "✅" if c.get("ok") else ("⚠️" if c.get("status") == "degraded" else "❌")
            lines.append(f"  {icon} {c['name']}: {c.get('detail', '')[:60]}")
    except Exception as e:
        lines.append(f"\n⚠️ 健康检查异常: {e}")

    return "\n".join(lines)


@mcp.tool()
def get_config() -> str:
    """查看当前记忆系统控制器参数配置。
    包含遗忘率、门限值、巩固参数、调度参数等。
    """
    memcore = _import("memcore")
    config = memcore.load_config()
    pid_state = memcore.load_pid_state()
    bounds_path = os.path.join(memcore.MEMORY_DIR, "param_bounds.json")

    lines = ["## 🔧 控制器配置", ""]
    lines.append("### 遗忘模型")
    for k in ["base_forget_rate", "consolidation_boost", "access_boost", "recency_halflife_days"]:
        lines.append(f"  {k}: {config.get(k, '?')}")

    lines.append("")
    lines.append("### 门控阈值")
    for k in ["theta_vital", "theta_dormant", "theta_purge", "centrality_floor"]:
        lines.append(f"  {k}: {config.get(k, '?')}")

    lines.append("")
    lines.append("### PID 状态")
    lines.append(f"  迭代次数: {pid_state.get('iteration', '?')}")
    lines.append(f"  最后更新: {pid_state.get('last_update', '?')}")

    if os.path.exists(bounds_path):
        try:
            bounds = json.loads(Path(bounds_path).read_text())
            lines.append("")
            lines.append("### 参数边界（自适应）")
            for k, v in bounds.items():
                lines.append(f"  {k}: [{v[0]}, {v[1]}]")
        except Exception:
            pass

    return "\n".join(lines)


@mcp.tool()
def detect_gaps() -> str:
    """检测知识空白：高频话题但无对应记忆文件、用户反复询问未建立记忆等。
    返回高优先级缺失知识列表。
    """
    try:
        evo = _import("evolution_engine")
        gap_result = evo.detect_gaps()
    except Exception as e:
        return f"⚠️ 知识空白检测异常: {e}"

    if not gap_result:
        return "✅ 未检测到知识空白。"

    gaps = gap_result if isinstance(gap_result, list) else gap_result.get("gaps", [gap_result])
    high = [g for g in gaps if isinstance(g, dict) and g.get("priority") == "high"]
    medium = [g for g in gaps if isinstance(g, dict) and g.get("priority") == "medium"]

    lines = [f"🔍 共 {len(gaps)} 个知识空白", ""]
    if high:
        lines.append(f"### 🔴 高优先级 ({len(high)})")
        for g in high:
            lines.append(f"  - {g.get('topic', '?')}: {g.get('reason', '')[:120]}")
    if medium:
        lines.append(f"")
        lines.append(f"### 🟡 中优先级 ({len(medium)})")
        for g in medium[:10]:
            lines.append(f"  - {g.get('topic', '?')}: {g.get('reason', '')[:100]}")

    return "\n".join(lines)


@mcp.tool()
def recall_semantic(query: str, limit: int = 5) -> str:
    """通过 Hindsight Recall API 进行语义向量搜索。
    使用中文向量模型 bge-small-zh-1.5 做嵌入，基于语义相似度召回。
    与关键词搜索互补：适合"找相似内容"而非"找精确匹配"。
    """
    try:
        sr = _import("semantic_retriever")
        results = sr.recall(query, limit=limit, tag_filter=None)
    except Exception as e:
        return f"⚠️ Hindsight 检索失败: {e}"

    if not results:
        return "（无相关语义结果）"

    lines = [f"🔍 '{query}' 语义检索 ({len(results)} 条)", ""]
    for r in results:
        score = r.get("score", 0)
        bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        icon = "🧠" if r.get("is_control_memory") else "📝"
        lines.append(f"{icon} [{score:.3f}] {bar}")
        lines.append(f"   {r.get('text', '')[:200]}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def run_forgetting_scan() -> str:
    """立即执行遗忘衰减扫描（第一回路），不触发其他流水线。
    计算每条记忆的 Ebbinghaus 衰减，重新分类活跃/休眠/低价值。
    """
    memcore = _import("memcore")
    forgetting = _import("forgetting_controller")
    config = memcore.load_config()
    stats = forgetting.scan_memories(config, dry_run=False)
    return (
        f"✅ 遗忘扫描完成\n"
        f"  扫描: {stats['scanned']} 条\n"
        f"  活跃: {stats['active']} | 休眠: {stats['dormant']} | 低价值: {stats['critical']}\n"
        f"  已更新: {stats['updated']} 条"
    )


@mcp.tool()
def run_pid_tuning() -> str:
    """立即执行 PID 自适应调参（第二回路）。
    观察记忆分布，计算与目标状态的误差，调整遗忘率等控制参数。
    """
    memcore = _import("memcore")
    pid = _import("pid_controller")
    memories_list = memcore.read_all_memories()
    if not memories_list:
        return "⚠️ 无记忆数据，无法调参。"

    config = memcore.load_config()
    observed = pid.observe_memory_state(memories_list)
    pid_state = memcore.load_pid_state()
    new_config, new_pid_state, log_entry = pid.tune_parameters(
        observed, config, pid_state=pid_state, dry_run=False
    )
    memcore.append_history(log_entry)
    return (
        f"✅ PID 调参完成 (第 {new_pid_state.get('iteration', '?')} 轮)\n"
        f"  观测: 活跃={observed.get('active_ratio',0)*100:.0f}% "
        f"休眠={observed.get('dormant_ratio',0)*100:.0f}% "
        f"低价值={observed.get('critical_ratio',0)*100:.0f}%\n"
        f"  base_forget_rate: {new_config.get('base_forget_rate', '?')}\n"
        f"  theta_vital: {new_config.get('theta_vital', '?')}\n"
        f"  access_boost: {new_config.get('access_boost', '?')}"
    )


@mcp.tool()
def get_pipeline_history(n: int = 10) -> str:
    """查看最近的 PID 调参历史记录。
    返回每次调参的时间、观测状态、控制动作。
    """
    memcore = _import("memcore")
    entries = memcore.read_history(n)

    if not entries:
        return "（无历史记录）"

    lines = [f"📊 最近 {len(entries)} 次调参记录", ""]
    for e in entries:
        ts = e.get("timestamp", "?")[:19]
        obs = e.get("observed", {})
        action = e.get("action", {})
        fr_action = action.get("base_forget_rate", {})
        tv_action = action.get("theta_vital", {})
        ab_action = action.get("access_boost", {})

        lines.append(f"**{ts}** | 迭代 #{e.get('iteration', '?')}")
        if obs:
            lines.append(f"  观测: 活跃={obs.get('active_ratio',0)*100:.0f}% "
                         f"休眠={obs.get('dormant_ratio',0)*100:.0f}% "
                         f"平均保留={obs.get('avg_retention',0):.3f}")
        if fr_action:
            old_v = fr_action.get("old", "?")
            new_v = fr_action.get("new", "?")
            lines.append(f"  动作: 遗忘率 {old_v} → {new_v}")
        if tv_action:
            old_v = tv_action.get("old", "?")
            new_v = tv_action.get("new", "?")
            lines.append(f"        θvital {old_v} → {new_v}")
        if ab_action:
            old_v = ab_action.get("old", "?")
            new_v = ab_action.get("new", "?")
            lines.append(f"        a_boost {old_v} → {new_v}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def run_reflection() -> str:
    """手动触发周级反思：矛盾检测 + 模式提炼 + 健康评分。
    输出写入 memory/reflect/ 目录。
    """
    try:
        import memory_reflector
        fpath = memory_reflector.reflect(force=True)
        if fpath and os.path.exists(fpath):
            content = Path(fpath).read_text()
            # 提取摘要
            lines = content.split("\n")
            summary_lines = [l for l in lines if l.strip() and not l.startswith(">") and not l.startswith("---")]
            summary = "\n".join(summary_lines[:15])
            return f"✅ 反思完成\n  输出: {fpath}\n\n{summary[:500]}"
        return "⚠️ 反思执行未产生输出"
    except Exception as e:
        return f"⚠️ 反思失败: {e}"


@mcp.tool()
def get_latest_reflection() -> str:
    """获取最新的周反思报告内容"""
    reflect_dir = os.path.join(SCRIPTS_DIR.replace("scripts", ""), ".claude/projects/-home-lxk/memory/reflect")
    # 正确路径
    reflect_dir = os.path.expanduser("~/.claude/projects/-home-lxk/memory/reflect")

    files = sorted(Path(reflect_dir).glob("*.md"), reverse=True)
    if not files:
        return "（尚无反思报告）"

    latest = files[0]
    content = Path(latest).read_text()
    return f"📄 {latest.name}\n\n{content[:1500]}"


@mcp.tool()
def run_monthly_compound(year: int = 0, month: int = 0) -> str:
    """生成月度全局摘要（记忆综合报告）。不传参数则生成本月。
    输出写入 memory/compounds/ 目录，并在 MEMORY.md 中链接。
    """
    import memory_compounder as mc
    now = __import__('datetime').datetime.now()
    y = year or now.year
    m = month or now.month
    try:
        mc.main()
        # 查找生成的摘要
        compounds_dir = os.path.expanduser("~/.claude/projects/-home-lxk/memory/compounds")
        fname = f"{y}-{m:02d}.md"
        fpath = os.path.join(compounds_dir, fname)
        if os.path.exists(fpath):
            content = Path(fpath).read_text()
            return f"✅ 月度摘要已生成: {fname}\n\n{content[:800]}"
        return f"✅ 月度摘要已生成（查看 compounds/{fname}）"
    except Exception as e:
        return f"⚠️ 生成失败: {e}"


@mcp.tool()
def generate_dashboard() -> str:
    """生成记忆系统可视化仪表板 HTML。
    输出到桌面 memory-dashboard.html。
    """
    try:
        sys.path.insert(0, os.path.expanduser("~/scripts"))
        import importlib
        gd = importlib.import_module("generate_dashboard")
        html_path = gd.main()
        if isinstance(html_path, str):
            return f"✅ 仪表板已生成: {html_path}"
        return "✅ 仪表板已生成（查看桌面 memory-dashboard.html）"
    except Exception as e:
        return f"⚠️ 仪表板生成失败: {e}"


@mcp.tool()
def get_memory_history(n: int = 10) -> str:
    """查看最近的 PID 调参历史记录。"""
    return get_pipeline_history(n=n)


@mcp.tool()
def rollback_config(iteration: int | None = None) -> str:
    """将控制器配置回滚到指定 PID 迭代轮次。
    如果不指定轮次，列出最近的 10 轮调参历史供选择。
    回滚通过 memory_history.jsonl 中的历史快照重建参数。
    """
    memcore = _import("memcore")
    history = memcore.read_history(20)

    if not history:
        return "⚠️ 无历史记录可回滚。"

    if iteration is None:
        lines = ["📋 最近的调参历史（使用 rollback_config(iteration=N) 回滚）:\n"]
        for e in history[-10:]:
            ts = e.get("timestamp", "?")[:19]
            it = e.get("iteration", "?")
            obs = e.get("observed", {})
            act = e.get("action", {})
            fr = act.get("base_forget_rate", {})
            tv = act.get("theta_vital", {})
            old_fr = fr.get("old", "?")
            new_fr = fr.get("new", "?")
            old_tv = tv.get("old", "?")
            new_tv = tv.get("new", "?")
            lines.append(f"  #{it} | {ts} | fr: {old_fr}→{new_fr} | θv: {old_tv}→{new_tv}")
        return "\n".join(lines)

    # 找到目标迭代的历史
    target = None
    for e in history:
        if e.get("iteration") == iteration:
            target = e
            break

    if not target:
        return f"⚠️ 未找到第 {iteration} 轮的调参记录。可用轮次: {sorted(set(h.get('iteration') for h in history if h.get('iteration')))}"

    # 从目标记录恢复参数
    config = memcore.load_config()
    pid_state = memcore.load_pid_state()
    target_action = target.get("action", {})

    for param_key in ["base_forget_rate", "theta_vital", "access_boost"]:
        action = target_action.get(param_key, {})
        if "old" in action:
            config[param_key] = action["old"]

    # 恢复 PID state
    target_obs = target.get("observed", {})
    if target_obs:
        pid_state["integral"]["fr"] = 0
        pid_state["iteration"] = iteration

    # 写入
    import json as _json
    Path(memcore.CONFIG_PATH).write_text(_json.dumps(config, indent=2, ensure_ascii=False))
    memcore.save_pid_state(pid_state)

    return (
        f"✅ 已回滚到第 {iteration} 轮\n"
        f"  遗忘率: {config.get('base_forget_rate', '?')}\n"
        f"  活跃门限: {config.get('theta_vital', '?')}\n"
        f"  访问增益: {config.get('access_boost', '?')}"
    )


# ════════════════════════════════════════════════════════════════════
# 启动
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 导入所有依赖，确保可用
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
