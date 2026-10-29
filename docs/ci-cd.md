# CI/CD 接入说明（GitHub Actions）

代码主仓在 Gitee，构建在 GitHub Actions 上跑，镜像推送到 GHCR，部署到自己的 Linux 服务器。

```
开发者 push 到 Gitee（同时镜像到 GitHub）
        │
        ▼
┌──────────── GitHub Actions（云端，不占你的服务器） ────────────┐
│ ci:      pip install → ruff → pytest → MySQL 上 alembic check  │
│ build:   docker build → push ghcr.io/<owner>/<repo>:sha-xxxxx  │
│ deploy:  SSH → 服务器执行 deploy/deploy.sh                     │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
                    你的服务器（docker compose）
                    备份 → 迁移 → 启动 → 健康检查 → 失败回滚
```

相关文件：

| 文件 | 作用 |
|---|---|
| `.github/workflows/ci-cd.yml` | 流水线定义 |
| `docker-compose.prod.yml` | 服务器上的 compose（含一次性 `migrate` 服务） |
| `deploy/deploy.sh` | 服务器端部署脚本：备份、迁移、启动、健康检查、回滚 |
| `ruff.toml` | CI 使用的 lint 规则 |
| `.dockerignore` | 避免把 venv / .env / 本地库打进镜像 |

---

## 一、一次性准备

### 1. GitHub 仓库（作为构建入口）

在 GitHub 新建一个空仓库，名字建议和 Gitee 一致：`lxl-low-code-platform`。

让 `git push` 同时推到 Gitee 和 GitHub：

```bash
git remote set-url --add --push origin https://gitee.com/light_111/lxl-low-code-platform.git
git remote set-url --add --push origin https://github.com/<你的GitHub用户名>/lxl-low-code-platform.git

git remote -v      # 应该看到两条 push 地址
git push origin main
```

之后每次 `git push origin main` 会同时推两个仓库，GitHub 上就能触发 Actions。

> 如果不想配双推，也可以只在要发布时执行 `git push github main`（先用 `git remote add github <地址>` 添加）。

### 2. GitHub 仓库设置

**Settings → Actions → General**：确认允许运行 workflow。

**Settings → Secrets and variables → Actions**：

| 类型 | 名称 | 内容 |
|---|---|---|
| Secret | `SSH_PRIVATE_KEY` | 部署私钥的**完整内容**（含 BEGIN/END 行） |
| Variable | `STAGING_HOST` | 测试服务器地址 |
| Variable | `STAGING_USER` | `deploy` |
| Variable | `PROD_HOST` | 生产服务器地址 |
| Variable | `PROD_USER` | `deploy` |

> 现阶段只有一台服务器时，**先只配 `STAGING_*`**，`PROD_*` 留空。否则生产任务会连到同一台机器上起第二套容器，2C4G 扛不住。

**Settings → Environments**：

- 新建 `staging`：不需要审批
- 新建 `production`：勾选 **Required reviewers**，填上发布负责人

这样生产部署会停在「等待审批」，有人点通过才会执行。

### 3. 服务器准备

```bash
# 目录
sudo mkdir -p /srv/lxl-staging
sudo chown deploy:deploy /srv/lxl-staging

# 拉代码（部署脚本和 compose 从这里更新）
su - deploy
cd /srv/lxl-staging
git clone https://gitee.com/light_111/lxl-low-code-platform.git .

# 环境变量
cp .env.example .env
openssl rand -hex 32       # 生成 SECRET_KEY
nano .env

# 登录镜像仓库（GHCR 私有镜像必须）
# 先在 GitHub 生成 PAT（classic），勾选 read:packages
docker login ghcr.io -u <GitHub用户名>
# 提示输入密码时粘贴 PAT
```

`.env` 关键项：

```ini
APP_ENV=production
DEBUG=false
SECRET_KEY=<openssl 生成的>
MYSQL_ROOT_PASSWORD=<强密码>
MYSQL_PASSWORD=<强密码>
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DB=lxl_low_code
MYSQL_HOST_PORT=3307
APP_PORT=8000
```

### 4. 部署密钥

`SSH_PRIVATE_KEY` 用一对专门给部署的密钥，不要复用个人密钥：

```bash
# 在你的本机生成
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/lxl_deploy -N ""

# 公钥放到服务器 deploy 用户的 authorized_keys
ssh-copy-id -i ~/.ssh/lxl_deploy.pub deploy@191.40.44.149

# 私钥内容贴到 GitHub Secret SSH_PRIVATE_KEY
cat ~/.ssh/lxl_deploy
```

