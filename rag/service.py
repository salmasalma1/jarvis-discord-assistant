"""rag/service.py — RAG service for NELLY (owned by Maryam).

CROSS-LANGUAGE design:
  The corpus (NELLY docs / blueprint) is in ENGLISH; users ask in ARABIC.
  We embed with a MULTILINGUAL model (`gemini-embedding-2`, via
  integrations.llm.embed) so EN docs and AR queries land in the same space.
  Retrieval therefore needs NO translation. Generation (reply to the user) is
  done by Gemini in the user's language while the context stays English.

Dependencies: only stdlib + google-genai (via integrations.llm.embed).
Vector store is a lightweight, dependency-free index persisted to a JSON file
in data/ (small corpora -> pure-Python cosine is instant and reliable).

Interfaces:
  embed_doc(text) -> list[float]
  ingest(text, metadata) -> None
  query(question, scope_filter=None, top_k=5) -> list[dict]
  is_in_scope(question) -> bool
  ensure_ready(force=False) -> bool   # build the index from the repo corpus
"""
import os
import re
import io
import json
import asyncio
from typing import List, Optional

# Lazily import the embedding helper so this file imports even before Gemini.
try:
    from integrations.llm import embed as _embed
    _HAS_EMBED = True
except Exception:
    _HAS_EMBED = False

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INDEX_PATH = os.getenv("RAG_INDEX_PATH", os.path.join(_PROJECT_ROOT, "data", "rag_index.json"))
# Owner-taught facts appended here (survives rebuilds + is re-indexed every build).
_KNOWLEDGE_PATH = os.getenv("RAG_KNOWLEDGE_PATH", os.path.join(_PROJECT_ROOT, "data", "knowledge.md"))
# Uploaded project documents (Chapters 2-7, etc.) are saved here + indexed.
_KDOC_DIR = os.getenv("RAG_KDOC_DIR", os.path.join(_PROJECT_ROOT, "data", "knowledge"))
# Files the RAG indexes on first use. Only REAL project knowledge lives here —
# we deliberately EXCLUDE README.md / docs/*.md (they contained placeholder
# module-owner names like "Dorira"/"Maryam" that polluted answers).
_CORPUS_GLOBS = ["blueprint/*.yaml", "data/knowledge/*.md", "data/knowledge/*.txt",
                 "data/knowledge/*.org"]
# Chunking
_CHUNK_CHARS = 900
_CHUNK_OVERLAP = 120

_SCOPE_KEYWORDS = (
    "nelly", "robot", "autonomous", "windows", "computer', 'use", "computer use",
    "voice", "vision", "automation", "perception", "slam", "lidar", "camera",
    "navigation", "safety", "memory", "rag", "retrieval", "chatbot", "assistant",
    "الروبوت", "التحكم", "رؤية", "صوت", "أتمتة", "سلامة", "ذاكرة", "استرجاع",
    "المشروع", "كيلاندر", "تاسك", "مهمة",
)


# ---------------------------------------------------------------------------
# Vector store (pure-Python cosine; persisted to JSON)
# ---------------------------------------------------------------------------
class _VectorStore:
    def __init__(self, path: str = _INDEX_PATH):
        self.path = path
        self.chunks: List[dict] = []
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.chunks = data.get("chunks", [])
        except Exception:
            self.chunks = []

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"chunks": self.chunks}, fh, ensure_ascii=False)

    def add(self, text: str, vec: List[float], metadata: dict):
        self.chunks.append({"text": text, "vec": vec, **metadata})

    def search(self, qvec: List[float], top_k: int, scope_filter=None) -> List[dict]:
        def cos(a, b):
            return sum(x * y for x, y in zip(a, b))
        qa = sum(x * x for x in qvec) ** 0.5 or 1.0
        scored = []
        for c in self.chunks:
            if scope_filter and c.get("doc_name") and scope_filter and \
               not any(s.strip().lower() in (c.get("doc_name") or "").lower() for s in scope_filter):
                continue
            nb = sum(x * x for x in c["vec"]) ** 0.5 or 1.0
            score = cos(qvec, c["vec"]) / (qa * nb)
            scored.append({"text": c["text"], "score": round(score, 4),
                           "source": c.get("source", ""), "doc_name": c.get("doc_name", ""),
                           "page": c.get("page"),
                           "meeting_date": c.get("meeting_date"), "author": c.get("author")})
        scored.sort(key=lambda d: d["score"], reverse=True)
        return scored[:top_k]


