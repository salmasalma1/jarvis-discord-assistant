"""agent/smart.py — Smart intent detection + multi-task parsing for JARVIS.

JARVIS should understand NATURAL language, not treat every message as a task
request. This module:

  * classify(text) -> 'greeting' | 'introduce' | 'add_tasks' | 'question' | 'other'
  * parse_tasks(text) -> list[ {title, label, list_name, due} ]
      so one message can create MANY cards + deadlines.

The classifier first tries deterministic keyword rules (fast, offline), then
optionally refines with Gemini (LLM) for anything it can't confidently label.
"""
import re
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Intent classification (offline heuristics — Arabic + English)
# ---------------------------------------------------------------------------

GREETING_WORDS = [
    "hi", "hello", "hey", "aha", "هلانت", "اهلا", "أهلا", "هاي", "مرحبا",
    "سلام", "هلا", "الو", "صباح", "مساء", "أهلا", "هايلو",
]
INTRODUCE_WORDS = [
    "من انت", "من انت", "شنو تسوي", "وش تسوي", "ماذا تفعل", "من هو",
    "what do you do", "who are you", "introduce", "تعريف", "اختصر",
]
TASK_WORDS = [
    "تاسك", "tاسك", "مهمة", "مهام", "ضيف", "اضف", "أضف", "create", "add",
    "deadline", "موعد", "task", "tasks", "كارت", "card", "cards",
]
QUESTION_WORDS = [
    "?", "what", "how", "why", "اشرح", "كيف", "ليه", "ايه", "ازاي",
    "explain", "means", "ماذا", "معنى", "يعني",
]


def _has_any(text: str, words: List[str]) -> bool:
    t = text.lower()
    return any(w in t for w in words)


def classify(text: str) -> str:
    """Return one of: greeting | introduce | add_tasks | question | other."""
    t = (text or "").strip().lower()
    if not t:
        return "other"
    # 1) Introduce request.
    if _has_any(t, INTRODUCE_WORDS) or "who are you" in t or "what do you do" in t:
        return "introduce"
    # 2) Task creation requested (strong signal) — check BEFORE greeting so a
    #    task phrase isn't mistaken for a greeting.
    if _looks_like_task_request(t) and _has_any(t, TASK_WORDS):
        return "add_tasks"
    # 3) Pure greeting: must be short AND start with / equal a greeting word
    #    (word boundaries, so "architecture" with a substring 'hi' is not one).
    if _is_pure_greeting(t):
        return "greeting"
    # 4) A question.
    if "؟" in t or _has_any(t, QUESTION_WORDS):
        return "question"
    return "other"


_GREET_RE = re.compile(r"^(hi|hello|hey|selam|salam|ahlan|مرحبا|اهلا|أهلا|هاي|سلام|هلا|الو|صباح|مساء|يا)\b")


def _is_pure_greeting(t: str) -> bool:
    """True only for a short message that is exactly/near a greeting."""
    t = t.strip().strip("!؟.!?")
    if not t or len(t) > 40:
        return False
    # Arabic greeting words.
    if any(w in t.split() for w in ["مرحبا", "اهلا", "أهلا", "هاي", "سلام",
                                    "هلا", "الو", "أهلا", "صباح", "مساء"]):
        return True
    # English greeting at the start (word-boundary), e.g. "hi", "hello jarvis".
    if _GREET_RE.match(t):
        return True
    return False


def _looks_like_task_request(text: str) -> bool:
    """Stronger signal than a bare keyword: has task vocab + card-ish structure."""
    t = text.lower()
    # "add task", "create card", "ضيف مهمة", "ضيف تاسك", "حط مهمة"...
    if any(k in t for k in ["add task", "create task", "create card", "add card",
                            "ضيف مهمة", "اضف مهمة", "أضف مهمة", "ضيف تاسك",
                            "حط مهمة", "ضيف مهام", "اضف مهام", "أضف مهام",
                            "مهمة جديدة", "تاسك جديد", "new task", "له مهام"]):
        return True
    # Also treat a bulleted list with task keywords as a task request.
    if any(line.strip().startswith(("-", "*", "+", "1.", "2.", "3.", "4.", "5.",
                                    "6.", "7.", "8.", "9.")) and
           any(k in line.lower() for k in TASK_WORDS)
           for line in text.splitlines()):
        return True
    return False


# ---------------------------------------------------------------------------
# Multi-task parsing — extract cards + deadlines from one message
# ---------------------------------------------------------------------------

_TEAM_LABELS = ["Team 1", "Team 2", "Team 3", "All Teams"]
_SPECIAL_LABELS = ["Milestone", "Handoff", "Reviewer / TA", "Reviewer"]
_LIST_NAMES = ["Project Information", "Backlog", "This Sprint", "In Progress",
               "Blocked", "Handoff / Review", "Integration Testing", "Done"]


def _find_label(text: str) -> Optional[str]:
    for lab in _SPECIAL_LABELS + _TEAM_LABELS:
        if lab.lower() in text.lower():
            return lab
    return None


def _find_list(text: str) -> str:
    for name in _LIST_NAMES:
        if name.lower() in text.lower():
            return name
    return "Backlog"