---

## 二、首次发布

1. 确认 GitHub 上已有代码（`git push origin main`）。
2. 打开仓库 → **Actions** → 选择 `CI/CD` → **Run workflow**
3. `deploy_env` 选 `none`，先只验证 CI。
4. 绿了以后，再选 `staging` 构建并部署。
5. 在服务器上验证：

```bash
cd /srv/lxl-staging
docker compose -f docker-compose.prod.yml ps
curl -s http://127.0.0.1:8000/health
docker compose -f docker-compose.prod.yml exec -T mysql \
  sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SELECT version_num FROM alembic_version" "$MYSQL_DATABASE"'
```

6. 生产：再 Run workflow，选 `production`。GitHub 会先跑 staging，然后在 production 环境等待审批。

---

## 三、日常流程

| 操作 | 结果 |
|---|---|
| PR 到 main | 只跑 `ci`（lint / pytest / 迁移校验） |
| push 到 main | `ci` → 构建推送镜像 → 自动部署 staging |
| 手动 Run workflow → `none` | 只跑 CI + 构建镜像 |
| 手动 Run workflow → `staging` | CI + 构建 + 部署 staging |
| 手动 Run workflow → `production` | CI + 构建 + staging + **审批后**生产 |

### 加字段/改表结构时

1. 本地改模型 → `alembic revision --autogenerate` → review → `alembic upgrade head` → pytest
2. 迁移文件和模型**一起提交**
3. push → CI 的 `alembic check` 会拦住「只改模型没生成迁移」
4. 新列默认用可空（`Mapped[str | None]`），非空走 expand/contract 分两次发布

---

## 四、回滚

**应用回滚**

健康检查失败时 `deploy.sh` 会自动用 `.last_good_image` 回滚。手工回滚：

```bash
ssh deploy@191.40.44.149
cd /srv/lxl-staging
cat .last_good_image
IMAGE=<上一个镜像> ./deploy/deploy.sh staging <上一个镜像>
```

也可以重新 Run workflow 指定一个旧 commit——但 Actions 默认构建当前 HEAD，更直接的方式是上面的命令。

**数据库回滚**

- staging：可以 `alembic downgrade -1`
- production：不 downgrade，用备份恢复

```bash
cd /srv/lxl-production
docker compose -f docker-compose.prod.yml exec -T mysql \
  sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < backups/xxx.sql
```

---

## 五、免费额度说明

| 项目 | 额度 |
|---|---|
| 公共仓库 | Actions 分钟数无限制 |
| 私有仓库 | 每月 2000 分钟（Free 计划） |
| GHCR 存储 | 私有镜像有免费额度，超出按 GB 计费 |
| 并发 | Free 计划 20 个并发任务 |

按本项目的流水线（每次约 3–5 分钟），私有仓库每月 2000 分钟大约够 400 次构建。

---

## 六、排错

| 现象 | 原因 / 处理 |
|---|---|
| Actions 里没有 workflow | 代码没推到 GitHub，或 workflow 文件不在默认分支 |
| `alembic check` 失败 | 改了模型没生成迁移 |
| 登录 GHCR 失败 | workflow 需要 `packages: write`（已在文件里配置） |
| 服务器拉镜像 `unauthorized` | 服务器没执行 `docker login ghcr.io`，或 PAT 没 `read:packages` |
| SSH 部署失败 `Permission denied` | `SSH_PRIVATE_KEY` 不完整，或公钥没加到 deploy 用户 |
| `git pull` 失败 | 服务器用的是 Gitee，确认 GitHub 和 Gitee 内容一致；私有仓库要配 Gitee 部署公钥 |
| 部署成功但健康检查失败 | `docker compose logs api`；常见是 `.env` 的 MySQL 配置或 `SECRET_KEY` |
| 生产任务一直等待 | 正常，去 Actions 页面点 Approve |

---

## 七、上线前检查清单

- [ ] 生产 `.env` 里 `DEBUG=false`、`SECRET_KEY` 已更换
- [ ] 数据库端口只监听 `127.0.0.1`
- [ ] 应用端口前有网关/反向代理和 HTTPS
- [ ] `backups/` 目录有写入权限且磁盘充足
- [ ] `production` 环境配置了 Required reviewers
- [ ] 迁移脚本经过 review，确认向后兼容
- [ ] 服务器执行过 `docker login ghcr.io`
- [ ] 只配置了当前实际拥有的环境（单机时先不要同时跑 staging 和 production）
