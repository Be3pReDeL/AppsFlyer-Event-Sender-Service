# Deployment Scripts

Коллекция скриптов для автоматизации деплоя, мониторинга и управления AppsFlyer Event Sender Service.

---

## Список скриптов

| Скрипт | Описание | Использование |
|--------|----------|---------------|
| `deploy-setup.sh` | Начальная настройка сервера | `bash deploy-setup.sh` |
| `preflight-check.sh` | Проверка готовности к деплою | `bash preflight-check.sh` |
| `auto-deploy.sh` | Автоматический деплой | `bash auto-deploy.sh [production\|staging\|dev]` |
| `rollback.sh` | Откат на предыдущую версию | `bash rollback.sh [timestamp]` |
| `health-monitor.sh` | Мониторинг здоровья сервиса | `bash health-monitor.sh` |

---

## 1. deploy-setup.sh

**Назначение:** Полная автоматическая настройка свежего сервера DigitalOcean.

**Что делает:**
- Обновляет систему
- Устанавливает Docker, Nginx, Certbot
- Создаёт пользователя `deploy`
- Настраивает firewall (UFW)
- Создаёт SSH ключ для GitHub
- Настраивает системные параметры (swap, sysctl)
- Создаёт скрипты резервного копирования

**Использование:**

```bash
# На локальной машине
scp scripts/deploy-setup.sh root@YOUR_SERVER_IP:/tmp/

# На сервере
ssh root@YOUR_SERVER_IP
bash /tmp/deploy-setup.sh
```

**Требования:**
- Ubuntu 22.04
- Root доступ
- Интернет соединение

**Время выполнения:** ~5-10 минут

---

## 2. preflight-check.sh

**Назначение:** Проверка готовности системы перед деплоем.

**Что проверяет:**
- Операционная система
- Docker и Docker Compose
- Необходимые утилиты
- Порты (8000, 6379, 80, 443)
- Системные ресурсы (RAM, disk)
- Nginx и Certbot
- Firewall (UFW)
- Сетевое соединение
- SSH ключи для GitHub
- Файлы проекта
- Environment переменные

**Использование:**

```bash
cd /opt/apps/AppsFlyer-Event-Sender-Service
bash scripts/preflight-check.sh
```

**Exit codes:**
- `0` - Система готова (или только warnings)
- `1` - Найдены критические ошибки

**Пример вывода:**

```
========================================
AppsFlyer Event Sender - Pre-flight Check
========================================

1. Операционная система
✓ Ubuntu 22.04

2. Docker
✓ Docker установлен: 24.0.7
✓ Docker daemon работает
✓ Пользователь deploy в группе docker

...

========================================
ИТОГОВЫЙ ОТЧЕТ
========================================
✓ Система готова к деплою!
```

---

## 3. auto-deploy.sh

**Назначение:** Полностью автоматический деплой новой версии.

**Что делает:**
1. Проверяет зависимости
2. Создаёт backup текущей версии (Redis + .env)
3. Получает обновления из Git
4. Валидирует конфигурацию
5. Останавливает текущие контейнеры
6. Пересобирает Docker образы
7. Запускает новую версию
8. Проверяет health checks
9. Отправляет тестовый запрос
10. Cleanup старых образов и backups
11. Генерирует отчёт

**Использование:**

```bash
cd /opt/apps/AppsFlyer-Event-Sender-Service

# Production deployment
bash scripts/auto-deploy.sh production

# Staging deployment
bash scripts/auto-deploy.sh staging

# Dev deployment
bash scripts/auto-deploy.sh dev
```

**Параметры:**
- `environment` - окружение: `production`, `staging`, `dev` (по умолчанию: `production`)

**Время выполнения:** ~5-10 минут (зависит от размера образов)

**Rollback при проблемах:**

Если деплой не прошёл валидацию, откатитесь:

```bash
# Откат на последний backup
bash scripts/rollback.sh

# Или на конкретный timestamp
bash scripts/rollback.sh 20260129_143022
```

**Автоматизация через cron:**

