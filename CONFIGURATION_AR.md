# إعدادات النظام

## متغيرات البيئة

كل متغيرات البيئة تبدأ بالبادئة `TUC_`.

- `TUC_DATABASE_URL`: رابط قاعدة البيانات. الإعداد الحالي يستخدم MySQL.
- `TUC_TELEGRAM_API_ID`: رقم تطبيق تيليجرام من `my.telegram.org`.
- `TUC_TELEGRAM_API_HASH`: مفتاح تطبيق تيليجرام.
- `TUC_TELEGRAM_SESSION_PATH`: مكان حفظ جلسة تيليجرام المحلية.
- `TUC_CHANNELS_CONFIG_PATH`: مسار ملف القنوات.
- `TUC_SUBJECTS_CONFIG_PATH`: مسار ملف المواد.
- `TUC_OCR_LANGUAGE`: لغات OCR، والقيمة الافتراضية `ara+eng`.
- `TUC_AI_PROVIDER`: مزود التصنيف. القيمة الحالية الافتراضية `none`.
- `TUC_CLASSIFICATION_MIN_CONFIDENCE`: أقل ثقة لقبول التصنيف.
- `TUC_CLASSIFICATION_MIN_EVIDENCE_ITEMS`: أقل عدد أدلة لقبول التصنيف.
- `TUC_TELEGRAM_COLLECT_TEXT_MESSAGES`: هل يتم حفظ الرسائل النصية دون ملفات.

## إضافة قناة

يتم تعديل `config/channels.yaml` فقط:

```yaml
channels:
  - name: database
    username: "@database_channel"
    enabled: true
```

## إضافة مادة

يتم تعديل `config/subjects.yaml` فقط:

```yaml
subjects:
  - code: DB101
    name_ar: "قواعد البيانات"
    name_en: "Database"
```

التصنيف لا يقبل أي كود مادة غير موجود في هذا الملف.

## أنواع المحتوى

القيم الداخلية الثابتة:

- `lecture`
- `previous_exam`
- `assignment`
- `answer_model`
- `summary`

أي قيمة أخرى من المصنف تتحول إلى `unclassified`.

## مزود الذكاء الاصطناعي

القيمة الافتراضية:

```env
TUC_AI_PROVIDER=none
```

بهذه الحالة يعمل الجمع والتخزين، وتصبح الملفات غير مصنفة بدون فشل. لاستخدام OpenAI:

```env
TUC_AI_PROVIDER=openai
TUC_OPENAI_API_KEY=...
TUC_OPENAI_MODEL=gpt-4.1-mini
```

لا يتم قبول أي ناتج من النموذج إلا إذا مر على قواعد التحقق: مادة موجودة، نوع محتوى مسموح، ثقة كافية، وأدلة كافية.

## الواجهة

تشغيل الواجهة:

```bash
python -m app.cli serve --host 127.0.0.1 --port 8000
```

المسارات المهمة:

- `/`: الواجهة.
- `/api/overview`: ملخص النظام.
- `/api/files`: الملفات.
- `/api/runs`: تشغيلات المعالجة.
- `/api/demo/seed`: إنشاء بيانات تجربة.
