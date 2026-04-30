#!/bin/sh
# SQLite 每日备份脚本：由 docker-compose backup 服务的 busybox crond 在容器内调用。
#
# 备份策略：
#   - 使用 sqlite3 .backup 命令（WAL 安全热备份）
#   - 备份文件打包为 tar.gz 后删除原 .db 文件
#   - 保留最近 7 份，滚动删除旧备份
#
# 容器内路径约定（与 docker-compose.yml volumes 对应）：
#   DB:      /app/webui/server/data/app.db
#   备份目录: /app/webui/server/data/backups/

set -e

DB="/app/webui/server/data/app.db"
BACKUP_DIR="/app/webui/server/data/backups"
KEEP=7

if [ ! -f "$DB" ]; then
  echo "[backup] DB not found at $DB, skipping."
  exit 0
fi

mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d_%H%M%S)
SNAP="${BACKUP_DIR}/app_${TS}.db"
ARCHIVE="${BACKUP_DIR}/app_${TS}.tar.gz"

echo "[backup] starting backup at $(date)"
sqlite3 "$DB" ".backup ${SNAP}"
tar -czf "$ARCHIVE" -C "$BACKUP_DIR" "app_${TS}.db"
rm -f "$SNAP"
echo "[backup] created ${ARCHIVE}"

# 保留最近 KEEP 份，删除多余的旧备份
ls -t "${BACKUP_DIR}"/*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r OLD; do
  rm -f "$OLD"
  echo "[backup] removed old backup: $OLD"
done

echo "[backup] done. backups kept: $(ls "${BACKUP_DIR}"/*.tar.gz 2>/dev/null | wc -l)"
