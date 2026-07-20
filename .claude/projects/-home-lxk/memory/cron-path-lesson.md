---
name: cron-path-lesson
description: crontab 路径错误教训 — 接口处的故障应直接修复而非仅报告
metadata: 
node_type: memory
type: feedback
originSessionId: 35bfdd34-7706-4133-a7fd-710e69e901aa
modified: 2026-07-20T04:16:17.435352+00:00
retention_strength: 1.0
consolidation_level: 0.85
forget_rate: 0.03
centrality: 0.15
access_count: 0
last_accessed: 2026-07-20T04:16:16.672083+00:00
last_checked: 2026-07-20T04:16:16.672083+00:00
---自动完善记忆。主题 **cron path lesson** 的会话提取信息：

## 会话摘要
- 已把这次反思写入记忆系统：

- **`cron-path-lesson.md`** — 记录了这个教训和三条原则
- **`MEMORY.md`** — 索引已追加故障记录
- 好问题。回顾整个对话，盘点已完成的三项和仍然存在的缺口：

## ✅ 已完成的改进

1. **MCP 接口** — 15 个工具，记忆系统可通过 MCP 交互
2. **层级读取 + 渐进式回忆** — L0 (精简索引) / L1 (按需搜索) / L2 (完整读取)
3. **周期反思** — 矛盾检测 + 模式提炼 + 健康评分

## 🔴 仍然存在的问题

### 1. 8 条 hindsight-* 空 stub 未被清理
它们从 MEMORY.md 索引移除了，但**文件实体还在磁盘上**。`retention=1.0, body=""`，每次遗忘扫描都会扫描它们，`memory
- ## ✅ 全部修完

### 1. 🗑 清理 8 条 hindsight 空 stub
**问题**：`memory_reclaimer.py` 的 `main()` 默认永远是 `dry-run`（`or True` 写死了），导致回收器**从未实际执行过**。
**修复**：改了默认逻辑 + 加强了 stub 判定规则（优先清空正文的记忆）。
**结果**：8 条 hindsight-* 文件已删除，只剩 9 个有效记忆文件。

### 2. 🔧 修复死链接 + 信号字段
- **MEMORY.md**：hindsight 索引引用从"11 条（含 8 条 hindsight）"修正为"3

## 关联文件
- /home/lxk/.claude/projects/-home-lxk/memory/cron-path-lesson.md
- /home/lxk/.claude/projects/-home-lxk/memory/MEMORY.md
- /home/lxk/.claude/plans/partitioned-wobbling-toucan.md
- 参见 [[github.com]]
- 参见 [[workspace-quant]]
- 参见 [[sharefolder-data]]
- 参见 [[karpathy-guidelines-installed]]
- 参见 [[workspace-quant]]
- 参见 [[workspace-quant]]
