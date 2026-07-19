#!/usr/bin/env python3
"""
协作层：多项目桥接 + 导出/导入 + Hindsight 同步

功能：
1. 多项目桥接：扫描所有 Claude Code 项目，发现共享知识
2. 导出/导入：便携 JSON 格式 + 版本戳 + 冲突检测
3. Hindsight 同步：控制论记忆 ↔ Hindsight hermes 银行双向同步

用法：
  python3 collaboration_engine.py --scan          # 扫描所有项目
  python3 collaboration_engine.py --export        # 导出为 JSON
  python3 collaboration_engine.py --import FILE   # 从 JSON 导入
  python3 collaboration_engine.py --sync-hindsight # 同步到 Hindsight
  python3 collaboration_engine.py --all           # 全部运行
"""

import json
import os
import re
import datetime
from pathlib import Path
from collections import defaultdict

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
SCRIPTS_DIR = os.path.expanduser("~/scripts")
EXPORT_DIR = os.path.expanduser("~/桌面/memory-exports")
HINDSIGHT_API = "http://127.0.0.1:8888/v1/default/banks/hermes"
COLLAB_LOG = os.path.expanduser("/tmp/collaboration.log")

# 版本戳
VERSION = "1.0"


# ─── 多项目桥接 ──────────────────────────────────────────────────────────

def discover_projects() -> list[dict]:
    """扫描所有 Claude Code 项目目录"""
    projects = []
    for d in sorted(os.listdir(PROJECTS_DIR)):
        dpath = os.path.join(PROJECTS_DIR, d)
        if not os.path.isdir(dpath):
            continue

        project = {
            "id": d,
            "path": dpath,
            "has_claude": os.path.exists(os.path.join(dpath, "CLAUDE.md")),
            "has_memory": False,
            "memory_count": 0,
            "memory_files": [],
            "session_count": len([f for f in os.listdir(dpath) if f.endswith('.jsonl')]),
        }

        mem_dir = os.path.join(dpath, "memory")
        if os.path.isdir(mem_dir):
            mem_files = [f for f in os.listdir(mem_dir) if f.endswith('.md') and f != 'MEMORY.md']
            project["has_memory"] = True
            project["memory_count"] = len(mem_files)
            project["memory_files"] = mem_files

        projects.append(project)

    return projects


def build_shared_index(projects: list[dict]) -> dict:
    """构建跨项目共享索引"""
    index = {
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_projects": len(projects),
        "total_memories": sum(p["memory_count"] for p in projects),
        "projects": [],
        "cross_project_topics": defaultdict(list),
    }

    for p in projects:
        if not p["has_memory"]:
            continue
        mem_dir = os.path.join(p["path"], "memory")
        project_info = {
            "id": p["id"],
            "memory_count": p["memory_count"],
            "memories": [],
        }
        for fname in p["memory_files"]:
            content = Path(os.path.join(mem_dir, fname)).read_text(encoding="utf-8")
            nm = re.search(r'name:\s*(.+)', content)
            desc = re.search(r'description:\s*(.+)', content)
            mem_type = re.search(r'^type:\s*(.+)', content, re.MULTILINE)
            name = nm.group(1).strip() if nm else fname.replace('.md', '')

            # 提取关键词
            parts = content.split('---', 2)
            body = parts[2] if len(parts) >= 3 else ''
            keywords = set(re.findall(r'[一-鿿]{3,6}|[a-zA-Z]{3,}', body.lower()))

            project_info["memories"].append({
                "name": name,
                "description": desc.group(1).strip()[:80] if desc else "",
                "type": mem_type.group(1).strip() if mem_type else "memory",
                "keywords": list(keywords),
            })

            # 跨项目主题追踪
            for kw in list(keywords)[:10]:
                index["cross_project_topics"][kw].append(f"{p['id']}/{name}")

        index["projects"].append(project_info)

    # 清理 defaultdict
    index["cross_project_topics"] = dict(index["cross_project_topics"])

    return index


def scan_and_report() -> dict:
    """扫描所有项目，生成跨项目报告"""
    projects = discover_projects()
    index = build_shared_index(projects)

    print(f"{'='*60}")
    print(f"  协作层：多项目桥接")
    print(f"{'='*60}")
    print(f"\n📊 发现 {len(projects)} 个项目:")
    for p in projects:
        mem_info = f" ({p['memory_count']} 记忆)" if p["has_memory"] else ""
        claude_info = " 📄CLAUDE.md" if p["has_claude"] else ""
        print(f"  {'📁' if p['has_memory'] else '📂'} {p['id']}{mem_info}{claude_info}")
        if p["memory_files"]:
            for mf in p["memory_files"]:
                print(f"      📝 {mf}")

    # 跨项目共享主题
    if index.get("cross_project_topics"):
        shared = {k: v for k, v in index["cross_project_topics"].items() if len(v) >= 2}
        if shared:
            print(f"\n🔗 跨项目共享主题:")
            for topic, refs in sorted(shared.items(), key=lambda x: -len(x[1]))[:10]:
                print(f"  {topic:20s} → {', '.join(refs[:3])}")

    return index


