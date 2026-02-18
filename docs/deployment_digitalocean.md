# Инструкция по деплою на DigitalOcean

Пошаговое руководство по развёртыванию AppsFlyer Event Sender Service на сервере DigitalOcean из приватного GitHub-репозитория.

---

## Содержание

1. [Предварительные требования](#1-предварительные-требования)
2. [Создание и настройка сервера](#2-создание-и-настройка-сервера)
3. [Настройка SSH доступа](#3-настройка-ssh-доступа)
4. [Установка необходимого ПО](#4-установка-необходимого-по)
5. [Настройка доступа к приватному GitHub репозиторию](#5-настройка-доступа-к-приватному-github-репозиторию)
6. [Клонирование и настройка проекта](#6-клонирование-и-настройка-проекта)
7. [Настройка firewall](#7-настройка-firewall)
8. [Запуск приложения](#8-запуск-приложения)
9. [Настройка Nginx с SSL (Let's Encrypt)](#9-настройка-nginx-с-ssl-lets-encrypt)
10. [Мониторинг и логирование](#10-мониторинг-и-логирование)
11. [Обновление приложения](#11-обновление-приложения)
12. [Резервное копирование](#12-резервное-копирование)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Предварительные требования

### 1.1. Локальная подготовка

- Аккаунт на [DigitalOcean](https://www.digitalocean.com/)
- SSH-ключ для доступа к серверу
- Доступ к приватному GitHub репозиторию с правами чтения
- Доменное имя (опционально, для SSL)

### 1.2. Учётные данные

Подготовьте следующие данные:
- **AppsFlyer Dev Key** — ключ разработчика из [AppsFlyer Dashboard](https://hq1.appsflyer.com/)
- **AppsFlyer App ID** — ID приложения (для iOS: `id123456789`, для Android: `com.example.app`)
- **API Tokens** — секретные токены для авторизации запросов (генерируйте криптостойкие: `openssl rand -hex 32`)
- **GitHub Personal Access Token** (для приватного репозитория)

---

## 2. Создание и настройка сервера

### 2.1. Создание Droplet

1. Войдите в панель управления DigitalOcean
2. **Create → Droplets**
3. Выберите параметры:

**Образ:**
```
Ubuntu 22.04 (LTS) x64
```

**Размер Droplet (рекомендации):**

| Нагрузка | План | vCPUs | RAM | SSD | Цена (примерно) |
|----------|------|-------|-----|-----|-----------------|
| Малая (тестирование) | Basic | 1 | 1 GB | 25 GB | $6/месяц |
| Средняя (production) | Basic | 2 | 2 GB | 50 GB | $12/месяц |
| Высокая | General Purpose | 2 | 4 GB | 80 GB | $24/месяц |

**Рекомендация для production**: минимум **2 GB RAM** (для Redis + API + Worker).

**Регион:**
- Выберите ближайший к вашей аудитории (например, Frankfurt для Европы, New York для США)

**Authentication:**
- Выберите **SSH keys** и добавьте свой публичный ключ

**Hostname:**
```
appsflyer-event-service
```

4. Нажмите **Create Droplet**

### 2.2. Получение IP адреса

После создания запишите IP адрес сервера:
```
IP: 123.456.789.012
```

---

## 3. Настройка SSH доступа

### 3.1. Первое подключение

```bash
ssh root@123.456.789.012
```

### 3.2. Создание пользователя (рекомендуется)

Работа от `root` небезопасна. Создайте отдельного пользователя:

```bash
# Создать пользователя
adduser deploy

# Добавить в группу sudo
usermod -aG sudo deploy

# Настроить SSH доступ
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

### 3.3. Отключение root-доступа (опционально, после проверки)

```bash
# Редактировать конфигурацию SSH
nano /etc/ssh/sshd_config

# Изменить строку:
PermitRootLogin no

# Перезапустить SSH
systemctl restart sshd
```

Теперь подключайтесь как:
```bash
ssh deploy@123.456.789.012
```

---

## 4. Установка необходимого ПО

Выполните команды от имени пользователя `deploy` (или `root` если не создавали пользователя).

### 4.1. Обновление системы

```bash
sudo apt update && sudo apt upgrade -y
```

### 4.2. Установка базовых утилит

```bash
sudo apt install -y \
    curl \
    wget \
    git \
    vim \
    htop \
    ufw \
    ca-certificates \
    gnupg \
    lsb-release
```

### 4.3. Установка Docker

```bash
# Добавить официальный GPG ключ Docker
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Добавить репозиторий Docker
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установить Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Добавить текущего пользователя в группу docker (чтобы не использовать sudo)
sudo usermod -aG docker $USER

# Применить изменения группы (или перелогиньтесь)
newgrp docker

# Проверить установку
docker --version
docker compose version
```

Ожидаемый вывод:
```
Docker version 24.0.x
Docker Compose version 2.x.x
```

### 4.4. Настройка автозапуска Docker

```bash
sudo systemctl enable docker
sudo systemctl start docker
```

---

## 5. Настройка доступа к приватному GitHub репозиторию

### 5.1. Создание SSH ключа для сервера

```bash
# Генерация SSH ключа (без пароля для автоматизации)
ssh-keygen -t ed25519 -C "deploy@appsflyer-service" -f ~/.ssh/github_deploy_key -N ""

# Посмотреть публичный ключ
cat ~/.ssh/github_deploy_key.pub
```

Скопируйте содержимое публичного ключа.

### 5.2. Добавление Deploy Key в GitHub

**Вариант A: Deploy Key (рекомендуется для одного репозитория)**

1. Перейдите в ваш GitHub репозиторий
2. **Settings → Deploy keys → Add deploy key**
3. **Title**: `DigitalOcean Production Server`
4. **Key**: вставьте содержимое `github_deploy_key.pub`
5. **Allow write access**: ❌ (не требуется, только чтение)
6. Нажмите **Add key**

**Вариант B: Personal Access Token (если нужен доступ к нескольким репозиториям)**

1. GitHub → **Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. **Generate new token (classic)**
3. **Note**: `DigitalOcean Deploy`
4. **Expiration**: 90 days (или No expiration для автоматизации, но небезопасно)
5. **Scopes**: выберите `repo` (Full control of private repositories)
6. Скопируйте сгенерированный token (покажется только один раз!)

### 5.3. Настройка SSH конфигурации

```bash
# Создать/отредактировать SSH config
nano ~/.ssh/config
```

Добавьте:
```
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_deploy_key
    IdentitiesOnly yes
    StrictHostKeyChecking no
```

Установите права:
```bash
chmod 600 ~/.ssh/config
chmod 600 ~/.ssh/github_deploy_key
```

### 5.4. Проверка доступа

```bash
ssh -T git@github.com
```

Ожидаемый вывод:
```
Hi <username>! You've successfully authenticated, but GitHub does not provide shell access.
```

---

## 6. Клонирование и настройка проекта

### 6.1. Создание директории проекта

```bash
# Создать директорию для приложений
sudo mkdir -p /opt/apps
sudo chown $USER:$USER /opt/apps

# Перейти в директорию
cd /opt/apps
```

### 6.2. Клонирование репозитория

**Вариант A: Используя SSH (если настроен Deploy Key)**

```bash
git clone git@github.com:YOUR_USERNAME/AppsFlyer-Event-Sender-Service.git
cd AppsFlyer-Event-Sender-Service
```

**Вариант B: Используя Personal Access Token**

```bash
git clone https://YOUR_TOKEN@github.com/YOUR_USERNAME/AppsFlyer-Event-Sender-Service.git
cd AppsFlyer-Event-Sender-Service
```

Замените:
- `YOUR_USERNAME` — ваш GitHub username
- `YOUR_TOKEN` — Personal Access Token (если используете)

### 6.3. Создание .env файла

```bash
# Создать .env из примера
cp .env.example .env

# Редактировать конфигурацию
nano .env
```

**Минимальная production конфигурация:**

```bash
# Application
APP_ENV=prod
DEBUG=false

# Authentication (ОБЯЗАТЕЛЬНО ИЗМЕНИТЬ!)
AUTH_MODE=token
# Генерация токенов: openssl rand -hex 32
API_TOKENS=your-super-secret-token-here,another-token-for-keitaro

# HMAC mode (опционально)
HMAC_KEYS_JSON={}
AUTH_TS_SKEW_SECONDS=300

# Redis (используем внутренний контейнер)
REDIS_URL=redis://redis:6379/0
STREAM_MAIN=events:main
STREAM_DLQ=events:dlq

# Worker
WORKER_CONSUMER_GROUP=af_sender
WORKER_CONCURRENCY=10
MAX_ATTEMPTS=8
BACKOFF_BASE_SECONDS=1
BACKOFF_MAX_SECONDS=60
PENDING_CLAIM_MS=60000

# AppsFlyer (ОБЯЗАТЕЛЬНО ЗАПОЛНИТЬ!)
APPSFLYER_BASE_URL=https://api3.appsflyer.com
APPSFLYER_TIMEOUT_SECONDS=5
APPSFLYER_DEV_KEY=YOUR_APPSFLYER_DEV_KEY_HERE
APPSFLYER_DEFAULT_APP_ID=id123456789

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_RPS=100
RATE_LIMIT_BURST=200

# Deduplication
DEDUP_TTL_SECONDS=604800

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

**Генерация криптостойких токенов:**
```bash
# Генерация токена (выполните локально или на сервере)
openssl rand -hex 32
```

**Важно:** Никогда не коммитьте `.env` в Git!

### 6.4. Проверка конфигурации

```bash
# Убедитесь что .env содержит реальные значения
cat .env | grep -E "(APPSFLYER_DEV_KEY|API_TOKENS|APPSFLYER_DEFAULT_APP_ID)"
```

Все переменные должны быть заполнены (не пустые).

---

## 7. Настройка firewall

### 7.1. Настройка UFW (Uncomplicated Firewall)

```bash
# Разрешить SSH (ВАЖНО: сделать до включения firewall!)
sudo ufw allow 22/tcp

# Разрешить HTTP и HTTPS (для Nginx)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Опционально: Prometheus metrics (только если нужен внешний доступ)
# sudo ufw allow 8000/tcp

# Включить firewall
sudo ufw enable

# Проверить статус
sudo ufw status verbose
```

Ожидаемый вывод:
```
Status: active

To                         Action      From
--                         ------      ----
22/tcp                     ALLOW       Anywhere
80/tcp                     ALLOW       Anywhere
443/tcp                    ALLOW       Anywhere
```

### 7.2. Настройка DigitalOcean Cloud Firewall (опционально)

В панели DigitalOcean:
1. **Networking → Firewalls → Create Firewall**
2. **Inbound Rules:**
   - SSH: TCP port 22, All IPv4/IPv6
   - HTTP: TCP port 80, All IPv4/IPv6
   - HTTPS: TCP port 443, All IPv4/IPv6
3. **Outbound Rules:**
   - All TCP, All IPv4/IPv6
   - All UDP, All IPv4/IPv6
4. **Apply to Droplets**: выберите ваш Droplet

---

## 8. Запуск приложения

### 8.1. Сборка и запуск контейнеров

```bash
# Перейти в директорию проекта
cd /opt/apps/AppsFlyer-Event-Sender-Service

# Собрать образы
docker compose build

# Запустить сервисы
docker compose up -d
```

### 8.2. Проверка статуса контейнеров

```bash
# Посмотреть запущенные контейнеры
docker compose ps

# Посмотреть логи
docker compose logs -f

# Логи отдельного сервиса
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f redis
```

Ожидаемый вывод `docker compose ps`:
```
NAME                              IMAGE                    STATUS              PORTS
appsflyer-event-sender-service-api-1      ...             Up (healthy)        0.0.0.0:8000->8000/tcp
appsflyer-event-sender-service-worker-1   ...             Up
appsflyer-event-sender-service-redis-1    redis:7-alpine  Up (healthy)        0.0.0.0:6379->6379/tcp
```

### 8.3. Проверка работоспособности

```bash
# Liveness probe
curl http://localhost:8000/health/live

# Readiness probe (проверяет Redis)
curl http://localhost:8000/health/ready

# Prometheus metrics
curl http://localhost:8000/metrics
```

Ожидаемый ответ:
```json
{"status": "healthy"}
```

### 8.4. Тестовый запрос

```bash
# Замените YOUR_TOKEN на токен из .env
curl -X POST "http://localhost:8000/v1/track/registration?\
token=YOUR_TOKEN&\
appsflyer_id=1658954220-test123&\
platform=ios"
```

Ожидаемый ответ:
```json
{
  "status": "accepted",
  "event_id": "...",
  "queued_at": "2026-01-29T12:34:56.789Z",
  "message": "Event queued for processing"
}
```

### 8.5. Настройка автозапуска

Docker Compose с `restart: always` автоматически перезапустит контейнеры при сбоях и перезагрузке сервера.

Дополнительная настройка (опционально):
```bash
# Создать systemd unit для Docker Compose
sudo nano /etc/systemd/system/appsflyer-service.service
```

Содержимое:
```ini
[Unit]
Description=AppsFlyer Event Sender Service
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/apps/AppsFlyer-Event-Sender-Service
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Активация:
```bash
sudo systemctl daemon-reload
sudo systemctl enable appsflyer-service
```

---

## 9. Настройка Nginx с SSL (Let's Encrypt)

### 9.1. Установка Nginx

```bash
sudo apt install -y nginx
```

### 9.2. Установка Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 9.3. Настройка доменного имени

**Предварительно:** убедитесь что ваш домен указывает на IP сервера:

```bash
# A-запись в DNS
your-domain.com → 123.456.789.012
```

Проверка:
```bash
dig +short your-domain.com
```

### 9.4. Создание конфигурации Nginx

```bash
sudo nano /etc/nginx/sites-available/appsflyer-service
```

**Минимальная конфигурация:**

```nginx
# Upstream для API
upstream appsflyer_api {
    server localhost:8000 max_fails=3 fail_timeout=30s;
}

# HTTP → HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name your-domain.com;

    # Let's Encrypt validation
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    # Redirect all HTTP to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name your-domain.com;

    # SSL certificates (будут созданы Certbot)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    # SSL настройки
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Logging
    access_log /var/log/nginx/appsflyer-access.log;
    error_log /var/log/nginx/appsflyer-error.log;

    # Client body size (для больших запросов, если потребуется)
    client_max_body_size 10M;

    # Timeouts
    proxy_connect_timeout 30s;
    proxy_send_timeout 30s;
    proxy_read_timeout 30s;

    # Health checks (публичные)
    location /health {
        proxy_pass http://appsflyer_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        access_log off;
    }

    # API endpoints
    location /v1 {
        # Важно: сохраняем /v1 префикс (не используйте trailing slash)
        proxy_pass http://appsflyer_api$request_uri;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Rate limiting (дополнительный слой, помимо приложения)
        limit_req zone=api_limit burst=20 nodelay;
    }

    # Metrics (защитить или закрыть в production!)
    location /metrics {
        # Опционально: ограничить по IP
        # allow 10.0.0.0/8;  # внутренняя сеть
        # deny all;
        
        proxy_pass http://appsflyer_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    # Запретить все остальное
    location / {
        return 404;
    }
}

# Rate limiting zone (опционально)
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=50r/s;
```

**Важно:** Замените `your-domain.com` на ваш реальный домен.

### 9.5. Активация конфигурации

```bash
# Создать симлинк
sudo ln -s /etc/nginx/sites-available/appsflyer-service /etc/nginx/sites-enabled/

# Удалить дефолтную конфигурацию
sudo rm /etc/nginx/sites-enabled/default

# Проверить конфигурацию
sudo nginx -t
```

### 9.6. Получение SSL сертификата

**Первый запуск (без SSL):**
```bash
# Временно изменить конфигурацию для HTTP-only
sudo nano /etc/nginx/sites-available/appsflyer-service
# Закомментируйте блок server с listen 443

# Перезапустить Nginx
sudo systemctl restart nginx

# Получить сертификат
sudo certbot --nginx -d your-domain.com

# Certbot автоматически настроит SSL и обновит конфигурацию
```

**Автопродление сертификата:**
```bash
# Certbot автоматически создаст cron job, проверьте:
sudo systemctl status certbot.timer

# Тест продления (dry run)
sudo certbot renew --dry-run
```

### 9.7. Перезапуск Nginx с полной конфигурацией

```bash
# Вернуть полную конфигурацию (с HTTPS блоком)
sudo nano /etc/nginx/sites-available/appsflyer-service
# Раскомментируйте блок server с listen 443

# Проверить и перезапустить
sudo nginx -t
sudo systemctl restart nginx

# Включить автозапуск
sudo systemctl enable nginx
```

### 9.8. Проверка HTTPS

```bash
# Проверить через curl
curl -I https://your-domain.com/health/live

# Проверить SSL
openssl s_client -connect your-domain.com:443 -servername your-domain.com
```

---

## 10. Мониторинг и логирование

### 10.1. Просмотр логов

**Логи приложения (Docker):**
```bash
# Все сервисы
docker compose logs -f --tail=100

# API
docker compose logs -f api --tail=100

# Worker
docker compose logs -f worker --tail=100

# Redis
docker compose logs -f redis --tail=100
```

**Логи Nginx:**
```bash
# Access log
sudo tail -f /var/log/nginx/appsflyer-access.log

# Error log
sudo tail -f /var/log/nginx/appsflyer-error.log
```

**Системные логи:**
```bash
# Docker daemon
sudo journalctl -u docker -f

# systemd service (если настроен)
sudo journalctl -u appsflyer-service -f
```

### 10.2. Мониторинг ресурсов

**Использование ресурсов Docker:**
```bash
# Статистика контейнеров в реальном времени
docker stats
```

**Системные ресурсы:**
```bash
# CPU, память, процессы
htop

# Использование диска
df -h

# Использование дискового I/O
iostat -x 1
```

### 10.3. Prometheus Metrics

**Доступ к метрикам:**
```bash
curl https://your-domain.com/metrics
```

**Интеграция с внешним Prometheus (опционально):**

1. Установите Prometheus на отдельном сервере или используйте облачный сервис (Grafana Cloud, Datadog)
2. Добавьте scrape config:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'appsflyer-event-service'
    scrape_interval: 15s
    static_configs:
      - targets: ['your-domain.com:443']
    scheme: https
    metrics_path: '/metrics'
```

### 10.4. Алерты (опционально)

**Мониторинг доступности (Uptime Robot, Better Uptime):**

1. Зарегистрируйтесь в сервисе мониторинга
2. Добавьте HTTP(S) monitor:
   - URL: `https://your-domain.com/health/ready`
   - Interval: 5 минут
   - Алерты: Email/Telegram/Slack

**Базовый healthcheck script (запускать через cron):**

```bash
# Создать скрипт
cat > /opt/apps/healthcheck.sh << 'EOF'
#!/bin/bash
HEALTH_URL="http://localhost:8000/health/ready"
ALERT_EMAIL="admin@example.com"

if ! curl -sf "$HEALTH_URL" > /dev/null; then
    echo "AppsFlyer Service DOWN at $(date)" | \
        mail -s "ALERT: AppsFlyer Service DOWN" "$ALERT_EMAIL"
fi
EOF

chmod +x /opt/apps/healthcheck.sh

# Добавить в cron (проверка каждые 5 минут)
crontab -e
# Добавить строку:
# */5 * * * * /opt/apps/healthcheck.sh
```

---

## 11. Обновление приложения

### 11.1. Процесс обновления

```bash
# 1. Перейти в директорию проекта
cd /opt/apps/AppsFlyer-Event-Sender-Service

# 2. Сделать бэкап (опционально)
docker compose exec redis redis-cli SAVE
cp -r /opt/apps/AppsFlyer-Event-Sender-Service /opt/apps/AppsFlyer-Event-Sender-Service.backup.$(date +%Y%m%d)

# 3. Остановить сервисы
docker compose down

# 4. Получить изменения из GitHub
git fetch origin
git pull origin main  # или ваша ветка (development, production)

# 5. Проверить изменения в .env.example
diff .env.example .env
# Если есть новые переменные - добавьте их в .env

# 6. Пересобрать образы (если изменился код)
docker compose build

# 7. Запустить сервисы
docker compose up -d

# 8. Проверить статус
docker compose ps
docker compose logs -f --tail=50

# 9. Проверить работоспособность
curl https://your-domain.com/health/ready
```

### 11.2. Откат при проблемах

```bash
# Остановить текущую версию
docker compose down

# Восстановить из бэкапа
cd /opt/apps
rm -rf AppsFlyer-Event-Sender-Service
mv AppsFlyer-Event-Sender-Service.backup.YYYYMMDD AppsFlyer-Event-Sender-Service

# Запустить
cd AppsFlyer-Event-Sender-Service
docker compose up -d
```

### 11.3. Zero-downtime deployment (опционально)

Для продвинутого деплоя без простоя используйте:
- Blue-Green deployment (2 окружения, переключение через Nginx)
- Docker Swarm или Kubernetes
- Managed Kubernetes (DigitalOcean DOKS)

---

## 12. Резервное копирование

### 12.1. Что нужно бэкапить

1. **Redis данные** (очередь, dedup keys, rate limit state)
2. **Конфигурация** (.env, docker-compose.yml)
3. **Nginx конфигурация**
4. **SSL сертификаты** (автоматически обновляются Certbot)

### 12.2. Бэкап Redis

**Ручной бэкап:**
```bash
# Trigger RDB snapshot
docker compose exec redis redis-cli BGSAVE

# Дождаться завершения
docker compose exec redis redis-cli LASTSAVE

# Скопировать dump.rdb
docker cp $(docker compose ps -q redis):/data/dump.rdb ./redis-backup-$(date +%Y%m%d-%H%M%S).rdb
```

**Автоматический бэкап (cron):**
```bash
# Создать скрипт
sudo mkdir -p /opt/backups
sudo chown $USER:$USER /opt/backups

cat > /opt/backups/backup-redis.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/backups/redis"
RETENTION_DAYS=7
DATE=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"
cd /opt/apps/AppsFlyer-Event-Sender-Service

# Trigger RDB save
docker compose exec redis redis-cli BGSAVE

# Wait for completion (max 60 seconds)
for i in {1..60}; do
    if docker compose exec redis redis-cli LASTSAVE > /tmp/lastsave.txt; then
        break
    fi
    sleep 1
done

# Copy dump
docker cp $(docker compose ps -q redis):/data/dump.rdb "$BACKUP_DIR/dump-$DATE.rdb"

# Cleanup old backups
find "$BACKUP_DIR" -name "dump-*.rdb" -mtime +$RETENTION_DAYS -delete

echo "Redis backup completed: $BACKUP_DIR/dump-$DATE.rdb"
EOF

chmod +x /opt/backups/backup-redis.sh

# Добавить в cron (ежедневно в 2:00 AM)
crontab -e
# Добавить:
# 0 2 * * * /opt/backups/backup-redis.sh >> /var/log/redis-backup.log 2>&1
```

### 12.3. Восстановление Redis

```bash
# 1. Остановить Redis
docker compose stop redis

# 2. Восстановить dump.rdb
docker cp ./redis-backup-YYYYMMDD-HHMMSS.rdb $(docker compose ps -aq redis):/data/dump.rdb

# 3. Запустить Redis
docker compose start redis

# 4. Проверить
docker compose exec redis redis-cli PING
```

### 12.4. Удалённый бэкап (DigitalOcean Spaces или S3)

**Установка s3cmd:**
```bash
sudo apt install -y s3cmd

# Настроить s3cmd для DigitalOcean Spaces
s3cmd --configure
# Введите Access Key и Secret Key из DigitalOcean Spaces
```

**Скрипт бэкапа в S3:**
```bash
cat > /opt/backups/backup-to-s3.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/backups"
S3_BUCKET="s3://your-bucket-name/appsflyer-service/"

# Backup Redis
/opt/backups/backup-redis.sh

# Backup configs
tar -czf "$BACKUP_DIR/configs-$(date +%Y%m%d).tar.gz" \
    /opt/apps/AppsFlyer-Event-Sender-Service/.env \
    /opt/apps/AppsFlyer-Event-Sender-Service/docker-compose.yml \
    /etc/nginx/sites-available/appsflyer-service

# Upload to S3
s3cmd sync "$BACKUP_DIR/" "$S3_BUCKET"

# Cleanup local backups older than 7 days
find "$BACKUP_DIR" -mtime +7 -delete
EOF

chmod +x /opt/backups/backup-to-s3.sh
```

---

## 13. Troubleshooting

### 13.1. Проблемы с контейнерами

**Контейнер не запускается:**
```bash
# Посмотреть логи
docker compose logs <service_name>

# Посмотреть статус
docker compose ps

# Перезапустить сервис
docker compose restart <service_name>

# Полная пересборка
docker compose down
docker compose build --no-cache
docker compose up -d
```

**Проблемы с Redis:**
```bash
# Проверить подключение
docker compose exec redis redis-cli PING

# Посмотреть memory usage
docker compose exec redis redis-cli INFO memory

# Очистить Redis (ОСТОРОЖНО - потеряются данные!)
docker compose exec redis redis-cli FLUSHALL
```

### 13.2. Проблемы с производительностью

**API медленно отвечает:**
```bash
# Проверить нагрузку на Redis
docker compose exec redis redis-cli --latency

# Увеличить workers в docker-compose.yml
# (для api сервиса в CMD изменить --workers)

# Проверить resource limits
docker stats
```

**Worker не обрабатывает события:**
```bash
# Посмотреть логи worker
docker compose logs -f worker

# Проверить pending messages в Redis
docker compose exec redis redis-cli XPENDING events:main af_sender

# Проверить DLQ
docker compose exec redis redis-cli XLEN events:dlq
```

### 13.3. Проблемы с AppsFlyer API

**События не доходят до AppsFlyer:**
```bash
# 1. Проверить логи worker
docker compose logs worker | grep -i appsflyer

# 2. Проверить DLQ
docker compose exec redis redis-cli XLEN events:dlq
docker compose exec redis redis-cli XRANGE events:dlq - + COUNT 10

# 3. Проверить credentials в .env
cat .env | grep APPSFLYER

# 4. Тест подключения к AppsFlyer вручную
curl -X POST "https://api3.appsflyer.com/inappevent/YOUR_APP_ID" \
  -H "authentication: YOUR_DEV_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "appsflyer_id": "test-123",
    "eventName": "af_test"
  }'
```

**Rate limit от AppsFlyer (429):**
```bash
# Увеличить backoff в .env
BACKOFF_MAX_SECONDS=120

# Уменьшить concurrency
WORKER_CONCURRENCY=5

# Перезапустить
docker compose restart worker
```

### 13.4. Проблемы с Nginx

**502 Bad Gateway:**
```bash
# Проверить что API запущен
curl http://localhost:8000/health/live

# Проверить Nginx config
sudo nginx -t

# Посмотреть логи Nginx
sudo tail -f /var/log/nginx/appsflyer-error.log

# Перезапустить Nginx
sudo systemctl restart nginx
```

**SSL сертификат не обновляется:**
```bash
# Проверить статус Certbot
sudo systemctl status certbot.timer

# Вручную продлить
sudo certbot renew --force-renewal

# Перезапустить Nginx
sudo systemctl restart nginx
```

### 13.5. Проблемы с диском

**Диск заполнен:**
```bash
# Проверить использование
df -h

# Найти большие файлы
sudo du -h / | sort -hr | head -20

# Очистить Docker
docker system prune -a --volumes

# Очистить старые логи
sudo journalctl --vacuum-time=7d

# Очистить APT cache
sudo apt clean
```

### 13.6. Проблемы с памятью

**Out of Memory (OOM):**
```bash
# Проверить использование памяти
free -h
docker stats

# Ограничить memory для Redis в docker-compose.yml
services:
  redis:
    deploy:
      resources:
        limits:
          memory: 512M

# Перезапустить
docker compose up -d
```

### 13.7. Получение поддержки

**Сбор диагностической информации:**
```bash
# Создать diagnostic bundle
cat > /tmp/diagnostic-report.txt << EOF
=== System Info ===
$(uname -a)
$(free -h)
$(df -h)

=== Docker Info ===
$(docker --version)
$(docker compose version)
$(docker compose ps)

=== Service Logs ===
$(docker compose logs --tail=100)

=== Health Checks ===
$(curl -s http://localhost:8000/health/ready)
$(curl -s http://localhost:8000/metrics | head -50)

=== Redis Info ===
$(docker compose exec redis redis-cli INFO)
$(docker compose exec redis redis-cli XINFO STREAM events:main)
EOF

# Отправить отчет
cat /tmp/diagnostic-report.txt
```

---

## Чек-лист успешного деплоя

После завершения всех шагов проверьте:

- [ ] Сервер создан и доступен по SSH
- [ ] Docker и Docker Compose установлены
- [ ] Репозиторий склонирован
- [ ] `.env` файл настроен с реальными credentials
- [ ] Firewall настроен (UFW)
- [ ] Контейнеры запущены и healthy
- [ ] Health checks возвращают OK
- [ ] Nginx настроен и работает
- [ ] SSL сертификат получен и активен
- [ ] Тестовый запрос через HTTPS проходит успешно
- [ ] Логи не содержат ошибок
- [ ] Prometheus metrics доступны
- [ ] Автоматический бэкап настроен
- [ ] Мониторинг настроен (опционально)

---

## Дополнительные ресурсы

- [DigitalOcean Documentation](https://docs.digitalocean.com/)
- [Docker Documentation](https://docs.docker.com/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [AppsFlyer S2S Events API](https://dev.appsflyer.com/hc/docs/server-to-server-events-api)

---

## Контакты и поддержка

При возникновении проблем:

1. Проверьте раздел [Troubleshooting](#13-troubleshooting)
2. Посмотрите логи: `docker compose logs -f`
3. Проверьте health endpoints
4. Создайте diagnostic report (см. раздел 13.7)

**Разработчик:** AppsFlyer Event Sender Service  
**Версия документа:** 1.0  
**Последнее обновление:** 2026-01-29