_STORE = None


def _store() -> _VectorStore:
    global _STORE
    if _STORE is None:
        _STORE = _VectorStore()
    return _STORE


# ---------------------------------------------------------------------------
# Chunking + corpus loading
# ---------------------------------------------------------------------------
def _chunk(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + _CHUNK_CHARS])
        i += _CHUNK_CHARS - _CHUNK_OVERLAP
    return out


def _corpus_files() -> List[tuple]:
    import glob
    files = []
    for g in _CORPUS_GLOBS:
        for p in glob.glob(os.path.join(_PROJECT_ROOT, g)):
            if os.path.isfile(p):
                files.append((p, os.path.basename(p)))
    return files


def _load_corpus_text() -> List[dict]:
    """Return [{text, source, doc_name}] from the repo docs + owner knowledge."""
    items = []
    seen = set()
    for p, name in _corpus_files():
        try:
            with open(p, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except Exception:
            continue
        for chunk in _chunk(raw):
            if chunk in seen:
                continue
            seen.add(chunk)
            items.append({"text": chunk, "source": name, "doc_name": name})
    # Owner-taught facts (data/knowledge.md) — highest priority knowledge.
    if os.path.isfile(_KNOWLEDGE_PATH):
        try:
            with open(_KNOWLEDGE_PATH, "r", encoding="utf-8") as fh:
                raw = fh.read()
            for chunk in _chunk(raw):
                if chunk in seen:
                    continue
                seen.add(chunk)
                items.append({"text": chunk, "source": "knowledge.md",
                              "doc_name": "Project Knowledge"})
        except Exception:
            pass
    return items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _extract_pages(filename: str, raw: bytes) -> List[tuple]:
    """Return [(page:int|None, text:str)] so we keep page provenance.
    PDFs -> one entry per page (page number = 1-based). Others -> (None, text)."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            return [(i + 1, (p.extract_text() or "")) for i, p in enumerate(reader.pages)]
        except Exception:
            return []
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return [(None, raw.decode(enc))]
        except Exception:
            continue
    return []


def extract_file_text(filename: str, raw: bytes) -> str:
    """Turn an uploaded file (pdf/md/txt/org) into plain text for ingestion."""
    pages = _extract_pages(filename, raw)
    return "\n\n".join(t for _, t in pages)


def embed_doc(text: str) -> List[float]:
    """Embed one doc/query chunk -> vector (blocking; use via to_thread if in loop)."""
    if not _HAS_EMBED:
        return []
    res = asyncio.run(_embed([text]))
    return res[0] if res else []


async def ingest(text: str, metadata: Optional[dict] = None) -> None:
    """Index a chunk (docs, meeting summaries, refs). Async-safe."""
    md = dict(metadata or {})
    if not _HAS_EMBED:
        return
    vecs = await _embed([text])
    if not vecs:
        return
    st = _store()
    st.add(text, vecs[0], md)
    st.save()


async def query(question: str, scope_filter: Optional[List[str]] = None,
                top_k: int = 5) -> List[dict]:
    """Retrieve top_k relevant chunks (async-safe)."""
    if not _HAS_EMBED:
        return []
    st = _store()
    if not st.chunks:
        return []
    vecs = await _embed([question])
    if not vecs:
        return []
    return st.search(vecs[0], top_k, scope_filter)


def is_in_scope(question: str) -> bool:
    """Scope gate — refuse anything clearly outside NELLY's project scope."""
    q = (question or "").lower()
    if any(k.lower() in q for k in _SCOPE_KEYWORDS):
        return True
    return False


_BUILD_ATTEMPTED = False


async def ensure_ready(force: bool = False) -> bool:
    """Build the index from the repo corpus if it's empty (or forced).

    Only attempts the (expensive) corpus embedding ONCE per process — so when
    Gemini quota is low we don't re-attempt and waste requests on every question.
    """
    global _BUILD_ATTEMPTED
    st = _store()
    if st.chunks and not force:
        return True
    if _BUILD_ATTEMPTED and not force:
        return bool(st.chunks)
    _BUILD_ATTEMPTED = True
    if not _HAS_EMBED:
        return False
    items = _load_corpus_text()
    if not items:
        return False
    texts = [it["text"] for it in items]
    vecs = await _embed(texts)
    if not vecs:
        return False
    for it, vec in zip(items, vecs):
        st.add(it["text"], vec, {"source": it["source"], "doc_name": it["doc_name"]})
    st.save()
    return True


async def ingest_file(filename: str, raw: bytes) -> int:
    """Full ingest: save the uploaded doc, split into chunks (keeping PAGE number
    for provenance), embed + index. Returns number of chunks indexed."""
    safe = os.path.basename(filename or "doc.txt") or "doc.txt"
    pages = _extract_pages(filename, raw)
    if not pages:
        return 0
    # Persist a human-readable, page-marked copy for reference + re-indexing.
    os.makedirs(_KDOC_DIR, exist_ok=True)
    try:
        with open(os.path.join(_KDOC_DIR, safe), "w", encoding="utf-8") as fh:
            for p, t in pages:
                if p:
                    fh.write(f"\n===== PAGE {p} =====\n")
                fh.write(t or "")
    except Exception:
        pass
    # Chunk per page so each chunk remembers its page number.
    items = []  # (text, doc_name, page)
    for p, t in pages:
        if not t or not t.strip():
            continue
        for c in _chunk(t):
            items.append((c, safe, p))
    if not items:
        return 0
    if _HAS_EMBED:
        vecs = await _embed([it[0] for it in items])
        if vecs:
            st = _store()
            for (text, doc, page), vec in zip(items, vecs):
                st.add(text, vec, {"source": "knowledge-doc", "doc_name": doc, "page": page})
            st.save()
    return len(items)


async def remember(fact: str) -> None:
    """Teach JARVIS a fact: append to the knowledge file (persists) + index it."""
    fact = (fact or "").strip()
    if not fact:
        return
    os.makedirs(os.path.dirname(_KNOWLEDGE_PATH), exist_ok=True)
    try:
        with open(_KNOWLEDGE_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"- {fact}\n")
    except Exception:
        pass
    if _HAS_EMBED:
        vecs = await _embed([fact])
        if vecs:
            st = _store()
            st.add(fact, vecs[0], {"source": "knowledge.md", "doc_name": "Project Knowledge"})
            st.save()


def _display_name(doc_name: str, page=None) -> str:
    """How a chunk's source is shown to the user.
    The only reference we surface is 'the NELLY documentation' — we never
    name .yaml/blueprint files. For uploaded PDFs we DO keep the page number
    so citations stay useful, but still under the generic label."""
    base = "the NELLY documentation"
    if page:
        return f"{base}, p.{page}"
    return base


async def build_context(question: str, top_k: int = 4) -> str:
    """Retrieve + flatten to a prompt-ready context string (empty if none)."""
    await ensure_ready()
    hits = await query(question, top_k=top_k)
    if not hits:
        return ""
    lines = []
    for h in hits:
        loc = _display_name(h.get("doc_name", ""), h.get("page"))
        lines.append(f"[{loc}] {h['text'].strip()!r}")
    return "\n\n".join(lines)