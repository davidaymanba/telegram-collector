# النشر على خادم Ubuntu VPS

هذا الدليل يشرح نشر النظام على خادم Ubuntu VPS مستقل عن جهاز المطور.

## متطلبات النظام المتوقعة

- Ubuntu 22.04 أو أحدث.
- Python 3.12 أو أحدث.
- MySQL للإنتاج أو التشغيل المحلي.
- Redis إذا تم تفعيل العمال غير المتزامنين في مرحلة لاحقة.
- Tesseract OCR مع دعم العربية:

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv mysql-server tesseract-ocr tesseract-ocr-ara poppler-utils
```

إذا كان Python 3.12 غير متاح في مستودعات النظام، استخدم طريقة تثبيت رسمية مناسبة لإصدار Ubuntu لديك.

## تجهيز مستخدم الخدمة

```bash
sudo adduser --system --group --home /opt/telegram-university-collector collector
sudo mkdir -p /opt/telegram-university-collector
sudo chown -R collector:collector /opt/telegram-university-collector
```

## تثبيت المشروع

```bash
sudo -u collector git clone <REPOSITORY_URL> /opt/telegram-university-collector
cd /opt/telegram-university-collector
sudo -u collector python3.12 -m venv .venv
sudo -u collector .venv/bin/pip install -e .
```

## إعداد MySQL

```bash
sudo mysql
```

ثم داخل MySQL:

```sql
CREATE DATABASE IF NOT EXISTS telegram_collector CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'collector'@'localhost' IDENTIFIED BY 'CHANGE_ME_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON telegram_collector.* TO 'collector'@'localhost';
```

ضع رابط الاتصال في `.env`:

```env
TUC_DATABASE_URL=mysql+pymysql://collector:CHANGE_ME_STRONG_PASSWORD@127.0.0.1:3306/telegram_collector?charset=utf8mb4
```

## ملف البيئة

```bash
sudo -u collector cp .env.example .env
sudo chmod 600 .env
```

املأ:

- `TUC_TELEGRAM_API_ID`
- `TUC_TELEGRAM_API_HASH`
- `TUC_DATABASE_URL`
- `TUC_AI_PROVIDER`
- `TUC_OPENAI_API_KEY` إذا تم استخدام OpenAI

## تشغيل migrations

```bash
sudo -u collector .venv/bin/alembic upgrade head
```

## تسجيل دخول تيليجرام على VPS

يجب تنفيذ تسجيل الدخول على الخادم نفسه:

```bash
sudo -u collector .venv/bin/python -m app.cli telegram-login
```

لا تنقل ملف الجلسة من جهاز آخر.

## اختبار قناة واحدة

عدّل `config/channels.yaml` بقناة مصرح بها، ثم:

```bash
sudo -u collector .venv/bin/python -m app.cli health-check
sudo -u collector .venv/bin/python -m app.cli collect --channel database --limit 5
sudo -u collector .venv/bin/python -m app.cli process
sudo -u collector .venv/bin/python -m app.cli report
```

## cron

انسخ محتوى `deploy/cron.example` وعدّل المسارات حسب مكان المشروع:

```bash
sudo -u collector crontab -e
```

المثال يستخدم `flock` حتى لا يبدأ تشغيل جديد قبل انتهاء السابق.

## systemd timer

بديل cron:

```bash
sudo cp deploy/telegram-collector.service /etc/systemd/system/
sudo cp deploy/telegram-collector.timer /etc/systemd/system/
sudo cp deploy/telegram-process.service /etc/systemd/system/
sudo cp deploy/telegram-process.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-collector.timer telegram-process.timer
```

## النسخ الاحتياطي

- انسخ قاعدة MySQL دوريا باستخدام `mysqldump`.
- انسخ مجلد `storage/processed` و`storage/unclassified`.
- احتفظ بنسخ مشفرة من `.env` وملف جلسة تيليجرام داخل سياسة أسرار آمنة.
- لا ترفع النسخ الاحتياطية إلى Git.

## ملاحظات أمان

- لا تنقل جلسة تيليجرام من جهاز المطور إلى الخادم.
- نفذ تسجيل الدخول مرة واحدة على الخادم نفسه.
- لا تحفظ `.env` أو ملفات `*.session` داخل Git.
- اجعل صلاحيات ملفات الأسرار مقيدة بالمستخدم الذي يشغل الخدمة.
