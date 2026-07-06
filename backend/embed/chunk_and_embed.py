import os
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")  # fixes gRPC DNS on macOS

import re
import time
import requests
from google.cloud import firestore as fs
from google.oauth2 import service_account
from google.cloud.firestore_v1.vector import Vector
from PyPDF2 import PdfReader
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

ROOT = Path(__file__).parent.parent
DOCS_FOLDER = ROOT / "docs"
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
EMBED_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={GOOGLE_API_KEY}"

gcp_creds = service_account.Credentials.from_service_account_file(ROOT / "firebase-key.json")
db = fs.Client(project=os.getenv("FIREBASE_PROJECT_ID"), credentials=gcp_creds)

# Explicit routing — must match the exact PDF stem (filename without extension).
# Check a Firestore document's 'source' field if unsure of the exact string.
DESIGN_FILES = ["d3-clientreq", "d3-solution"]
CODE_FILES   = ["eurocode1", "eurocode3"]

def collection_for(source_name: str) -> str:
    if source_name in DESIGN_FILES:
        return "design_chunks"
    if source_name in CODE_FILES:
        return "code_chunks"
    return "unclassified_chunks"


def read_pdf_with_pages(filepath: Path) -> list[dict]:
    """Return list of {page: int, text: str} — one entry per PDF page."""
    reader = PdfReader(filepath)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({"page": i, "text": text})
    return pages


CLAUSE_RE = re.compile(r'\b([1-9]\d?\.\d{1,2}(?:\.\d{1,2})*)\b')

def chunk_pages(pages: list[dict], source_name: str) -> list[dict]:
    """Sliding-window chunk across the full text, preserving page numbers and last-seen clause."""
    word_tokens = []  # (word, page, clause_at_this_word_or_None)
    last_clause = None
    for entry in pages:
        words = entry["text"].split()
        for w in words:
            m = CLAUSE_RE.match(w.rstrip('.:,)'))
            if m:
                last_clause = m.group(1)
            word_tokens.append((w, entry["page"], last_clause))

    chunks = []
    i = 0
    index = 0
    while i < len(word_tokens):
        slice_ = word_tokens[i : i + CHUNK_SIZE]
        words_only = [t[0] for t in slice_]
        page = slice_[0][1] if slice_ else None
        # use the last clause number seen within this chunk
        clause_number = next(
            (t[2] for t in reversed(slice_) if t[2] is not None), None
        )
        chunks.append({
            "chunk_id":     f"{source_name}-{index}",
            "source":       source_name,
            "text":         " ".join(words_only),
            "word_count":   len(words_only),
            "chunk_index":  index,
            "page":         page,
            "clause_number": clause_number,
        })
        i += CHUNK_SIZE - CHUNK_OVERLAP
        index += 1
    return chunks


def embed_chunks(chunks: list[dict]) -> list[dict]:
    for i, chunk in enumerate(chunks):
        for attempt in range(5):
            response = requests.post(EMBED_URL, json={
                "model": "models/gemini-embedding-001",
                "content": {"parts": [{"text": chunk["text"]}]},
                "taskType": "RETRIEVAL_DOCUMENT",
                "outputDimensionality": 1536,
            })
            if response.status_code in (429, 500, 503):
                wait = 2 ** attempt
                print(f"  HTTP {response.status_code} on chunk {i}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            chunk["embedding"] = Vector(response.json()["embedding"]["values"])
            break
        time.sleep(0.5)  # stay under free-tier RPM
        if "embedding" not in chunk:
            raise RuntimeError(f"Failed to embed chunk {chunk['chunk_id']} after 5 attempts")
    return chunks


def store_chunks(chunks: list[dict], collection: str):
    for i in range(0, len(chunks), 500):
        batch = db.batch()
        for chunk in chunks[i : i + 500]:
            ref = db.collection(collection).document(chunk["chunk_id"])
            batch.set(ref, chunk)
        batch.commit()
    print(f"  Stored {len(chunks)} chunks → {collection}")


def process_all_docs():
    pdfs = list(DOCS_FOLDER.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {DOCS_FOLDER}")
        return

    for pdf_path in pdfs:
        source_name = pdf_path.stem
        collection = collection_for(source_name)

        existing = db.collection(collection).where("source", "==", source_name).limit(1).get()
        if existing:
            print(f"\nSkipping {pdf_path.name} (already stored in {collection})")
            continue

        if collection == "unclassified_chunks":
            print(f"\nWARNING: {pdf_path.name} not in DESIGN_FILES or CODE_FILES — storing in unclassified_chunks")

        print(f"\nProcessing: {pdf_path.name}  →  {collection}")
        pages = read_pdf_with_pages(pdf_path)
        chunks = chunk_pages(pages, source_name)
        print(f"  {len(chunks)} chunks created (across {len(pages)} pages)")

        chunks = embed_chunks(chunks)
        store_chunks(chunks, collection)

    print("\nDone — all documents chunked and stored in Firebase")


if __name__ == "__main__":
    process_all_docs()
