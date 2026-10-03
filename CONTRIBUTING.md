# دليل المساهمة في مشروع رتّب (Contributing to Rateb) 🤝

شكراً لاهتمامك بالمساهمة في مشروع **رتّب (Rateb)**! نحن نرحب بمساهمات المطورين لتحسين الأداء وإضافة المزايا وحل المشاكل.

Thank you for your interest in contributing to **Rateb**! We welcome contributions to improve performance, add features, and fix issues.

---

## 🛠️ بيئة التطوير (Development Setup)

### المتطلبات الأساسية (Prerequisites)

- **Python:** 3.11 أو أحدث
- **Git**
- نظام تشغيل: Windows, macOS, أو Linux

### خطوات التثبيت (Installation)

1. استنسخ المستودع (Clone the repo):

   ```bash
   git clone https://github.com/jalalmatluq-eng/exam-sorter.git
   cd exam-sorter
   ```

2. أنشئ بيئة افتراضية وفعّلها (Create and activate a virtual environment):

   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. ثبّت الاعتماديات (Install dependencies):

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install ruff pytest
   ```

4. نزّل نماذج الذكاء الاصطناعي الأوفلاين (Download offline AI models):

   ```bash
   python tools/download_ai_models.py
   ```

---

## 🧪 تشغيل الفحوصات الآلية (Running Tests)

قبل تقديم أي طلب سحب (PR)، تأكد من نجاح جميع الفحوصات الآلية الـ 21:

```bash
python test_modules.py
```

وفحص جودة الكود وتنسيقه بواسطة `ruff`:

```bash
ruff check .
```

---

## 📝 معايير الكود (Coding Standards)

- **Python Version:** متوافق مع Python 3.11+.
- **Type Annotations:** يُفضّل توثيق الأنواع بـ Type Hints (`Path`, `str`, `list[str]`, etc.).
- **Docstrings:** كتابة توثيق واضح باللغة العربية أو الإنجليزية لكل دالة ووحدة جديدة.
- **Safety First:** يجب حماية بيانات المستخدم وملفاته الأصلية دائماً، وعدم حذف أي ملف مصدر إلا بعد التحقق الصارم من سلامة النسخة في الوجهة وحجمها بالبايت.
- **Android Compatibility:** مراعاة قيود Scoped Storage و Storage Access Framework (SAF) و Android 10-14.
- **Security:** لا تضع أبداً أي مفاتيح API أو بيانات اعتماد في الكود المصدري.

---

## 🚀 دورة إرسال التعديلات (Pull Request Workflow)

1. أنشئ فرعاً جديداً لتعديلك:

   ```bash
   git checkout -b feature/your-feature-name
   # أو لإصلاح خطأ:
   git checkout -b fix/issue-description
   ```

2. قم بتطبيق التعديلات واختبارها.
3. التزم بتنسيق الكود وفحصه بـ `ruff` و `test_modules.py`.
4. اكتب رسالة Commit وصفية واضحة:

   ```bash
   git commit -m "feat: add multi-language support foundation"
   # أو
   git commit -m "fix: resolve sqlite handle leak on cleanup"
   ```

5. ارفع الفرع وأنشئ Pull Request إلى فرع `main`.

---

## 📄 الترخيص (License)

بمساهمتك في هذا المستودع، فإنك توافق على أن تكون مساهماتك خاضعة لترخيص [MIT License](LICENSE).
