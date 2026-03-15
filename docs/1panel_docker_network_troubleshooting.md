# 1Panel + Docker：容器未加入同一自定义网络时能否通信？（排查手册）

适用场景：

- 你在 1Panel 中以 Docker 方式部署 `openclaw`（或任意应用容器）
- 同时还部署了数据库/缓存/反向代理等容器
- 这些容器**没有显式加入同一个 Docker 自定义网络**（或部署在不同 1Panel 应用/不同 compose 项目）
- 你需要判断它们在默认 `bridge` 隔离场景下是否能通信，并给出排查与修复方案

---

## 结论先行

1. **能不能通信取决于是否在同一个网络命名空间（同一 Docker network）里**。
2. **默认 `bridge` 网络并不等于“能用容器名互相解析”**：
   - 同一网络里通常可以用 IP 互通。
   - 但“容器名解析（DNS）”在 Docker 里主要由**自定义 bridge 网络的内置 DNS（127.0.0.11）**提供。
   - 默认 `bridge` 网络对容器名解析的支持有限，很多情况下会表现为“DNS 找不到”。
3. **如果 openclaw 和数据库不在同一网络**：
   - 直接用 `db:5432` 这类容器名连接通常失败（DNS 失败）
   - 直接用数据库容器的 `172.x` IP 连接也失败（路由隔离）
   - 只有在你把 DB 端口映射到宿主机并通过“宿主机 IP:映射端口”访问时，才可能绕开网络隔离

---

## 1) Docker 网络模型原理

### 1.1 `bridge`（默认与自定义）

- **默认 bridge**：Docker 自带的 `bridge` 网络（通常名为 `bridge`）。
  - 容器默认会被放到这里（如果你没有指定网络）。
  - 容器之间三层互通通常没问题，但**容器名 DNS 解析不稳定/不推荐依赖**。
- **自定义 bridge**：`docker network create <name>` 创建。
  - Docker 会启用内置 DNS（容器内 `127.0.0.11`）。
  - 同一网络内可以通过 **服务名/容器名/别名**解析到 IP。
  - 这是生产上最常用、也最推荐的单机网络形态。

### 1.2 `host`

- 容器与宿主机共享网络栈（没有独立容器 IP）。
- 端口不再做 NAT，容器进程直接占用宿主机端口。
- 性能好、网络最简单，但**隔离性差**，端口冲突风险大。

### 1.3 `none`

- 容器只有 loopback，没有外部网络。
- 用于极端隔离或自己手动挂网络设备的场景。

### 1.4 自定义网络（bridge/overlay/macvlan 等）

- 单机最常用：**自定义 bridge**。
- Swarm/多机：overlay。
- 高级：macvlan（容器像“物理机”一样直接接入二层）。

---

## 1.5 容器名解析规则（重点）

在 Docker 的“自定义 bridge 网络”里：

- `容器名`、`compose service name`、`network aliases` 都可以用于 DNS 解析
- 解析发生在容器内 `127.0.0.11`，Docker 维护一张网络内的名称表
- 不同网络之间**不会互相解析**（即使名字相同）

在默认 `bridge` 网络里：

- 许多环境下无法可靠通过容器名解析；你可能会看到 `Name or service not known`
- 你可以通过 `--link` 或手动写 `/etc/hosts` 达成“名字可用”，但**不推荐用于生产**

---

## 2) 跨网络通信失败的典型现象与根因

### 2.1 `DNS 解析失败`

现象：

- 应用日志：`getaddrinfo ENOTFOUND db` / `Name or service not known`
- 容器内：`getent hosts db` 无输出

根因：

- openclaw 与 db 不在同一自定义网络
- 或你在默认 `bridge` 上依赖了容器名解析
- 或 1Panel 给容器创建的网络不同（不同应用/不同 compose 项目）

### 2.2 `连接超时 (timeout)`

现象：

- 应用日志：`connect ETIMEDOUT` / `i/o timeout` / `context deadline exceeded`
- `nc -vz db 5432` 卡住

根因：

