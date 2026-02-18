#!/bin/bash
#
# Pre-flight Check Script
# Проверяет готовность системы к деплою AppsFlyer Event Sender Service
#
# Использование: bash preflight-check.sh
#

set -e

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PASS="${GREEN}✓${NC}"
FAIL="${RED}✗${NC}"
WARN="${YELLOW}⚠${NC}"
INFO="${BLUE}ℹ${NC}"

ERRORS=0
WARNINGS=0

echo "=========================================="
echo "AppsFlyer Event Sender - Pre-flight Check"
echo "=========================================="
echo ""

# Helper functions
check_pass() {
    echo -e "${PASS} $1"
}

check_fail() {
    echo -e "${FAIL} $1"
    ERRORS=$((ERRORS + 1))
}

check_warn() {
    echo -e "${WARN} $1"
    WARNINGS=$((WARNINGS + 1))
}

check_info() {
    echo -e "${INFO} $1"
}

# 1. Проверка операционной системы
echo "1. Операционная система"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [[ "$ID" == "ubuntu" ]]; then
        check_pass "Ubuntu $VERSION_ID"
        if [[ "$VERSION_ID" < "20.04" ]]; then
            check_warn "Рекомендуется Ubuntu 20.04 или новее"
        fi
    else
        check_warn "OS: $ID $VERSION_ID (рекомендуется Ubuntu)"
    fi
else
    check_fail "Не удалось определить ОС"
fi
echo ""

# 2. Проверка Docker
echo "2. Docker"
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version | grep -oP '\d+\.\d+\.\d+' | head -1)
    check_pass "Docker установлен: $DOCKER_VERSION"
    
    # Проверка что Docker daemon запущен
    if docker info &> /dev/null; then
        check_pass "Docker daemon работает"
    else
        check_fail "Docker daemon не запущен"
    fi
    
    # Проверка прав текущего пользователя
    if groups | grep -q docker; then
        check_pass "Пользователь $USER в группе docker"
    else
        check_warn "Пользователь $USER не в группе docker (потребуется sudo)"
    fi
else
    check_fail "Docker не установлен"
fi
echo ""

# 3. Проверка Docker Compose
echo "3. Docker Compose"
if docker compose version &> /dev/null; then
    COMPOSE_VERSION=$(docker compose version | grep -oP '\d+\.\d+\.\d+' | head -1)
    check_pass "Docker Compose установлен: $COMPOSE_VERSION"
else
    check_fail "Docker Compose не установлен"
fi
echo ""

# 4. Проверка Git
echo "4. Git"
if command -v git &> /dev/null; then
    GIT_VERSION=$(git --version | grep -oP '\d+\.\d+\.\d+')
    check_pass "Git установлен: $GIT_VERSION"
else
    check_fail "Git не установлен"
fi
echo ""

# 5. Проверка портов
echo "5. Проверка портов"
check_port() {
    local port=$1
    local service=$2
    if ss -tuln | grep -q ":$port "; then
        check_warn "Порт $port ($service) занят"
        ss -tuln | grep ":$port " | head -1
    else
        check_pass "Порт $port ($service) свободен"
    fi
}

check_port 8000 "API"
check_port 6379 "Redis"
check_port 80 "HTTP"
check_port 443 "HTTPS"
echo ""

# 6. Проверка системных ресурсов
echo "6. Системные ресурсы"

# RAM
TOTAL_RAM=$(free -m | awk '/^Mem:/{print $2}')
if [ "$TOTAL_RAM" -ge 1900 ]; then
    check_pass "RAM: ${TOTAL_RAM}MB (достаточно)"
elif [ "$TOTAL_RAM" -ge 900 ]; then
    check_warn "RAM: ${TOTAL_RAM}MB (минимально приемлемо, рекомендуется 2GB+)"
else
    check_fail "RAM: ${TOTAL_RAM}MB (недостаточно, минимум 1GB)"
fi

# Disk space
DISK_AVAILABLE=$(df -BG / | awk 'NR==2 {print $4}' | sed 's/G//')
if [ "$DISK_AVAILABLE" -ge 10 ]; then
    check_pass "Свободное место: ${DISK_AVAILABLE}GB"
elif [ "$DISK_AVAILABLE" -ge 5 ]; then
    check_warn "Свободное место: ${DISK_AVAILABLE}GB (рекомендуется 10GB+)"
else
    check_fail "Свободное место: ${DISK_AVAILABLE}GB (недостаточно)"
fi

# CPU cores
CPU_CORES=$(nproc)
check_info "CPU cores: $CPU_CORES"
echo ""

# 7. Проверка Nginx (если установлен)
echo "7. Nginx"
if command -v nginx &> /dev/null; then
    NGINX_VERSION=$(nginx -v 2>&1 | grep -oP '\d+\.\d+\.\d+')
    check_pass "Nginx установлен: $NGINX_VERSION"
    
    if systemctl is-active --quiet nginx; then
        check_pass "Nginx запущен"
    else
        check_warn "Nginx не запущен"
    fi
else
    check_info "Nginx не установлен (опционально для production)"
fi
echo ""

# 8. Проверка Certbot (если установлен)
echo "8. Certbot (SSL)"
if command -v certbot &> /dev/null; then
    CERTBOT_VERSION=$(certbot --version 2>&1 | grep -oP '\d+\.\d+\.\d+')
    check_pass "Certbot установлен: $CERTBOT_VERSION"
else
    check_info "Certbot не установлен (опционально для SSL)"
