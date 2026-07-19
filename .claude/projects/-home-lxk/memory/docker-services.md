---
name: docker-services
description: Docker 运行服务 — searxng, baidupcs-rust, hindsight, portainer
metadata:
  node_type: memory
  type: reference
  created: 2026-07-19T04:22:00.000Z
  modified: 2026-07-19T04:18:40.478216+00:00
  access_count: 2
  last_accessed: 2026-07-19T04:22:00.000Z
  retention_strength: 1.0
  consolidation_level: 0.45
  forget_rate: 0.03
  centrality: 0.35
  last_checked: 2026-07-19T04:18:40.478216+00:00
  originSessionId: 21bab9b7-062c-4131-81e8-84400a6faff9
---Docker 环境下运行的服务。

## 容器列表

| 容器 | 端口 | 镜像 | 状态 |
|------|------|------|------|
| **searxng** | 8080→8080 | searxng/searxng:latest | Docker compose (`~/docker/searxng/`) |
| **baidupcs-rust** | 18888→18888 | komorebicarry/baidupcs-rust:latest | 百度网盘客户端 (健康) |
| **hindsight** | 8888:8888, 9999:9999 | hindsight:latest | 记忆系统 API |
| **portainer** | 9443:9443 | 6053537/portainer-ce:latest | Docker 管理面板 |

## Docker 配置

- Docker Compose 文件: `~/docker/` (searxng), `~/omniroute/docker-compose.yml`
- 运行时: Docker 29.6.2
- 参见 [[user-profile]]
- 参见 [[scripts-toolset]]
- 参见 [[environment-doc]]
- 参见 [[hindsight-a95be4dc]]
- 参见 [[hindsight-ec11ffdf]]
- 参见 [[hindsight-9cc47260]]
- 参见 [[hindsight-5df53529]]
- 参见 [[hindsight-565245f6]]