# ─── 导出/导入 ──────────────────────────────────────────────────────────

def export_memories() -> str:
    """导出所有记忆为便携 JSON"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    export = {
        "version": VERSION,
        "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_project": "-home-lxk",
        "memories": [],
        "controller_config": {},
        "pid_state": {},
    }

    # 读取记忆文件
    for fpath in sorted(Path(MEMORY_DIR).glob("*.md")):
        if fpath.name == "MEMORY.md":
            continue
        content = fpath.read_text(encoding="utf-8")
        if not content.startswith("---"):
            continue
        export["memories"].append({
            "filename": fpath.name,
            "content": content,
        })

    # 读取配置
    config_path = os.path.join(MEMORY_DIR, "controller_config.json")
    if os.path.exists(config_path):
        export["controller_config"] = json.loads(Path(config_path).read_text())

    pid_path = os.path.join(MEMORY_DIR, "pid_state.json")
    if os.path.exists(pid_path):
        export["pid_state"] = json.loads(Path(pid_path).read_text())

    # 文件去重：检查是否有相同内容的记忆
    export["stats"] = {
        "total_memories": len(export["memories"]),
        "total_chars": sum(len(m["content"]) for m in export["memories"]),
    }

    # 写入文件
    Path(EXPORT_DIR).mkdir(parents=True, exist_ok=True)
    out_path = os.path.join(EXPORT_DIR, f"memory-export-{timestamp}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

    print(f"✅ 导出完成: {out_path}")
    print(f"📊 {export['stats']['total_memories']} 条记忆")
    return out_path


def import_memories(import_path: str) -> int:
    """从 JSON 文件导入记忆"""
    if not os.path.exists(import_path):
        print(f"⚠ 文件不存在: {import_path}")
        return 0

    with open(import_path, encoding="utf-8") as f:
        data = json.load(f)

    version = data.get("version", "0")
    print(f"📦 导入版本: {version} (来自 {data.get('source_project', 'unknown')})")
    print(f"📊 包含 {len(data.get('memories', []))} 条记忆")

    imported = 0
    skipped = 0
    conflicted = []

    for mem in data.get("memories", []):
        fname = mem["filename"]
        content = mem["content"]
        out_path = os.path.join(MEMORY_DIR, fname)

        # 冲突检测：文件名存在 + 内容不同
        if os.path.exists(out_path):
            existing = Path(out_path).read_text(encoding="utf-8")
            if existing == content:
                skipped += 1
                continue
            else:
                # 冲突：添加时间戳后缀
                stem, ext = os.path.splitext(fname)
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                new_fname = f"{stem}_imported_{ts}{ext}"
                out_path = os.path.join(MEMORY_DIR, new_fname)
                conflicted.append((fname, new_fname))

        Path(out_path).write_text(content, encoding="utf-8")
        imported += 1

    # 导入控制器配置（标记冲突）
    if data.get("controller_config") and os.path.exists(os.path.join(MEMORY_DIR, "controller_config.json")):
        print("  ⏭ 控制器配置已存在，跳过导入（手动检查）")

    print(f"✅ 导入: {imported} 新 / {skipped} 重复")
    if conflicted:
        print(f"⚠ 冲突（已重命名）:")
        for old, new in conflicted:
            print(f"  {old} → {new}")

    return imported


# ─── Hindsight 同步 ─────────────────────────────────────────────────────

def check_hindsight() -> bool:
    """检查 Hindsight API 是否可达"""
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://127.0.0.1:8888/health", timeout=3)
        return resp.status == 200
    except Exception:
        return False


def push_to_hindsight(memories: list[dict] = None) -> int:
    """将高质量核心记忆推送到 Hindsight（跳过 stub 和 hindsight 同步来的）"""
    if memories is None:
        memories = []
        for fpath in sorted(Path(MEMORY_DIR).glob("*.md")):
            if fpath.name == "MEMORY.md":
                continue
            content = fpath.read_text(encoding="utf-8")
            nm = re.search(r'name:\s*(.+)', content)
            name = nm.group(1).strip() if nm else fpath.stem

            # 过滤：不推送 stub（自动创建未完善）和 hindsight 同步来的
            if not content.startswith("---"):
                continue
            cl = re.search(r'consolidation_level:\s*([\d.]+)', content)
            consolidation = float(cl.group(1)) if cl else 0.0
            if "hindsight" in name.lower() or consolidation < 0.40:
                continue

            memories.append({"name": name, "content": content})

    pushed = 0
    for mem in memories:
        text_to_search = f"[控制论记忆] {mem['name']}"
        try:
            import urllib.request, json as j
            recall_data = j.dumps({"query": text_to_search, "limit": 1}).encode()
            req = urllib.request.Request(
                f"{HINDSIGHT_API}/memories/recall",
                data=recall_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=5)
            existing = j.loads(resp.read())
            if existing.get("results") and len(existing["results"]) > 0:
                continue  # 已存在，跳过
        except Exception:
            pass

        body_parts = mem["content"].split('---', 2)
        body = body_parts[2].strip() if len(body_parts) >= 3 else ""

        observation = f"[控制论记忆] {mem['name']}: {body[:500]}"
        try:
            import urllib.request, json as j
            # Hindsight API 用 memories endpoint 而不是 documents
            mem_data = j.dumps({
                "text": observation,
                "context": "control-theory-memory-system",
                "source": "control-theory-memory",
                "tags": ["control-memory"],
            }).encode()
            req = urllib.request.Request(
                f"{HINDSIGHT_API}/memories",
                data=mem_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=5)
            pushed += 1
            print(f"  ↗️  {mem['name']}")
        except Exception as e:
            print(f"  ⚠ 推送失败: {mem['name']}: {e}")

    return pushed


def pull_from_hindsight(limit: int = 15) -> int:
    """从 Hindsight 拉取高质量记忆片段（避免大量低质量导入）"""
    imported = 0
    # 已有 hindsight 记忆数上限
    existing_hindsight = len([f for f in os.listdir(MEMORY_DIR) if f.startswith('hindsight-')])
    if existing_hindsight >= 8:
        print(f"  ⏭ hindsight 已达上限 ({existing_hindsight}/8)，跳过拉取")
        return 0

    # 只拉取需要补足到 8 的数量
    pull_target = min(limit, 8 - existing_hindsight)
    if pull_target <= 0:
        return 0

    try:
        import urllib.request, json as j
        resp = urllib.request.urlopen(f"{HINDSIGHT_API}/memories/list?limit={pull_target * 2}", timeout=5)
        data = j.loads(resp.read())
        items = data.get("items", [])

        for item in items:
            text = item.get("text", "")
            if not text or "[控制论记忆]" in text:
                continue  # 避免循环导入

            # 质量过滤：只导入长度超过 80 字符的片段
            if len(text) < 80:
                continue

            memory_id = item.get("id", "")[:8]
            fname = f"hindsight-{memory_id}.md"
            fpath = os.path.join(MEMORY_DIR, fname)
            if os.path.exists(fpath):
                continue

            # 去重：检查是否与已有 hindsight 记忆内容相似
            existing_content = ""
            for ef in os.listdir(MEMORY_DIR):
                if not ef.startswith('hindsight-') or ef == fname:
                    continue
                try:
                    existing_content = Path(os.path.join(MEMORY_DIR, ef)).read_text()
                except:
                    continue
            if existing_content:
                body = existing_content.split('---')[-1].lower() if '---' in existing_content else ''
                if text[:60].lower() in body:
                    continue

            # 提取前 100 字作为描述
            desc = text[:80].replace('\n', ' ')
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            content = f"""---
name: hindsight-{memory_id}
description: 从 Hindsight 同步的记忆片段
metadata:
  node_type: memory
  type: reference
  created: {now}
  modified: {now}
  access_count: 1
  last_accessed: {now}
  retention_strength: 0.70
  consolidation_level: 0.30
  forget_rate: 0.04
  centrality: 0.15
  last_checked: {now}
