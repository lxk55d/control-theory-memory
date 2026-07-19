---
name: workspace-quant
description: A股量化研究工作区 — 因子、回测、数据
metadata:
  node_type: memory
  type: project
  created: 2026-07-19T04:20:00.000Z
  modified: 2026-07-19T04:18:26.339036+00:00
  access_count: 2
  last_accessed: 2026-07-19T04:20:00.000Z
  retention_strength: 1.0
  consolidation_level: 0.7
  forget_rate: 0.01
  centrality: 0.6
  last_checked: 2026-07-19T04:18:26.339036+00:00
  originSessionId: 21bab9b7-062c-4131-81e8-84400a6faff9
---

A股量化研究工作区，路径 `~/workspace/`。

## 子项目

- **a-stock-data/** — A股数据项目（数据管道、存储）
- **factor-lab/** — 因子实验室（因子研究与测试）
- **ai-website-cloner-template/** — AI 网站克隆模板

## 主要脚本

| 文件 | 说明 |
|------|------|
| `etf_net_flow_pipeline.py` | ETF 资金流管道（主力数据处理） |
| `swing_vs_rsi_backtest.py` | 摆动策略 vs RSI 策略回测对比 |
| `import_15min_2026.py` | 2026年15分钟K线导入 |
| `import_15min_gap.py` | 15分钟K线数据补缺口 |
| `derive_15min_from_5min.sql` | 5分钟→15分钟K线衍生 SQL |

## 与记忆系统的关联

量化研究中的因子、策略、回测结果可以通过记忆系统跨会话追溯。
