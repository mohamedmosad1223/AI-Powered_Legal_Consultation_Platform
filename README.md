# ⚖️ منصة الاستشارات القانونية بالذكاء الاصطناعي

نظام استشارات قانونية ذكي يعتمد على تقنية **RAG (Retrieval Augmented Generation)** مبني على قانون ضريبة الدخل الأردني وأحكامه القضائية.

---

## 🚀 المشروع باختصار

المنصة تسمح للمستخدم بطرح أسئلة قانونية بالعربية العامية أو الفصحى، والنظام يفهم **المعنى** (Semantic Search) لا الكلمة الحرفية، ثم يجلب أدق المواد القانونية والأحكام القضائية المرتبطة، ويصيغ إجابة مفصلة ودقيقة.

---

## 🏗️ المعمارية (Architecture)

```
سؤال المستخدم (بالعربية)
         │
         ▼
[1] Cohere Embedding API
    → تحويل السؤال لمتجه رياضي (1024 بُعد)
         │
         ▼
[2] Qdrant Vector DB
    → البحث عن أقرب 4 مواد قانونية/أحكام بالتشابه الدلالي
         │
         ▼
[3] Neo4j Graph DB
    → لكل مادة يجلب الأحكام القضائية المرتبطة بها (CITES graph)
         │
         ▼
[4] Groq LLM (llama-3.3-70b-versatile)
    → يصيغ إجابة قانونية مفصلة مع ذكر المصادر
         │
         ▼
الإجابة + المصادر (المواد والأحكام)
```

---

## 🧱 مكونات النظام

| المكون | الأداة | الوظيفة |
|---|---|---|
| **Vector Database** | Qdrant (Docker) | تخزين وبحث المتجهات |
| **Graph Database** | Neo4j (Docker) | العلاقات بين القوانين والأحكام |
| **Embedding Model** | Cohere `embed-multilingual-v3.0` | تحويل النصوص العربية لمتجهات |
| **LLM** | Groq `llama-3.3-70b-versatile` | توليد الإجابات |
| **Backend API** | FastAPI | الـ API endpoints |

---

## 📂 هيكل المشروع

```
AI-Powered_Legal_Consultation_Platform/
├── data/                          # ملفات القوانين والأحكام (.docx)
│   ├── قانون رقم 34 ... 2015.docx
│   ├── قانون رقم 34 ... وتعديلاته.docx
│   ├── الحكم رقم 101 ... العليا.docx
│   ├── الحكم رقم 10424 ... جزا.docx
│   └── الحكم رقم 140 ... الضريبة.docx
│
├── src/
│   ├── app.py                     # FastAPI application entry point
│   ├── models/
│   │   ├── docx_parser.py         # تحليل ملفات DOCX واستخراج المواد
│   │   ├── neo4j_model.py         # التعامل مع قاعدة بيانات Neo4j
│   │   ├── embeddings_model.py    # Cohere Embedding wrapper
│   │   ├── vector_store.py        # Qdrant Vector Store wrapper
│   │   └── llm_client.py          # Groq LLM wrapper
│   ├── controllers/
│   │   ├── ingestion.py           # استيراد الملفات لـ Neo4j
│   │   ├── indexing.py            # فهرسة البيانات من Neo4j لـ Qdrant
│   │   ├── rag_controller.py      # Pipeline الرئيسي للـ RAG
│   │   └── graph_viewer.py        # مستكشف الـ Graph
│   └── views/
│       └── templates/
│           ├── index.html         # واجهة مستكشف القوانين (Graph)
│           └── rag.html           # واجهة المستشار الذكي (Chat)
│
├── docker-compose.yml             # تشغيل Neo4j + Qdrant
├── requirements.txt               # المكتبات المطلوبة
├── .env                           # مفاتيح API (لا تُرفع على GitHub!)
└── .env.example                   # مثال على ملف .env
```

---

## ⚙️ إعداد المشروع من الصفر

### 1. المتطلبات الأساسية
- Python 3.10+
- Docker Desktop (مشتغل)
- Conda (أو أي Python environment manager)

### 2. تجهيز البيئة
```bash
# إنشاء بيئة conda
conda create -n legal python=3.10
conda activate legal

# تثبيت المكتبات
pip install -r requirements.txt
```

### 3. مفاتيح الـ API
انسخ ملف `.env.example` وأعد تسميته `.env`، وضع مفاتيحك:
```bash
# احصل على مفاتيح مجانية من:
# Groq API Key:   https://console.groq.com/
# Cohere API Key: https://dashboard.cohere.com/
```

