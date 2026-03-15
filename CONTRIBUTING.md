# 贡献指南 / Contributing

感谢你愿意为 Halo-CTL 做贡献。

Thanks for your interest in contributing to Halo-CTL.

## 开发环境 / Development

前置要求：Python 3.10+

Prerequisites: Python 3.10+

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[dev]"
```

运行检查 / Run checks:

```bash
ruff check .
pytest
```

## 提交规范 / Commit style

建议使用 Conventional Commits：

Use Conventional Commits:

- `feat:` 新功能 / new feature
- `fix:` 修复缺陷 / bug fix
- `docs:` 仅文档 / docs only
- `chore:` 工具/维护 / tooling/maintenance

## 签名提交 / Signed commits

建议在提交信息里添加 `Signed-off-by`（DCO 风格），尤其是较大的贡献。

We recommend adding `Signed-off-by` lines (DCO-style), especially for larger contributions.

## 安全注意 / Security

请不要在 Issue/PR/日志/测试数据中包含任何密钥（PAT、API Key 等）。

Do not include secrets (PAT, API keys) in issues, PRs, logs, or test fixtures.
