# 安装与配置指南

## 系统要求

- **Python** 3.10+
- **Docker** (可选，用于 Hindsight 集成)
- **Claude Code** (可选，用于 Stop 钩子自动触发)
- 网络：代理访问 GitHub (可选)

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/lxk55d/control-theory-memory.git
cd control-theory-memory
```

### 2. 配置 Claude Code 项目

```bash
mkdir -p .claude/projects/-home-lxk/memory
cp scripts/*.py ~/scripts/
```

将 `hooks/hooks.json` 复制到 Claude Code 项目目录，或在 `settings.local.json` 中注册：

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/scripts/memory_session_hook.py",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

### 3. 初始化记忆目录

```bash
# 创建初始记忆目录和配置文件
python3 -c "
import os, json
from pathlib import Path

mem_dir = Path.home() / '.claude/projects/-home-lxk/memory'
mem_dir.mkdir(parents=True, exist_ok=True)

# 创建默认控制器配置
config = {
    'base_forget_rate': 0.03,
    'consolidation_boost': 0.5,
    'access_boost': 0.15,
    'recency_halflife_days': 7,
    'theta_vital': 0.8,
    'theta_dormant': 0.4,
    'theta_purge': 0.15,
    'centrality_floor': 0.05,
    'initial_retention': 0.9,
    'initial_consolidation': 0.3,
    'default_forget_rate': 0.03,
    'default_centrality': 0.1,
    'scan_interval_hours': 24,
    'archive_threshold_days': 90,
}
(mem_dir / 'controller_config.json').write_text(json.dumps(config, indent=2))

# 创建 MEMORY.md 索引
(mem_dir / 'MEMORY.md').write_text('# 记忆索引\n\n欢迎使用控制论记忆系统。\n')
print('初始化完成')
"
```

### 4. 运行测试

```bash
cd ~/scripts
python3 test_suite.py
```

全部通过后，系统就绪。

### 5. 注册定时任务 (可选)

```bash
crontab -l 2>/dev/null
echo "17 3 * * * python3 $HOME/scripts/memory_session_hook.py >> /tmp/memory-self-iterate.log 2>&1"
```

---

## Hindsight 集成 (可选)

系统可以与 [Hindsight](https://github.com/your-org/hindsight) 集成以获得语义检索能力。

### 前提条件

确保 Hindsight 服务运行在本地的 8888 端口：

```bash
curl http://127.0.0.1:8888/health
# 返回: {"status":"ok"}
```

### 启用语义检索

```bash
# 单次检索测试
python3 ~/scripts/semantic_retriever.py "查询内容" --limit 5

# 将核心记忆同步到 Hindsight 索引
python3 ~/scripts/collaboration_engine.py --sync-hindsight
```

### API 校验

```bash
python3 ~/scripts/health_check.py
```

---

## 记忆文件创建指南

创建一条新记忆：

```markdown
---
name: my-knowledge
description: 关于某个主题的知识记录
metadata:
  node_type: memory
  type: reference
  created: 2026-01-01T00:00:00.000Z
  modified: 2026-01-01T00:00:00.000Z
  access_count: 1
  last_accessed: 2026-01-01T00:00:00.000Z
  retention_strength: 0.90
  consolidation_level: 0.30
  forget_rate: 0.03
  centrality: 0.15
  last_checked: 2026-01-01T00:00:00.000Z
---

在这里写记忆内容。支持 **Markdown** 和 [[link]] 语法。

参见 [[related-memory]]
```

将文件以 `.md` 扩展名放入 `memory/` 目录。下次流水线运行时，遗忘控制器会自动接管。

---

## 命令速查

```bash
# 手动触发完整自迭代
python3 ~/scripts/memory_session_hook.py

# 仅运行遗忘控制器
python3 ~/scripts/forgetting_controller.py

# 查看 PID 调参过程
python3 ~/scripts/pid_controller.py

# 健康检查
python3 ~/scripts/health_check.py

# 语义检索
python3 ~/scripts/semantic_retriever.py "你的问题"

# 生成仪表板
python3 ~/scripts/generate_dashboard.py

# 生成知识图谱
python3 ~/scripts/generate_graph.py

# 运行测试
python3 ~/scripts/test_suite.py

# 压力测试
python3 ~/scripts/scale_test.py --full 50 100 200
```

---

## 目录结构

```
控制论记忆系统/
├── README.md                         ← 项目说明
├── INSTALL.md                        ← 本文件
├── scripts/                          ← 所有 Python 组件
│   ├── memcore.py                            核心库
│   ├── forgetting_controller.py              遗忘控制器
│   ├── pid_controller.py                     PID 调参器
│   ├── memory_session_hook.py                自迭代入口
│   ├── session_analyzer.py                   会话分析
│   ├── memory_enricher.py                    记忆完善
│   ├── memory_linker.py                      自动关联
│   ├── meta_learner.py                       元学习
│   ├── evolution_engine.py                   进化层
│   ├── collaboration_engine.py               协作层
│   ├── semantic_retriever.py                 语义检索
│   ├── health_check.py                       健康检查
│   ├── error_alert.py                        告警系统
│   ├── memory_reclaimer.py                   记忆回收
│   ├── scale_test.py                         压力测试
│   ├── test_suite.py                         测试套件
│   ├── generate_status.py                    状态生成
│   ├── generate_dashboard.py                 仪表板
│   └── generate_graph.py                     知识图谱
├── .claude/projects/-home-lxk/
│   ├── CLAUDE.md                             项目配置
│   ├── memory-system-design.md               设计文档
│   ├── gap-analysis.md                       差距分析
│   ├── environment.md                        环境文档
│   ├── memory/                               记忆文件
│   │   ├── MEMORY.md                         索引
│   │   ├── controller_config.json            控制参数
│   │   ├── pid_state.json                    PID 状态
│   │   └── *.md                              各条记忆
│   └── .claude/hooks/
│       └── hooks.json                        Stop 钩子
└── .gitignore
```
