#!/usr/bin/env bash
set -eo pipefail

BACKUP_DIR="/root/abc-project/backups"
LOG_FILE="/var/log/quant-backup.log"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/quant_backup_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting PostgreSQL backup..." | tee -a "${LOG_FILE}"

if docker exec enterprise-ai-quant-postgres pg_dump -U quant -d quant | gzip > "${BACKUP_FILE}"; then
    FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup successful: ${BACKUP_FILE} (${FILE_SIZE})" | tee -a "${LOG_FILE}"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: PostgreSQL backup failed!" | tee -a "${LOG_FILE}" >&2
    exit 1
fi

find "${BACKUP_DIR}" -name "quant_backup_*.sql.gz" -type f -mtime +7 -exec rm -f {} \;
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Old backups cleanup completed." | tee -a "${LOG_FILE}"
