import os
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

from google.cloud import firestore as fs
from google.oauth2 import service_account
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

ROOT = Path(__file__).parent.parent

DESIGN_FILES = ["d3-clientreq", "d3-solution"]
CODE_FILES   = ["eurocode1", "eurocode3"]


def classify(source: str) -> str:
    if source in DESIGN_FILES:
        return "design_chunks"
    if source in CODE_FILES:
        return "code_chunks"
    return "unclassified_chunks"


def migrate(db: fs.Client):
    print("\nReading all documents from 'chunks'...")
    old_docs = list(db.collection("chunks").stream())
    print(f"Found {len(old_docs)} documents.\n")

    counts   = {"design_chunks": 0, "code_chunks": 0, "unclassified_chunks": 0}
    batch    = db.batch()
    pending  = 0

    for doc in old_docs:
        data   = doc.to_dict()
        target = classify(data.get("source", ""))
        data["source_type"] = target.replace("_chunks", "")

        ref = db.collection(target).document(doc.id)
        batch.set(ref, data)
        counts[target] += 1
        pending        += 1

        if pending >= 400:
            batch.commit()
            batch   = db.batch()
            pending = 0
            print(f"  flushed batch — running totals: {counts}")

    if pending:
        batch.commit()

    print("\n── Migration complete ─────────────────────────────")
    print(f"  design_chunks:        {counts['design_chunks']}")
    print(f"  code_chunks:          {counts['code_chunks']}")
    print(f"  unclassified_chunks:  {counts['unclassified_chunks']}")

    if counts["unclassified_chunks"]:
        print(
            "\n  WARNING: some chunks didn't match any known filename.\n"
            "  Open Firestore → unclassified_chunks, read the 'source' field,\n"
            "  update DESIGN_FILES / CODE_FILES in this script, delete the\n"
            "  three new collections, then re-run."
        )


def main():
    print("═══════════════════════════════════════════════════")
    print("  CHUNK MIGRATION: chunks → design_chunks / code_chunks")
    print("═══════════════════════════════════════════════════")
    print(f"  DESIGN files: {', '.join(DESIGN_FILES)}")
    print(f"  CODE files:   {', '.join(CODE_FILES)}")
    print()

    answer = input("Migrate these files into design_chunks and code_chunks? (yes/no): ").strip().lower()
    if answer != "yes":
        print("Cancelled.")
        return

    gcp_creds = service_account.Credentials.from_service_account_file(ROOT / "firebase-key.json")
    db = fs.Client(project=os.getenv("FIREBASE_PROJECT_ID"), credentials=gcp_creds)

    migrate(db)

    print(
        "\nNext steps:\n"
        "  1. Open Firestore console and verify the three collections.\n"
        "  2. Run an end-to-end MCP test through Claude.\n"
        "  3. Once confirmed, delete the old 'chunks' collection manually."
    )


if __name__ == "__main__":
    main()
