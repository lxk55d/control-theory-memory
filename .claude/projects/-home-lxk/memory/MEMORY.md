- [User Profile](user-profile.md) — 用户画像：A股量化交易者，研究方向与兴趣
- [Workspace Quant](workspace-quant.md) — A股量化研究工作区（因子、回测、数据管道）
- [Scripts Toolset](scripts-toolset.md) — 实用脚本集（七星日报、LOF、OCR、记忆系统控制器）
- [Hindsight System](hindsight-system.md) — Hindsight 记忆系统 Mono-Repo 概况
- [ShareFolder Data](sharefolder-data.md) — Samba 共享目录结构与内容索引
- [Docker Services](docker-services.md) — 运行中的 Docker 容器与服务
- [Memory System Design](memory-system-design.md) — 基于工程控制论的自调节、自进化记忆系统设计（蓝图）
- [Gap Analysis](gap-analysis.md) — 当前系统 vs 控制论理想的差距分析
- [Environment](environment-doc.md) — 系统环境说明文档

## 系统组件

- `forgetting_controller.py` — 遗忘衰减 + 三级门控（第一回路）
- `pid_controller.py` — PID 自适应调参 + 自适应边界（第二回路）
- `session_analyzer.py` — 会话日志分析 + 自动创建记忆（观测层）
- `memory_enricher.py` — 从会话丰富记忆内容（完善层）
- `meta_learner.py` — 结构性诊断 + 自动合并重复 + 参数建议（第三回路）
- `memory_session_hook.py` — Stop 钩子入口（完整自迭代流水线）
- `generate_status.py` — CLAUDE.md 状态块自动生成
- `generate_dashboard.py` — 可视化仪表板（输出到桌面）

## 自动流水线

每次 Stop / 每日 crontab：
```
访问更新 → 遗忘衰减 → PID调参 → 会话分析 → 自动创建记忆 → 内容完善 → 元学习诊断 → 合并重复 → 边界放宽 → 状态报告
```
