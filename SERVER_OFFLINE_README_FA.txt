Holding Smart Agent 2.4.6 - Offline Windows Server Release
===========================================================

این بسته برای Windows Server 64-bit و Python 3.13 ساخته شده و برای نصب یا نمایش Swagger به اینترنت نیاز ندارد.

مسیر پیشنهادی:
C:\Services\HoldingSmartAgent

نصب اولیه:
1) CMD را با Run as administrator باز کنید.
2) وارد پوشه پروژه شوید:
   cd /d C:\Services\HoldingSmartAgent
3) نصب کاملا آفلاین:
   install.bat
4) تنظیمات را بسازید:
   copy .env.example .env
   notepad .env
5) اجرای آزمایشی:
   run_prod.bat

آدرس پیش فرض Swagger:
http://192.168.50.153:13657/swagger

Health Check:
http://192.168.50.153:13657/api/agent/live
http://192.168.50.153:13657/api/agent/ready

نکات:
- پوشه wheelhouse شامل تمام پکیج های Windows x64 / Python 3.13 است.
- Swagger از فایل های محلی app\static\swagger استفاده می کند.
- install.bat به اینترنت وصل نمی شود.
- فایل .env واقعی و اطلاعات محرمانه را داخل ZIP نگهداری نکنید.
- اگر Windows Service از قبل نصب است، پس از جایگزینی فایل ها سرویس را Restart کنید.