---

从 Hindsight 自动同步的记忆片段（来源：hermes bank）。

> {desc}

原文长度: {len(text)} 字符
Hindsight ID: {item.get('id', 'unknown')}
"""

            Path(fpath).write_text(content, encoding="utf-8")
            imported += 1
            print(f"  ↙️  {fname}")

    except Exception as e:
        print(f"  ⚠ 拉取出错: {e}")

    return imported


def sync_hindsight() -> dict:
    """Hindsight 双向同步"""
    print(f"\n{'='*60}")
    print(f"  Hindsight 双向同步")
    print(f"{'='*60}")

    if not check_hindsight():
        print("  ⚠ Hindsight API 不可达 (http://127.0.0.1:8888)")
        return {"status": "unreachable"}

    print("  ✅ Hindsight 可达\n")

    # 推送到 Hindsight
    print("  ↗️  推送记忆到 Hindsight:")
    pushed = push_to_hindsight()

    # 从 Hindsight 拉取
    print("\n  ↙️  从 Hindsight 拉取:")
    pulled = pull_from_hindsight(limit=15)

    print(f"\n  📊 结果: {pushed} 推送 / {pulled} 拉取")
    return {"pushed": pushed, "pulled": pulled, "status": "ok"}


# ─── 主入口 ─────────────────────────────────────────────────────────────

def main():
    import sys

    args = sys.argv[1:] if len(sys.argv) > 1 else ["--scan"]

    if "--all" in args:
        args = ["--scan", "--export", "--sync-hindsight"]

    if "--scan" in args or "-s" in args:
        scan_and_report()

    if "--export" in args or "-e" in args:
        export_memories()

    for i, arg in enumerate(args):
        if arg == "--import" and i + 1 < len(args):
            import_memories(args[i + 1])

    if "--sync-hindsight" in args or "--sync" in args:
        sync_hindsight()


if __name__ == "__main__":
    main()
