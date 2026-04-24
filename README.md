# LEGAL_E_LEARNING

A Flask legal assistant with user accounts, chat history, and local RAG retrieval over category-wise legal knowledge files.

## Features

- Login, signup, OTP email flow, profile, and chat history
- Legal chat categories such as family law, employment, consumer rights, criminal law, and more
- Local ChromaDB vector search over `knowledge_base/`
- Groq-backed LLM responses when `GROQ_API_KEY` is valid
- Local RAG fallback when the LLM provider is unavailable

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp data.env.example data.env
python init_db.py
python rag_engine.py
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Environment

Create `data.env` from `data.env.example` and fill in your values:

```env
EMAIL_ADDRESS=""
EMAIL_PASSWORD=""
GROQ_API_KEY=""
LLM_PROVIDER="groq"
SECRET_KEY="change-this-to-a-random-secret-key"
```

`data.env` is ignored by Git so secrets are not pushed.

## RAG Data

The source documents live in `knowledge_base/<category>/overview.txt`.

The generated vector index lives in `chroma_db/` and is ignored by Git. If `chroma_db/` is missing, the app can rebuild it from `knowledge_base/`, or you can run:

```bash
python rag_engine.py
```

## Notes

- A `401 Invalid API Key` response from Groq means the key in `data.env` is invalid or revoked.
- Without a valid Groq key, the chatbot still returns the most relevant local reference material.
