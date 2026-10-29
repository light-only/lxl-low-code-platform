# CI/CD 接入说明

Jenkins（自建）+ Linux 服务器 + docker compose 的完整流程。

```
开发者 push / 合并 PR
        │
        ▼
┌──────────────── Jenkins ────────────────┐
│ 安装依赖 → ruff → pytest                │
│ 迁移校验（临时 MySQL 容器）：            │
│   alembic upgrade head + alembic check  │
│ 构建镜像 →（main 分支）推送镜像仓库       │
└───────────────┬─────────────────────────┘
                │ SSH
                ▼
┌──────────── 服务器 ─────────────────────┐
│ git pull                                │
│ deploy.sh：                             │
│   启库 → 备份 → 拉镜像 → alembic upgrade │
│   → 启动 api → 健康检查（失败自动回滚）  │
└─────────────────────────────────────────┘
```

相关文件：

| 文件 | 作用 |
|---|---|
| `Jenkinsfile` | 流水线定义（CI + 部署） |
| `docker-compose.prod.yml` | 服务器上的 compose（含一次性 `migrate` 服务） |
| `deploy/deploy.sh` | 服务器端部署脚本：备份、迁移、启动、健康检查、回滚 |
| `ruff.toml` | CI 使用的 lint 规则 |
| `.dockerignore` | 避免把 venv / .env / 本地库打进镜像 |

---

## 一、一次性准备

### 1. 镜像仓库

准备一个可访问的 registry（Harbor、阿里云 ACR、GitLab Container Registry 都可以），记下地址。

### 2. 服务器（staging / production 各一台或各一个目录）

以 staging 为例，production 把目录换成 `/srv/lxl-production`：

```bash
# 部署用户需要能操作 docker
sudo usermod -aG docker deploy

sudo mkdir -p /srv/lxl-staging
sudo chown deploy:deploy /srv/lxl-staging

# 服务器上放一份仓库克隆（deploy 时会 git pull 更新 compose/脚本）
git clone <你的仓库地址> /srv/lxl-staging
cd /srv/lxl-staging

# 环境变量文件不提交，需在服务器上手工创建
cp .env.example .env
vim .env

chmod +x deploy/deploy.sh
```

服务器 `.env` 最少需要这些值（**不要提交到 git**）：

```ini
APP_NAME=lxl-low-code-platform-backend
APP_ENV=production
DEBUG=false                       # 生产必须关掉，否则会打印所有 SQL
SECRET_KEY=<随机生成的长字符串>
BACKEND_CORS_ORIGINS=["https://your-frontend.example.com"]

DB_TYPE=mysql
MYSQL_ROOT_PASSWORD=<强密码>       # 只在服务器上存在
MYSQL_USER=app
MYSQL_PASSWORD=<强密码>
MYSQL_HOST=mysql                  # compose 内部服务名
MYSQL_PORT=3306
MYSQL_DB=lxl_low_code
MYSQL_HOST_PORT=3307              # 只监听 127.0.0.1，不对外暴露
APP_PORT=8000
```

防火墙只放行应用端口（建议前面挂 Nginx/网关，8000 不直接对外）。

### 3. Jenkins

**节点要求**：git、python3.12、docker（含 compose v2）、curl、ssh，并且 Jenkins 用户能执行 docker。

**凭据**（Manage Jenkins → Credentials）：

| ID | 类型 | 内容 |
|---|---|---|
| `docker-registry-creds` | Username with password | 镜像仓库账号密码 |
| `deploy-ssh-key` | SSH Username with private key | 能免密登录两台服务器的私钥，用户名填 `deploy` |

**创建任务**：New Item → Pipeline → 名字 `lxl-backend-pipeline` → Pipeline script from SCM → Git（填仓库地址）→ Branch `main` → Script Path `Jenkinsfile`。

**参数**（首次构建前确认）：

- `REGISTRY`：镜像仓库地址，如 `harbor.example.com`
- `IMAGE_NAME`：默认 `lxl-low-code-platform-backend`
- `STAGING_HOST` / `PROD_HOST`：服务器地址
- `DEPLOY_ENV`：默认 `staging`；`none` 只跑 CI；`production` 会先部署 staging，再等人工确认后部署生产

> 参数默认值由 `Jenkinsfile` 里的 `choices` 顺序决定（第一项为默认），在任务页面改默认值不生效，要改就直接改 `Jenkinsfile`。

---

## 二、首次发布

