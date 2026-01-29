#!/bin/bash
#
# Rollback Script
# Откат на предыдущую версию при проблемах с деплоем
#
# Использование:
#   bash scripts/rollback.sh [backup_timestamp]
#
# Пример:
#   bash scripts/rollback.sh 20260129_143022
#   bash scripts/rollback.sh  # откат на последний backup
#

set -e

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Конфигурация
PROJECT_DIR="/opt/apps/AppsFlyer-Event-Sender-Service"
BACKUP_DIR="/opt/backups/deployments"
BACKUP_TIMESTAMP="${1:-}"

echo "=========================================="
echo "AppsFlyer Event Sender - Rollback"
echo "=========================================="
echo ""

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

log_step() {
    echo -e "\n${BLUE}>>> $1${NC}\n"
}

# Проверка прав
if [ "$EUID" -eq 0 ]; then
    log_warn "Running as root. Consider using 'deploy' user instead."
fi

# Проверка директории проекта
if [ ! -d "$PROJECT_DIR" ]; then
    log_error "Project directory not found: $PROJECT_DIR"
fi

cd "$PROJECT_DIR"

# Проверка директории бэкапов
if [ ! -d "$BACKUP_DIR" ]; then
    log_error "Backup directory not found: $BACKUP_DIR"
fi

# Найти последний backup если timestamp не указан
if [ -z "$BACKUP_TIMESTAMP" ]; then
    log_info "No timestamp provided, finding latest backup..."
    
    LATEST_ENV=$(ls -t "$BACKUP_DIR"/env-backup-* 2>/dev/null | head -1)
    
    if [ -z "$LATEST_ENV" ]; then
        log_error "No backups found in $BACKUP_DIR"
    fi
    
    BACKUP_TIMESTAMP=$(basename "$LATEST_ENV" | sed 's/env-backup-//')
    log_info "Using latest backup: $BACKUP_TIMESTAMP"
fi

# Проверка что backup существует
ENV_BACKUP="$BACKUP_DIR/env-backup-$BACKUP_TIMESTAMP"
REDIS_BACKUP="$BACKUP_DIR/redis-backup-$BACKUP_TIMESTAMP.rdb"

if [ ! -f "$ENV_BACKUP" ]; then
    log_error "Environment backup not found: $ENV_BACKUP"
fi

log_info "Found environment backup: $ENV_BACKUP"

if [ -f "$REDIS_BACKUP" ]; then
    log_info "Found Redis backup: $REDIS_BACKUP"
else
    log_warn "Redis backup not found: $REDIS_BACKUP (will skip Redis restore)"
fi

# Подтверждение
echo ""
echo "=========================================="
echo "ROLLBACK CONFIRMATION"
echo "=========================================="
echo "This will:"
echo "  1. Stop current containers"
echo "  2. Restore .env from backup: $BACKUP_TIMESTAMP"
echo "  3. Restore Redis data (if available)"
echo "  4. Restart containers"
echo ""
echo "Current commit: $(git rev-parse --short HEAD)"
echo "Current branch: $(git rev-parse --abbrev-ref HEAD)"
echo ""

read -p "Continue with rollback? (yes/no): " -r CONFIRM
echo ""

if [[ ! "$CONFIRM" =~ ^[Yy][Ee][Ss]$ ]]; then
    log_info "Rollback cancelled by user"
    exit 0
fi

# 1. Остановить текущие контейнеры
log_step "Step 1: Stopping current containers..."

docker compose down --timeout 30
log_info "Containers stopped"

# 2. Backup текущей конфигурации (на всякий случай)
log_step "Step 2: Creating safety backup of current state..."

SAFETY_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
cp .env "$BACKUP_DIR/env-rollback-safety-$SAFETY_TIMESTAMP" 2>/dev/null || true
log_info "Current .env backed up to: env-rollback-safety-$SAFETY_TIMESTAMP"

CURRENT_COMMIT=$(git rev-parse --short HEAD)
echo "$CURRENT_COMMIT" > "$BACKUP_DIR/commit-rollback-safety-$SAFETY_TIMESTAMP"
log_info "Current commit saved: $CURRENT_COMMIT"

# 3. Восстановить .env
log_step "Step 3: Restoring environment configuration..."

cp "$ENV_BACKUP" .env
log_info ".env restored from backup"

# Показать разницу
log_info "Environment changes:"
diff "$BACKUP_DIR/env-rollback-safety-$SAFETY_TIMESTAMP" .env || true

# 4. Восстановить Redis (если backup есть)
if [ -f "$REDIS_BACKUP" ]; then
    log_step "Step 4: Restoring Redis data..."
    
    # Запустить только Redis временно
    docker compose up -d redis
    sleep 5
    
    # Проверить что Redis запущен
    if ! docker compose exec redis redis-cli PING > /dev/null 2>&1; then
        log_error "Failed to start Redis for restore"
    fi
    
    # Остановить Redis
    docker compose stop redis
    sleep 2
    
    # Восстановить dump.rdb
    REDIS_CONTAINER=$(docker compose ps -aq redis)
    if [ -n "$REDIS_CONTAINER" ]; then
        docker cp "$REDIS_BACKUP" "$REDIS_CONTAINER:/data/dump.rdb"
        log_info "Redis data restored from backup"
    else
        log_error "Redis container not found"
    fi
