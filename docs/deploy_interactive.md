# 交互式一键部署（Docker 用户）

本项目提供 `deploy.sh` 作为面向 Docker 用户的交互式一键部署脚本。

它会：

1. 扫描本机正在运行的 Docker 容器并列表展示（容器名/镜像/状态/端口映射）
2. 让你选择“AI/Agent 所在容器”（openclaw 或其他 agent）
3. 创建/复用一个共享 bridge 网络（默认 `openclaw-net`）并把目标容器加入该网络（带别名 `agent`）
4. 部署本工具并加入同一网络，确保容器名互相通信
5. 全程输出步骤结果，并把完整日志写入 `/var/log/docker_deploy.log`

---

## 运行

```bash
curl -sSL https://raw.githubusercontent.com/Hinln/Halo-CTL/main/deploy.sh | bash
```

## 配置与校验

部署脚本会交互式要求你输入：

- `HALO_BASE_URL`：Halo 博客地址（必须以 `http://` 或 `https://` 开头）
- `HALO_PAT`：Halo API 密钥（PAT）

写入位置：`$HOME/Halo-CTL/.env`，权限为 `600`（仅当前用户可读写），以减少密钥泄露风险。

随后脚本会自动执行一次校验：

- `docker compose run --rm halo-cli whoami`

如果校验失败，会提示你重新输入地址/PAT（最多重试 3 次）。

## 远程公网模式（Halo 不在本机宿主机）

当脚本无法从本机 Docker 枚举到合适的容器，或你在容器选择阶段输入 `r`，脚本会切换到“远程公网模式”。

- 你需要直接输入 Halo 站点公网域名（例如 `https://blog.example.com`）
- 脚本会先对 Halo API 路径做可达性验证（HTTP 200/401/403 视为可达）
- 随后跳过“本地容器选择/网络接入”，直接进入配置写入与部署流程

---

## 参数

- `-h/--help`：帮助
- `-y/--yes`：跳过确认
- `-v/--verbose`：DEBUG 日志
- `--dry-run`：仅模拟，不实际修改网络/拉镜像
- `--reconfigure`：强制重新配置并重写 `.env`

---

## 故障判定

### 选择容器后反复提示不支持网络模式

脚本不支持对 `host`/`none` 模式的容器自动挂载自定义网络，请选择使用 bridge 网络的容器。

### 日志无法写入 `/var/log/docker_deploy.log`

需要 `sudo` 权限来创建并写入日志文件。

---

## 回滚

如果网络加入失败或部署失败：

- 脚本会尝试把目标容器从新网络中断开
- 如果该网络是脚本刚创建的，会尝试删除该网络
