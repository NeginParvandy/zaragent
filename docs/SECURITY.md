# Security

## حالت فعلی بدون تغییر Backend

```env
AUTH_REQUIRED=false
ENABLE_ADMIN_ENDPOINTS=false
```

در این Mode، Agent همان `employeeId` و `session` موجود در Body اپلیکیشن را مصرف می‌کند و Header جدیدی لازم نیست. برای کاهش ریسک:

- Session فقط در حافظه همان Request استفاده می‌شود.
- Token و Hash در SQLite ذخیره نمی‌شوند.
- URL، Query، Header و Body حساس در Log Redact می‌شوند.
- Body size، Rate limit، Trusted Host، CORS و Security Header فعال‌اند.
- Writeها بدون Confirm اجرا نمی‌شوند.
- عملیات نامطمئن خودکار Retry نمی‌شود.

## TLS

در Production:

```env
VERIFY_SSL=true
```

برای CA داخلی:

```env
INTERNAL_CA_BUNDLE=C:\Certificates\company-ca.pem
```

خاموش‌کردن Verify در Production توسط Validation برنامه رد می‌شود.

## CORS و Host

مقادیر دقیق Origin و Host اپلیکیشن را تنظیم کنید؛ Wildcard در Production پذیرفته نمی‌شود.

```env
ALLOWED_HOSTS=agent.company.local,127.0.0.1,localhost
CORS_ORIGINS=https://app.company.local
CORS_ALLOW_CREDENTIALS=false
```

## حالت اختیاری Trusted Gateway

اگر در آینده خود تیم زیرساخت بخواهد بدون تغییر قرارداد عمومی یک Gateway مطمئن اضافه کند:

```env
AUTH_REQUIRED=true
AGENT_API_KEY=<minimum-32-character-secret>
TRUSTED_GATEWAY_HEADER=X-Employee-Id
```

این Mode در نسخه فعلی اجباری نیست.

## Admin داخلی

مسیر Admin پیش‌فرض 404 است. فقط در صورت نیاز:

```env
ENABLE_ADMIN_ENDPOINTS=true
ADMIN_API_KEY=<minimum-32-character-secret>
```