def _find_checklists(text: str) -> List[dict]:
    """Pull MULTIPLE named checklists out of a task message.

    Recognises patterns like:
      checklist "Design": sketch, mockup, wireframe
      [Design] sketch, mockup, wireframe
      Checklist: item1, item2           (unnamed -> "Subtasks")
    Returns a list of {"name": str, "items": [str, ...]}.
    """
    groups = []
    low = text
    # (a) checklist "Name": a, b, c
    for m in re.finditer(r'checklist\s*["\']?\s*([^"\'\]{]{1,40})["\']?\s*:\s*(.+)', low, flags=re.I):
        name = (m.group(1).strip() or "Subtasks")
        items = _split_items(m.group(2))
        if items:
            groups.append({"name": name, "items": items})
    # (b) [Name] a, b, c  (bracketed, may have no colon)
    for m in re.finditer(r'\[([^\]]{1,40})\]\s*:?\s*(.+)', low):
        name = m.group(1).strip() or "Subtasks"
        items = _split_items(m.group(2))
        if items:
            groups.append({"name": name, "items": items})
    # (c) bare "Checklist: item1, item2" (unnamed -> "Subtasks")
    if not groups:
        m = re.search(r'checklist\s*:\s*(.+)', low, flags=re.I)
        if m:
            items = _split_items(m.group(1))
            if items:
                groups.append({"name": "Subtasks", "items": items})
    return groups


def _split_items(body: str) -> List[str]:
    items = [x.strip() for x in re.split(r'[;,\n]| or ', body) if x.strip()]
    return [i for i in items if len(i) >= 2][:20]


def _find_due(text: str) -> Optional[str]:
    """Find an ISO date or dd-mm-yyyy / dd/mm from the text. Returns YYYY-MM-DD ISO."""
    # ISO first
    m = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if m:
        return m.group(0)
    # dd-mm-yyyy or dd/mm/yyyy
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", text)
    if m:
        d, mo, y = m.groups()
        y = ("20" + y) if len(y) == 2 else y
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None


# A line that is a checklist continuation (bracketed name or "checklist ...").
_CHECK_LINE_RE = re.compile(r"^\s*(?:[•\-\*\d\.\)]+\s*)?(?:checklist|\[)", flags=re.I)


def _split_blocks(text: str) -> List[str]:
    """Split a message into task blocks.

    A block starts at a top-level bullet (`- title`) or a non-checklist line.
    Checklist continuation lines are appended to the previous block, so one task
    can carry several named checklists."""
    blocks: List[str] = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if _CHECK_LINE_RE.match(ln):
            if blocks:
                blocks[-1] = f"{blocks[-1]}\n{ln}"
            else:
                blocks.append(ln)
            continue
        blocks.append(ln)
    return blocks


def parse_tasks(text: str) -> List[dict]:
    """Parse one message into a list of task dicts (multi-task support).

    Task separation: each top-level bullet/line is one task. Checklist lines
    (`- checklist "Name": ...` / `[Name] ...`) attach to the PREVIOUS task so a
    single task can carry several named checklists.
    """
    # Drop leading directive + @mention: "add tasks:", "@JARVIS add tasks:", ...
    body = re.sub(r"^[\s@\S]*?\b(add|create|ضيف|اضف|أضف)\s+(the\s+)?(tasks?|cards?|مهام|مهمة|كروت|كرت)\b\s*:?\s*",
                  "", text or "", flags=re.I).strip()
    blocks = _split_blocks(body)
    tasks: List[dict] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        # Title = everything except the checklist continuation lines.
        title_part = [ln for ln in lines if not _CHECK_LINE_RE.match(ln)]
        title_text = " ".join(title_part) if title_part else lines[0]
        title = _clean_title(title_text)
        if len(title) < 2:
            continue
        # Checklists: pull from the whole block (title + continuation lines).
        checklists = _find_checklists(block)
        tasks.append({
            "title": title,
            "label": _find_label(block),
            "list_name": _find_list(block),
            "due": _find_due(block),
            "checklists": checklists,
        })
    # If nothing usable, fall back to the whole cleaned message as one task.
    if not tasks:
        tasks = [{
            "title": _clean_title(re.sub(r"^(add|create|ضيف|اضف|أضف)\s+", "", text or "")),
            "label": _find_label(text or ""),
            "list_name": _find_list(text or ""),
            "due": _find_due(text or ""),
            "checklists": _find_checklists(text or ""),
        }]
    # Dedup identical titles.
    seen, out = set(), []
    for t in tasks:
        key = (t["title"], t["label"], t["list_name"], t["due"])
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def _clean_title(it: str) -> str:
    title = it.strip()
    # Strip surrounding quotes.
    title = title.strip("\"'“”")
    # Remove directive prefixes like "add tasks:" / "اضف المهام:".
    title = re.sub(r"^(add|create|ضيف|اضف|أضف)\s+(the\s+)?(tasks?|cards?|مهام?|كروت?)?\s*[:\-]?\s*",
                   "", title, flags=re.I)
    # Remove parenthetical notes (kept for label/date detection, not for title).
    title = re.sub(r"\([^)]*\)", "", title)
    title = re.sub(r"[\[\[].*?[\]\]]", "", title)
    # Remove label mentions.
    for lab in _TEAM_LABELS + _SPECIAL_LABELS + _LIST_NAMES:
        title = re.sub(re.escape(lab), "", title, flags=re.I)
    # Remove date tokens.
    title = re.sub(r"\d{4}-\d{2}-\d{2}", "", title)
    title = re.sub(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", "", title)
    # Remove "due" / "deadline" / "موعد" + surrounding punctuation.
    title = re.sub(r"(due|deadline|موعد|استحقاق)\s*[:\-]?\s*", "", title, flags=re.I)
    # Remove team-ish words like "fريق/fفريق" but keep title words.
    title = re.sub(r"\b(team|فريق)\s*\d?\b", "", title, flags=re.I)
    title = re.sub(r"\s{2,}", " ", title).strip(" ,;:-")
    return title or "New task"