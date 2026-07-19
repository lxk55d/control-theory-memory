# 环境说明文档

> 生成日期：2026-07-19
> 路径：/home/lxk/.claude/projects/-home-lxk/environment.md

---

## 1. 系统信息

| 项目 | 值 |
|------|-----|
| 操作系统 | Ubuntu 24.04.4 LTS (Noble Numbat) |
| 内核版本 | Linux 7.0.0-28-generic x86_64 |
| 主机名 | lxk-SER8 |
| 用户名 | lxk |
| 默认 Shell | Bash |
| 桌面环境 | 有 (DISPLAY=:0) |

## 2. 开发工具与运行时

| 工具 | 版本 | 路径 |
|------|------|------|
| Python | 3.12.3 (系统) | /usr/bin/python3 |
| Node.js | v24.18.0 | /usr/bin/node |
| GCC | 13.3.0 | /usr/bin/cc |
| Docker | 29.6.2 | 守护进程运行中 |
| Git | 系统默认 | 已配置 HTTP/1.1 + 大缓冲区 |
| Claude Code | v2.1.215 | @anthropic-ai/claude-code |

### 未安装
- Go、Rust、Java

## 3. 网络与代理

- Claude API 通过本地代理：`http://127.0.0.1:15721`
- 模型映射：Opus/Sonnet/Haiku/Fable 均指向 `deepseek-v4-flash-free`
- Docker 网络正常，容器间可通信

## 4. 运行中的 Docker 服务

| 容器 | 镜像 | 端口映射 | 用途 | 运行时间 |
|------|------|---------|------|---------|
| searxng | searxng/searxng:latest | 8080:8080 | 自建搜索引擎 | ~38 小时 |
| baidupcs-rust | komorebicarry/baidupcs-rust:latest | 18888:18888 | 百度网盘服务 | ~6 天 (健康) |
| hindsight | hindsight:latest | 8888:8888, 9999:9999 | 记忆系统 | ~8 天 |
| portainer | 6053537/portainer-ce:latest | 9443:9443 | Docker 管理面板 | ~8 天 |

## 5. 主目录结构 (~/)

| 目录/文件 | 类型 | 说明 |
|-----------|------|------|
| `workspace/` | 目录 | **量化金融主力工作区** |
| `hindsight/` | 目录 | **Hindsight 记忆系统 (Mono-Repo)** |
| `scripts/` | 目录 | **实用脚本集** (量化/数据/运维) |
| `ShareFolder/` | 链接→`/srv/samba/share` | **Samba 共享目录** |
| `baidupcs-rust/` | 目录 | 百度网盘 Rust 客户端 (数据+日志) |
| `KhQuant/` | 目录 | 量化策略 |
| `docker/` | 目录 | Docker 配置文件 (searxng) |
| `omniroute/` | 目录 | docker-compose 配置 |
| `桌面/` | 目录 | 桌面快捷方式 + 图表脚本 |
| `下载/` | 目录 | 下载文件 (Chrome/Navicat/项目ZIP) |
| `snap/` | 目录 | Snap 应用 (Chromium, VSCode, Firefox, PyCharm) |
| `PyCharmMiscProject/` | 目录 | PyCharm 项目配置 |

### 5.1 workspace/ 详细

| 项目/文件 | 说明 |
|-----------|------|
| `a-stock-data/` | A股数据项目 |
| `factor-lab/` | 因子实验室 |
| `ai-website-cloner-template/` | AI 网站克隆模板 |
| `etf_net_flow_pipeline.py` | ETF 资金流管道 |
| `swing_vs_rsi_backtest.py` (~12KB) | 摆动/RSI 回测 |
| `import_15min_2026.py` | 15分钟K线导入 |
| `import_15min_gap.py` | 15分钟数据补缺口 |
| `derive_15min_from_5min.sql` | 5→15分钟K线衍生 SQL |

### 5.2 hindsight/ 详细

Hindsight 是一个记忆系统 Mono-Repo，包含：
- `hindsight-api/`, `hindsight-api-slim/` — API 服务
- `hindsight-cli/` — 命令行工具
- `hindsight-clients/` — 客户端 SDK
- `hindsight-control-plane/` — 控制面板
- `hindsight-embed/`, `hindsight-integrations/` — 嵌入与集成
- `hindsight-dev/`, `hindsight-all/`, `hindsight-all-npm/`, `hindsight-all-slim/` — 构建变体
- `hindsight-tools/`, `hindsight-docs/` — 工具与文档
- `monitoring/`, `helm/`, `docker/`, `scripts/` — 运维
- `skills/`, `cookbook/` — 技能与示例

### 5.3 scripts/ 详细

| 脚本 | 主要用途 |
|------|---------|
| `qixing_etf_daily_report.py` (~30KB) | **七星ETF日报** — 主力脚本 |
| `qixing_daily_cron.sh` | 七星日报定时任务 |
| `import_etf_daily.py` | ETF 日线数据导入 |
| `sync_all_lof.py` / `sync_lof_data.py` | LOF 基金数据同步 |
| `update_lof_daily.py` + `.sh` | LOF 日线更新 |
| `hindsight_backfill.py` / `hindsight_strip.py` | Hindsight 工具 |
| `hindsight_safe_patch.sh` | 安全补丁 |
| `rapidocr_cli.py` | 命令行 OCR |

### 5.4 ShareFolder/ (Samba 共享) 详细

| 子目录 | 说明 |
|--------|------|
| `888/` | 核心数据目录 |
| `策略仓库/` | 策略代码库 |
| `本地量化系统/` | 量化系统部署文件 |
| `AI盯盘教学系统魔改版/` | AI 教学系统 |
| `BaiduNetdiskDownload/` | 百度网盘下载文件 |
| `Loop回测框架/` | 回测框架 (有 .rar 压缩包) |
| `小宇量化/` | 量化子项目 |
| `克隆/` + `clone/` | 克隆的仓库 |
| `obsidian/` + `Obsidian/` | Obsidian 笔记库 |
| `book/`, `数据/`, `待办/` | 文档/数据 |
| `11/` | 未知 |

## 6. 已安装的全局 Node 包

| 包名 | 用途 |
|------|------|
| @anthropic-ai/claude-code | Claude Code CLI |
| @openai/codex | OpenAI Codex CLI |
| hermes-web-ui | Hermes Web UI |
| mcporter | 工具 |
| undici | HTTP 客户端 |

## 7. 用户画像

- **主要领域**：A股量化交易
- **工作内容**：ETF 资金流分析、因子研究、K线数据处理、回测
- **基础设施**：Docker 部署服务、Samba 文件共享、百度网盘
- **使用工具**：Claude Code、Python、Node.js、Docker、Samba
- **笔记系统**：Obsidian

## 8. 常用命令速查

```bash
# Docker 服务状态
docker ps

# 量化脚本运行
python3 ~/scripts/qixing_etf_daily_report.py
python3 ~/workspace/etf_net_flow_pipeline.py
python3 ~/workspace/swing_vs_rsi_backtest.py

# Claude Code 代理
# ANTHROPIC_BASE_URL=http://127.0.0.1:15721
```

---

> 本文档由 Claude Code 自动生成，保存于安装目录项目中。
> 如需更新，请重新运行环境探测。
