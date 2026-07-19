# 🧠 工程控制论 · 自进化记忆系统

> 基于钱学森《工程控制论》(Engineering Cybernetics, 1954) 框架设计的个人知识记忆系统。  
> 不是一个静态数据库，而是一个 **能自我调节、持续进化的闭环控制系统**。

**简体中文** · [设计文档](.claude/projects/-home-lxk/memory-system-design.md) · [差距分析](.claude/projects/-home-lxk/gap-analysis.md)

---

## 系统架构

```
                        ┌──────────────────────────────────────┐
                        │        进化层 · 知识空白检测          │
                        │  自我发现不知道什么 → 主动提问用户    │
                        └──────────────┬───────────────────────┘
                                        │
                        ┌──────────────┴───────────────────────┐
                        │     第三回路 · 元学习诊断             │
                        │  分布检测 → 重复合并 → 参数饱和检测   │
                        └──────────────┬───────────────────────┘
                                        │
  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
  │ 完善层      │   │ 关联层      │   │ 协作层      │   │ 检索层      │
  │ 内容自动丰富 │   │ [[link]]    │   │ 多项目桥接  │   │ 语义搜索    │
  │ 跨会话追加  │   │ 自动发现    │   │ Hindsight   │   │ bge-small   │
  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
          │                 │                 │                 │
          └────────┬────────┴─────────┬───────┴────────┬────────┘
                    │                                    │
          ┌─────────┴────────────────────────────────────┴─────────┐
          │          第二回路 · PID 自适应控制                      │
          │  Kp·e(t) + Ki·∫e(τ)dτ + Kd·de(t)/dt → 遗忘率自动收敛  │
          └─────────────────────────┬──────────────────────────────┘
                                    │
          ┌─────────────────────────┴──────────────────────────────┐
          │          第一回路 · 遗忘控制器                          │
          │  d(retention)/dt = -k·r + access_signal(t)             │
          │  活跃 (≥0.8) | 休眠 (≥0.4) | 低价值 (<0.4) 三级门控   │
          └─────────────────────────┬──────────────────────────────┘
                                    │
          ┌─────────────────────────┴──────────────────────────────┐
          │          回收层 · 低信号清理                            │
          │  hindsight 24h / stub 3d → 自动回收                   │
          └────────────────────────────────────────────────────────┘
```

**自迭代频率**: 每次 Claude Code 会话结束时 (`Stop` 钩子) + 每日凌晨 3:17 (`crontab`)

---

## 组件地图

```
scripts/
├── memcore.py                  ← 核心库（frontmatter 解析、配置、状态管理）
│
├── forgetting_controller.py    第一回路 · 遗忘衰减 + 三级门控
├── pid_controller.py           第二回路 · PID 自适应调参 + 边界放宽
│
├── session_analyzer.py         观测层 · 会话日志分析 + 主题提取
├── memory_enricher.py          完善层 · 从会话丰富记忆内容
├── memory_linker.py            关联层 · 自动发现 [[link]]
│
├── meta_learner.py             第三回路 · 元学习诊断 + 自动合并
├── evolution_engine.py         进化层 · 知识空白检测 + 主动提问
│
├── collaboration_engine.py     协作层 · 多项目 + 导出/导入 + Hindsight
├── semantic_retriever.py       检索层 · Hindsight Recall API 语义搜索
│
├── health_check.py             健康层 · 外部依赖监控
├── error_alert.py              告警层 · 分级错误收集 + 自动重试
├── memory_reclaimer.py         回收层 · 低信号记忆清理
│
├── scale_test.py               压力测试 · 合成记忆验证规模行为
├── test_suite.py               测试套件 · 15/15 通过
│
├── generate_status.py          状态生成 · CLAUDE.md 动态块
├── generate_dashboard.py       仪表板 · 自包含 HTML
├── generate_graph.py           知识图谱 · 力导向网络图
│
└── memory_session_hook.py      Stop 钩子入口 · 完整自迭代流水线
```

### 核心算法

#### 遗忘衰减 (控制论第一回路)

```
d(retention)/dt = -k(m) · retention(t) + access_signal(t)

k(m)        = base_forget_rate / (1 + consolidation_level)
access_signal(t) = Σ 访问脉冲 · recency_factor
```

#### PID 调参 (控制论第二回路)

```
error(t)        = target - observed
Δθ(t)           = Kp·e(t) + Ki·∫e(τ)dτ + Kd·de(t)/dt
Δ_scaled(t)     = Δθ(t) · N_eff / N_ref    ← 记忆量自适应缩放
```

---

## 记忆文件格式

每条记忆是一个带有 frontmatter 元数据的 Markdown 文件：

```yaml
---
name: my-memory
description: 一句话描述
metadata:
  node_type: memory
  type: reference          # reference | project | user | feedback
  created: ISO 时间戳
  modified: ISO 时间戳
  access_count: N
  last_accessed: ISO 时间戳
  retention_strength: 0.95     # [0, 1] 遗忘控制器维护
  consolidation_level: 0.60    # [0, 1] 巩固度
  forget_rate: 0.01            # 个体遗忘率
  centrality: 0.50             # 网络中心度
  last_checked: ISO 时间戳
---
```

记忆文件之间通过 `[[link]]` 语法建立关联，由关联层自动发现和维护。

---

## 集成

### Hindsight 记忆系统

本系统与 [Hindsight](https://github.com/your-org/hindsight) 深度集成：
- **向量嵌入**: `bge-small-zh-1.5` (384 维)
- **语义排序**: `glm-4-flash`
- **索引存储**: hnswlib 近似最近邻
- **双向同步**: 控制论记忆 ↔ Hindsight hermes bank

### Claude Code

系统通过 Claude Code 的 `Stop` 钩子系统自动触发，无需手动操作。

---

## 状态文件

| 文件 | 说明 |
|------|------|
| `memory/controller_config.json` | PID 控制参数 |
| `memory/pid_state.json` | PID 积分器状态 |
| `memory/memory_history.jsonl` | 调节历史 |
| `memory/error_log.jsonl` | 告警记录 |
| `memory/param_bounds.json` | 自适应边界 |
| `memory/knowledge_gaps.jsonl` | 知识空白记录 |
| `memory/health_history.jsonl` | 健康检查历史 |

---

## 技术债务与规模

| 指标 | 当前值 |
|------|--------|
| Python 组件 | 19 个脚本 |
| 代码行数 | ~4800 行 |
| 测试 | 15/15 通过 |
| 遗忘控制 O(n) | 10000 条预估 < 1s |
| PID 调参 | O(1) |
| 语义检索 | O(log n) via Hindsight |

---

## 设计文档

- [完整设计蓝图](.claude/projects/-home-lxk/memory-system-design.md) — 工程控制论理论推导
- [差距分析](.claude/projects/-home-lxk/gap-analysis.md) — 当前系统 vs 理想模型的差距

---

## 许可证

MIT License
