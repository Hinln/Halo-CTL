# 变更日志

本项目遵循 SemVer（语义化版本）。

## 未发布

-

## v1.0.2-beta

- 部署：修复通过 `curl ... | bash` 运行时交互输入导致的异常中断（改为从 `/dev/tty` 读取交互输入并提供友好提示）
- 部署：新增远程公网模式（本机无容器或用户选择远程时，直接输入站点域名并进行可达性验证，跳过容器选择/网络接入）

## v1.0.1-beta

- 新增：`last-trace` 输出最近一次 API 请求现场（可持久化），便于 AI 自愈
- 加固：urllib 客户端异常分支与退避重试（支持 `Retry-After`、抖动、上限）
- 优化：`publish-json` 增加 JSON 输入预校验并输出双语修复建议
- 新增：`context` 输出博客元数据快照；`pat-probe` 探测 PAT 可用性与权限
- 部署：`deploy.sh` 增强交互式配置、可用性校验（whoami）、支持重配
- OpenAPI：`API_INDEX.md` 改为表格格式，更适合 LLM 检索
- 工程：补齐更多单测，`client.py` 覆盖率提升至 90%

## v1.0.0

- 工程化：Python 包化、CI（测试/静态检查）、Docker/GHCR、多架构镜像
- 发布：文章幂等 upsert、异步发布轮询、长文输出优化
- OpenAPI：支持从 Halo 实例同步官方 OpenAPI 并生成接口清单/错误对照
