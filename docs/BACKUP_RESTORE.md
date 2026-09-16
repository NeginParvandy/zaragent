# Backup و Restore

SQLite فقط State داخلی Agent را نگه می‌دارد و دیتابیس HR/Food را تغییر نمی‌دهد.

## Backup

```cmd
.venv\Scripts\python.exe scripts\backup_state.py
```

Backup با API خود SQLite ساخته می‌شود تا فایل سازگار باشد.

## Restore

1. Service را Stop کنید.
2. از DB فعلی Safety Backup بگیرید.
3. اجرا کنید:

```cmd
.venv\Scripts\python.exe scripts\restore_state.py path\to\backup.db
```

4. Service را Start و `/api/agent/ready` را تست کنید.

هرگز DB را هنگام Restore در حال استفاده نگه ندارید و DB را بین چند Instance Share نکنید.
