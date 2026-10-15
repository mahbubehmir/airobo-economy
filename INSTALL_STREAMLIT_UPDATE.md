# اعمال نسخه Streamlit روی پروژه فعلی ویندوز

این بسته شامل کدها و مستندات به‌روزشده است؛ **فایل دیتابیس، پوشه `.git` و داده‌های خروجی شخصی شما داخل بسته نیستند**.

1. اگر `main.py` باز است، با `Ctrl+C` متوقفش کنید. فایل‌های CSV را نیز اگر در Excel باز هستند ببندید.
2. از پوشه فعلی پروژه یک کپی پشتیبان بگیرید. دیتابیس مهم شما در `data/rebar_observatory.sqlite3` است؛ آن را حذف یا جایگزین نکنید.
3. ZIP را ابتدا در یک پوشه موقت استخراج کنید. فایل‌های موجود در ریشه ZIP را روی ریشه پروژه `D:\airobo-economy` کپی کنید و اجازه دهید نسخه‌های کد جایگزین شوند. پوشه `data` یا `output` خودتان را پاک نکنید.
4. در Anaconda Prompt یا CMD با محیط `(myenv)` فعال، از مسیر پروژه اجرا کنید:

```cmd
cd /d D:\airobo-economy
python -m pip install -r requirements.txt
python -m py_compile app.py dashboard_storage.py analysis.py report.py collectors.py main.py
python -m unittest discover -s tests -v
```

5. داشبورد را در یک پنجره CMD اجرا کنید:

```cmd
python -m streamlit run app.py
```

مرورگر را روی آدرس محلی اعلام‌شده در ترمینال باز کنید؛ معمولاً `http://localhost:8501`.

6. اگر می‌خواهید داده‌ها در کنار داشبورد به‌صورت زمان‌بندی‌شده جمع‌آوری شوند، پنجره CMD دوم باز کنید و اجرا کنید:

```cmd
python main.py
```

Streamlit و `main.py` به یک دیتابیس مشترک وصل‌اند. برای شروع فقط یک بار `main.py` را اجرا کنید؛ اجرای خودکار بعدی طبق تنظیم پیش‌فرض ۲۴ ساعت بعد است. هنگام باز بودن CSV در Excel ممکن است گزارش‌ساز ویندوز با `PermissionError` روبه‌رو شود.

## Docker (اختیاری)

برای اجرای جمع‌آوری‌کننده و داشبورد به‌صورت دو سرویس: در یک محیط دارای Docker Desktop، از ریشه پروژه اجرا کنید:

```cmd
docker compose up --build -d
```

سپس داشبورد در `http://localhost:8501` در دسترس است. سرویس‌ها از پوشه‌های `data` و `output` به‌صورت مشترک استفاده می‌کنند.
