"""integrations/voice.py — F4: meeting-audio summarisation for JARVIS.

Pulls the transcription idea from the team's notebook (faster-whisper) and makes
it bot-friendly:

  * transcribe_file(path)  -> raw text (faster-whisper; LOCAL, no Gemini/quota)
  * summarize_audio(path)  -> dict {summary, decisions, tasks, deadlines} using
                              Gemini (skips cleanly to a transcript-only reply if
                              Gemini is unavailable / out of quota).

faster-whisper is installed on demand (see requirements.txt). If it is not
present, functions degrade gracefully instead of crashing the bot.
"""
import asyncio
import logging
import os
import time
from pathlib import Path
from typing import List, Optional

from config import WHISPER_MODEL

logger = logging.getLogger("jarvis.voice")

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".mpeg"}

# Cached model so we load faster-whisper only once per process.
_MODEL = None
_MODEL_TRIED = False


def _get_model():
    """Load the faster-whisper model once. Returns None if the lib/model is absent."""
    global _MODEL, _MODEL_TRIED
    if _MODEL is not None or _MODEL_TRIED:
        return _MODEL
    _MODEL_TRIED = True
    try:
        from faster_whisper import WhisperModel
        _MODEL = WhisperModel(WHISPER_MODEL or "small", device="cpu", compute_type="int8")
        logger.info("faster-whisper model '%s' loaded.", WHISPER_MODEL)
    except Exception as exc:  # library missing / no network / bad combo
        logger.warning("faster-whisper model unavailable: %s", exc)
        _MODEL = None
    return _MODEL


def transcribe_file(path: str) -> str:
    """Transcribe one audio file to text (faster-whisper, local). Returns '' on any failure."""
    p = Path(path)
    if not p.exists() or p.suffix.lower() not in SUPPORTED_EXTENSIONS:
        logger.error("invalid audio path/type: %s", path)
        return ""
    model = _get_model()
    if model is None:
        return ""
    try:
        segments, info = model.transcribe(str(p), beam_size=5, vad_filter=True)
        texts = []
        for seg in segments:
            texts.append(seg.text.strip())
        full = " ".join(text.strip() for text in texts if text).strip()
        logger.info("[voice] transcribed %s (%s chars)", p.name, len(full))
        return full
    except Exception as exc:
        logger.error("[voice] transcription failed: %s", exc)
        return ""


async def _summarize_with_llm(text: str) -> Optional[dict]:
    """Produce a structured meeting summary via Gemini (returns None if unavailable).

    Mirror the team's Notebook 2 extraction schema:
      {title, summary, decisions[],
       tasks[{task, assignee, deadline}]}
    """
    from integrations.llm import generate_json, _USE_API
    if not _USE_API:
        return None
    prompt = (
        "You are a precise meeting-notes extraction engine. Extract structured "
        "information from a meeting transcript. Return ONLY a single valid JSON "
        "object with EXACTLY these keys:\n"
        "{\n"
        '  "title": "<short descriptive meeting title>",\n'
        '  "summary": "<concise executive summary, 3-6 sentences>",\n'
        '  "decisions": ["<decision 1>", "<decision 2>"],\n'
        '  "tasks": [{"task": "<desc>", "assignee": "<person or Unassigned>", '
        '"deadline": "<due date or Not specified>"}]\n'
        "}\n"
        "Rules: empty list if none; NEVER invent facts not present or reasonably "
        "implied; output must be valid parseable JSON and nothing else.\n\n"
        f"TRANSCRIPT:\n{text}"
    )
    try:
        data = await generate_json(prompt)
        if data:
            # Normalize to a consistent shape used by the bot.
            return {
                "summary": data.get("summary", ""),
                "decisions": [str(d) for d in data.get("decisions", [])],
                "tasks": data.get("tasks", []),
            }
    except Exception as exc:
        logger.warning("[voice] summarize_llm failed: %s", exc)
    return None


def _fallback_summary(text: str) -> dict:
    """If Gemini is out of quota, still give a useful (raw transcript) reply."""
    return {
        "summary": text,
        "decisions": [],
        "tasks": [],
    }


async def _ingest_meeting(data: dict) -> None:
    """Auto-index a meeting summary into the RAG store so `/ask` can later recall
    what was decided/discussed. Uses the existing lightweight index (Gemini
    embeddings, cross-language) — NOT ChromaDB/all-MiniLM (English-only + heavy)."""
    try:
        from rag import service as rag
        if not data.get("summary"):
            return
        lines = [f"Meeting: {data.get('source', '')}",
                 f"Summary: {data['summary']}"]
        if data.get("decisions"):
            lines.append("Decisions:")
            lines += [f"- {d}" for d in data["decisions"]]
        if data.get("tasks"):
            lines.append("Action Items:")
            for t in data["tasks"]:
                if isinstance(t, dict):
                    lines.append(f"- {t.get('task')} (Assignee: {t.get('assignee', 'Unassigned')}, "
                                 f"Deadline: {t.get('deadline', 'Not specified')})")
                else:
                    lines.append(f"- {t}")
        await rag.ingest("\n".join(lines), {
            "source": "meeting-summary",
            "doc_name": data.get("source", "Meeting Summary"),
        })
        logger.info("[voice] indexed meeting summary into RAG.")
    except Exception as exc:
        logger.warning("[voice] ingest into RAG failed: %s", exc)


async def summarize_audio(path: str) -> dict:
    """Full F4 pipeline: transcribe (local) + summarize (Gemini, best-effort).

    Returns a dict: {transcript, summary, decisions, tasks, deadlines, source}
    """
    start = time.time()
    transcript = await asyncio.to_thread(transcribe_file, path)
    elapsed = time.time() - start
    if not transcript:
        return {"transcript": "", "summary": "",
                "error": "No transcript. Unsupported/corrupt audio, or faster-whisper not installed "
                         "(pip install faster-whisper)."}
    data = await _summarize_with_llm(transcript)
    if data is None:
        data = _fallback_summary(transcript)
    data["transcript"] = transcript
    data["source"] = Path(path).name
    data["secs"] = round(elapsed, 1)
    # Auto-index the meeting summary into RAG for later `/ask` recall.
    await _ingest_meeting(data)
    return data


def _fmt_summary(data: dict) -> str:
    """Human-readable Discord message from a summary dict.

    Tasks are rendered as `task — @assignee · due deadline` (mirrors Notebook 2)."""
    lines = []
    if data.get("error"):
        return f" {data['error']}"
    if data.get("source"):
        lines.append(f"🎙 **{data['source']}**")
    if data.get("summary"):
        lines.append(f" **Summary**\n{data['summary'][:1500]}")
    if data.get("decisions"):
        lines.append("\n **Decisions**")
        for d in data["decisions"][:8]:
            lines.append(f"  • {d}")
    if data.get("tasks"):
        lines.append("\n🗂 **Tasks**")
        for t in data["tasks"][:8]:
            if isinstance(t, dict):
                task = t.get("task", "")
                who = t.get("assignee") or "Unassigned"
                when = t.get("deadline") or "Not specified"
                piece = f"  • {task} — 👤 {who}"
                if when and str(when).lower() not in ("not specified", "none", ""):
                    piece += f" · 📅 {when}"
                lines.append(piece)
            else:
                lines.append(f"  • {t}")
    return "\n".join(lines)