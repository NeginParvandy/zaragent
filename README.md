# Holding Smart Agent 2.4.6

نسخه تمیز مخصوص اجرا در **VS Code روی Windows با Python 3.13**.

## ویژگی‌های این بسته

- نصب وابستگی‌ها کاملا آفلاین از پوشه `wheelhouse`
- Swagger در مسیر `/swagger`
- مسیر قدیمی `/redoc` به Swagger هدایت می‌شود.
- اجرای Development با Reload
- اجرای Production بدون Reload
- بدون Docker
- بدون فایل‌های نصب محلی پکیج‌ها
- بدون فایل‌های محلی Swagger UI

## پیش‌نیاز

- Windows 10/11 یا Windows Server
- Python 3.13 نسخه 64-bit
- دسترسی اینترنت برای نصب پکیج‌ها و بارگذاری رابط Swagger/ReDoc

بررسی Python:

```powershell
py -3.13 --version
```

## اجرای سریع در VS Code

1. فایل ZIP را Extract کنید.
2. همان پوشه‌ای را در VS Code باز کنید که `setup_and_run_vscode.bat` داخل آن است.
3. از منوی `Terminal > New Terminal` یک ترمینال باز کنید.
4. اجرا کنید:

```powershell
.\setup_and_run_vscode.bat
```

پس از اجرا:

- Swagger آفلاین: `http://127.0.0.1:13657/swagger`
- Live: `http://127.0.0.1:8000/api/agent/live`
- Ready: `http://127.0.0.1:8000/api/agent/ready`

برای توقف پروژه در ترمینال `Ctrl+C` بزنید.

## اجرای مرحله‌ای

```powershell
.\install.bat
.\run_vscode.bat
```

`run_vscode.bat` در اولین اجرا، اگر `.env` وجود نداشته باشد، آن را از `.env.example` می‌سازد.

## بررسی سلامت نصب

بعد از نصب:

```powershell
.\verify_project.bat
```

این دستور موارد زیر را بررسی می‌کند:

- صحت Syntax فایل‌های Python
- سلامت وابستگی‌های نصب‌شده
- اتصال SQLite داخلی Agent
- نسخه‌های اصلی FastAPI، HTTPX و Pydantic

## اجرای Production

ابتدا فایل `.env` را برای محیط مقصد تنظیم کنید، سپس:

```powershell
.\run_prod.bat
```

در Production مقدارهای امنیتی و آدرس APIها را متناسب با محیط خودتان تنظیم کنید.

## فایل‌های مهم

- `.env.example`: نمونه تنظیمات
- `requirements.lock.txt`: نسخه دقیق وابستگی‌ها
- `install.bat`: ساخت `.venv` و نصب کاملا آفلاین از `wheelhouse`
- `run_vscode.bat`: اجرای Development
- `run_prod.bat`: اجرای Production
- `verify_project.bat`: کنترل نهایی نصب
- `API_CONTRACT.md`: قرارداد API
- `ARCHITECTURE.md`: معماری پروژه

## نکته امنیتی

فایل `.env`، Tokenها، Hashها و رمزها را Commit یا برای دیگران ارسال نکنید.
