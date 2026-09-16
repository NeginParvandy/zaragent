# Operations

## Health

- `/api/agent/live`: Process زنده است.
- `/api/agent/ready`: SQLite و Startup آماده‌اند.
- `/api/agent/health`: نسخه، زمان و Mode Agent.

## Log

مسیر پیش‌فرض:

```text
logs/agent.log
```

در گزارش خطا `X-Request-Id` را ثبت کنید. Credentialها Redact می‌شوند، ولی فایل Log همچنان باید فقط برای تیم مجاز قابل‌خواندن باشد.

## State Maintenance

در Startup و سپس هر `MAINTENANCE_INTERVAL_MINUTES`:

- Pending منقضی Expire می‌شود.
- Processing قدیمی به Unknown می‌رود.
- Stateهای قدیمی پاک می‌شوند.

## Action Unknown

اگر Status برابر `unknown` شد:

1. Confirm را دوباره ارسال نکنید.
2. Action Status را بررسی کنید.
3. وضعیت واقعی HR/Food را از Read API تطبیق دهید.
4. فقط پس از اطمینان عملیات جدید بسازید.

## مانیتورینگ پیشنهادی

- HTTP status و latency مسیرهای live/ready
- تعداد 5xx و `DOWNSTREAM_*`
- تعداد Actionهای `unknown`
- اندازه DB و فضای Disk
- Rotation و Backup Log/DB
