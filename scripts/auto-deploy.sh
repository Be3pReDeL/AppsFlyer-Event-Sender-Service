#!/bin/bash
#
# Automatic Deployment Script
# Полностью автоматический деплой AppsFlyer Event Sender Service
#
# Использование:
#   bash scripts/auto-deploy.sh [environment]
#
# Параметры:
#   environment: dev|staging|production (по умолчанию: production)
#
# Пример:
#   bash scripts/auto-deploy.sh production
#

set -e

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Конфигурация
ENVIRONMENT="${1:-production}"
PROJECT_DIR="/opt/apps/AppsFlyer-Event-Sender-Service"
BACKUP_DIR="/opt/backups/deployments"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=========================================="
echo "AppsFlyer Event Sender - Auto Deploy"
echo "Environment: $ENVIRONMENT"
echo "Timestamp: $TIMESTAMP"
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

# Проверка окружения
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|production)$ ]]; then
    log_error "Invalid environment: $ENVIRONMENT. Use: dev, staging, or production"
fi

# Проверка прав
if [ "$EUID" -eq 0 ]; then
    log_warn "Running as root. Consider using 'deploy' user instead."
fi

# Проверка зависимостей
log_step "Checking dependencies..."

MISSING_DEPS=()

if ! command -v git &> /dev/null; then
    MISSING_DEPS+=("git")
fi

if ! command -v docker &> /dev/null; then
    MISSING_DEPS+=("docker")
fi

if ! docker compose version &> /dev/null; then
    MISSING_DEPS+=("docker-compose")
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    log_error "Missing dependencies: ${MISSING_DEPS[*]}"
fi

log_info "All dependencies present"

# Создать backup директорию
mkdir -p "$BACKUP_DIR"

# Проверка что мы в правильной директории
if [ ! -f "$PROJECT_DIR/docker-compose.yml" ]; then
    log_error "Project directory not found: $PROJECT_DIR"
fi

cd "$PROJECT_DIR"
log_info "Working directory: $(pwd)"

# 1. Backup текущей версии
log_step "Step 1: Backing up current deployment..."

if docker compose ps -q &> /dev/null; then
    log_info "Creating Redis backup..."
    docker compose exec -T redis redis-cli BGSAVE || true
    sleep 2
    
    REDIS_CONTAINER=$(docker compose ps -q redis 2>/dev/null)
    if [ -n "$REDIS_CONTAINER" ]; then
        docker cp "$REDIS_CONTAINER:/data/dump.rdb" "$BACKUP_DIR/redis-backup-$TIMESTAMP.rdb" || true
        log_info "Redis backup saved: $BACKUP_DIR/redis-backup-$TIMESTAMP.rdb"
    fi
fi

# Backup .env
if [ -f .env ]; then
    cp .env "$BACKUP_DIR/env-backup-$TIMESTAMP"
    log_info ".env backup saved: $BACKUP_DIR/env-backup-$TIMESTAMP"
fi

# 2. Получить обновления
log_step "Step 2: Fetching updates from Git..."

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
CURRENT_COMMIT=$(git rev-parse --short HEAD)

log_info "Current branch: $CURRENT_BRANCH"
log_info "Current commit: $CURRENT_COMMIT"

# Stash local changes if any
if ! git diff-index --quiet HEAD --; then
    log_warn "Local changes detected, stashing..."
    git stash
fi

git fetch origin
git pull origin "$CURRENT_BRANCH"

NEW_COMMIT=$(git rev-parse --short HEAD)
log_info "Updated to commit: $NEW_COMMIT"

if [ "$CURRENT_COMMIT" == "$NEW_COMMIT" ]; then
    log_info "No new commits, already up to date"
else
    log_info "Updated from $CURRENT_COMMIT to $NEW_COMMIT"
    git log --oneline "$CURRENT_COMMIT..$NEW_COMMIT" | head -5
fi

# 3. Проверить изменения в .env.example
log_step "Step 3: Checking environment configuration..."

if [ -f .env.example ]; then
    if ! diff -q .env.example .env > /dev/null 2>&1; then
        log_warn ".env and .env.example differ"
        
        # Показать новые переменные
        NEW_VARS=$(comm -13 <(grep -v '^#' .env | cut -d= -f1 | sort) <(grep -v '^#' .env.example | cut -d= -f1 | sort) || true)
        
        if [ -n "$NEW_VARS" ]; then
            log_warn "New variables in .env.example:"
            echo "$NEW_VARS"
            log_warn "You may need to update .env manually"
        fi
    else
        log_info ".env is up to date"
    fi
fi

# Проверить обязательные переменные
log_info "Validating required environment variables..."

REQUIRED_VARS=("API_TOKENS" "APPSFLYER_DEV_KEY" "APPSFLYER_DEFAULT_APP_ID")
MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if ! grep -q "^${var}=.\+" .env; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    log_error "Missing required variables in .env: ${MISSING_VARS[*]}"
fi

log_info "All required variables present"

# 4. Pre-deployment тесты (опционально)
log_step "Step 4: Running pre-deployment checks..."