1. 先在本地把基线迁移跑起来（见仓库 README）。
2. 提交并推送到 `main`（服务器上也需要能 `git pull` 到最新，否则拿不到 `deploy/` 脚本）。
3. Jenkins 里 Build with Parameters，选 `DEPLOY_ENV=staging`。
4. 流水线会依次执行：
   - ruff + pytest
   - 临时 MySQL 上 `alembic upgrade head` + `alembic check`
   - 构建并推送镜像
   - SSH 到 staging：备份（首次是空库）→ 迁移建表 → 启动 → 健康检查
5. 在 staging 上验证：

```bash
ssh deploy@staging.example.com
cd /srv/lxl-staging
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=50 api
curl -s http://127.0.0.1:8000/health
docker compose -f docker-compose.prod.yml exec -T mysql \
  sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SELECT version_num FROM alembic_version" "$MYSQL_DATABASE"'
```

6. 测试通过后，再选 `DEPLOY_ENV=production` 构建一次。生产阶段前会弹出 **人工确认**，确认后才会执行。

---

## 三、日常发布流程

| 操作 | 结果 |
|---|---|
| 功能分支 push | 只跑 CI（ruff / pytest / 迁移校验 / 构建镜像），不部署 |
| 合并到 `main` | CI + 推送镜像 + **自动部署 staging** |
| 手动选 `DEPLOY_ENV=production` | 先自动走一遍 staging，再等人工确认后部署生产 |
| 手动选 `DEPLOY_ENV=none` | 只跑 CI，适合验证改动 |

> - Jenkins 任务需要配置 Webhook（或 SCM 轮询）监听 `main`，否则合并后不会自动构建。
> - 生产确认弹窗有超时限制：整个流水线 `timeout 90 分钟`，超过未确认会自动中止，**不会部署**。发布窗口较长时请临时调大 `Jenkinsfile` 里的 `timeout`。

### 加字段/改表结构时

1. 本地改模型 → `alembic revision --autogenerate` → review → `alembic upgrade head` → pytest。
2. 迁移文件跟模型一起提交（CI 的 `alembic check` 会拦住只改模型不改迁移的情况）。
3. 合并 → staging 自动部署 → 回归 → 手动触发生产。
4. 新列默认用**可空**（`Mapped[str | None]`），需要非空走 expand/contract，分两次发布。

---

## 四、回滚

**应用回滚（最常用）**

```bash
ssh deploy@host
cd /srv/lxl-production
cat .last_good_image                          # 上一个成功版本
IMAGE=<上一个镜像> ./deploy/deploy.sh production <上一个镜像>
```

健康检查失败时 `deploy.sh` 会**自动**用 `.last_good_image` 回滚应用，并保留当前数据库结构。

**数据库回滚**

- staging：可以 `alembic downgrade -1`，但要注意 `downgrade()` 是否有损。
- production：**不执行 downgrade**。恢复备份：

```bash
cd /srv/lxl-production
docker compose -f docker-compose.prod.yml exec -T mysql \
  sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < backups/xxx.sql
```

备份目录 `backups/` 自动保留最近 10 份，每次部署前都会生成。

---

## 五、排错

| 现象 | 原因 / 处理 |
|---|---|
| `permission denied ... docker.sock` | `sudo usermod -aG docker deploy` 后重新登录 |
| `alembic check` 失败 | 改了模型但没生成迁移；本地补 `alembic revision --autogenerate` |
| 部署脚本报 `缺少 .env` | 服务器上没创建环境变量文件 |
| 镜像拉取失败 | 服务器未 `docker login`，或在 compose 里配置了错误的 registry |
| 健康检查一直失败 | `docker compose logs api`；常见原因是 `.env` 里的 `MYSQL_*` 配错或 `SECRET_KEY` 缺失 |
| `git pull` 失败 | 部署用户的 SSH key 没加到仓库（只读 deploy key 即可） |
| 首次部署备份为空 | 正常，此时库还是空的；从第二次起才有内容 |

---

## 六、上线前检查清单

- [ ] 生产 `.env` 里 `DEBUG=false`、`SECRET_KEY` 已更换
- [ ] 数据库端口只监听 `127.0.0.1`
- [ ] 应用端口前面有网关/反向代理和 HTTPS
- [ ] 服务器 `backups/` 目录有写入权限且磁盘充足
- [ ] Jenkins 里生产任务有权限控制，只有发布负责人能触发
- [ ] 迁移脚本经过 review，确认向后兼容（旧代码能在新 schema 上运行）
