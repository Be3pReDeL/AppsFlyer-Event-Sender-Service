# AppsFlyer API Documentation

Документация по интеграции с AppsFlyer S2S API.

> **Источник**: Context7 MCP - `/websites/dev_appsflyer_hc_reference`  
> **Дата обращения**: 2026-01-29

## Endpoint

```
POST https://api2.appsflyer.com/inappevent/{app_id}
```

Альтернативный (более новый):
```
POST https://api3.appsflyer.com/inappevent/{app_id}
```

## Аутентификация

**Header**: `authentication: <dev_key>` (для старой версии API)  
**или**  
**Header**: `Authorization: Bearer <api_v2_token>` (для новой версии)

## Path Parameters

| Параметр | Тип | Описание |
|----------|-----|----------|
| app_id | string | App ID в AppsFlyer dashboard. Для iOS - префикс `id` (например `id123456789`). Для Android - package name (например `com.example.myapp`) |

## Request Body

### Обязательные параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| appsflyer_id | string | Уникальный ID устройства AppsFlyer |
| event_name | string | Название события (max 64 chars) |

### Опциональные параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| event_value | object | JSON объект с параметрами события |
| event_time | string | ISO 8601 timestamp (например `2023-10-27T10:00:00Z`) |
| customer_user_id | string | ID пользователя (max 64 chars) |
| device_ids | object | Объект с advertising_id, idfa и т.д. |
| platform | string | Платформа: iOS, Android, Windows |
| ip | string | IP адрес устройства |
| app_version | string | Версия приложения |

## Названия событий

### Registration
- **event_name**: `af_complete_registration`
- **event_value**: произвольные параметры регистрации

### Purchase
- **event_name**: `af_purchase`
- **event_value**: 
  - `af_revenue` (string) - сумма покупки
  - `af_currency` (string) - код валюты (ISO 4217)
  - `af_content_id` (string) - ID товара
  - `af_quantity` (number) - количество

## Пример запроса (Registration)

```json
{
  "appsflyer_id": "1658954220-1234567",
  "event_name": "af_complete_registration",
  "event_value": {
    "registration_method": "email"
  },
  "customer_user_id": "user_123",
  "platform": "iOS"
}
```

## Пример запроса (Purchase)

```json
{
  "appsflyer_id": "1658954220-1234567",
  "event_name": "af_purchase",
  "event_value": {
    "af_revenue": "19.99",
    "af_currency": "USD",
    "af_content_id": "product_123"
  },
  "customer_user_id": "user_456",
  "platform": "Android"
}
```

## Коды ответов

| Код | Описание | Действие |
|-----|----------|----------|
| 200 | Успех (событие принято) | Ack |
| 400 | Неверные параметры или missing mandatory fields | DLQ (non-retryable) |
| 401 | Неверная авторизация (invalid dev_key) | DLQ (non-retryable) |
| 403 | Forbidden (Zero package limit) | DLQ (non-retryable) |
| 429 | Rate limit | Retry с Retry-After header |
| 500 | Internal server error | Retry (retryable) |
| 5xx | Ошибка сервера | Retry (retryable) |

## Успешный ответ

```json
{
  "status": "success",
  "message": "Event received successfully."
}
```

или просто:
```json
"OK"
```

## Примечания

- **Payload limit**: до 1KB
- **Security**: требуется TLS v1.2 или выше
- **URL encoding**: зарезервированные символы должны быть percent-encoded
- **200 OK не гарантирует**: полную запись события (только минимальную валидацию)
- **Device identifiers**: для точной атрибуции рекомендуется передавать advertising_id или customer_user_id
