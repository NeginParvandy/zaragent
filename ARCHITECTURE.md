# معماری Holding Smart Agent 2.4

## اصل طراحی

Agent یک سرویس مستقل است و قرارداد موجود تیم اپلیکیشن و APIهای HR/Food را تغییر نمی‌دهد.

```text
Application -> Agent API -> Use Cases -> HR/Food Adapters -> Existing APIs
                          -> Local State Repository (SQLite)
```

## لایه‌ها

- `app/api`: Routeها، Middleware و قرارداد HTTP
- `app/application`: Use Caseها، Chat، Action، Reminder و Daily Brief
- `app/domain`: مدل‌ها، قواعد متنی، تاریخ و Validation
- `app/infrastructure/clients`: اتصال مقاوم به APIهای موجود
- `app/infrastructure/repositories`: State داخلی Agent
- `scripts`: نصب، اجرا، Backup، Restore و Cleanup

## قواعد عملیاتی

1. Readها مستقیماً داده واقعی API را برمی‌گردانند.
2. Writeها ابتدا Pending Action می‌سازند.
3. Confirm با Transaction اتمیک `pending -> processing` Claim می‌شود.
4. Result قطعی به `succeeded` یا `failed` می‌رود.
5. Result نامطمئن به `unknown` می‌رود و نباید خودکار تکرار شود.
6. Restart، Action قدیمی `processing` را به `unknown` تبدیل می‌کند.
7. Maintenance دوره‌ای Cleanup و Recovery را انجام می‌دهد.
8. Token و Hash نه در State و نه در Log ذخیره نمی‌شوند.

## مقیاس اجرا

نسخه SQLite برای یک Instance و یک Worker طراحی شده است. برای Scale چند Instance باید فقط Repository داخلی Agent به دیتابیس مشترک ارتقا یابد؛ API تیم اپلیکیشن و HR/Food نیاز به تغییر ندارند.
