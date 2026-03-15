# Halo 自动发布脚本：同机 AI 调用部署教程

本教程面向这样的部署形态：

- Halo 运行在服务器（你已有）
- AI 与本发布脚本运行在同一台服务器（同机调用，不走远程 HTTP）
- AI 负责生成 JSON 文件，脚本负责调用 Halo API 创建/更新/发布文章

核心原则：

- **密钥不进仓库**：PAT 只放在服务器受限文件或进程环境里
- **AI 不直接持有 PAT**（可选）：AI 只触发脚本，脚本在受控环境中读到 PAT
- **幂等发布**：固定 `slug`，重复发布更新同一篇文章

---

## 0. 项目结构与入口

- 入口：`halo_publish.py`
- CLI：`halo_cli/cli.py`
- 发布逻辑：`halo_cli/publish.py`

脚本通过 Halo Console API 调用（Bearer PAT）。

---

## 1. 服务器准备（Ubuntu 示例）

```bash
apt update
apt install -y python3 python3-venv python3-pip git
```

部署到 `/opt/halo-cli`（你也可以换成其他目录）：

```bash
cd /opt
git clone <你的仓库地址> halo-cli
cd /opt/halo-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

---

## 2. 准备 Halo PAT（一次性）

在 Halo 后台创建 Personal Access Token（PAT），获得形如 `pat_...` 的 token。

安全建议：

- PAT 视同密码，泄露立即撤销重建
- 不要写进 Git，不要打印到日志

---

## 3. 推荐的密钥存放方式（EnvironmentFile）

同机 AI 调用最稳的方式：把密钥放在 **root 可读**的文件里，通过 `EnvironmentFile` 注入脚本执行环境。

### 3.1 创建密钥文件

```bash
sudo mkdir -p /etc/halo-cli
sudo nano /etc/halo-cli/halo-cli.env
```

写入：

```bash
HALO_BASE_URL=https://your-halo.example
HALO_PAT=pat_xxx
HALO_TIMEOUT_S=120
HALO_DEBUG=0
```

收紧权限：

```bash
sudo chmod 600 /etc/halo-cli/halo-cli.env
```

### 3.2 手动测试（在 shell 中加载）

```bash
cd /opt/halo-cli
source .venv/bin/activate
set -a
source /etc/halo-cli/halo-cli.env
set +a

python halo_publish.py whoami
```

---

## 4. AI 应该生成什么 JSON（发布约定）

AI 输出一个 JSON 文件（例如 `/tmp/payload.json` 或你自己的工作目录）。

字段说明：

- `title`：必填
- `slug`：强烈建议必填（用于幂等更新同一篇文章）
- `markdown`：必填（文章 Markdown 正文）
- `publish`：可选，默认 `true`
- `tags`：可选，数组（填 tag 的 `name`）
- `categories`：可选，数组（填分类的 `name`）
- `visible`：可选：`PUBLIC`/`INTERNAL`/`PRIVATE`

示例：

```json
{
  "title": "AI 自动发布示例",
  "slug": "ai-auto-post-demo",
  "markdown": "# Hello\n\n这是一篇由 AI 自动发布的文章。\n\n- 支持列表\n- 支持代码块\n",
  "tags": ["ai", "halo"],
  "categories": ["tech"],
  "visible": "PUBLIC",
  "publish": true
}
```

---

## 5. 发布命令（AI 同机调用）

只要 AI 能在服务器上执行命令行，就可以用下面方式发布。

### 5.1 最简命令

```bash
cd /opt/halo-cli
source .venv/bin/activate
set -a; source /etc/halo-cli/halo-cli.env; set +a

python halo_publish.py publish-json --file /tmp/payload.json
```

脚本默认输出简短结果 JSON（适合 AI 解析）：

```json
{"post_name":"...","slug":"...","head_snapshot":"..."}
```

如果你需要把输入也一起输出（大文章会慢）：

```bash
python halo_publish.py publish-json --file /tmp/payload.json --dump-input
```

### 5.2 开启调试（排障用）

```bash
export HALO_DEBUG=1
python halo_publish.py publish-json --file /tmp/payload.json
```

会打印每个 API 请求的状态码与耗时，定位卡点很快。

---

## 6. 给 AI 一个最稳的调用方式：封装成一个 shell 脚本

创建 `/usr/local/bin/halo-publish-json`（root 写入）：

```bash
sudo tee /usr/local/bin/halo-publish-json >/dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/opt/halo-cli"
ENV_FILE="/etc/halo-cli/halo-cli.env"

if [[ $# -lt 1 ]]; then
  echo "usage: halo-publish-json /path/to/payload.json" >&2
  exit 2
fi

PAYLOAD="$1"
cd "$REPO_DIR"

source .venv/bin/activate
set -a
source "$ENV_FILE"
set +a

python halo_publish.py publish-json --file "$PAYLOAD"
EOF

sudo chmod 755 /usr/local/bin/halo-publish-json
```

之后 AI 只需要：

```bash
halo-publish-json /tmp/payload.json
```

---

## 7. 幂等策略（强烈建议）

要让 AI 多次发布“同一篇文章”，请固定 `slug`。

- `slug` 不变：更新同一篇
- `slug` 变化：创建新文章

建议 slug 规则（任选一种）：

- `topic-<stable-id>`（例如 `product-update-2026w11`）
- `openclaw-<task-id>`
- `news-<yyyy-mm-dd>`

---

## 8. 常见问题

### 8.1 终端“没反应/卡住”

通常是输出太长或发布等待。建议：

- 不要用 `--dump-input`
- 开 `HALO_DEBUG=1` 看卡在哪个请求

### 8.2 504 Gateway Time-out

这是网关超时，不一定发布失败。脚本走异步发布并轮询确认发布状态。

### 8.3 400 名称重复 / 500 服务器内部错误

建议做两件事：

- 开 `HALO_DEBUG=1` 获取 `requestId`
- 在 Halo 容器日志里按 `requestId` 过滤（你之前已经这么做了），抓到异常第一行 + `Caused by` 才能准确定位

---

## 9. 最小权限与安全边界建议

如果 AI 与脚本同机，最推荐的安全策略：

- AI 运行账户没有 `/etc/halo-cli/halo-cli.env` 读取权限
- 用一个受控的“发布命令入口”（例如上面的 `/usr/local/bin/halo-publish-json`）执行发布
- 或者用 systemd service 让 AI 只触发 `systemctl start halo-publish@xxx.service`（需要的话我可以补一套 service 模板）
