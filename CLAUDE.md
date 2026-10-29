# CLAUDE.md

FastAPI + SQLAlchemy 2.0 (async) + MySQL 8（开发走 docker compose 的 3307 端口）。
表结构由 **Alembic** 管理。

## 常用命令（Windows，venv 在仓库根目录）

```bash
venv/Scripts/python.exe -m uvicorn app.main:app --reload   # 启动
venv/Scripts/python.exe -m pytest                          # 测试（内存 SQLite）
venv/Scripts/python.exe -m ruff check app migrations       # lint
```

## 数据库迁移：改模型的唯一正确流程

**顺序不能反**——`alembic upgrade` 只执行已有脚本，不做任何对比；对比只发生在 `revision --autogenerate` 那一刻。

```bash
# 1. 改 app/models/*.py
# 2. 生成迁移脚本（此时才对比 模型 <> 数据库）
venv/Scripts/python.exe -m alembic revision --autogenerate -m "描述这次改动"
# 3. 人工 review migrations/versions/<new>.py ：autogenerate 只是草稿
# 4. 应用
venv/Scripts/python.exe -m alembic upgrade head
```

其他：

```bash
venv/Scripts/python.exe -m alembic current        # 当前库版本
venv/Scripts/python.exe -m alembic history        # 版本链
venv/Scripts/python.exe -m alembic downgrade -1   # 回退一版（仅开发用）
venv/Scripts/python.exe -m alembic upgrade head --sql   # 只打印 DDL，不执行
```

### 必须遵守的约定

- **禁止**在应用启动时用 `Base.metadata.create_all` 建表（[app/main.py](app/main.py) 的 lifespan 已移除）。测试用的内存库仍在 [app/tests/conftest.py](app/tests/conftest.py) 里用 `create_all`，那是独立数据库、不跑迁移，保持不变。
- `migrations/versions/*.py` **必须提交**，且不能被 `.gitignore` 忽略。
- 已在任何环境中执行过的迁移文件**冻结**，不要修改；要修正就新增一条迁移。
- 生产/多实例环境：迁移是独立发布步骤，启动应用前由**单个**实例执行一次 `alembic upgrade head`，不要让每个副本启动时自动跑。
- 数据库连接统一来自 [app/config.py](app/config.py) 的 `database_url`（[migrations/env.py](migrations/env.py) 注入），不要在 `alembic.ini` 里配置 URL。
- `alembic.ini` 必须保持**纯 ASCII**：Windows 中文环境下 `configparser` 按 GBK 读取，中文注释会导致 `UnicodeDecodeError`。

### autogenerate 的已知盲区（review 时重点看）

- **改列名**会被识别成「删旧列 + 加新列」→ 数据丢失。手动改成 `op.alter_column("users", "old", new_column_name="new")`。
- **数据迁移**（给新列回填值、清洗数据）完全不生成，需手写 `op.execute(...)`。
- 部分索引 / 约束 / 默认值的差异识别不完整。

## CI/CD 约定

- 流水线：[.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml)。CI 依次跑 `ruff check`、`pytest`、MySQL service 容器上的 `alembic upgrade head` + `alembic check`、构建并推送镜像到 GHCR；main 分支推送后自动部署 staging，生产需手动触发并在 `production` 环境审批。
- **模型改动和迁移脚本必须在同一个 PR/提交里**，否则 CI 的 `alembic check` 会失败。
- lint 规则固定在 [ruff.toml](ruff.toml)，不要靠开发者本地全局配置。
- 服务器部署走 [deploy/deploy.sh](deploy/deploy.sh)，流程是「备份 → 迁移 → 启动 → 健康检查 → 失败回滚应用」；生产由 `production` 环境的 Required reviewers 审批后触发。
- 生产 `.env` 必须 `DEBUG=false`；`.env` 永不提交。
- 完整接入步骤见 [docs/ci-cd.md](docs/ci-cd.md)。

### 对已有数据的库接入 Alembic

表结构已经和模型一致时，不要跑 upgrade，用 `alembic stamp head` 记一笔即可；结构不一致时，需要先删表再 `upgrade head`（`create_all` 建出的旧表无法被 `CREATE TABLE` 覆盖）。
