# halo-cli 2.0 升级范围说明与路线图

你提出的 2.0 目标包含三类内容：

1. **Halo 官方 REST API 的完整能力封装**（可通过 OpenAPI 生成/封装）
2. **SEO/推送/重定向/监控等增强能力**（大多不是 Halo API 自带，需要额外服务或插件）
3. **工程化交付体系**（SDK、多语言、CI、质量门禁、发布自动化、性能基准）

本仓库当前是一个 Python 脚本型 CLI。2.0 的正确落地方式是“分层 + 分阶段”，先把工程化外壳与 API 封装基座搭好，再逐步扩全能力。

---

## Phase 0（已完成）：2.0 工程化基座

- Python 包化：`pyproject.toml`、版本号、console script
- 最小 CI：lint + 单测
- 仓库卫生：`.gitignore`

---

## Phase 1：Halo API 全量封装（按 OpenAPI 驱动）

目标：对接 Halo 官方 OpenAPI（Console API / Content API / Security API 等），生成并封装客户端。

交付：

- `halo_cli.api`：统一 HTTP 客户端、认证、重试、错误码映射、分页器
- 以 OpenAPI 生成的 TypeScript SDK（用于 AI/Node 生态）
- 以 OpenAPI 生成的 Java SDK（用于 JVM 生态）

说明：如果某些能力在 Halo OpenAPI 不公开（或属于付费/插件能力），需要按“扩展模块”实现。

---

## Phase 2：内容与资源增强能力（非 Halo API 原生）

以下需求通常需要“额外服务/插件/主题支持”，并不等同于调用 Halo API：

- sitemap/robots 动态生成与刷新
- canonical/alternate/prev-next 输出（通常是主题/渲染层）
- 百度/Google/Bing 主动推送（外部 API）
- 301/302 重定向表、404 监控
- 图片 alt/尺寸/lazy/webp（内容处理 + 主题/媒体处理）

落地建议：

- **AI 发布前处理**：在脚本端做内容规范化（alt/lazy/webp 链接替换等）
- **Halo 插件**：做 sitemap/redirect/404 统计等“站点级”能力

---

## Phase 3：交付与质量目标

你提出的覆盖率 ≥90%、CI、eslint/prettier/commitlint/husky/semantic-release、OpenAPI 3.1、Postman、基准测试等，将在 Phase 1/2 逐步补齐。

性能基准（P99 200ms、1k QPS）更偏向“服务端网关/中间层”指标；对于 CLI/SDK 本身，指标应改为：

- SDK 本地序列化/校验开销
- 并发请求的正确性（限流/重试/退避）
- 端到端发布链路成功率

