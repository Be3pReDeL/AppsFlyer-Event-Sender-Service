# Deployment Files

Эта директория содержит файлы и шаблоны для деплоя AppsFlyer Event Sender Service.

---

## Содержимое

### Конфигурационные файлы

| Файл | Описание |
|------|----------|
| `nginx.conf.template` | Шаблон конфигурации Nginx с SSL и security headers |
| `appsflyer-service.service` | systemd unit файл для автоматического управления сервисом |

### Environment примеры

Директория `env-examples/` содержит шаблоны конфигурации для разных окружений:

| Файл | Окружение | Описание |
|------|-----------|----------|
| `development.env` | Dev | Локальная разработка, DEBUG=true, мягкие лимиты |
| `staging.env` | Staging | Тестовое окружение, умеренные лимиты |
| `production.env` | Production | Production окружение, строгая безопасность |

---

## Использование

### 1. Nginx конфигурация

```bash
# Скопировать шаблон
sudo cp deploy/nginx.conf.template /etc/nginx/sites-available/appsflyer

# Заменить YOUR_DOMAIN на реальный домен
sudo sed -i 's/YOUR_DOMAIN/your-actual-domain.com/g' /etc/nginx/sites-available/appsflyer

# Активировать конфигурацию
sudo ln -s /etc/nginx/sites-available/appsflyer /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default

# Проверить и перезапустить
sudo nginx -t
sudo systemctl restart nginx
```

### 2. systemd service

```bash
# Скопировать unit файл
sudo cp deploy/appsflyer-service.service /etc/systemd/system/

# Перезагрузить systemd
sudo systemctl daemon-reload

# Включить автозапуск
sudo systemctl enable appsflyer-service

# Запустить сервис
sudo systemctl start appsflyer-service

# Проверить статус
sudo systemctl status appsflyer-service
```

### 3. Environment конфигурация

**Development:**
```bash
cp deploy/env-examples/development.env .env
# Отредактировать .env при необходимости
docker compose up
```

**Staging:**
```bash
cp deploy/env-examples/staging.env .env
nano .env  # Заполнить staging credentials
docker compose up -d
```

**Production:**
```bash
cp deploy/env-examples/production.env .env
nano .env  # ОБЯЗАТЕЛЬНО заполнить production credentials!
docker compose up -d
```

---

## Важные замечания

### Безопасность

1. **НИКОГДА** не коммитьте `.env` файлы в Git
2. Используйте криптостойкие токены: `openssl rand -hex 32`
3. Регулярно ротируйте credentials (каждые 90 дней)
4. Храните production credentials в безопасном месте (1Password, HashiCorp Vault)

### Nginx

1. Замените `YOUR_DOMAIN` на реальный домен
2. Получите SSL сертификат через Certbot: `sudo certbot --nginx -d your-domain.com`
3. Настройте rate limiting под вашу нагрузку
4. Закройте или защитите `/metrics` endpoint в production

### systemd

1. Проверьте что `WorkingDirectory` указывает на правильную директорию
2. Убедитесь что user `deploy` существует и имеет доступ к Docker
3. Логи доступны через `journalctl -u appsflyer-service -f`

---

## Environment переменные

### Обязательные для production

| Переменная | Описание | Пример |
|------------|----------|--------|
| `API_TOKENS` | API токены для авторизации | `abc123...,def456...` |
| `APPSFLYER_DEV_KEY` | AppsFlyer Dev Key | `aBcDeFgH123456789` |
| `APPSFLYER_DEFAULT_APP_ID` | Default App ID | `id1234567890` или `com.example.app` |
| `APP_ENV` | Окружение | `prod` |
| `DEBUG` | Debug режим | `false` |

### Опциональные (с разумными defaults)

| Переменная | Default | Описание |
|------------|---------|----------|
| `WORKER_CONCURRENCY` | `10` | Число параллельных worker tasks |
| `MAX_ATTEMPTS` | `8` | Макс. попыток перед DLQ |
| `RATE_LIMIT_RPS` | `100` | Requests per second |
| `LOG_LEVEL` | `INFO` | Уровень логирования |

Полный список переменных см. в [.env.example](../.env.example)

---

## Деплой: быстрый старт

### Минимальные шаги

1. **Подготовить сервер:**
   ```bash
   bash scripts/deploy-setup.sh
   ```

2. **Клонировать репозиторий:**
   ```bash
   git clone git@github.com:USER/REPO.git /opt/apps/AppsFlyer-Event-Sender-Service
   cd /opt/apps/AppsFlyer-Event-Sender-Service
   ```

3. **Настроить .env:**
   ```bash
   cp deploy/env-examples/production.env .env
   nano .env  # Заполнить credentials
   ```

4. **Запустить:**
   ```bash
   docker compose up -d
   ```

5. **Настроить Nginx + SSL:**
   ```bash
   sudo cp deploy/nginx.conf.template /etc/nginx/sites-available/appsflyer
   sudo sed -i 's/YOUR_DOMAIN/your-domain.com/g' /etc/nginx/sites-available/appsflyer
   sudo ln -s /etc/nginx/sites-available/appsflyer /etc/nginx/sites-enabled/
   sudo certbot --nginx -d your-domain.com
   sudo systemctl restart nginx
   ```

### Подробная документация

См. [docs/deployment_digitalocean.md](../docs/deployment_digitalocean.md) для полного руководства.

---

## Troubleshooting

**Nginx не запускается:**
```bash
sudo nginx -t  # Проверить конфигурацию
sudo tail -f /var/log/nginx/error.log
```

**systemd сервис не запускается:**
```bash
sudo journalctl -u appsflyer-service -n 50
sudo systemctl status appsflyer-service
```

**SSL сертификат не обновляется:**
```bash
sudo certbot renew --dry-run
sudo systemctl status certbot.timer
```

---

## Ссылки

- [Deployment Guide](../docs/deployment_digitalocean.md) - Полное руководство
- [Deployment Quickstart](../docs/deployment_quickstart.md) - Быстрый старт
- [Deployment Checklist](../docs/deployment_checklist.md) - Чеклист проверки
- [Main README](../README.md) - Основная документация проекта
