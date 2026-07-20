---
name: scripts-toolset
description: 实用脚本集 — 七星级ETF日报、LOF数据、OCR、Hindsight运维
metadata: 
node_type: memory
type: project
created: 2026-07-19T04:20:30.000Z
modified: 2026-07-20T04:16:18.486048+00:00
access_count: 0
last_accessed: 2026-07-20T04:16:16.672083+00:00
retention_strength: 1.0
consolidation_level: 0.7
forget_rate: 0.015
centrality: 0.5
last_checked: 2026-07-20T04:16:16.672083+00:00
originSessionId: 21bab9b7-062c-4131-81e8-84400a6faff9
---自动完善记忆。主题 **scripts toolset** 的会话提取信息：

## 会话摘要
- ## ✅ 全部修完

### 1. 🗑 清理 8 条 hindsight 空 stub
**问题**：`memory_reclaimer.py` 的 `main()` 默认永远是 `dry-run`（`or True` 写死了），导致回收器**从未实际执行过**。
**修复**：改了默认逻辑 + 加强了 stub 判定规则（优先清空正文的记忆）。
**结果**：8 条 hindsight-* 文件已删除，只剩 9 个有效记忆文件。

### 2. 🔧 修复死链接 + 信号字段
- **MEMORY.md**：hindsight 索引引用从"11 条（含 8 条 hindsight）"修正为"3
- ## ✅ P0 + P1 已完成

### 修了什么

| 问题 | 根因 | 修复 |
|------|------|------|
| **三个回路看到三种数据** | `memcore.read_all_memories()` 只从 `fm[key]` 取值，但标准 frontmatter 是 `fm.metadata[key]` — 所有信号字段读到都是默认值 0.5/0.3 | ✅ 改为 `metadata` 优先，`fm` 降级。所有回路现在看到完全一致的数据 |
| **meta_learner 自己写了一套解析** | `read_memory_files()` 用正则直接从文

## 相关操作
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
- /home/lxk/.claude/projects/-home-lxk/memory/environment-doc.md
- 参见 [[遗忘率]]
- 参见 [[sharefolder-data]]
- 参见 [[user-profile]]
- 参见 [[workspace-quant]]
- 参见 [[user-profile]]
- 参见 [[workspace-quant]]
