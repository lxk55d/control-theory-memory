---
name: sharefolder-data
description: Samba 共享目录 (ShareFolder) — 策略、数据、AI 教学、笔记
metadata:
  node_type: memory
  type: reference
  created: 2026-07-19T04:21:30.000Z
  modified: 2026-07-19T04:18:40.478216+00:00
  access_count: 2
  last_accessed: 2026-07-19T04:21:30.000Z
  retention_strength: 1.0
  consolidation_level: 0.5
  forget_rate: 0.025
  centrality: 0.4
  last_checked: 2026-07-19T04:18:40.478216+00:00
  originSessionId: 21bab9b7-062c-4131-81e8-84400a6faff9
---Samba 共享目录 `~/ShareFolder/` → `/srv/samba/share`。局域网文件共享。

## 目录结构

| 子目录 | 说明 |
|--------|------|
| `888/` | 核心数据目录（含 `mini_ai_spring` 前端项目） |
| `策略仓库/` | 量化策略代码库 |
| `本地量化系统/` | 本地量化交易系统部署文件 |
| `AI盯盘教学系统魔改版/` | AI 盯盘教学系统 |
| `BaiduNetdiskDownload/` | 百度网盘下载中转 |
| `Loop回测框架/` + `.rar` | 回测框架程序 |
| `克隆/` + `clone/` | 代码仓库克隆 |
| `小宇量化/` | 量化子项目 |
| `obsidian/` + `Obsidian/` | Obsidian 笔记知识库 |
| `book/` | 书籍资料 |
| `数据/` | 各类数据文件 |
| `待办/` | 任务待办 |
| `11/` | 未知目录 |

## 关键文件

- `A股交易规则.txt` — 交易规则笔记
- `skill-图谱运维手册.md` — 运维手册
- `待办任务.md` — 任务跟踪

## 注意

共享目录权限为 `nobody:nogroup`，lxk 用户可读写。桌面有快捷方式 `~/桌面/ShareFolder` 指向此目录。
- 参见 [[user-profile]]
