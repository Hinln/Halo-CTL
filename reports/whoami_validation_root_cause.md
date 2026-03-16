# whoami 验证失败根因报告（Halo base URL & PAT）

## 背景

部署脚本在写入 `.env` 后，会通过 `docker compose run --rm halo-cli whoami` 验证 `HALO_BASE_URL` 与 `HALO_PAT` 的可用性。历史上该步骤可能出现：

- `validation failed: check base URL, PAT, or network`

但由于验证命令默认静默执行（stdout/stderr 被丢弃），导致排障时无法确认最终请求 URL、Header 注入方式、以及服务端返回的状态码与响应体。

## 复现方式（本次修复后）

在同一套 `HALO_BASE_URL`/`HALO_PAT` 下，分别在两种网络视角执行 `whoami`：

1. 本地（宿主机 / local）

```bash
export HALO_BASE_URL='https://your-halo.example'
export HALO_PAT='pat_xxx'
export HALO_DUMP_HTTP=1
export HALO_TRACE_BODY=1
halo-ctl whoami
```

2. 目标网络（Docker Compose 容器网络 / target network）

```bash
docker compose run --rm \
  -e HALO_DUMP_HTTP=1 -e HALO_TRACE_BODY=1 \
  halo-cli whoami
```

输出会包含：时间戳、最终 URL、脱敏后的 `Authorization`、请求/响应 headers、response body、status code。

如需让输出时间戳与某条历史日志完全一致，可设置固定时间戳：

```bash
export HALO_TRACE_FIXED_TS='2026-03-16T00:14:54+0800'
```

## 根因分类与排查要点

### 1) base URL 拼接/输入不规范

现象：最终请求 URL 变成 `.../console/apis/...` 或 `.../api/apis/...`，服务端返回 404/401/5xx。

原因：用户把 Halo “页面地址”误当作 `HALO_BASE_URL`（例如带 `/console` 或 `/api` 后缀）。

修复：CLI 构建 client 时会自动剥离末尾的 `/console` 或 `/api` 片段，并且对缺失协议、携带 query/fragment 的 base URL 进行显式报错。

### 2) 容器网络无法访问宿主机 localhost

现象：宿主机 `curl`/`halo-ctl whoami` 成功，但 `docker compose run ... whoami` 失败（超时、连接拒绝、DNS 失败）。

原因：`HALO_BASE_URL` 使用 `http://localhost:PORT`、`http://127.0.0.1:PORT`、`http://0.0.0.0:PORT` 时，在容器内指向的是容器自身而非宿主机。

修复建议（环境级）：

- 用可从容器访问的地址替换 base URL：域名、宿主机 LAN IP、或反向代理域名。
- Docker Desktop（Windows/macOS）可尝试 `http://host.docker.internal:PORT`。
- 若存在代理环境变量，配置 `NO_PROXY`/`no_proxy` 覆盖内网域名与 IP。

### 3) TLS/证书/代理/防火墙

现象：`URLError`、证书校验失败、TLS handshake error、或仅在特定网络环境失败。

排查：

- 检查公司代理/透明代理：`HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`。
- 检查自签名证书：将证书加入系统/容器信任或使用可信证书。
- 检查 DNS 缓存：容器内 `nslookup`/`getent hosts` 与宿主机是否一致。
- 检查防火墙：容器到目标主机的出站策略。

### 4) 服务端权限策略/版本差异

现象：返回 401/403，响应体提示缺少权限。

排查：

- 确认 PAT 对 `whoami` 端点具备足够权限。
- 输出的 request/response dump 可直接对照手工 `curl` 调用是否一致。

## 证据采集（替代抓包）

本仓库提供两种“可共享的排障证据”输出：

- `HALO_DUMP_HTTP=1`：在 stderr 输出完整请求/响应（Authorization 已脱敏）。
- `halo-ctl last-trace`：输出最近一次请求的结构化 trace（默认路径 `halo-ctl-last-trace.json`）。

以上输出可作为排障证据随 issue/PR 一并附上。

