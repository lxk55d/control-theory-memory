# 变更日志

> 所有显著变化都将记录在此文件中。

## [2.0.0] — 2026-07-20

### 新增

- **MCP 接口**: 19 个 MCP 工具，记忆系统可通过 Claude Code 直接交互
  - `search_memories`, `get_memory`, `list_memories` — 基础搜索与读取
  - `search_memories_index`, `get_memory_compact` — 渐进式回忆（L1 层）
  - `run_pipeline`, `run_forgetting_scan`, `run_pid_tuning` — 流水线控制
  - `system_status`, `get_config`, `detect_gaps` — 系统诊断
  - `run_reflection`, `get_latest_reflection` — 周反思
  - `run_monthly_compound`, `generate_dashboard` — 报告生成
  - `rollback_config` — PID 参数回滚
  - `get_memory_history`, `get_pipeline_history` — 历史追溯
- **memory_reflector.py**: 周级反思器（531 行）
  - 矛盾检测：端口冲突、版本冲突、路径冲突
  - 模式提炼：LLM 驱动的每周主题/跨领域分析
  - 健康评分：综合 PID 状态 + 记忆分布 + 矛盾数
- **memory_compounder.py**: 月度摘要生成器（251 行）
  - LLM 综合高信号记忆生成月度报告
  - 跨领域连接、知识弱项、改进建议
- **3 个 MCP 内存配置文件**: compounds/(月度), reflect/(周反思)

### 改进

- **渐进式回忆架构**: L0 (精简索引 ~200 tok) → L1 (MCP 按需搜索) → L2 (完整读取)
- **MEMORY.md 索引精简**: token 从 ~480 降至 ~200（−58%）
  - 9 条低价值条目移至 L2 仅 MCP 可查
  - 每条索引标注 token 成本
- **PID 参数自适应边界**: 参数逼近上界时自动放宽（base_forget_rate 0.10→0.15、theta_vital 0.95→0.9785）
- **自动化增强**: crontab 从 2 条增至 4 条
  - 新增：每周日 5:05 周反思
  - 新增：每月 1 日 4:00 月度摘要
- **测试覆盖率**: 15/15 测试全部通过（遗忘控制器 + PID + 文件解析 + 主题提取 + 空白检测）

### 修复

- **数据一致性 (P0)**: `memcore.read_all_memories()` 改为 `fm.metadata[key]` 优先→`fm[key]` 降级
  - 之前：memcore/遗忘控制器/meta_learner 三个回路看到三种不同的记忆数据分布
  - 之后：全链路一致
- **meta_learner 冗余解析 (P0)**: 自有的 `read_memory_files()` 改用 `memcore.read_all_memories()`
- **Hindsight Stats "0 条记忆" (P3)**: 健康检查读错字段（`memory_count` 不存在），改为 `total_nodes`
  - 之前：健康报告 `Hindsight Stats: 0 条记忆`
  - 之后：`Hindsight Stats: 16310 个节点, 578 文档` ✅ 8/8 通过
- **PID 迭代计数混乱**: `pid_state.json` iteration=5 但 `memory_history.jsonl` 记录 13 轮
  - 修复：`load_pid_state()` 自动从 history 校准最大 iteration
- **retention 卡死在 1.0**: 三个叠加问题
  - `touch_all_memories()` 在遗忘扫描前膨胀 access_count → 已移除
  - delta_days 基于 `days_since_mod`（被扫描自身更新）而非 `days_since_checked` → 已修复
  - access_count 永不重置 → 脉冲消费后归零
- **空 stub 占用**: 回收器默认永远 dry-run（`or True` 写死）→ `--force` 路径修复
  - 清理 8 条 hindsight-* 空文件：16 文件 → 9 文件
- **死链接**: MEMORY.md 引用 3 个不存在的文件（hindsight-system.md, memory-system-design.md, gap-analysis.md）
  - 索引精简时一并移除
- **缺信号字段**: cron-path-lesson.md（全部缺失）、environment-doc.md（centrality 缺失）、karpathy-guidelines-installed.md（forget_rate/centrality 缺失）
  - 全部补齐 → 100% 覆盖
- **memcore 缺少 save_config()**: 只有 `load_config` 无对应写函数 → 新增 `save_config()`

### 删除

- `touch_all_memories()` — 不再在流水线中预先膨胀访问计数
- 8 条 hindsight-* 空 stub 文件（正文为空，保留在 gitignore 中）
- 3 个 MEMORY.md 死链接条目

### 依赖

- 新增: `mcp>=1.28` (MCP Python SDK, FastMCP)

---

## [1.0.0] — 2026-07-19

### 新增

- 初始版本：基于工程控制论的三回路记忆系统
- 第一回路：遗忘控制器（Ebbinghaus 衰减 + 三级门控）
- 第二回路：PID 自适应调参
- 第三回路：元学习诊断（分布、重复、配置、收敛性）
- 观测层：会话分析 + 知识空白检测
- 完善层：记忆内容自动丰富
- 关联层：[[link]] 自动发现
- 回收层：低信号清理
- 协作层：跨项目桥接 + Hindsight 同步
- CLAUDE.md 状态块自动生成
- 可视化仪表板
- crontab 2 条（每日流水线 + Hermes 维护）
- 测试套件 15 项
