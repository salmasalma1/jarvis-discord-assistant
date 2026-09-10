"""integrations/llm.py — Gemini client (generation + tool calling).

Used by: agent graph replies, conventional commit descriptions, meeting
summarization, intent classification, and scope checking.
Extend freely — the core interfaces are ready and tested.
"""
import asyncio
import json
import os
import sys as _sys
from typing import List, Optional

from config import GEMINI_KEY

_USE_API = bool(GEMINI_KEY)

# Allow import even if the SDK is not installed yet.
try:
    from google import genai
    from google.genai import types as gtypes
    _HAS_SDK = True
except Exception:
    _HAS_SDK = False


_DEFAULT_MODEL = "gemini-3.5-flash"

# Ordered fallback models if the primary is temporarily unavailable.
_FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-flash-latest"]

# Multilingual embedding models available to this key (try in order).
_EMBED_MODELS = ["gemini-embedding-2", "gemini-embedding-001", "text-embedding-004"]


def _client():
    global _CLIENT
    if not _HAS_SDK:
        raise RuntimeError("google-genai is not installed. Run: pip install google-genai")
    if _CLIENT is None:
        _CLIENT = genai.Client(api_key=GEMINI_KEY)
    return _CLIENT


_CLIENT = None


async def generate(prompt: str, system: Optional[str] = None,
                   model: str = _DEFAULT_MODEL, temperature: float = 0.3) -> str:
    """Single-shot text generation with automatic fallback models.

    IMPORTANT: the Google-genai SDK call is synchronous (blocking). We run it
    in a worker thread via asyncio.to_thread so it NEVER freezes the Discord
    event loop — otherwise the bot receives a message but can't reply until
    Gemini returns (which looks like "it doesn't reply").
    """
    if not _USE_API or not _HAS_SDK:
        return f"[local engine] (no Gemini API) prompt={prompt[:120]}"
    full = (system + "\n\n" if system else "") + prompt
    for m in [model] + list(_FALLBACK_MODELS):
        try:
            resp = await asyncio.to_thread(
                lambda: _client().models.generate_content(model=m, contents=full))
            return getattr(resp, "text", "") or ""
        except Exception as e:
            if "503" in str(e) or "unavailable" in str(e).lower():
                continue
            # Quota/rate limit (429 / RESOURCE_EXHAUSTED) — caller can fall back
            # to returning the retrieved context without the LLM.
            if "429" in str(e) or "quota" in str(e).lower() or "resource_exhausted" in str(e).lower():
                return "[NO_LLM] Gemini quota exhausted — see docs/rate-limits."
            return f"[Gemini error] {e}"
    return "[Gemini error] all models busy (503) — try again shortly."


async def generate_json(prompt: str, model: str = _DEFAULT_MODEL) -> Optional[dict]:
    """Structured JSON output (used for meeting summaries / descriptions)."""
    if not _USE_API or not _HAS_SDK:
        return None
    try:
        client = _client()
        resp = await asyncio.to_thread(
            lambda: client.models.generate_content(
                model=model, contents=prompt,
                config=gtypes.GenerateContentConfig(
                    response_mime_type="application/json")))
        txt = getattr(resp, "text", "")
        return json.loads(txt) if txt else None
    except Exception:
        return None


async def tool_loop(messages, tools, model=_DEFAULT_MODEL):
    """Basic tool-calling loop. Returns the final response text."""
    if not _USE_API or not _HAS_SDK:
        return None
    try:
        client = _client()
        config = gtypes.GenerateContentConfig(tools=tools)
        resp = await asyncio.to_thread(
            lambda: client.models.generate_content(
                model=model, contents=messages, config=config))
        return getattr(resp, "text", "") or ""
    except Exception:
        return None


async def embed(texts: List[str]) -> Optional[List[List[float]]]:
    """Multilingual embeddings — maps both EN docs and AR queries to one space.
    This is the key to cross-language RAG (EN corpus + AR questions).
    Tries several valid embedding models (falls back if one is unavailable);
    logs the real error so we can debug quota/endpoint issues instead of hiding it."""
    if not _USE_API or not _HAS_SDK:
        return None
    for m in _EMBED_MODELS:
        try:
            client = _client()
            res = await asyncio.to_thread(
                lambda: client.models.embed_content(model=m, contents=texts))
            return [r.values for r in res.embeddings]
        except Exception as e:
            print(f"[embed] model={m} error: {e}", file=_sys.stderr)
            # 404/not found -> try next model; quota/rate -> stop, tell the user.
            if "quota" in str(e).lower() or "rate" in str(e).lower() or "429" in str(e):
                print("[embed] quota exhausted — not retrying other models.")
                return None
            continue
    return None


# ---------- Semantic helpers for F1 / F6 ----------
JARVIS_RULES = (
    "You are JARVIS, a friendly, concise team assistant. Answer directly, in a "
    "short, natural way — do NOT start every reply by announcing your name, "
    "your project, or that you are an assistant. Do NOT use filler like "
    "\\\"As the team assistant\\\" or \\\"Since we are working on...\\\"; just answer "
    "the question. Be helpful and stay within reason. If you do not know, say "
    "so honestly — never invent facts. Reply in the same language the user "
    "writes in (Arabic if Arabic)."
)


async def summarize_meeting(transcript: str) -> dict:
    """Meeting summary -> JSON {decisions, tasks, responsibilities, deadlines, summary}."""
    prompt = (
        "Summarize the following meeting into JSON with keys: "
        '{"decisions":[], "tasks":[], "responsibilities":[], "deadlines":[], "summary":""}. '
        "Write the JSON values in English (the summary may be rendered to the user in any language).\n"
        f"TEXT:\n{transcript}"
    )
    data = await generate_json(prompt)
    return data or {"summary": transcript[:200]}


async def review_against_architecture(diff: str) -> str:
    """Code review vs NELLY's 7-layer architecture (F6), not generic standards."""
    prompt = (
        "Review this diff against NELLY's 7-layer architecture. Call out only "
        "interface violations and wrong-layer ownership. Do NOT apply generic "
        "best-practice advice.\n" + diff[:3000]
    )
    return await generate(prompt)


async def translate_query(question: str, target="en") -> Optional[str]:
    """Optional cross-language helper: translate an Arabic query to English
    before retrieval (used when embeddings are not multilingual)."""
    if not _USE_API:
        return question
    return await generate(f"Translate to {target}. Output only the translation:\n{question}")