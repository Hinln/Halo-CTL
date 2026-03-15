# Halo-CTL（Python CLI）

## **本项目为 AI 开发项目**

[![CI](https://github.com/Hinln/Halo-CTL/actions/workflows/ci.yml/badge.svg)](https://github.com/Hinln/Halo-CTL/actions/workflows/ci.yml)
![Status](https://img.shields.io/badge/status-beta--testing-yellow)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

> ⚠️ **重要提示：本项目目前仍处于实机测试阶段（Beta）**
>
> - **测试状态**：已在真实 Halo 实例 + Docker 环境中进行功能验证；CI 已跑通 `pytest/ruff`，并包含 shellcheck+bats。
> - **已知限制**：
>   - 总体测试覆盖率仍在持续提升（当前 CI 设定阈值为 `>=65%`，`client.py` 覆盖率已达 `>=90%`）。
>   - `pat-probe` 默认执行只读探针；写入探针需要显式开启 `--write-probe`，并依赖 Halo 侧权限策略。
> - **注意事项**：
>   - 请勿把 PAT 写入代码或公开仓库；推荐仅写入本机 `.env`（脚本会设置 `600` 权限）或环境变量。
>   - 建议先在测试站点验证发布/同步流程，再用于生产。

Halo-CTL 是一个面向 **AI Agent** 的 Halo 运维/内容自动化工具集（Python CLI）。它基于 Halo Console API，通过标准库 `urllib` 实现轻量级 HTTP 客户端，并提供可观测性与部署友好的工作流，使 Agent 能在 Docker 环境中稳定地执行“发布、诊断、同步规范、权限自检”等操作。

仓库地址：<https://github.com/Hinln/Halo-CTL>

---

## 项目介绍

### 背景

在“AI 生成内容 → 自动发布 → 自动诊断/自愈”的闭环中，Agent 往往需要：

- 可靠的发布接口（幂等、可重试、可观测）
- 对接真实运维环境（Docker/1Panel/OpenResty 等）
- 能把“失败现场”结构化输出，供下一轮 Prompt 直接利用

Halo-CTL 以 CLI 形式提供这些能力，降低集成复杂度。

### 核心功能

- **文章发布/更新**：支持 Markdown → HTML 渲染写入，保证前台排版一致
- **诊断与自愈支持**：
  - `last-trace` 输出并持久化“最后一次 API 请求现场”（URL/Method/状态码/TraceId/重试次数/请求体摘要）
  - `pat-probe` 探测 PAT 可用性与权限（只读/可选写入探针）
- **OpenAPI 同步**：从 Halo 实例同步官方 OpenAPI，并生成对 LLM 友好的索引
- **交互式部署**：一键部署脚本扫描容器、自动接入共享网络，并引导配置 Halo 地址与 PAT

### 技术架构（简述）

- CLI：`halo_cli/cli.py`（子命令路由、输入校验、错误友好输出）
- HTTP 客户端：`halo_cli/client.py`（`urllib`、指数退避+抖动、常见网关错误分支、ResponseTracker）
- 发布链路：`halo_cli/publish.py`
- OpenAPI：`halo_cli/openapi_sync.py`
- 部署脚本：`deploy.sh`（容器扫描/网络接入/配置写入/校验）

### 目标用户

- 需要让 **AI Agent** 接管 Halo 运维与内容发布的个人/团队
- 有 Docker/1Panel 环境、希望用“脚本化 + 可观测”方式维护博客的运维人员
- 需要在 CI 或自动化流水线中稳定发布 Halo 内容的开发者

---

## 项目状态与版本

- Git 标签：`v1.0.1-beta`
- Python 包版本（PEP 440）：`1.0.1b0`

---

## 安装

### 方式 A：本地 Python 运行

```powershell
pip install -r requirements.txt
```

推荐安装开发依赖（用于本地测试/覆盖率/安全扫描）：

```powershell
python -m pip install -e ".[dev]"
```

### 方式 B：Docker 一键部署（推荐）

```bash
curl -sSL https://raw.githubusercontent.com/Hinln/Halo-CTL/main/deploy.sh | bash
```

脚本会：

- 扫描运行中的 Docker 容器并交互式选择 AI/Agent 容器
- 创建/复用共享 bridge 网络并把目标容器加入该网络
- 引导配置 `HALO_BASE_URL` 与 `HALO_PAT`，写入 `$HOME/Halo-CTL/.env`（`600` 权限）
- 自动执行 `whoami` 校验可用性，失败会提示重新配置

如需强制重配：

```bash
bash deploy.sh --reconfigure
```

---

## 配置

### 环境变量

- `HALO_BASE_URL`：Halo 站点地址，例如 `https://your-halo.example`
- `HALO_PAT`：个人访问令牌（PAT）
- `HALO_TIMEOUT_S`：请求超时秒数（默认 120）
- `HALO_DEBUG`：调试输出（0/1）
- `HALO_LANG`：输出语言模式（`zh`/`en`/`bi`，默认 `bi`）

PowerShell 示例：

```powershell
$env:HALO_BASE_URL = "https://your-halo.example"
$env:HALO_PAT = "pat_..."
$env:HALO_TIMEOUT_S = "120"
```

---

## 使用方法

> 推荐使用 `halo-ctl` 命令；同时保留 `halo-publish` 作为兼容入口。

### 连接性验证

```powershell
halo-ctl whoami
```

### 发布 Markdown

```powershell
halo-ctl publish --title "我的新文章" --slug "my-new-post" --markdown-file .\post.md
```

### AI 生成 JSON 发布（带预校验）

```json
{
  "title": "我的新文章",
  "slug": "my-new-post",
  "markdown": "# Hello\n\nfrom agent",
  "tags": ["halo", "python"],
  "categories": ["tech"],
  "visible": "PUBLIC",
  "publish": true
}
```

```powershell
halo-ctl publish-json --file .\payload.json
```

当 AI 生成字段不合法时，CLI 会返回带“修复建议”的双语错误信息。

### 获取上下文（给 Prompt 注入用）

```powershell
halo-ctl context
```

### 失败后现场（自愈输入）

```powershell
halo-ctl last-trace
```

### PAT 权限探针

```powershell
halo-ctl pat-probe
```

---

## OpenAPI 文档

同步：

```powershell
halo-ctl sync-openapi
```

生成物默认在 `openapi/specs/`，并生成索引文档（更适合 LLM 检索）。

---

## 安全

- 不要提交任何 PAT/API Key（包括日志、截图、测试数据）。
- 安全问题请按 [SECURITY.md](SECURITY.md) 私下上报。

---

## 贡献指南

- 贡献流程：见 [CONTRIBUTING.md](CONTRIBUTING.md)
- 贡献者协议：本项目采用 DCO，见 [DCO.md](DCO.md)
- 行为准则：见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

---

## 许可证

本项目采用 MIT License，见 [LICENSE](LICENSE)。

---

## 联系方式

- Bug/功能建议：请通过 GitHub Issues
- 安全问题：请按 [SECURITY.md](SECURITY.md) 私下上报