```env
GROQ_API_KEY=your_groq_api_key_here
COHERE_API_KEY=your_cohere_api_key_here
QDRANT_URL=http://localhost:6333
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123
```

### 4. تشغيل قواعد البيانات (Docker)
```bash
docker compose up -d
```
هذا سيشغل:
- **Neo4j** على: http://localhost:7474 (Login: neo4j / password123)
- **Qdrant** على: http://localhost:6333

### 5. استيراد البيانات لـ Neo4j
```bash
conda activate legal
python -m src.controllers.ingestion
```
المتوقع:
```
Initializing database connection...
Clearing existing database contents...
Parsing 2015 Law version: ...
Successfully ingested 2015 Law.
Parsing Amended Law version: ...
Successfully ingested Amended Law.
Parsing Judgment: الحكم رقم 101 ...
...
Ingestion completed successfully.
```

### 6. فهرسة البيانات في Qdrant (مرة واحدة فقط)
```bash
python -m src.controllers.indexing
```
المتوقع:
```
Starting indexing process...
Fetching ArticleVersions from Neo4j...
Indexing 164 ArticleVersions...
  Indexed batch 1 (50 items)...
  ...
Fetching Judgments from Neo4j...
Indexing 3 Judgments...
Indexing completed successfully!
```

### 7. تشغيل التطبيق
```bash
python -m src.app
```
افتح المتصفح على:
- **المستشار الذكي (RAG):** http://127.0.0.1:8000/rag
- **مستكشف القوانين (Graph):** http://127.0.0.1:8000/

---

## 🔌 API Endpoints

| Method | Endpoint | الوصف |
|---|---|---|
| `POST` | `/api/rag/query` | إرسال سؤال قانوني والحصول على إجابة |
| `GET` | `/api/graph/laws` | جلب جذر الـ Graph (القوانين) |
| `GET` | `/api/graph/children` | جلب أبناء عنصر معين في الـ Graph |
| `POST` | `/api/ingest` | إعادة استيراد البيانات |

### مثال على استخدام `/api/rag/query`:
```bash
curl -X POST http://127.0.0.1:8000/api/rag/query \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"هل النشاط الزراعي معفى من ضريبة الدخل؟\"}"
```

**الاستجابة:**
```json
{
  "status": "success",
  "data": {
    "answer": "وفقًا للمادة 5، يعفى من الضريبة كامل الدخل المتأتي من نشاط زراعي داخل المملكة...",
    "sources": [
      {"id": "law_34_2014_art_5_v_2015", "type": "ArticleVersion", "label": "مادة قانونية 5", "score": 0.684},
      {"id": "law_34_2014_art_5_v_amended", "type": "ArticleVersion", "label": "مادة قانونية 5", "score": 0.681}
    ]
  }
}
```

---

## 🧪 نتيجة الاختبار الفعلي

**السؤال:** "عندي أرض زراعية وببيع المحصول بتاعها، هل عليا ضريبة دخل على الزراعة؟"

```
==================================================
[الخطوة 1] استلام السؤال
[الخطوة 2] Cohere Embedding --> تم (1024 بُعد)
[الخطوة 3] Qdrant Search    --> 4 نتائج
[الخطوة 4] Neo4j Graph      --> المادة 5 (68.5%) + المادة 3 (58.5% مع أحكام)
[الخطوة 5] Groq LLM         --> إجابة مفصلة
==================================================
```

**الإجابة:** *"وفقًا للمادة 5، يعفى من الضريبة كامل الدخل المتأتي من نشاط زراعي داخل المملكة. كما يُعفى أول مليون دينار من مبيعات الشخص الطبيعي المتأتية من نشاط زراعي. ويُعتبر النشاط الزراعي: إنتاج المحاصيل والحبوب والخضراوات والفواكه والنباتات والزهور والأشجار، وتربية المواشي والأسماك والطيور والنحل..."*

---

## 📊 البيانات المتاحة حالياً

| النوع | العدد |
|---|---|
| نسخ قوانين | 2 (2015 + المعدل) |
| مواد قانونية مفهرسة في Qdrant | 164 |
| أحكام قضائية | 3 |
| **إجمالي نقاط في Qdrant** | **167** |

---

## 🔮 التطوير المستقبلي

- [ ] إضافة المزيد من القوانين الأردنية (ضريبة المبيعات، عمل، تجاري...)
- [ ] دعم تحميل الملفات مباشرة من الواجهة
- [ ] إضافة تاريخ المحادثة (Chat History / Memory)
- [ ] Streaming responses للإجابات الطويلة
- [ ] تقييم جودة الإجابة (Feedback Loop)
