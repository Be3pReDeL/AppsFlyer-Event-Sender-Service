#!/bin/bash
#
# Health Monitor Script
# Проверяет здоровье сервиса и отправляет алерты при проблемах
#
# Установка (добавить в crontab):
#   */5 * * * * /opt/apps/AppsFlyer-Event-Sender-Service/scripts/health-monitor.sh
#
# Конфигурация через переменные окружения:
#   ALERT_EMAIL - email для отправки алертов
#   HEALTH_URL - URL health endpoint (по умолчанию http://localhost:8000/health/ready)
#   TELEGRAM_BOT_TOKEN - токен Telegram бота (опционально)
#   TELEGRAM_CHAT_ID - ID чата Telegram (опционально)
#

set -u

# Конфигурация
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health/ready}"
ALERT_EMAIL="${ALERT_EMAIL:-}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"
PROJECT_DIR="${PROJECT_DIR:-/opt/apps/AppsFlyer-Event-Sender-Service}"
LOG_FILE="${LOG_FILE:-/var/log/appsflyer-health-monitor.log}"
STATE_FILE="/tmp/appsflyer-health-state"

# Timeouts
HEALTH_TIMEOUT=5
CONNECT_TIMEOUT=3

# Цвета для логов
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] OK: $1${NC}" | tee -a "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARN: $1${NC}" | tee -a "$LOG_FILE"
}

# Функция отправки email
send_email_alert() {
    local subject="$1"
    local body="$2"
    
    if [ -n "$ALERT_EMAIL" ]; then
        if command -v mail &> /dev/null; then
            echo "$body" | mail -s "$subject" "$ALERT_EMAIL"
            log "Email alert sent to $ALERT_EMAIL"
        else
            log_warn "mail command not found, cannot send email alert"
        fi
    fi
}

# Функция отправки в Telegram
send_telegram_alert() {
    local message="$1"
    
    if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        curl -s -X POST \
            "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=${message}" \
            -d "parse_mode=HTML" \
            > /dev/null
        log "Telegram alert sent"
    fi
}

# Функция отправки алерта
send_alert() {
    local subject="$1"
    local message="$2"
    
    send_email_alert "$subject" "$message"
    send_telegram_alert "$message"
}

# Загрузить предыдущее состояние
load_previous_state() {
    if [ -f "$STATE_FILE" ]; then
        cat "$STATE_FILE"
    else
        echo "unknown"
    fi
}

# Сохранить текущее состояние
save_current_state() {
    echo "$1" > "$STATE_FILE"
}

# Проверка health endpoint
check_health_endpoint() {
    local response
    local http_code
    
    response=$(curl -s -w "\n%{http_code}" --connect-timeout "$CONNECT_TIMEOUT" --max-time "$HEALTH_TIMEOUT" "$HEALTH_URL" 2>&1)
    http_code=$(echo "$response" | tail -n1)
    
    if [ "$http_code" == "200" ]; then
        return 0
    else
        log_error "Health endpoint returned HTTP $http_code"
        return 1
    fi
}