# Проверить синтаксис docker-compose
if ! docker compose config > /dev/null 2>&1; then
    log_error "docker-compose.yml validation failed"
fi

log_info "docker-compose.yml is valid"

# 5. Остановить текущие контейнеры
log_step "Step 5: Stopping current containers..."

if docker compose ps -q &> /dev/null; then
    log_info "Stopping containers..."
    docker compose down --timeout 30
    log_info "Containers stopped"
else
    log_info "No running containers"
fi

# 6. Пересборка образов
log_step "Step 6: Building Docker images..."

log_info "Building images (this may take a few minutes)..."
docker compose build --no-cache --pull

log_info "Images built successfully"

# 7. Запуск новой версии
log_step "Step 7: Starting new deployment..."

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

# Liveness
if curl -sf http://localhost:8000/health/live > /dev/null; then
    log_info "✓ Liveness check passed"
else
    log_error "✗ Liveness check failed"
fi

# Readiness
if curl -sf http://localhost:8000/health/ready > /dev/null; then
    log_info "✓ Readiness check passed"
else
    log_error "✗ Readiness check failed"
fi

# Container status
log_info "Container status:"
docker compose ps

# 10. Проверка логов
log_step "Step 10: Checking logs for errors..."

# Проверить последние 50 строк логов на ошибки
ERROR_COUNT=$(docker compose logs --tail=50 2>&1 | grep -i error | wc -l)

if [ "$ERROR_COUNT" -gt 0 ]; then
    log_warn "Found $ERROR_COUNT error messages in recent logs"
    log_warn "Recent errors:"
    docker compose logs --tail=50 2>&1 | grep -i error | head -5
else
    log_info "No errors in recent logs"
fi

# 11. Тестовый запрос
log_step "Step 11: Sending test request..."

# Получить первый токен из .env
TEST_TOKEN=$(grep "^API_TOKENS=" .env | cut -d= -f2 | cut -d, -f1)

if [ -n "$TEST_TOKEN" ]; then
    TEST_RESPONSE=$(curl -s -X POST "http://localhost:8000/v1/track/registration?token=$TEST_TOKEN&appsflyer_id=deploy-test-$(date +%s)&platform=ios")
    
    if echo "$TEST_RESPONSE" | grep -q "accepted"; then
        log_info "✓ Test request successful"
        echo "Response: $TEST_RESPONSE"
    else
        log_warn "Test request returned unexpected response:"
        echo "$TEST_RESPONSE"
    fi
else
    log_warn "Cannot extract API token for test request"
fi

# 12. Cleanup старых образов
log_step "Step 12: Cleaning up..."

log_info "Removing old Docker images..."
docker image prune -f > /dev/null 2>&1 || true

# Cleanup старых бэкапов (старше 30 дней)
find "$BACKUP_DIR" -type f -mtime +30 -delete 2>/dev/null || true

log_info "Cleanup completed"

# 13. Финальный отчёт
log_step "Deployment Summary"

echo "Environment:       $ENVIRONMENT"
echo "Previous commit:   $CURRENT_COMMIT"
echo "Current commit:    $NEW_COMMIT"
echo "Deploy timestamp:  $TIMESTAMP"
echo "Backup location:   $BACKUP_DIR"
echo ""

# Показать running containers
echo "Running containers:"
docker compose ps
echo ""

# Показать resource usage
echo "Resource usage:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
echo ""

# Финальная проверка
log_step "Final Validation"

VALIDATION_FAILED=0

# Health checks
if ! curl -sf http://localhost:8000/health/ready > /dev/null; then
    log_error "Health check failed"
    VALIDATION_FAILED=1
fi

# Container count
EXPECTED_CONTAINERS=3  # api, worker, redis
RUNNING_CONTAINERS=$(docker compose ps -q | wc -l)

if [ "$RUNNING_CONTAINERS" -ne "$EXPECTED_CONTAINERS" ]; then
    log_error "Expected $EXPECTED_CONTAINERS containers, but $RUNNING_CONTAINERS are running"
    VALIDATION_FAILED=1
fi

# Проверить DLQ
DLQ_SIZE=$(docker compose exec -T redis redis-cli XLEN events:dlq 2>/dev/null || echo "0")
if [ "$DLQ_SIZE" -gt 0 ]; then
    log_warn "DLQ contains $DLQ_SIZE messages"
fi

if [ $VALIDATION_FAILED -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo -e "${GREEN}✓ DEPLOYMENT SUCCESSFUL!${NC}"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "1. Monitor logs: docker compose logs -f"
    echo "2. Check metrics: curl http://localhost:8000/metrics"
    echo "3. Verify via domain (if applicable)"
    echo ""
    echo "Rollback (if needed):"
    echo "  docker compose down"
    echo "  git checkout $CURRENT_COMMIT"
    echo "  docker compose up -d"
    exit 0
else
    echo ""
    echo "=========================================="
    echo -e "${RED}✗ DEPLOYMENT FAILED VALIDATION${NC}"
    echo "=========================================="
    echo ""
    echo "Check logs: docker compose logs"
    echo ""
    echo "Rollback:"
    echo "  bash scripts/rollback.sh $TIMESTAMP"
    exit 1
fi