```bash
# Автоматический деплой каждый день в 2:00 AM
crontab -e

# Добавить строку:
0 2 * * * cd /opt/apps/AppsFlyer-Event-Sender-Service && bash scripts/auto-deploy.sh production >> /var/log/auto-deploy.log 2>&1
```

---

## 4. rollback.sh

**Назначение:** Откат на предыдущую версию при проблемах.

**Что делает:**
1. Останавливает текущие контейнеры
2. Создаёт safety backup текущего состояния
3. Восстанавливает .env из backup
4. Восстанавливает Redis данные (если доступны)
5. Опционально откатывает Git commit
6. Пересобирает образы
7. Запускает контейнеры
8. Проверяет health checks

**Использование:**

```bash
cd /opt/apps/AppsFlyer-Event-Sender-Service

# Откат на последний backup
bash scripts/rollback.sh

# Откат на конкретный timestamp
bash scripts/rollback.sh 20260129_143022
```

**Нахождение доступных backups:**

```bash
ls -lht /opt/backups/deployments/env-backup-*
```

**Интерактивные вопросы:**

Скрипт спросит:
1. Подтверждение отката
2. Нужно ли откатить Git commit

**Время выполнения:** ~3-5 минут

---

## 5. health-monitor.sh

**Назначение:** Периодический мониторинг здоровья сервиса с алертами.

**Что проверяет:**
- Health endpoint (/health/ready)
- Статус Docker контейнеров
- Redis доступность
- Размер DLQ
- Использование памяти
- Использование диска

**Что делает при проблемах:**
1. Логирует ошибку
2. Отправляет алерты (Email + Telegram)
3. Собирает диагностическую информацию
4. Пытается автоматическое восстановление (restart)
5. Отправляет алерт о восстановлении

**Использование:**

```bash
# Ручной запуск
bash scripts/health-monitor.sh

# С конфигурацией через переменные окружения
ALERT_EMAIL="admin@example.com" \
TELEGRAM_BOT_TOKEN="123456:ABC..." \
TELEGRAM_CHAT_ID="987654321" \
bash scripts/health-monitor.sh
```

**Настройка через cron:**

```bash
crontab -e

# Проверка каждые 5 минут
*/5 * * * * /opt/apps/AppsFlyer-Event-Sender-Service/scripts/health-monitor.sh
```

**Конфигурация через environment:**

Создайте файл `/etc/appsflyer-monitor.conf`:

```bash
export ALERT_EMAIL="admin@example.com"
export HEALTH_URL="http://localhost:8000/health/ready"
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
export PROJECT_DIR="/opt/apps/AppsFlyer-Event-Sender-Service"
export LOG_FILE="/var/log/appsflyer-health-monitor.log"
```

Обновите cron:

```bash
*/5 * * * * source /etc/appsflyer-monitor.conf && /opt/apps/AppsFlyer-Event-Sender-Service/scripts/health-monitor.sh
```

**Логи:**

```bash
# Просмотр логов мониторинга
tail -f /var/log/appsflyer-health-monitor.log
```

**Состояния:**
- `healthy` - всё работает
- `degraded` - есть предупреждения (high DLQ, high memory)
- `unhealthy` - критические проблемы (контейнеры упали, health check failed)
- `recovered` - восстановлено автоматически

---

## Типичные сценарии использования

### Первый деплой на новый сервер

```bash
# 1. Настройка сервера
bash deploy-setup.sh

# 2. Переключиться на пользователя deploy
su - deploy

# 3. Клонировать репозиторий
cd /opt/apps
git clone git@github.com:USER/REPO.git AppsFlyer-Event-Sender-Service
cd AppsFlyer-Event-Sender-Service

# 4. Настроить .env
cp deploy/env-examples/production.env .env
nano .env

# 5. Pre-flight check
bash scripts/preflight-check.sh

# 6. Деплой
bash scripts/auto-deploy.sh production
```

### Обновление существующего деплоя

```bash
cd /opt/apps/AppsFlyer-Event-Sender-Service

# Автоматический деплой с проверками
bash scripts/auto-deploy.sh production
```