- 网络隔离导致无路由到对方容器 IP
- DB 没暴露端口，但你又在用宿主机 IP 访问
- 防火墙规则/安全组拦截（尤其是跨主机访问时）

### 2.3 `Connection refused`

现象：

- 应用日志：`ECONNREFUSED` / `Connection refused`
- `nc -vz <host> <port>` 立即拒绝

根因：

- 目标端口没有进程监听
- 监听地址不对（例如只监听 `127.0.0.1`）
- 反向代理/DB 未启动或启动失败

### 2.4 `认证失败/协议错误`

现象：

- 网络通了，但返回 `password authentication failed` / `unauthorized` / `handshake failure`

根因：

- 环境变量配置错误（用户/密码/数据库名）
- TLS/非 TLS 连接参数不匹配

---

## 3) 可操作的诊断步骤（命令 + 判定）

下面命令都在宿主机执行。假设容器名：

- openclaw：`openclaw`
- postgres：`postgres`
- redis：`redis`
- nginx：`nginx`

把名字替换成你在 1Panel 里看到的真实容器名（`docker ps` 可查）。

### 3.1 列出容器与网络

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
docker network ls
```

判定：

- 如果这些容器分别属于不同网络（例如 `app_default`、`openclaw_default`、`1panel-network`），**默认无法通过容器名互连**。

### 3.2 查看容器加入了哪些网络

```bash
docker inspect -f '{{json .NetworkSettings.Networks}}' openclaw | jq
docker inspect -f '{{json .NetworkSettings.Networks}}' postgres | jq
```

判定：

- 两者至少要有一个**共同的网络名**，否则默认无法直接互通。

如果宿主机没装 `jq`，用：

```bash
docker inspect openclaw --format '{{.Name}} {{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

### 3.3 在容器内测试 DNS 与连通

#### DNS

```bash
docker exec -it openclaw sh -lc 'getent hosts postgres || true'
docker exec -it openclaw sh -lc 'cat /etc/resolv.conf'
```

判定：

- `getent hosts postgres` 有输出：说明 DNS 可解析
- `resolv.conf` 里出现 `nameserver 127.0.0.11`：说明在自定义网络里走 Docker 内置 DNS

#### TCP 连通

Postgres（5432）：

```bash
docker exec -it openclaw sh -lc 'nc -vz -w 2 postgres 5432'
```

Redis（6379）：

```bash
docker exec -it openclaw sh -lc 'nc -vz -w 2 redis 6379'
```

HTTP（例如 nginx 80）：

```bash
docker exec -it openclaw sh -lc 'curl -fsS http://nginx/ || true'
```

判定：

- 成功：`succeeded` / `open`
- 超时：网络不通或被拦截
- 拒绝：端口未监听或监听地址不对

### 3.4 看日志（必须带上时间窗口）

```bash
docker logs openclaw --tail 200
docker logs postgres --tail 200
docker logs redis --tail 200
docker logs nginx --tail 200
```

判定：

- openclaw 日志出现 `ENOTFOUND` 先查网络/DNS
- 出现 `ECONNREFUSED` 先查目标容器是否监听端口

---

## 4) 生产级解决方案（>=3 种）对比

### 方案 A：创建共用自定义网络（推荐）

做法：

```bash
docker network create openclaw-net
docker network connect openclaw-net openclaw
docker network connect openclaw-net postgres
docker network connect openclaw-net redis
docker network connect openclaw-net nginx
```

优点：

- 不改容器启动参数即可“补网”
- DNS/容器名解析稳定

缺点：

- 需要确保容器重建时仍会被连接（建议用 compose 固化）

安全风险：

- 同网容器默认可互访，需配合应用层鉴权与最小端口暴露

适用：

- 你在 1Panel 分散创建了多个容器，但希望它们互联

### 方案 B：用 Docker Compose 显式声明 networks（推荐，最可维护）

在 `docker-compose.yml`：

```yaml
networks:
  app-net:
    name: openclaw-net

services:
  openclaw:
    networks: [app-net]
  postgres:
    networks: [app-net]
  redis:
    networks: [app-net]
```

