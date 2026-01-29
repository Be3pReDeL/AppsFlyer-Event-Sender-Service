# API Examples

Примеры запросов к сервису для отправки событий в AppsFlyer.

## Базовая настройка

Перед отправкой запросов убедитесь, что:
- Сервис запущен (`docker compose up -d` или `uvicorn app.main:app`)
- Установлена переменная `API_TOKENS` с валидным токеном
- Установлена переменная `APPSFLYER_DEV_KEY` с вашим dev key
- Установлена переменная `APPSFLYER_DEFAULT_APP_ID` (или передавайте `app_id` в запросах)

## Регистрация (Registration)

### GET запрос (минимальный)

```bash
curl -X GET "http://localhost:8000/v1/track/registration?token=YOUR_TOKEN&appsflyer_id=1234567890-abcdef&platform=ios"
```

### GET запрос (полный)

```bash
curl -X GET "http://localhost:8000/v1/track/registration?\
token=YOUR_TOKEN&\
app_id=id123456789&\
appsflyer_id=1658954220-1234567890&\
customer_user_id=user_12345&\
device_id=ios-device-abc&\
platform=ios&\
registration_method=email&\
event_id=reg_custom_id_001"
```

**Ответ (202 Accepted):**
```json
{
  "status": "accepted",
  "event_id": "reg_custom_id_001",
  "queued_at": "2026-01-29T15:30:45.123Z",
  "message": "Event queued for processing"
}
```

### POST запрос (query параметры, Keitaro-совместимый)

```bash
curl -X POST "http://localhost:8000/v1/track/registration?\
token=YOUR_TOKEN&\
app_id=id123456789&\
appsflyer_id=1658954220-1234567890&\
customer_user_id=user_12345&\
platform=ios&\
registration_method=social&\
event_id=reg_abc123"
```

> **Note**: POST endpoint принимает данные из query-параметров (не из body), так как Keitaro не поддерживает body в POST запросах.

## Покупка (Purchase)

### GET запрос (минимальный)

```bash
curl -X GET "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
appsflyer_id=1234567890-abcdef&\
revenue=19.99&\
currency=USD&\
platform=android"
```

### GET запрос (полный)

```bash
curl -X GET "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
app_id=com.example.myapp&\
appsflyer_id=1658954220-9876543210&\
customer_user_id=user_67890&\
revenue=29.99&\
currency=EUR&\
product_id=premium_monthly&\
order_id=order_xyz789&\
quantity=1&\
platform=android&\
event_id=purchase_custom_002"
```

**Ответ (202 Accepted):**
```json
{
  "status": "accepted",
  "event_id": "purchase_custom_002",
  "queued_at": "2026-01-29T15:35:12.456Z",
  "message": "Event queued for processing"
}
```

### POST запрос (query параметры, Keitaro-совместимый)

```bash
curl -X POST "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
app_id=com.example.myapp&\
appsflyer_id=1658954220-9876543210&\
customer_user_id=user_67890&\
revenue=49.99&\
currency=USD&\
product_id=premium_yearly&\
order_id=order_abc456&\
quantity=1&\
platform=android&\
event_id=purchase_def456"
```

> **Note**: POST endpoint принимает данные из query-параметров (не из body), так как Keitaro не поддерживает body в POST запросах.

## Использование HMAC аутентификации

Если настроен `AUTH_MODE=hmac`, используйте подпись вместо token:

```bash
# Пример генерации подписи (bash)
KEY="my-key-id"
SECRET="my-secret-key"
TS=$(date +%s)
PARAMS="appsflyer_id=1234567890-abcdef&key=$KEY&platform=ios&ts=$TS"
SIG=$(echo -n "$PARAMS" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)

curl -X GET "http://localhost:8000/v1/track/registration?\
key=$KEY&\
ts=$TS&\
sig=$SIG&\
appsflyer_id=1234567890-abcdef&\
platform=ios"
```

## Мультиприложения (Multiple Apps)

Сервис поддерживает отправку событий для разных приложений через параметр `app_id`:

### iOS приложение

```bash
curl -X GET "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
app_id=id123456789&\
appsflyer_id=ios-device-123&\
revenue=9.99&\
currency=USD&\
platform=ios"
```

### Android приложение

```bash
curl -X GET "http://localhost:8000/v1/track/purchase?\
token=YOUR_TOKEN&\
app_id=com.example.androidapp&\
appsflyer_id=android-device-456&\
revenue=14.99&\
currency=EUR&\
platform=android"
```

## Обработка дубликатов

Если отправить событие с тем же `event_id` повторно:

```bash
# Первый запрос
curl -X GET "http://localhost:8000/v1/track/registration?\
token=YOUR_TOKEN&\
appsflyer_id=device-123&\
event_id=unique_event_001"

# Ответ: {"status": "accepted", "event_id": "unique_event_001", ...}

# Второй запрос (дубликат)
curl -X GET "http://localhost:8000/v1/track/registration?\
token=YOUR_TOKEN&\
appsflyer_id=device-123&\
event_id=unique_event_001"

# Ответ: {"status": "accepted", "event_id": "unique_event_001", "message": "Duplicate event (already processed)"}
```

## Коды ответов

| Код | Описание |
|-----|----------|
| 202 | Событие принято и поставлено в очередь |
| 400 | Неверные параметры (например, отрицательный revenue) |
| 401 | Неверный токен или подпись |
| 422 | Ошибка валидации Pydantic (неверный формат данных) |
| 503 | Redis недоступен |

## Проверка работоспособности

```bash
# Liveness probe
curl http://localhost:8000/health/live

# Readiness probe
curl http://localhost:8000/health/ready
```

## Примечания

1. **Обязательные параметры для purchase**: `revenue` и `currency`
2. **app_id**: если не передан, используется `APPSFLYER_DEFAULT_APP_ID` из конфигурации
3. **event_id**: если не передан, генерируется автоматически (например `reg_a1b2c3d4`)
4. **Дедупликация**: события с одинаковым `event_id` обрабатываются только один раз (TTL 7 дней)
5. **Platform**: автоматически нормализуется (`ios` → `iOS`, `android` → `Android`)
6. **Currency**: автоматически приводится к uppercase (`usd` → `USD`)