### Откат при проблемах

```bash
cd /opt/apps/AppsFlyer-Event-Sender-Service

# Быстрый откат
bash scripts/rollback.sh

# Проверка
curl http://localhost:8000/health/ready
docker compose logs -f
```

### Настройка мониторинга

```bash
# Создать конфигурацию
sudo tee /etc/appsflyer-monitor.conf << EOF
export ALERT_EMAIL="admin@example.com"
export HEALTH_URL="http://localhost:8000/health/ready"
EOF

# Добавить в cron
crontab -e
# Добавить: */5 * * * * source /etc/appsflyer-monitor.conf && /opt/apps/AppsFlyer-Event-Sender-Service/scripts/health-monitor.sh

# Протестировать
bash scripts/health-monitor.sh
```

---

## Переменные окружения

### auto-deploy.sh

| Переменная | Default | Описание |
|------------|---------|----------|
| `PROJECT_DIR` | `/opt/apps/AppsFlyer-Event-Sender-Service` | Директория проекта |
| `BACKUP_DIR` | `/opt/backups/deployments` | Директория backups |

### rollback.sh

| Переменная | Default | Описание |
|------------|---------|----------|
| `PROJECT_DIR` | `/opt/apps/AppsFlyer-Event-Sender-Service` | Директория проекта |
| `BACKUP_DIR` | `/opt/backups/deployments` | Директория backups |

### health-monitor.sh

| Переменная | Default | Описание |
|------------|---------|----------|
| `HEALTH_URL` | `http://localhost:8000/health/ready` | URL health endpoint |
| `ALERT_EMAIL` | - | Email для алертов |
| `TELEGRAM_BOT_TOKEN` | - | Telegram bot token |
| `TELEGRAM_CHAT_ID` | - | Telegram chat ID |
| `PROJECT_DIR` | `/opt/apps/AppsFlyer-Event-Sender-Service` | Директория проекта |
| `LOG_FILE` | `/var/log/appsflyer-health-monitor.log` | Файл логов |

---

## Troubleshooting

### Скрипт не запускается

```bash
# Сделать исполняемым
chmod +x scripts/*.sh

# Проверить права
ls -l scripts/
```

### Permission denied

```bash
# Запустить с sudo
sudo bash scripts/deploy-setup.sh

# Или переключиться на правильного пользователя
su - deploy
```

### Docker команды не работают

```bash
# Добавить пользователя в группу docker
sudo usermod -aG docker $USER

# Перелогиниться
newgrp docker
```

### Backup не создаётся

```bash
# Создать директорию вручную
sudo mkdir -p /opt/backups/deployments
sudo chown $USER:$USER /opt/backups/deployments
```

### Health monitor не отправляет алерты

```bash
# Проверить переменные окружения
env | grep -E "(ALERT_EMAIL|TELEGRAM)"

# Проверить наличие mail команды
which mail

# Установить mailutils
sudo apt install mailutils
```

---

## Логи

### Логи скриптов

```bash
# Auto-deploy
tail -f /var/log/auto-deploy.log

# Health monitor
tail -f /var/log/appsflyer-health-monitor.log

# Cron
grep CRON /var/log/syslog
```

### Логи приложения

```bash
# Все сервисы
docker compose logs -f

# Конкретный сервис
docker compose logs -f api
docker compose logs -f worker
```

---

## Best Practices

1. **Всегда запускайте preflight-check перед деплоем**
2. **Используйте auto-deploy для consistency**
3. **Настройте health monitoring с первого дня**
4. **Храните backups минимум 30 дней**
5. **Тестируйте rollback процедуру на staging**
6. **Документируйте все manual изменения**
7. **Используйте git tags для production releases**

---

## Дополнительная документация

- [Полное руководство по деплою](../docs/deployment_digitalocean.md)
- [Быстрый старт](../docs/deployment_quickstart.md)
- [Чеклист деплоя](../docs/deployment_checklist.md)
- [Deploy конфигурации](../deploy/README.md)