优点：

- 重启/重建都稳定
- 名称解析最可靠（用 service name）

缺点：

- 需要把服务纳入同一个 compose 项目管理（1Panel 里可能意味着“同一应用编排”）

安全风险：

- 同方案 A

### 方案 C：1Panel 里统一网络/别名配置（推荐，面板化）

做法（思路）：

- 在 1Panel 的 Docker 网络管理里创建一个网络（例如 `openclaw-net`）
- 将 openclaw、postgres、redis、nginx 都加入该网络
- 为数据库容器设置网络别名（例如 `postgres`）确保解析一致

优点：

- 不要求你手动写 compose
- 运维同学更易操作

缺点：

- 不同 1Panel 版本 UI 位置不同
- 需要你确认“容器重建策略”是否会保留网络配置

安全风险：

- 同方案 A

### 方案 D：端口暴露 + 宿主机 IP 访问（可用但不推荐作为默认）

做法：

- 把 postgres/redis 端口映射到宿主机（例如 `-p 5432:5432`）
- openclaw 用 `宿主机IP:5432` 访问数据库

优点：

- 不需要同一个 Docker 网络

缺点：

- 破坏“服务只在内部网络可见”的隔离
- 端口冲突风险
- 需要处理 Linux 上容器访问宿主机地址（通常用宿主机网卡 IP）

安全风险：

- 数据库端口暴露到宿主机，若防火墙/安全组没拦住，可能被公网扫描

适用：

- 临时排障、迁移阶段、必须跨网络但无法调整网络拓扑

### 方案 E：`--network=host`（强性能、低隔离，不推荐默认）

做法：

- 让 openclaw 或 DB 使用 host 网络

优点：

- 网络最简单（当作宿主机进程）
- 无 NAT 开销

缺点：

- 端口冲突
- 隔离性差

安全风险：

- 容器几乎等价于宿主机网络权限

适用：

- 特殊性能场景或极简单机部署（且你能承受隔离下降）

---

## 5) 验证脚本与测试用例

仓库提供脚本：`scripts/check_container_connectivity.sh`。

用法示例：

```bash
bash scripts/check_container_connectivity.sh \
  --from openclaw \
  --to postgres:5432 \
  --to redis:6379 \
  --to nginx:80
```

判定标准：

- 输出 `OK dns` + `OK tcp` 才算通过
- 任何 `FAIL dns`：同网但无 DNS（常见是默认 bridge 或没加入同一自定义网络）
- 任何 `FAIL tcp`：网络不通/端口未监听/安全策略拦截

建议测试用例：

1. **冷启动**：`docker restart openclaw postgres redis nginx` 后立刻跑脚本
2. **重建容器**：用 1Panel 重建其中一个容器后再跑脚本（验证网络配置是否丢失）
3. **断网恢复**：把容器从网络断开再连回（验证恢复路径）

---

## 6) 故障判定与修复流程（运维手册）

### Step 1：确认“是否同网”

```bash
docker inspect openclaw --format '{{.Name}} {{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
docker inspect postgres --format '{{.Name}} {{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

判定：

- 无共同网络名：直接进入“方案 A/B/C”

### Step 2：确认 DNS 是否可解析

```bash
docker exec -it openclaw sh -lc 'getent hosts postgres || true'
```

判定：

- 没有输出：优先改为同一自定义网络（方案 A/B/C）

### Step 3：确认端口是否可连

```bash
docker exec -it openclaw sh -lc 'nc -vz -w 2 postgres 5432'
```

判定：

- `timed out`：网络/路由/防火墙
- `refused`：目标端口没监听或应用没启动

### Step 4：查看目标容器监听情况

```bash
docker exec -it postgres sh -lc 'ss -ltnp || netstat -lntp || true'
```

判定：

- 5432 没监听：查 postgres 配置/启动日志

### Step 5：应用配置对照

确认 openclaw 使用的连接串：

- 同网：`postgres:5432` / `redis:6379`
- 非同网（不推荐）：`<host-ip>:5432`（需端口映射 + 安全组/防火墙）

