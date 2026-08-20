# تقرير مراحل التنفيذ

## قبل التنفيذ

- الغموض الأساسي: هل تحفظ الرسائل النصية بدون ملفات؟ تم جعلها إعدادا عبر `TUC_TELEGRAM_COLLECT_TEXT_MESSAGES` والقيمة الافتراضية `false`.
- قرار قاعدة البيانات: MySQL للتشغيل الحالي، وSQLite للاختبارات والتطوير الخفيف.
- قرار العمال: لم تتم إضافة Celery في النسخة الأساسية لأن المعالجة المتزامنة عبر cron تكفي كبداية وتقلل التعقيد. Redis موجود في Docker Compose كتجهيز اختياري للتوسع.

## Phase 1: الهيكل والإعدادات والتسجيل

- التغيير: إنشاء بنية `app/` و`config/` و`tests/` وملفات README و`.env.example` و`.gitignore`.
- السبب: فصل المسؤوليات ومنع hardcoding للقنوات والمواد والأسرار.
- التشغيل: `python -m app.cli health-check`.
- الاختبارات: إعدادات البيئة، تحميل YAML، وحجب الأسرار في السجلات.
- النتيجة المتوقعة: ظهور عدد القنوات المفعلة والمواد بدون تسريب أسرار.
- المخاطر: ملفات القنوات والمواد الحقيقية يجب أن يراجعها العميل.

## Phases 2-7: تيليجرام والجمع والتخزين الأولي

- التغيير: إضافة Telethon login، عميل تيليجرام، جامع تدريجي، تحميل ملفات، SHA-256، ومنع التكرار.
- الملفات: `app/telegram/*` و`app/ingestion/*` و`app/database/*`.
- السبب: جمع الجديد فقط وعدم معالجة نفس الرسالة أو الملف مرتين.
- التشغيل: `python -m app.cli telegram-login` ثم `python -m app.cli collect --channel database --limit 5`.
- الاختبارات: مزيفات Telegram تتحقق من التحميل والهاش والتكرار وتقدم `last_message_id`.
- النتيجة المتوقعة: الملفات الجديدة تصبح `downloaded`، والمكررة تصبح `duplicate`.
- المخاطر: الاختبار الحي يحتاج قناة مصرح بها وبيانات Telegram API.

## Phases 8-13: المعالجة والتصنيف والتخزين والتقارير

- التغيير: استخراج PDF، OCR عربي، استخراج DOCX/PPTX، تنظيف النص، تصنيف آمن، تخزين نهائي، وتقرير.
- الملفات: `app/processing/*` و`app/storage/*` و`app/reports/*`.
- السبب: تجهيز المحتوى التعليمي للتصنيف بدون تخمين.
- التشغيل: `python -m app.cli process` ثم `python -m app.cli report`.
- الاختبارات: PDF طبيعي، OCR fallback، ملفات legacy unsupported، قواعد unclassified، ومسارات التخزين.
- النتيجة المتوقعة: الملفات المصنفة تنتقل إلى `processed/<subject>/<type>`، والغامضة إلى `unclassified`.
- المخاطر: جودة OCR العربي تعتمد على جودة المسح وتثبيت Tesseract واللغة العربية.

## Phases 14-17: الاعتمادية والنشر

- التغيير: قفل تشغيل، retry helper، FloodWait handling، Alembic migration، Docker Compose، systemd، cron، ودليل نشر.
- الملفات: `app/runtime/*` و`deploy/*` و`docker-compose.yml` و`DEPLOYMENT_AR.md`.
- السبب: منع تداخل التشغيل واحترام حدود تيليجرام وتجهيز VPS.
- التشغيل: `alembic upgrade head`، أو `systemctl enable --now telegram-collector.timer telegram-process.timer`.
- الاختبارات: lock، retry، FloodWait، وCLI smoke test.
- النتيجة المتوقعة: تشغيل دوري آمن وقابل للمراقبة.
- المخاطر: يجب ضبط صلاحيات `.env` وملف جلسة تيليجرام على VPS.

## واجهة الإدارة

- التغيير: إضافة `app/web/server.py` و`app/web/static/*` و`app/web/admin.py`.
- السبب: تجربة النظام من المتصفح وإدارة القنوات والمواد ورؤية الملفات والتقارير.
- التشغيل: `python -m app.cli serve --host 127.0.0.1 --port 8000`.
- الاختبارات: `tests/unit/test_web_admin.py`.
- النتيجة المتوقعة: فتح الواجهة، ضغط `Seed Demo`، ظهور ملفات وتصنيفات وتقارير من MySQL.

## Phase 18: الاختبار الحي

- الحالة: غير منفذ داخل هذه البيئة لعدم وجود بيانات اعتماد وقناة تيليجرام مصرح بها.
- طريقة التنفيذ على VPS: `telegram-login` ثم `collect --channel <name> --limit 5` ثم `process` ثم `report`.
- معيار النجاح: ظهور رسائل جديدة في قاعدة البيانات، ملفات محفوظة، وعدم ظهور أسرار في السجلات.

## Phase 19: التوثيق النهائي

- التغيير: تحديث README، README_AR، DEPLOYMENT_AR، CONFIGURATION_AR، TROUBLESHOOTING_AR، ARCHITECTURE_AR، وSOURCE_FILES_AR.
- السبب: تسليم قابل للفهم والتشغيل بدون معرفة ضمنية من المطور.
- الاختبارات: `pytest` و`ruff check`.
- النتيجة: 32 اختبارا ناجحا وlint clean.
