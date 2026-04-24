"""
Local RAG engine for LEGAL_E_LEARNING.

Vector store: ChromaDB, persisted under ./chroma_db
Embeddings: Chroma's default MiniLM embedding function
LLM: Groq by default, or Ollama when LLM_PROVIDER=ollama
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.environ["HOME"] = str(BASE_DIR)
os.environ.setdefault("XDG_CACHE_HOME", str(BASE_DIR / ".cache"))

import chromadb
from chromadb.utils import embedding_functions

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

CHROMA_DIR = Path(os.environ.get("CHROMA_DIR", BASE_DIR / "chroma_db"))
KB_DIR = Path(os.environ.get("KB_DIR", BASE_DIR / "knowledge_base"))

_chroma_client = None
_embedding_fn = None

LEGAL_CATEGORIES = [
    "family-law",
    "property-disputes",
    "employment",
    "consumer-rights",
    "criminal-law",
    "business-law",
    "civil-rights",
    "others",
]

CATEGORY_LABELS = {
    "family-law": "Family Law",
    "property-disputes": "Property Disputes",
    "employment": "Employment Issues",
    "consumer-rights": "Consumer Rights",
    "criminal-law": "Criminal Law",
    "business-law": "Business Law",
    "civil-rights": "Civil Rights",
    "others": "General Legal",
}


def _get_embedding_fn():
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = embedding_functions.DefaultEmbeddingFunction()
    return _embedding_fn


def _get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _chroma_client


def _collection_name(category: str) -> str:
    return f"legal-{category}"


def _get_or_create_collection(category: str):
    client = _get_chroma_client()
    return client.get_or_create_collection(
        name=_collection_name(category),
        embedding_function=_get_embedding_fn(),
        metadata={"hnsw:space": "cosine"},
    )


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        start += chunk_size - overlap
    return chunks


def ingest_knowledge_base(force: bool = False) -> None:
    for category in LEGAL_CATEGORIES:
        cat_dir = KB_DIR / category
        if not cat_dir.is_dir():
            continue

        collection = _get_or_create_collection(category)
        if not force and collection.count() > 0:
            continue

        docs, ids, metas = [], [], []
        files = []
        for pattern in ("*.txt", "*.md", "*.json"):
            files.extend(glob.glob(str(cat_dir / pattern)))

        for file_path in files:
            try:
                path = Path(file_path)
                raw = path.read_text(encoding="utf-8")

                if path.suffix == ".json":
                    try:
                        obj = json.loads(raw)
                        raw = obj.get("content", json.dumps(obj))
                    except json.JSONDecodeError:
                        pass

                for index, chunk in enumerate(_chunk_text(raw)):
                    doc_id = f"{category}::{path.name}::{index}"
                    docs.append(chunk)
                    ids.append(doc_id)
                    metas.append(
                        {"source": path.name, "category": category, "chunk": index}
                    )
            except OSError as exc:
                print(f"[RAG] Error reading {file_path}: {exc}")

        if docs:
            batch_size = 100
            for index in range(0, len(docs), batch_size):
                collection.upsert(
                    documents=docs[index : index + batch_size],
                    ids=ids[index : index + batch_size],
                    metadatas=metas[index : index + batch_size],
                )
            print(f"[RAG] Ingested {len(docs)} chunks into '{category}'")


def retrieve_context(category: str, query: str, n_results: int = 5) -> str:
    if category not in LEGAL_CATEGORIES:
        category = "others"

    collection = _get_or_create_collection(category)
    count = collection.count()
    if count == 0:
        ingest_knowledge_base(force=False)
        count = collection.count()
        if count == 0:
            return ""

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, count),
    )
    docs = results.get("documents", [[]])[0]
    return "\n\n---\n\n".join(docs)


def _call_groq(system_prompt: str, user_message: str) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured")

    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        model=GROQ_MODEL,
        temperature=0.3,
        max_tokens=1024,
    )
    return chat_completion.choices[0].message.content.strip()


def _call_ollama(system_prompt: str, user_message: str) -> str:
    import requests

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {"temperature": 0.3},
    }
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["message"]["content"].strip()


def _fallback_response(label: str, context: str) -> str:
    if not context:
        return (
            f"I found the {label} category, but there is no local reference "
            "material loaded for this exact question. Please consult a qualified "
            "lawyer for serious legal matters."
        )

    summary = context.split("\n\n---\n\n", 1)[0].strip()
    return (
        f"I could not reach the configured LLM provider, so here is the most "
        f"relevant local reference material for {label}:\n\n{summary}\n\n"
        "For serious legal matters, consult a qualified lawyer."
    )


def get_rag_response(category: str, user_query: str) -> str:
    if category not in LEGAL_CATEGORIES:
        category = "others"

    label = CATEGORY_LABELS.get(category, "General Legal")
    context = retrieve_context(category, user_query)

    if context:
        system_prompt = f"""You are a helpful legal assistant specialising in {label}.
Use the following reference material to answer the user's question accurately and clearly.
If the answer is not fully covered by the material, say so and provide general guidance.
Always recommend consulting a qualified lawyer for serious legal matters.

Reference material:
{context}
"""
    else:
        system_prompt = f"""You are a helpful legal assistant specialising in {label}.
No specific knowledge-base documents are loaded for this category yet, so rely on your
general legal knowledge. Always recommend consulting a qualified lawyer for serious matters.
"""

    try:
        if LLM_PROVIDER == "ollama":
            return _call_ollama(system_prompt, user_query)
        return _call_groq(system_prompt, user_query)
    except Exception as exc:
        print(f"[RAG] LLM provider error: {exc}")
        return _fallback_response(label, context)


if __name__ == "__main__":
    print("[RAG] Starting knowledge-base ingestion...")
    ingest_knowledge_base(force=True)
    print("[RAG] Done.")