# Проверка Docker контейнеров
check_docker_containers() {
    cd "$PROJECT_DIR" || return 1
    
    local api_status
    local worker_status
    local redis_status
    
    api_status=$(docker compose ps -q api 2>/dev/null | xargs docker inspect -f '{{.State.Status}}' 2>/dev/null)
    worker_status=$(docker compose ps -q worker 2>/dev/null | xargs docker inspect -f '{{.State.Status}}' 2>/dev/null)
    redis_status=$(docker compose ps -q redis 2>/dev/null | xargs docker inspect -f '{{.State.Status}}' 2>/dev/null)
    
    local issues=()
    
    if [ "$api_status" != "running" ]; then
        issues+=("API container not running (status: $api_status)")
    fi
    
    if [ "$worker_status" != "running" ]; then
        issues+=("Worker container not running (status: $worker_status)")
    fi
    
    if [ "$redis_status" != "running" ]; then
        issues+=("Redis container not running (status: $redis_status)")
    fi
    
    if [ ${#issues[@]} -gt 0 ]; then
        for issue in "${issues[@]}"; do
            log_error "$issue"
        done
        return 1
    fi
    
    return 0
}

# Проверка Redis
check_redis() {
    cd "$PROJECT_DIR" || return 1
    
    if docker compose exec -T redis redis-cli PING 2>/dev/null | grep -q "PONG"; then
        return 0
    else
        log_error "Redis not responding to PING"
        return 1
    fi
}

# Проверка размера DLQ
check_dlq_size() {
    cd "$PROJECT_DIR" || return 1
    
    local dlq_size
    dlq_size=$(docker compose exec -T redis redis-cli XLEN events:dlq 2>/dev/null || echo "0")
    
    if [ "$dlq_size" -gt 100 ]; then
        log_warn "DLQ size is high: $dlq_size messages"
        return 1
    fi
    
    return 0
}

# Проверка использования памяти
check_memory_usage() {
    cd "$PROJECT_DIR" || return 1
    
    local redis_memory
    redis_memory=$(docker stats --no-stream --format "{{.MemPerc}}" $(docker compose ps -q redis) 2>/dev/null | sed 's/%//')
    
    if [ -n "$redis_memory" ]; then
        if (( $(echo "$redis_memory > 90" | bc -l) )); then
            log_warn "Redis memory usage is high: ${redis_memory}%"
            return 1
        fi
    fi
    
    return 0
}

# Проверка использования диска
check_disk_usage() {
    local disk_usage
    disk_usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    
    if [ "$disk_usage" -gt 90 ]; then
        log_error "Disk usage is critical: ${disk_usage}%"
        return 1
    elif [ "$disk_usage" -gt 80 ]; then
        log_warn "Disk usage is high: ${disk_usage}%"
        return 1
    fi
    
    return 0
}

# Сбор диагностической информации
collect_diagnostics() {
    local output=""
    
    output+="=== Service Status ===\n"
    output+="$(cd "$PROJECT_DIR" && docker compose ps)\n\n"
    
    output+="=== Docker Stats ===\n"
    output+="$(docker stats --no-stream)\n\n"
    
    output+="=== Recent Logs (API) ===\n"
    output+="$(cd "$PROJECT_DIR" && docker compose logs --tail=20 api)\n\n"
    
    output+="=== Recent Logs (Worker) ===\n"
    output+="$(cd "$PROJECT_DIR" && docker compose logs --tail=20 worker)\n\n"
    
    output+="=== Redis Info ===\n"
    output+="$(cd "$PROJECT_DIR" && docker compose exec -T redis redis-cli INFO | grep -E '(redis_version|used_memory_human|connected_clients)')\n\n"
    
    output+="=== DLQ Size ===\n"
    output+="$(cd "$PROJECT_DIR" && docker compose exec -T redis redis-cli XLEN events:dlq)\n\n"
    
    echo -e "$output"
}

# Попытка автоматического восстановления
attempt_recovery() {
    log "Attempting automatic recovery..."
    
    cd "$PROJECT_DIR" || return 1
    
    # Проверка что контейнеры существуют
    if ! docker compose ps &>/dev/null; then
        log_error "Cannot access docker compose, manual intervention required"
        return 1
    fi
    
    # Попытка перезапуска сервисов
    log "Restarting services..."
    if docker compose restart; then
        sleep 10
        
        # Проверка что восстановление успешно
        if check_health_endpoint && check_docker_containers; then
            log_success "Recovery successful"
            return 0
        else
            log_error "Recovery failed"
            return 1
        fi
    else
        log_error "Failed to restart services"
        return 1
    fi
}

# Основная проверка
main() {
    log "Starting health check..."
    
    local previous_state
    local current_state="healthy"
    local issues=()
    
    previous_state=$(load_previous_state)
    
    # Выполнить все проверки
    if ! check_health_endpoint; then
        issues+=("Health endpoint check failed")
        current_state="unhealthy"
    fi
    
    if ! check_docker_containers; then
        issues+=("Docker containers check failed")
        current_state="unhealthy"
    fi
    
    if ! check_redis; then
        issues+=("Redis check failed")
        current_state="unhealthy"
    fi
    
    if ! check_dlq_size; then
        issues+=("DLQ size check failed")
        current_state="degraded"
    fi
    
    if ! check_memory_usage; then
        issues+=("Memory usage check failed")
        current_state="degraded"
    fi
    
    if ! check_disk_usage; then
        issues+=("Disk usage check failed")
        current_state="degraded"
    fi
    
    # Обработка результатов
    if [ "$current_state" == "unhealthy" ]; then
        log_error "Service is UNHEALTHY"
        
        # Отправить алерт только если состояние изменилось
        if [ "$previous_state" != "unhealthy" ]; then
            local alert_message="🔴 <b>AppsFlyer Event Sender - SERVICE DOWN</b>\n\n"
            alert_message+="Time: $(date '+%Y-%m-%d %H:%M:%S')\n"
            alert_message+="Issues:\n"
            for issue in "${issues[@]}"; do
                alert_message+="- $issue\n"
            done
            alert_message+="\nDiagnostics:\n$(collect_diagnostics)"
            
            send_alert "CRITICAL: AppsFlyer Service DOWN" "$alert_message"
            
            # Попытка автоматического восстановления
            if attempt_recovery; then
                current_state="recovered"
                send_alert "INFO: AppsFlyer Service RECOVERED" "Service has been automatically recovered at $(date '+%Y-%m-%d %H:%M:%S')"
            fi
        fi
        
    elif [ "$current_state" == "degraded" ]; then
        log_warn "Service is DEGRADED"
        
        if [ "$previous_state" == "healthy" ] || [ "$previous_state" == "unknown" ]; then
            local alert_message="⚠️ <b>AppsFlyer Event Sender - SERVICE DEGRADED</b>\n\n"
            alert_message+="Time: $(date '+%Y-%m-%d %H:%M:%S')\n"
            alert_message+="Issues:\n"
            for issue in "${issues[@]}"; do
                alert_message+="- $issue\n"
            done
            
            send_alert "WARNING: AppsFlyer Service DEGRADED" "$alert_message"
        fi
        
    else
        log_success "Service is HEALTHY"
        
        # Отправить алерт о восстановлении
        if [ "$previous_state" == "unhealthy" ] || [ "$previous_state" == "degraded" ]; then
            send_alert "INFO: AppsFlyer Service RECOVERED" "✅ Service has recovered and is now healthy at $(date '+%Y-%m-%d %H:%M:%S')"
        fi
    fi
    
    # Сохранить текущее состояние
    save_current_state "$current_state"
    
    log "Health check completed: $current_state"
}

# Запуск
main "$@"
