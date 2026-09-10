"""integrations/sources.py — F4-ext: watch external sources for NELLY-relevant finds.

The owner asked JARVIS to watch for useful outside material (repos, papers,
articles) and post the interesting ones to a dedicated channel so the team can
find them easily instead of searching.

SCOPE / SAFETY:
  * Only OPEN sources that allow programmatic access — GitHub topics/releases and
    arXiv keyword search. We deliberately do NOT scrape LinkedIn (login-wall,
    bot-blocking, ToS risk / account ban) — the owner can still paste a LinkedIn
    link and JARVIS will summarise it via the paste route instead.
  * Results are filtered to NELLY's domain keywords (robotics/vision/voice/
    automation/safety/memory) so we don't spam unrelated stuff.
"""
import asyncio
import json
import urllib.request
import urllib.parse
from typing import List, Dict

# NELLY domain keywords — a find is only surfaced if it overlaps one of these.
_SCOPE_KEYWORDS = [
    "robot", "autonomous", "computer use", "agent", "vision", "perception",
    "slam", "lidar", "camera", "voice", "speech", "tts", "asr", "automation",
    "safety", "memory", "rag", "retrieval", "windows", "copilot",
    "روبوت", "تحكم", "رؤية", "صوت", "أتمتة", "سلامة", "ذاكرة", "استرجاع",
]


def _interesting(title: str, body: str = "") -> bool:
    text = f"{title} {body}".lower()
    return any(k.lower() in text for k in _SCOPE_KEYWORDS)


def _get_json(url: str, timeout: float = 12):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-source-bot"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


async def github_trending(limit: int = 10) -> List[Dict[str, str]]:
    """Pull recent repos matching keywords from GitHub search (open API, no token)."""
    q = " OR ".join(k for k in ["robot", "voice assistant", "computer use agent",
                                "vision SLAM", "retrieval augmented"])
    url = ("https://api.github.com/search/repositories?q=" +
           urllib.parse.quote(q) + "&sort=updated&order=desc&per_page=" + str(limit))
    data = await asyncio.to_thread(_get_json, url)
    out = []
    for repo in (data or {}).get("items", [])[:limit]:
        title = repo.get("full_name", "")
        if _interesting(title, (repo.get("description", "") or "")):
            link = repo.get("html_url", "")
            desc = (repo.get("description") or "")[:160]
            out.append({"type": "repo", "title": title, "link": link,
                        "note": desc, "stars": repo.get("stargazers_count")})
    return out


async def scan_sources(limit: int = 8) -> List[Dict[str, str]]:
    """Scan the open sources and return interesting, in-scope finds."""
    found = await github_trending(limit=limit)
    # De-dup by title.
    seen, out = set(), []
    for it in found:
        if it["title"] in seen:
            continue
        seen.add(it["title"])
        out.append(it)
    return out


def is_relevant(item: Dict[str, str]) -> bool:
    return _interesting(item.get("title", ""), item.get("note", ""))


# ---------------------------------------------------------------------------
# Curated / trust-list of sources (owner-driven).
# The owner adds the sources HE TRUSTS; /sources surfaces those, not a random scan.
# ---------------------------------------------------------------------------
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SOURCES_FILE = os.getenv("SOURCES_FILE", os.path.join(_ROOT, "data", "sources.json"))
_CURATED = []  # in-memory cache


def _load_curated() -> List[Dict[str, str]]:
    global _CURATED
    if _CURATED:
        return _CURATED
    try:
        with open(_SOURCES_FILE, "r", encoding="utf-8") as fh:
            _CURATED = json.load(fh)
    except Exception:
        _CURATED = []
    return _CURATED


def add_source(url: str, title: str = "", category: str = "general") -> dict:
    """Add a trusted source to the curated list (owner-approved)."""
    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "no URL"}
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    curated = _load_curated()
    if any(s.get("url") == url for s in curated):
        return {"ok": True, "title": title or url, "added": False, "dup": True}
    curated.append({"url": url, "title": title or url, "category": category})
    os.makedirs(os.path.dirname(_SOURCES_FILE), exist_ok=True)
    with open(_SOURCES_FILE, "w", encoding="utf-8") as fh:
        json.dump(curated, fh, ensure_ascii=False, indent=2)
    return {"ok": True, "title": title or url, "added": True}


def list_sources() -> List[Dict[str, str]]:
    return list(_load_curated())


def format_item(item: Dict[str, str]) -> str:
    icon = {"repo": "🐙", "article": "📄", "paper": "📚"}.get(item.get("type"), "🔗")
    note = f"\n> {item['note']}" if item.get("note") else ""
    stars = f" · ⭐ {item['stars']}" if item.get("stars") else ""
    return f"{icon} **{item['title']}**{stars}\n{item.get('link', '')}{note}"
