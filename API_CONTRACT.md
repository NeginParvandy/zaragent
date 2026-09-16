# API Contract - Holding Smart Agent 2.4

Base URL نمونه:

```text
http://127.0.0.1:8000
```

## سازگاری با Backend موجود

حالت پیش‌فرض پروژه:

```env
AUTH_REQUIRED=false
```

در این حالت هیچ Header جدیدی لازم نیست. `employeeId` و `session` از Body موجود اپلیکیشن دریافت می‌شوند. فیلدهای اضافه Body برای جلوگیری از شکستن قرارداد نادیده گرفته می‌شوند، اما فیلدهای شناخته‌شده دقیق اعتبارسنجی می‌شوند.

حالت اختیاری Trusted Gateway در آینده قابل فعال‌سازی است، ولی برای اجرای فعلی لازم نیست و به تیم اپلیکیشن تحمیل نشده است.

## قالب پاسخ استاندارد

موفق:

```json
{
  "hasError": false,
  "data": {},
  "message": "...",
  "error": null
}
```

خطا:

```json
{
  "hasError": true,
  "data": null,
  "message": "...",
  "error": {
    "code": "VALIDATION_ERROR",
    "details": null
  }
}
```

تمام پاسخ‌های 404، 409، 422، 500 و خطاهای Integration همین Envelope را دارند.

## Context مشترک

```json
{
  "employeeId": "10001234",
  "displayName": "نام کاربر",
  "date": "1405/04/22",
  "restaurantId": 84,
  "mealId": 1,
  "pageContext": "dashboard",
  "session": {
    "authorizationToken": "REAL_TOKEN",
    "usernameHash": "REAL_USERNAME_HASH",
    "passwordHash": "REAL_PASSWORD_HASH",
    "digitCode": 123456
  }
}
```

`date`، `restaurantId` و `mealId` اختیاری‌اند و Agent مقدار پیش‌فرض معتبر می‌سازد. Credentialها Log یا در SQLite ذخیره نمی‌شوند.

## Endpointها

### GET `/api/agent/live`

Liveness ساده؛ به API خارجی وصل نمی‌شود.

### GET `/api/agent/ready`

آماده‌بودن برنامه و SQLite را بررسی می‌کند؛ وضعیت HR/Food را جعل نمی‌کند.

### GET `/api/agent/health`

وضعیت داخلی، نسخه و Mode را برمی‌گرداند.

### GET `/api/agent/capabilities`

قابلیت‌های Agent را اعلام می‌کند.

### POST `/api/agent/chat`

```json
{
  "message": "منوی امروز را نشان بده",
  "context": {
    "employeeId": "10001234",
    "session": {
      "authorizationToken": "REAL_TOKEN",
      "usernameHash": "REAL_USERNAME_HASH",
      "passwordHash": "REAL_PASSWORD_HASH",
      "digitCode": 123456
    }
  }
}
```

درخواست‌های نمایشی فقط Read هستند. عملیات‌هایی مثل ثبت، رزرو، حذف یا امتیازدهی فقط Pending Action می‌سازند.

### POST `/api/agent/daily-brief`

Body همان Context است. اگر یکی از منابع HR/Food خطا دهد، بخش‌های سالم با وضعیت Partial برمی‌گردند.

### POST `/api/agent/reminders/check`

```json
{
  "employeeId": "10001234",
  "includeDailyBrief": true,
  "session": {}
}
```

### POST `/api/agent/reminders`

```json
{
  "employeeId": "10001234",
  "status": "pending",
  "session": {}
}
```

Statusهای Reminder:

```text
pending | shown | acted | dismissed | expired
```

### POST `/api/agent/reminders/dismiss`

```json
{
  "employeeId": "10001234",
  "reminderId": "REMINDER_ID",
  "session": {}
}
```

### POST `/api/agent/action/confirm`

```json
{
  "actionId": "ACTION_ID",
  "employeeId": "10001234",
  "session": {}
}
```

Confirm اتمیک است. دو درخواست هم‌زمان نمی‌توانند یک عملیات را دوبار اجرا کنند.

### POST `/api/agent/action/status`

```json
{
  "actionId": "ACTION_ID",
  "employeeId": "10001234",
  "session": {}
}
```

Statusهای Action:

```text
pending | processing | succeeded | failed | cancelled | expired | unknown
```

`unknown` یعنی Agent نمی‌تواند با قطعیت بگوید API مقصد عملیات را انجام داده یا نه. در این وضعیت Confirm را دوباره ارسال نکنید.

### POST `/api/agent/action/cancel`

فقط Action با وضعیت `pending` قابل لغو است.

## کدهای مهم خطا

| Code | HTTP | معنی |
|---|---:|---|
| `VALIDATION_ERROR` | 422 | ورودی شناخته‌شده نامعتبر است |
| `MISSING_CONFIGURATION` | 400 | Session یا تنظیم لازم موجود نیست |
| `NOT_FOUND` | 404 | رکورد یا مسیر پیدا نشد |
| `CONFLICT` | 409 | عملیات تکراری، منقضی یا غیرقابل اجرا است |
| `ACTION_RESULT_UNKNOWN` | 409/500 | نتیجه عملیات مقصد نامطمئن است؛ تکرار نکنید |
| `DOWNSTREAM_TIMEOUT` | 502 | API مقصد Timeout داده است |
| `DOWNSTREAM_UNAVAILABLE` | 502 | API مقصد قابل دسترس نیست |
| `DOWNSTREAM_CIRCUIT_OPEN` | 502 | Circuit Breaker موقتاً باز است |
| `UNHANDLED_ERROR` | 500 | خطای کنترل‌شده داخلی؛ X-Request-Id را گزارش کنید |

## Admin داخلی

Endpoint `/api/integration/config` به‌صورت پیش‌فرض خاموش است:

```env
ENABLE_ADMIN_ENDPOINTS=false
```

این بخش هیچ وابستگی به تیم اپلیکیشن ندارد. فقط در صورت نیاز عملیاتی می‌توان آن را با `ADMIN_API_KEY` فعال کرد.
