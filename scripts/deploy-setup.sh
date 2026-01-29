#!/bin/bash
#
# AppsFlyer Event Sender Service - Server Setup Script
# Автоматизация начальной настройки сервера DigitalOcean
#
# Использование:
#   1. Скопировать скрипт на сервер: scp deploy-setup.sh root@IP:/tmp/
#   2. Запустить: ssh root@IP "bash /tmp/deploy-setup.sh"
#

set -e

echo "=========================================="
echo "AppsFlyer Event Sender - Server Setup"
echo "=========================================="

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка что скрипт запущен от root
if [ "$EUID" -ne 0 ]; then 
    log_error "Запустите скрипт от root: sudo bash $0"
    exit 1
fi

# 1. Обновление системы
log_info "Обновление системы..."
apt-get update -qq
apt-get upgrade -y -qq

# 2. Установка базовых утилит
log_info "Установка базовых утилит..."
apt-get install -y -qq \
    curl \
    wget \
    git \
    vim \
    htop \
    ufw \
    ca-certificates \
    gnupg \
    lsb-release \
    software-properties-common

# 3. Установка Docker
log_info "Установка Docker..."
if ! command -v docker &> /dev/null; then
    # Добавить GPG ключ
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    
    # Добавить репозиторий
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Установить Docker
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Включить автозапуск
    systemctl enable docker
    systemctl start docker
    
    log_info "Docker $(docker --version) установлен"
else
    log_info "Docker уже установлен: $(docker --version)"
fi

# 4. Создание пользователя deploy
log_info "Создание пользователя 'deploy'..."
if ! id -u deploy &> /dev/null; then
    adduser --disabled-password --gecos "" deploy
    usermod -aG sudo deploy
    usermod -aG docker deploy
    
    # Копировать SSH ключи
    if [ -d /root/.ssh ]; then
        mkdir -p /home/deploy/.ssh
        cp /root/.ssh/authorized_keys /home/deploy/.ssh/ 2>/dev/null || true
        chown -R deploy:deploy /home/deploy/.ssh
        chmod 700 /home/deploy/.ssh
        chmod 600 /home/deploy/.ssh/authorized_keys 2>/dev/null || true
    fi
    
    log_info "Пользователь 'deploy' создан"
else
    log_info "Пользователь 'deploy' уже существует"
fi

# 5. Настройка UFW Firewall
log_info "Настройка UFW Firewall..."
if command -v ufw &> /dev/null; then
    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp comment 'SSH'
    ufw allow 80/tcp comment 'HTTP'
    ufw allow 443/tcp comment 'HTTPS'
    ufw --force enable
    log_info "Firewall настроен"
fi

# 6. Установка Nginx
log_info "Установка Nginx..."
if ! command -v nginx &> /dev/null; then
    apt-get install -y -qq nginx
    systemctl enable nginx
    systemctl start nginx
    log_info "Nginx установлен"
else
    log_info "Nginx уже установлен"
fi

# 7. Установка Certbot
log_info "Установка Certbot..."
if ! command -v certbot &> /dev/null; then
    apt-get install -y -qq certbot python3-certbot-nginx
    log_info "Certbot установлен"
else
    log_info "Certbot уже установлен"
fi

# 8. Создание директории для приложения
log_info "Создание директории приложения..."
mkdir -p /opt/apps
chown deploy:deploy /opt/apps

mkdir -p /opt/backups
chown deploy:deploy /opt/backups

# 9. Настройка автоматических обновлений безопасности (опционально)
log_info "Настройка unattended-upgrades..."
apt-get install -y -qq unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades

# 10. Настройка swap (если отсутствует)
if [ ! -f /swapfile ]; then
    log_info "Создание swap файла (2GB)..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    log_info "Swap создан"
fi

# 11. Оптимизация sysctl для production
log_info "Оптимизация параметров ядра..."
cat > /etc/sysctl.d/99-appsflyer.conf << EOF
# Network tuning
net.core.somaxconn = 1024
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.ip_local_port_range = 1024 65535

# Redis recommendations
vm.overcommit_memory = 1

