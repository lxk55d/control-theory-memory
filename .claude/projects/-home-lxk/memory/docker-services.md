---
name: docker-services
description: Docker 运行服务 — searxng, baidupcs-rust, hindsight, portainer
metadata: 
node_type: memory
type: reference
created: 2026-07-19T04:22:00.000Z
modified: 2026-07-20T04:16:18.704783+00:00
access_count: 0
last_accessed: 2026-07-20T04:16:16.672083+00:00
retention_strength: 1.0
consolidation_level: 0.55
forget_rate: 0.03
centrality: 0.35
last_checked: 2026-07-20T04:16:16.672083+00:00
originSessionId: 21bab9b7-062c-4131-81e8-84400a6faff9
---自动完善记忆。主题 **docker services** 的会话提取信息：

## 会话摘要
- 全部就绪！来看看我们做了什么。

---

## ✅ MCP 接口已完成

### 安装
- `pip install mcp` ✅ (FastMCP v1.28.1)
- 注册到 `~/.claude.json` 的 `mcpServers`

### MCP 工具（11 个）

| 工具 | 功能 | 测试 |
|------|------|------|
| `search_memories(query, limit)` | 关键词全文搜索 | ✅ |
| `get_memory(name)` | 读取单条记忆完整内容 | ✅ |
| `list_memories(filter_type
- 全部完成！以下是完整结果：

---

## ✅ 层级读取 + 渐进式回忆 完成

### 变更总结

| 文件 | 操作 | 说明 |
|------|------|------|
| `memory/MEMORY.md` | **精简** | 从 29 行 → 14 行，5 条高信号条目 + token 标注 + 月度摘要链接 |
| `scripts/mcp_memory_server.py` | **增强** | 新增 2 工具，增强 2 工具，共 13 个 MCP 工具 |
| `scripts/memory_compounder.py` | **新建** | LLM 驱动的月度摘要
- ## ✅ 全部修完

### 1. 🗑 清理 8 条 hindsight 空 stub
**问题**：`memory_reclaimer.py` 的 `main()` 默认永远是 `dry-run`（`or True` 写死了），导致回收器**从未实际执行过**。
**修复**：改了默认逻辑 + 加强了 stub 判定规则（优先清空正文的记忆）。
**结果**：8 条 hindsight-* 文件已删除，只剩 9 个有效记忆文件。

### 2. 🔧 修复死链接 + 信号字段
- **MEMORY.md**：hindsight 索引引用从"11 条（含 8 条 hindsight）"修正为"3

## 相关操作
- `head -20 /home/lxk/.claude/projects/-home-lxk/memory/docker-services.md`
- `python3 << 'TESTEOF'
import sys, json, time, subprocess

proc = subprocess.Popen(
    ['python3', '/home/lxk/scripts/mcp...`
- `cat << 'PYEOF' > /home/lxk/scripts/generate_status.py
#!/usr/bin/env python3
"""
系统状态生成器 — 将记忆系统的当前状态写入 CLAUDE.md。

这样下一...`

## 关联文件
- /home/lxk/.claude/plans/partitioned-wobbling-toucan.md
- /home/lxk/.claude/projects/-home-lxk/memory/MEMORY.md
- /home/lxk/scripts/mcp_memory_server.py
- /home/lxk/scripts/memory_compounder.py
- /home/lxk/.claude/projects/-home-lxk/memory/docker-services.md
- 参见 [[mysql]]
- 参见 [[karpathy-guidelines-installed]]
- 参见 [[environment-doc]]
- 参见 [[sharefolder-data]]
- 参见 [[karpathy-guidelines-installed]]
- 参见 [[karpathy-guidelines-installed]]
