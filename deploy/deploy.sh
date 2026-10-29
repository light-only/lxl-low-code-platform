#!/usr/bin/env bash
#
# 服务器端部署脚本（由 GitHub Actions 通过 SSH 调用，也可手工执行）
#
#   ./deploy/deploy.sh <staging|production> <image:tag>
#
# 流程：启库 → 备份 → 拉镜像 → 跑迁移 → 启动应用 → 健康检查 → 失败回滚应用
#
# 约定：数据库迁移必须向后兼容（expand/contract）。因此健康检查失败时
# 只回滚应用镜像，不回滚数据库——旧代码必须能在新表结构上继续运行。

set -euo pipefail

ENV_NAME="${1:?用法: deploy.sh <staging|production> <image:tag>}"
IMAGE="${2:?用法: deploy.sh <staging|production> <image:tag>}"

APP_DIR="${APP_DIR:-/srv/lxl-${ENV_NAME}}"
COMPOSE_FILE="$APP_DIR/docker-compose.prod.yml"

cd "$APP_DIR"
[ -f "$COMPOSE_FILE" ] || { echo "缺少 $COMPOSE_FILE"; exit 1; }
[ -f .env ] || { echo "缺少 $APP_DIR/.env"; exit 1; }

# 同一环境同时只允许一个部署在执行
if command -v flock >/dev/null 2>&1; then
    exec 9>"$APP_DIR/.deploy.lock"
    flock -n 9 || { echo "已有部署正在执行，退出"; exit 1; }
fi

log() { printf '\n[%s] %s\n' "$(date '+%F %T')" "$*"; }
compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

APP_PORT="$(grep -E '^APP_PORT=' .env 2>/dev/null | head -n1 | cut -d= -f2- | tr -d '\r"' || true)"
APP_PORT="${APP_PORT:-8000}"

log "0/6 确保 MySQL 已启动"
compose up -d mysql
for _ in $(seq 1 60); do
    if compose exec -T mysql sh -c \
        'mysqladmin ping -h127.0.0.1 -uroot -p"$MYSQL_ROOT_PASSWORD" --silent' >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

log "1/6 备份数据库"
mkdir -p backups
BACKUP_FILE="backups/${ENV_NAME}_$(date +%Y%m%d_%H%M%S).sql"
compose exec -T mysql sh -c \
    'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines "$MYSQL_DATABASE"' \
    > "$BACKUP_FILE"
if [ ! -s "$BACKUP_FILE" ]; then
    echo "备份文件为空，中止部署"
    exit 1
fi
log "备份完成: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
# 只保留最近 10 份备份
ls -1t backups/*.sql 2>/dev/null | tail -n +11 | xargs -r rm -f || true

PREV_IMAGE="$(cat .last_good_image 2>/dev/null | tr -d '\r' || true)"

log "2/6 拉取镜像 $IMAGE"
IMAGE="$IMAGE" compose pull api

log "3/6 执行数据库迁移"
IMAGE="$IMAGE" compose run --rm migrate

log "4/6 启动应用"
IMAGE="$IMAGE" compose up -d --no-deps api

log "5/6 健康检查 http://127.0.0.1:${APP_PORT}/health"
OK=0
for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
        OK=1
        break
    fi
    sleep 2
done

if [ "$OK" -ne 1 ]; then
    log "健康检查失败，最近日志："
    compose logs --tail=100 api || true
    if [ -n "$PREV_IMAGE" ]; then
        log "回滚应用到上一版本 $PREV_IMAGE（数据库结构保持不变）"
        IMAGE="$PREV_IMAGE" compose up -d --no-deps api
    fi
    exit 1
fi

echo "$IMAGE" > .last_good_image
log "6/6 部署成功: $IMAGE"
