---
name: scripts-toolset
description: 实用脚本集 — 七星级ETF日报、LOF数据、OCR、Hindsight运维
metadata:
  node_type: memory
  type: project
  created: 2026-07-19T04:20:30.000Z
  modified: 2026-07-19T04:18:26.339036+00:00
  access_count: 2
  last_accessed: 2026-07-19T04:20:30.000Z
  retention_strength: 1.0
  consolidation_level: 0.65
  forget_rate: 0.015
  centrality: 0.5
  last_checked: 2026-07-19T04:18:26.339036+00:00
  originSessionId: 21bab9b7-062c-4131-81e8-84400a6faff9
---实用脚本集，路径 `~/scripts/`。

## 量化数据类

| 脚本 | 说明 |
|------|------|
| `qixing_etf_daily_report.py` (~30KB) | **七星ETF日报** — 主力日报生成脚本 |
| `qixing_daily_cron.sh` | 七星日报定时触发 |
| `import_etf_daily.py` | ETF 日线数据导入数据库 |
| `sync_all_lof.py` | LOF 全量同步 |
| `sync_lof_data.py` | LOF 增量数据同步 |
| `update_lof_daily.py` + `.sh` | LOF 日线更新 |

## 内存系统类 (新增)

| 脚本 | 说明 |
|------|------|
| `forgetting_controller.py` | **遗忘控制器** — Ebbinghaus 衰减 + 控制论 |
| `pid_controller.py` | **PID 自适应调参器** — 第二回路 |
| `memory_session_hook.py` | **会话钩子** — Stop 事件自动触发 |

## 其他

| 脚本 | 说明 |
|------|------|
| `rapidocr_cli.py` | 命令行 OCR 工具 |
| `hindsight_backfill.py` | Hindsight 数据回填 |
| `hindsight_strip.py` | Hindsight 数据清理 |
| `hindsight_safe_patch.sh` | 安全补丁脚本 |

## 定时任务

- `qixing_daily_cron.sh` 通过外部 cron 每日执行
- `forgetting_controller.py` 通过 `crontab` 凌晨 3:17 执行
- 参见 [[user-profile]]
- 参见 [[workspace-quant]]