else
    log_step "Step 4: Skipping Redis restore (no backup found)"
fi

# 5. Откат Git (опционально)
log_step "Step 5: Git repository..."

CURRENT_COMMIT=$(git rev-parse --short HEAD)
log_info "Current commit: $CURRENT_COMMIT"

# Спросить нужно ли откатить Git
read -p "Do you want to checkout to a specific commit? (yes/no): " -r GIT_ROLLBACK
echo ""

if [[ "$GIT_ROLLBACK" =~ ^[Yy][Ee][Ss]$ ]]; then
    read -p "Enter commit hash (or 'previous' for HEAD~1): " -r TARGET_COMMIT
    
    if [ "$TARGET_COMMIT" == "previous" ]; then
        TARGET_COMMIT="HEAD~1"
    fi
    
    log_info "Checking out to: $TARGET_COMMIT"
    git checkout "$TARGET_COMMIT"
    
    NEW_COMMIT=$(git rev-parse --short HEAD)
    log_info "Checked out to commit: $NEW_COMMIT"
else
    log_info "Keeping current Git commit"
fi

# 6. Пересборка образов (на случай если код изменился)
log_step "Step 6: Rebuilding Docker images..."

docker compose build --no-cache
log_info "Images rebuilt"

# 7. Запуск контейнеров
log_step "Step 7: Starting containers..."

docker compose up -d
log_info "Containers started"

# 8. Ожидание готовности
log_step "Step 8: Waiting for services to be ready..."

MAX_WAIT=60
WAIT_INTERVAL=2
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
    if curl -sf http://localhost:8000/health/ready > /dev/null 2>&1; then
        log_info "Service is ready! (waited ${ELAPSED}s)"
        break
    fi
    
    sleep $WAIT_INTERVAL
    ELAPSED=$((ELAPSED + WAIT_INTERVAL))
    echo -n "."
done

echo ""

if [ $ELAPSED -ge $MAX_WAIT ]; then
    log_error "Service failed to become ready within ${MAX_WAIT}s"
fi

# 9. Проверка здоровья
log_step "Step 9: Health checks..."

VALIDATION_FAILED=0

# Liveness
if curl -sf http://localhost:8000/health/live > /dev/null; then
    log_info "✓ Liveness check passed"
else
    log_error "✗ Liveness check failed"
    VALIDATION_FAILED=1
fi

# Readiness
if curl -sf http://localhost:8000/health/ready > /dev/null; then
    log_info "✓ Readiness check passed"
else
    log_error "✗ Readiness check failed"
    VALIDATION_FAILED=1
fi

# Container status
log_info "Container status:"
docker compose ps

# Проверить логи на ошибки
ERROR_COUNT=$(docker compose logs --tail=50 2>&1 | grep -i error | wc -l)

if [ "$ERROR_COUNT" -gt 0 ]; then
    log_warn "Found $ERROR_COUNT error messages in recent logs"
    docker compose logs --tail=20 2>&1 | grep -i error
else
    log_info "No errors in recent logs"
fi

# 10. Финальный отчёт
log_step "Rollback Summary"

echo "Rolled back to:    $BACKUP_TIMESTAMP"
echo "Current commit:    $(git rev-parse --short HEAD)"
echo "Current branch:    $(git rev-parse --abbrev-ref HEAD)"
echo ""

echo "Container status:"
docker compose ps
echo ""

echo "Recent logs:"
docker compose logs --tail=10
echo ""

if [ $VALIDATION_FAILED -eq 0 ]; then
    echo "=========================================="
    echo -e "${GREEN}✓ ROLLBACK SUCCESSFUL!${NC}"
    echo "=========================================="
    echo ""
    echo "Service has been rolled back to: $BACKUP_TIMESTAMP"
    echo ""
    echo "Next steps:"
    echo "1. Verify functionality with test requests"
    echo "2. Monitor logs: docker compose logs -f"
    echo "3. Check metrics: curl http://localhost:8000/metrics"
    echo ""
    echo "If rollback didn't fix the issue, check:"
    echo "  - Application logs: docker compose logs"
    echo "  - System logs: journalctl -u docker"
    echo "  - Nginx logs (if applicable): sudo tail -f /var/log/nginx/error.log"
    exit 0
else
    echo "=========================================="
    echo -e "${RED}✗ ROLLBACK VALIDATION FAILED${NC}"
    echo "=========================================="
    echo ""
    echo "Rollback was executed but validation failed."
    echo "Manual intervention may be required."
    echo ""
    echo "Check logs: docker compose logs"
    echo ""
    echo "Safety backup created at:"
    echo "  .env: env-rollback-safety-$SAFETY_TIMESTAMP"
    echo "  commit: commit-rollback-safety-$SAFETY_TIMESTAMP"
    exit 1
fi
