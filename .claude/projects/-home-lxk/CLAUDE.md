# 项目记忆系统

本项目使用基于工程控制论的**自调节记忆系统**。

## 核心文件

- `memory/MEMORY.md` — 记忆文件索引
- `memory/controller_config.json` — 遗忘控制器参数配置
- `memory/pid_state.json` — PID 自适应控制器状态
- `memory/memory_history.jsonl` — 系统调节历史日志

## 记忆文件格式

每条记忆文件使用 frontmatter 元数据，包含观测字段：

```yaml
---
name: memory-name
description: 一句话说明
metadata:
  node_type: memory
  type: user|feedback|project|reference
  created: ISO 时间戳
  modified: ISO 时间戳
  access_count: N
  last_accessed: ISO 时间戳
  retention_strength: 0.0–1.0  # 保留强度（遗忘控制器维护）
  consolidation_level: 0.0–1.0 # 巩固度
  forget_rate: 0.0–1.0         # 遗忘率
  centrality: 0.0–1.0          # 网络中心度
  last_checked: ISO 时间戳
---
```

## 遗忘控制器

每日凌晨 3:17 自动运行 (`crontab`)：
- 计算每条记忆的衰减 (Ebbinghaus 模型)
- 分类：活跃 / 休眠 / 低价值
- 更新保留强度

## PID 自适应调参

遗忘控制器运行后自动触发：
- 观测系统状态 (记忆分布、平均保留、波动率)
- 计算误差信号 (实际 vs 目标)
- 调节遗忘控制器的 3 个关键参数
- 参数自动收敛到最优

## 会话钩子

每次会话结束时自动触发：
- 记忆 access_count +1
- 运行遗忘控制器 + PID 调参

<!-- MEMORY_SYSTEM_STATUS_START -->
## 🧠 记忆系统状态 [converging]

### 记忆分布
**8** 条记忆 (L0=5 L2=3)
`████████████████████`

### 控制参数
| 参数 | 值 | PID 迭代 |
|---|---|---|
| base_forget_rate | `0.093619` | 第 7 轮 |
| theta_vital | `0.886186` | 目标活跃 ~40% |
| access_boost | `0.142101` | |
| theta_dormant | `0.4` | 休眠门限 |

### 最近调节
| # | 时间 | Δ遗忘率 | Δ活跃门限 | 活跃 | 休眠 |
|---|---|---|---|---|---|
| 10 | 0h ago | `0.099047` → `0.094209` | `0.940473` → `0.892092` | 0% | 100% |
| 11 | 0h ago | `0.094209` → `0.098114` | `0.892092` → `0.931139` | 100% | 0% |
| 12 | 0h ago | `0.098114` → `0.092619` | `0.931139` → `0.876186` | 0% | 100% |
| 6 | 0h ago | `0.092619` → `0.097419` | `0.876186` → `0.924186` | 100% | 0% |
| 7 | 0h ago | `0.097419` → `0.093619` | `0.924186` → `0.886186` | 0% | 100% |

### 诊断
- 活跃比例偏高 (100%) — PID 正在调大遗忘率
- PID 第 7 轮 — 仍在收敛中
- 遗忘率较高 (0.094) — 适合高速变化的知识环境

### 💡 系统想问你

> 我发现 **python** 是你经常提到的，但我还没有为此建立记忆。你想让我记录一些关于它的信息吗？

### 🔬 依赖健康
- ✅ Hindsight API: HTTP 200
- ✅ Hindsight Version: version: ?
- ✅ Hindsight Bank: banks: hermes
- ✅ Hindsight Recall: 77 results
- ✅ Hindsight Stats: 16244 个节点, 570 文档, 8417 观测
- ✅ 记忆目录完整: 8 个记忆文件 · config=✓ · pid=✓
- ✅ 配置完整性: 遗忘率 0.0936
- ✅ 磁盘占用: 135.6 KB

> 自动更新于 2026-07-20 04:41 UTC
<!-- MEMORY_SYSTEM_STATUS_END -->
