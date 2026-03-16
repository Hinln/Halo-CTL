# Halo Docs & API Crawler

目标：抓取并索引 `https://docs.halo.run` 与 `https://api.halo.run` 两个域名下的文章与接口文档，支持增量更新、断点续爬、PostgreSQL 去重存储、Elasticsearch 全文检索、Prometheus 指标与飞书告警。

## 快速开始

1) 启动依赖（PostgreSQL + Elasticsearch）

```bash
cd crawler
docker compose up -d
```

2) 初始化数据库

```bash
docker exec -i halo-crawler-postgres psql -U halo -d halo_crawler < sql/init.sql
```

3) 配置环境变量（示例见 `.env.example`）

```bash
cp .env.example .env
```

4) 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m halo_crawler.main crawl
```

## 必要环境变量

- `CRAWLER_START_URLS`：起始 URL，逗号分隔，默认包含 docs/api 两个域名
- `CRAWLER_USER_AGENT`：必须包含联系方式（合规要求）
- `PG_DSN`：PostgreSQL DSN，例如 `postgresql://halo:halo@localhost:5432/halo_crawler`
- `ES_URL`：Elasticsearch URL，例如 `http://localhost:9200`

## 可观测性

- `CRAWLER_METRICS_ADDR`：Prometheus metrics 监听地址（默认 `0.0.0.0:9108`）
- `FEISHU_WEBHOOK_URL`：飞书机器人 webhook（可选）

## 断点续爬与增量

- 以 `source_url` 为唯一键 upsert。
- 通过 `ETag/Last-Modified` 做条件请求；每天 02:00 定时增量。

## Elasticsearch 中文 IK

`es/mappings.json` 使用 `ik_max_word` 分词器。你需要在 ES 集群安装 IK 插件或使用带 IK 的镜像。

