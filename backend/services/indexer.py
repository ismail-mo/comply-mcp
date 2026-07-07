"""Deterministic document indexer — Stage 0 of the audit pipeline. No AI.

Parses an uploaded PROJECT PDF once and produces the document_index:
which structural elements it contains, which pages cover each element,
the section designation stated for each, and which codes it references.
Persisted as {file_id}_index.json next to the upload.
"""

import re

from pypdf import PdfReader

_DESIG = re.compile(
    r"(?:(UC|UB|UKC|UKB)\s*)?(\d{3})\s*[xX×]\s*(\d{2,3})\s*[xX×]\s*(\d{2,3})"
    r"(?:\s*(UC|UB|UKC|UKB))?"
)

_ELEMENT_KEYWORDS = {
    "column": ("column", "columns"),
    "beam": ("beam", "beams"),
}

_CODE_TOKENS = {
    "Eurocode 3": ("eurocode 3", "ec3", "en 1993", "1993-1-1"),
    "EN 1990": ("en 1990", "eurocode 0", "load combination"),
    "Eurocode 1": ("eurocode 1", "ec1", "en 1991"),
    "EN 10025-2": ("en 10025",),
}

MAX_PAGES_PER_ELEMENT = 6


def _family_from_context(explicit: str | None, page_text_lower: str) -> str:
    if explicit:
        return "UC" if explicit.upper() in ("UC", "UKC") else "UB"
    # Infer from context: which element family does this page talk about?
    if "column" in page_text_lower and "beam" not in page_text_lower:
        return "UC"
    if "ub" in page_text_lower or "beam" in page_text_lower:
        return "UB"
    return ""


def build_document_index(pdf_path: str) -> dict:
    reader = PdfReader(pdf_path)
    page_texts = []
    for page in reader.pages:
        try:
            page_texts.append(page.extract_text() or "")
        except Exception:
            page_texts.append("")

    element_pages: dict[str, list[tuple[int, float]]] = {k: [] for k in _ELEMENT_KEYWORDS}
    designations: dict[str, list[tuple[int, str]]] = {k: [] for k in _ELEMENT_KEYWORDS}
    codes: set[str] = set()

    for i, text in enumerate(page_texts, start=1):
        tl = text.lower()
        # calculation-density signals: units, equations, designations
        calc_score = (
            2.0 * len(re.findall(r"\bkN\b|\bkNm\b|N/mm", text))
            + 0.5 * text.count("=")
            + 5.0 * (1 if _DESIG.search(text) else 0)
        )
        for element, words in _ELEMENT_KEYWORDS.items():
            hits = sum(tl.count(w) for w in words)
            if hits:
                element_pages[element].append((i, hits + calc_score))
        for code, tokens in _CODE_TOKENS.items():
            if any(t in tl for t in tokens):
                codes.add(code)
        for m in _DESIG.finditer(text):
            family = _family_from_context(m.group(1) or m.group(5), tl)
            desig = f"{family} {m.group(2)}x{m.group(3)}x{m.group(4)}".strip()
            target = "column" if family == "UC" else "beam" if family == "UB" else None
            if target is None:
                # fall back to whichever element keyword owns the page
                for element, words in _ELEMENT_KEYWORDS.items():
                    if any(w in tl for w in words):
                        target = element
                        break
            if target:
                designations[target].append((i, desig))

    elements = []
    for element, scored in element_pages.items():
        if not scored:
            continue
        # Highest calculation-density pages win; the designation page always
        # makes the cut. Pages are then fed to extraction in document order.
        top = sorted(scored, key=lambda x: -x[1])[:MAX_PAGES_PER_ELEMENT]
        pages = {p for p, _ in top}
        for pn, _d in designations[element]:
            pages.add(pn)
        pages = sorted(pages)[:MAX_PAGES_PER_ELEMENT + 1]
        desig = designations[element][-1][1] if designations[element] else None
        elements.append({
            "type": element,
            "designation": desig,
            "pages": pages,
        })

    return {
        "page_count": len(page_texts),
        "elements": elements,
        "codes": sorted(codes),
    }


def read_pages(pdf_path: str, pages: list[int], max_chars: int = 15000) -> str:
    """Extract only the given 1-based pages — extraction latency scales with
    input size, so the AI is only ever fed the element's own pages."""
    reader = PdfReader(pdf_path)
    chunks = []
    for pn in pages:
        if 1 <= pn <= len(reader.pages):
            try:
                text = reader.pages[pn - 1].extract_text() or ""
            except Exception:
                text = ""
            chunks.append(f"[PAGE {pn}]\n{text.strip()}")
    combined = "\n\n".join(chunks)
    return combined[:max_chars]
