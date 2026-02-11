# 🚀 Quick Start Guide - Legal Aid Chatbot

## 5-Minute Setup

### 1️⃣ Prerequisites
- Python 3.9 or higher
- pip (Python package manager)
- Git (optional)

### 2️⃣ Clone/Navigate to Project
```bash
cd legal-aid-chatbot
```

### 3️⃣ Create Virtual Environment
```bash
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate
```

### 4️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

### 5️⃣ Configure API Keys
Create `.env` file in project root:
```env
PINECONE_API_KEY=your_key_here
PINECONE_ENV=gcp-starter
GROQ_API_KEY=your_key_here
```

**Get API Keys:**
- Pinecone: https://app.pinecone.io (Free tier available)
- Groq: https://console.groq.com (Free tier available)

### 6️⃣ Run the App
```bash
streamlit run app.py
```

Open browser to `http://localhost:8501`

---

## 🧪 Test the System

### Run all tests:
```bash
python test_modules.py
```

### Test law filter specifically:
```bash
python law_filter.py
```

### Expected Output:
- ✅ Law questions ACCEPTED
- ✅ Non-legal questions REJECTED
- ✅ All modules loaded correctly

---

## 📝 Example Workflow

### 1. Upload Legal Documents
- Click "Document Management" in sidebar
- Upload PDF files (e.g., Constitution, IPC)
- Click "Process & Index Documents"
- Wait for "✓ Documents Indexed"

### 2. Ask Legal Questions
Try these questions:
```
✅ "What are my fundamental rights?"
✅ "What is Article 14 of the Constitution?"
✅ "Can I file for divorce in India?"
✅ "What is Section 420 of IPC?"
```

### 3. Observe Rejection of Non-Legal Queries
Try these:
```
❌ "Who won the cricket match?"
❌ "Tell me a joke"
❌ "What's the weather?"
❌ "How to cook biryani?"
```

All will receive:
```
"I am designed to provide legal information only. 
Please ask questions related to law or legal awareness."
```

---

## 🔑 API Keys Explained

### Pinecone
- Cloud vector database for storing embeddings
- Free tier: 1M vectors included
- Sign up: https://app.pinecone.io

### Groq
- LLaMA 2 LLM service
- Fast inference (2-5 sec per query)
- Free tier: 1000 requests/day included
- Sign up: https://console.groq.com

---

## 📂 File Structure Quick Reference

```
legal-aid-chatbot/
├── app.py           ← Run this file!
├── law_filter.py    ← Query validation (law-only gatekeeper)
├── config.py        ← Configuration & API keys
├── requirements.txt ← Dependencies
├── test_modules.py  ← Run tests
├── .env.example     ← Copy and rename to .env
└── README.md        ← Full documentation
```

---

## ⚠️ Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| "API key not found" | Check .env file, restart app |
| "ModuleNotFoundError" | Run `pip install -r requirements.txt` |
| "Connection to Pinecone failed" | Check internet, verify API key |
| "No documents indexed" | Upload and process PDFs first |
| "Slow responses" | Check internet speed, Groq free tier limits |

---

## 🎓 For Viva Preparation

**Key Points to Memorize:**

1. **Law Filter (Most Important)**
   - Validates every query before LLM
   - 100+ legal keywords
   - Rejects non-legal queries with fixed message
   - Function: `is_legal_query(query) → (bool, reason)`

2. **RAG Architecture**
   - Retrieves legal documents
   - Augments with user query
   - Generates response via LLM
   - Appends disclaimer

3. **Hybrid Search**
   - Dense: Semantic similarity (Sentence Transformers)
   - Sparse: Keyword matching (BM25)
   - Combined: 70% dense + 30% sparse

4. **Tech Stack**
   - Frontend: Streamlit
   - Embeddings: Sentence Transformers + BM25
   - Vector DB: Pinecone
   - LLM: LLaMA via Groq

---

## 📊 Performance Expectations

- **Query Validation:** <10ms
- **Embedding Generation:** <50ms
- **Vector Search:** 100-500ms
- **LLM Response:** 2-5 seconds
- **Total Response Time:** 5-10 seconds

---

## 🔐 Security Best Practices

1. **Never commit .env file**
   ```bash
   # Add to .gitignore
   .env
   ```

2. **Rotate API keys regularly** (monthly)

3. **Use environment variables** in production

4. **Validate all inputs** (done automatically)

5. **Log all queries** (for audit trail)

---

## 📞 Support & Debugging

### Enable Verbose Logging
```python
# In any module, modify logging:
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Logs
- Streamlit logs: Terminal output
- App errors: Sidebar shows warnings
- API errors: Terminal output

### Debug Specific Module
```bash
# Test law filter
python -c "from law_filter import test_law_filter; test_law_filter()"

# Test embeddings
python -c "from embeddings import DenseEmbeddings; print('OK')"
```

---

## 🎉 Success Indicators

After setup, you should see:
- ✅ Streamlit app running on localhost:8501
- ✅ No error messages in terminal
- ✅ Able to upload PDFs
- ✅ Law filter test passes
- ✅ Legal questions answered
- ✅ Non-legal questions rejected

---

## 📚 Next Steps

1. Upload sample legal documents (Constitution, IPC, etc.)
2. Test with various law-related questions
3. Test rejection of non-legal queries
4. Review code comments for understanding
5. Prepare for viva with key concepts

---

**⚖️ Remember:** The chatbot is ONLY for legal awareness. Always consult qualified lawyers for specific legal matters!