# File descriptors
fs.file-max = 65536
EOF

sysctl -p /etc/sysctl.d/99-appsflyer.conf > /dev/null

# 12. Настройка логротации для Docker
log_info "Настройка Docker logging..."
cat > /etc/docker/daemon.json << EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF

systemctl restart docker

# 13. Создание SSH ключа для GitHub
log_info "Создание SSH ключа для GitHub (пользователь deploy)..."
sudo -u deploy bash << 'DEPLOY_SCRIPT'
if [ ! -f ~/.ssh/github_deploy_key ]; then
    ssh-keygen -t ed25519 -C "deploy@appsflyer-service" -f ~/.ssh/github_deploy_key -N ""
    
    # Создать SSH config
    cat > ~/.ssh/config << EOF
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_deploy_key
    IdentitiesOnly yes
    StrictHostKeyChecking no
EOF
    
    chmod 600 ~/.ssh/config
    chmod 600 ~/.ssh/github_deploy_key
    
    echo ""
    echo "=========================================="
    echo "ДОБАВЬТЕ ЭТОТ ПУБЛИЧНЫЙ КЛЮЧ В GITHUB:"
    echo "=========================================="
    cat ~/.ssh/github_deploy_key.pub
    echo "=========================================="
    echo ""
fi
DEPLOY_SCRIPT

# 14. Создание базового скрипта бэкапа
log_info "Создание скрипта резервного копирования..."
cat > /opt/backups/backup-redis.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/backups/redis"
RETENTION_DAYS=7
DATE=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"
cd /opt/apps/AppsFlyer-Event-Sender-Service || exit 1

# Trigger RDB save
docker compose exec -T redis redis-cli BGSAVE

# Wait for completion
sleep 5

# Copy dump
REDIS_CONTAINER=$(docker compose ps -q redis)
if [ -n "$REDIS_CONTAINER" ]; then
    docker cp "$REDIS_CONTAINER:/data/dump.rdb" "$BACKUP_DIR/dump-$DATE.rdb"
    echo "$(date): Backup created - dump-$DATE.rdb" >> /var/log/redis-backup.log
    
    # Cleanup old backups
    find "$BACKUP_DIR" -name "dump-*.rdb" -mtime +$RETENTION_DAYS -delete
else
    echo "$(date): ERROR - Redis container not found" >> /var/log/redis-backup.log
    exit 1
fi
EOF

chmod +x /opt/backups/backup-redis.sh
chown deploy:deploy /opt/backups/backup-redis.sh

# 15. Финальная информация
echo ""
echo "=========================================="
echo -e "${GREEN}УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО!${NC}"
echo "=========================================="
echo ""
echo "Следующие шаги:"
echo ""
echo "1. Добавьте SSH ключ в GitHub Deploy Keys:"
echo "   - Репозиторий → Settings → Deploy keys → Add deploy key"
echo "   - Ключ был показан выше, или: sudo -u deploy cat /home/deploy/.ssh/github_deploy_key.pub"
echo ""
echo "2. Переключитесь на пользователя deploy:"
echo "   su - deploy"
echo ""
echo "3. Клонируйте репозиторий:"
echo "   cd /opt/apps"
echo "   git clone git@github.com:YOUR_USERNAME/AppsFlyer-Event-Sender-Service.git"
echo ""
echo "4. Настройте .env файл:"
echo "   cd AppsFlyer-Event-Sender-Service"
echo "   cp .env.example .env"
echo "   nano .env  # Заполните реальные значения"
echo ""
echo "5. Запустите приложение:"
echo "   docker compose up -d"
echo ""
echo "6. Проверьте работоспособность:"
echo "   docker compose ps"
echo "   curl http://localhost:8000/health/ready"
echo ""
echo "7. Настройте Nginx с SSL (если есть домен):"
echo "   - Создайте конфигурацию в /etc/nginx/sites-available/"
echo "   - Получите SSL сертификат: sudo certbot --nginx -d your-domain.com"
echo ""
echo "=========================================="
echo "Полная документация: docs/deployment_digitalocean.md"
echo "=========================================="
