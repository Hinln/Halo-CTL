# v1.0.1-beta 发布说明

本版本为 Beta 预发布版本，对外标签为 `v1.0.1-beta`。

注意：Python 包版本使用 PEP 440 规范，表现为 `1.0.1b0`；与 Git 标签 `v1.0.1-beta` 对应。

## 功能亮点

- 可追溯性：新增 `halo-ctl last-trace`，输出并持久化“最后一次请求现场”，方便 AI/运维快速定位失败原因
- 稳定性：urllib 客户端针对 429/502/503/504 与常见网络异常做了更温和的指数退避 + 抖动重试
- AI 兼容：`publish-json` 增加输入预校验，给出双语修复建议，减少 Python traceback 干扰
- 上下文注入：新增 `halo-ctl context` 输出标签/分类快照，便于 AI Prompt 注入
- 部署体验：`deploy.sh` 支持交互式配置、自动 whoami 校验、支持重配

## 已知问题

- 覆盖率：当前总覆盖率约为 65%（Beta 阶段），后续会持续补齐 CLI/publish/openapi 相关分支测试
- 权限探针：`pat-probe` 默认只读探针；写入探针需要启用 `--write-probe`，且依赖 Halo 侧权限策略

## 升级指南

从旧版本升级建议：

1. 重新拉取最新镜像：

```bash
docker pull ghcr.io/hinln/halo-ctl:latest
```

2. 如需更新配置，运行：

```bash
curl -sSL https://raw.githubusercontent.com/Hinln/Halo-CTL/main/deploy.sh | bash
```

若需要强制重配：

```bash
bash deploy.sh --reconfigure
```

## 变更列表

见仓库根目录 `CHANGELOG.md` 的 `v1.0.1-beta` 段落。