fi
echo ""

# 9. Проверка firewall
echo "9. Firewall"
if command -v ufw &> /dev/null; then
    UFW_STATUS=$(ufw status | head -1)
    if [[ "$UFW_STATUS" == *"active"* ]]; then
        check_pass "UFW активен"
        
        # Проверка важных правил
        if ufw status | grep -q "22/tcp.*ALLOW"; then
            check_pass "Порт 22 (SSH) разрешен"
        else
            check_fail "Порт 22 (SSH) не разрешен - можете потерять доступ!"
        fi
        
        if ufw status | grep -q "80/tcp.*ALLOW"; then
            check_pass "Порт 80 (HTTP) разрешен"
        else
            check_info "Порт 80 (HTTP) не разрешен"
        fi
        
        if ufw status | grep -q "443/tcp.*ALLOW"; then
            check_pass "Порт 443 (HTTPS) разрешен"
        else
            check_info "Порт 443 (HTTPS) не разрешен"
        fi
    else
        check_warn "UFW не активен"
    fi
else
    check_warn "UFW не установлен"
fi
echo ""

# 10. Проверка сетевого соединения
echo "10. Сетевое соединение"
if ping -c 1 8.8.8.8 &> /dev/null; then
    check_pass "Интернет соединение работает"
    
    # Проверка DNS
    if ping -c 1 google.com &> /dev/null; then
        check_pass "DNS работает"
    else
        check_fail "DNS не работает"
    fi
    
    # Проверка доступности Docker Hub
    if curl -s --connect-timeout 5 https://hub.docker.com &> /dev/null; then
        check_pass "Docker Hub доступен"
    else
        check_warn "Docker Hub недоступен"
    fi
    
    # Проверка доступности GitHub
    if curl -s --connect-timeout 5 https://github.com &> /dev/null; then
        check_pass "GitHub доступен"
    else
        check_warn "GitHub недоступен"
    fi
    
    # Проверка доступности AppsFlyer API
    if curl -s --connect-timeout 5 https://api3.appsflyer.com &> /dev/null; then
        check_pass "AppsFlyer API доступен"
    else
        check_warn "AppsFlyer API недоступен"
    fi
else
    check_fail "Нет интернет соединения"
fi
echo ""

# 11. Проверка SSH ключей для GitHub
echo "11. SSH конфигурация (GitHub)"
if [ -d ~/.ssh ]; then
    check_pass "Директория ~/.ssh существует"
    
    # Проверка наличия ключей
    if ls ~/.ssh/id_* &> /dev/null || ls ~/.ssh/github* &> /dev/null; then
        check_pass "SSH ключи найдены"
        
        # Проверка прав доступа
        if [ "$(stat -c %a ~/.ssh)" == "700" ]; then
            check_pass "Права на ~/.ssh корректны (700)"
        else
            check_warn "Права на ~/.ssh некорректны (должно быть 700)"
        fi
    else
        check_warn "SSH ключи не найдены (потребуется создать для GitHub)"
    fi
    
    # Проверка подключения к GitHub
    if ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
        check_pass "SSH подключение к GitHub работает"
    else
        check_info "SSH подключение к GitHub не настроено"
    fi
else
    check_fail "Директория ~/.ssh не существует"
fi
echo ""

# 12. Проверка проекта (если находимся в директории проекта)
echo "12. Файлы проекта"
if [ -f "docker-compose.yml" ]; then
    check_pass "docker-compose.yml найден"
    
    if [ -f ".env.example" ]; then
        check_pass ".env.example найден"
        
        if [ -f ".env" ]; then
            check_pass ".env найден"
            
            # Проверка обязательных переменных
            check_env_var() {
                local var=$1
                if grep -q "^${var}=" .env && ! grep -q "^${var}=$" .env && ! grep -q "^${var}=\s*$" .env; then
                    check_pass "$var установлен в .env"
                else
                    check_fail "$var не установлен в .env"
                fi
            }
            
            check_env_var "API_TOKENS"
            check_env_var "APPSFLYER_DEV_KEY"
            check_env_var "APPSFLYER_DEFAULT_APP_ID"
        else
            check_warn ".env не найден (создайте из .env.example)"
        fi
    fi
    
    if [ -f "requirements.txt" ]; then
        check_pass "requirements.txt найден"
    fi
    
    if [ -d "app" ]; then
        check_pass "Директория app/ найдена"
    fi
    
    if [ -d "docker" ]; then
        check_pass "Директория docker/ найдена"
    fi
else
    check_info "Не в директории проекта (docker-compose.yml не найден)"
fi
echo ""

# Итоговый отчет
echo "=========================================="
echo "ИТОГОВЫЙ ОТЧЕТ"
echo "=========================================="

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ Система готова к деплою!${NC}"
    echo ""
    echo "Следующие шаги:"
    echo "1. Убедитесь что .env файл настроен с реальными credentials"
    echo "2. Запустите: docker compose up -d"
    echo "3. Проверьте: docker compose ps && curl http://localhost:8000/health/ready"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ Найдено предупреждений: $WARNINGS${NC}"
    echo ""
    echo "Можно продолжать деплой, но рекомендуется устранить предупреждения."
    exit 0
else
    echo -e "${RED}✗ Найдено критических ошибок: $ERRORS${NC}"
    echo -e "${YELLOW}⚠ Найдено предупреждений: $WARNINGS${NC}"
    echo ""
    echo "Устраните критические ошибки перед деплоем!"
    exit 1
fi
