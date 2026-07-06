import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pypdf
import requests
from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector
from google.oauth2 import service_account


BACKEND_DIR = Path(__file__).resolve().parents[1]
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50
PROJECT_COLLECTION = "project_chunks"
EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-embedding-001:embedContent"
)

_db: firestore.Client | None = None


def get_db() -> firestore.Client:
    global _db
    if _db is None:
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if credentials_path:
            credentials = service_account.Credentials.from_service_account_file(credentials_path)
        else:
            credentials = service_account.Credentials.from_service_account_file(
                BACKEND_DIR / "firebase-key.json"
            )
        _db = firestore.Client(
            project=os.getenv("FIREBASE_PROJECT_ID"),
            credentials=credentials,
        )
    return _db


def read_pdf_with_pages(filepath: Path) -> list[dict]:
    reader = pypdf.PdfReader(str(filepath))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({"page": index, "text": text.strip()})
    return pages


CLAUSE_RE = re.compile(r"\b([1-9]\d?\.\d{1,2}(?:\.\d{1,2})*)\b")


def chunk_pages(pages: list[dict], file_id: str, filename: str) -> list[dict]:
    word_tokens = []
    last_clause = None
    for entry in pages:
        for word in entry["text"].split():
            match = CLAUSE_RE.match(word.rstrip(".:,)"))
            if match:
                last_clause = match.group(1)
            word_tokens.append((word, entry["page"], last_clause))

    chunks = []
    index = 0
    cursor = 0
    while cursor < len(word_tokens):
        window = word_tokens[cursor : cursor + CHUNK_SIZE]
        words = [token[0] for token in window]
        page = window[0][1] if window else None
        clause_number = next(
            (token[2] for token in reversed(window) if token[2] is not None),
            None,
        )
        chunks.append(
            {
                "chunk_id": f"{file_id}-{index}",
                "file_id": file_id,
                "filename": filename,
                "source": filename,
                "classification": "PROJECT",
                "text": " ".join(words),
                "word_count": len(words),
                "chunk_index": index,
                "page": page,
                "clause_number": clause_number,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        cursor += CHUNK_SIZE - CHUNK_OVERLAP
        index += 1
    return chunks


def embed_text(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> Vector:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured")

    for attempt in range(5):
        response = requests.post(
            f"{EMBED_URL}?key={api_key}",
            json={
                "model": "models/gemini-embedding-001",
                "content": {"parts": [{"text": text}]},
                "taskType": task_type,
                "outputDimensionality": 1536,
            },
            timeout=30,
        )
        if response.status_code in (429, 500, 503) and attempt < 4:
            time.sleep(2**attempt)
            continue
        response.raise_for_status()
        return Vector(response.json()["embedding"]["values"])

    raise RuntimeError("Failed to embed text after retries")


def delete_project_chunks(file_id: str) -> None:
    db = get_db()
    existing = db.collection(PROJECT_COLLECTION).where("file_id", "==", file_id).stream()
    batch = db.batch()
    count = 0
    for doc in existing:
        batch.delete(doc.reference)
        count += 1
        if count % 450 == 0:
            batch.commit()
            batch = db.batch()
    if count % 450:
        batch.commit()


def store_chunks(chunks: list[dict]) -> None:
    db = get_db()
    for offset in range(0, len(chunks), 450):
        batch = db.batch()
        for chunk in chunks[offset : offset + 450]:
            ref = db.collection(PROJECT_COLLECTION).document(chunk["chunk_id"])
            batch.set(ref, chunk)
        batch.commit()


def embed_project_file(file_id: str, filename: str, path: str | Path) -> dict:
    filepath = Path(path)
    pages = read_pdf_with_pages(filepath)
    chunks = chunk_pages(pages, file_id, filename)
    if not chunks:
        return {"chunks": 0, "pages": len(pages), "collection": PROJECT_COLLECTION}

    for chunk in chunks:
        chunk["embedding"] = embed_text(chunk["text"])
        time.sleep(0.25)

    delete_project_chunks(file_id)
    store_chunks(chunks)
    return {"chunks": len(chunks), "pages": len(pages), "collection": PROJECT_COLLECTION}
