# whoami 验证回归测试报告

## 变更摘要

- CLI 对 `HALO_BASE_URL` 做了显式校验（必须包含 `http(s)://`、禁止 query/fragment），并自动剥离末尾 `/console` 与 `/api`。
- HTTP 客户端新增可观测性：支持输出最终 URL 与脱敏后的 `Authorization`，并记录请求/响应 headers、status、body 预览与时间戳到 last-trace。
- 部署脚本验证失败时可通过 `HALO_DEBUG=1` 输出 whoami 的请求/响应与 last-trace。

## 回归标准

- `whoami` 连续调用 5 次均返回 200（需在真实 Halo 环境验证）。
- 部署脚本不再出现无信息的校验失败；失败时能直接看到最终 URL、status code 与响应体。
- 单元测试覆盖：空 PAT、错误 URL、401、500 四种场景。

## 本地单测结果

运行：

```bash
python -m pytest -q
```

预期：全部通过。

## 线上验证操作（建议）

1) 先在宿主机验证：

```bash
export HALO_BASE_URL='https://your-halo.example'
export HALO_PAT='pat_xxx'
export HALO_DUMP_HTTP=1
export HALO_TRACE_BODY=1
halo-ctl whoami
```

2) 再在 Docker Compose 容器网络验证：

```bash
docker compose run --rm \
  -e HALO_DUMP_HTTP=1 -e HALO_TRACE_BODY=1 \
  halo-cli whoami
```

3) 若失败，直接导出结构化现场：

```bash
halo-ctl last-trace
```

## 下次发布注意事项

- 不要在日志/工单里粘贴明文 PAT；请使用 dump 输出（已脱敏）或 last-trace。
- 若 Halo 部署在反向代理/子路径下，确认 `HALO_BASE_URL` 指向可访问的 Halo 根地址；避免输入 `/console` 页面地址。
- 若 base URL 指向 `localhost`，容器网络下会失败；改用域名/LAN IP 或 Docker Desktop 的 `host.docker.internal`。

