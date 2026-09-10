"""integrations/trello.py — py-trello wrapper for F3.

Provides: get_tasks, add_task, update_status, close_if_message_claims,
reminders_pending, dependency_conflicts.
Auto-updates task status when a commit message contains 'closes TRELLO-N'
(ties F2 commits to F3 tasks).
"""
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from config import TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD

try:
    from trello import TrelloClient
    _HAS_TRELLO = True
except Exception:
    _HAS_TRELLO = False

# Expected list names (matches your board).
_LISTS = ["Project Information", "Backlog", "This Sprint", "In Progress",
          "Blocked", "Handoff / Review", "Integration Testing", "Done"]

# Fuzzy aliases so a status like "Handoff/Review" or "handoff" still resolves.
_ALIASES = {
    "handoff": "Handoff / Review",
    "handoff/review": "Handoff / Review",
    "handoff / review": "Handoff / Review",
    "review": "Handoff / Review",
    "backlog": "Backlog",
    "inprogress": "In Progress",
    "in progress": "In Progress",
    "blocked": "Blocked",
    "done": "Done",
    "this sprint": "This Sprint",
    "integration testing": "Integration Testing",
    "project information": "Project Information",
}


def _norm(s: str) -> str:
    """Normalize a label name for fuzzy matching: lowercase, drop spaces & slashes."""
    return re.sub(r"[^a-z0-9]", "", (s or "").strip().lower())


def _resolve_list_name(status: str) -> str:
    """Map a user-friendly status to an actual board list name (case-insensitive)."""
    s = (status or "").strip().lower()
    if not s:
        return "Backlog"
    # exact (case-insensitive) first
    for tgt in _LISTS:
        if s == tgt.lower():
            return tgt
    return _ALIASES.get(s, status)  # fall back to whatever the caller passed


def _client():
    if not (TRELLO_API_KEY and TRELLO_TOKEN) or not _HAS_TRELLO:
        raise RuntimeError("Trello keys missing or py-trello not installed")
    return TrelloClient(api_key=TRELLO_API_KEY, token=TRELLO_TOKEN)


def _board():
    c = _client()
    if TRELLO_BOARD:
        return c.get_board(TRELLO_BOARD)
    return c.list_boards()[0]


def get_tasks() -> List[dict]:
    """F3 — read all cards with title, list, due, labels, members."""
    board = _board()
    out = []
    for lst in board.list_lists():
        for card in lst.list_cards():
            out.append({
                "id": card.id,
                "title": card.name,
                "list": lst.name,
                "due": card.due_date.isoformat() if card.due_date else None,
                "labels": [lab.name for lab in card.labels],
                "members": [m.full_name for m in card.members],
                "desc": card.description or "",
            })
    return out


def add_task(title: str, member: Optional[str] = None, due: Optional[str] = None,
             deps: Optional[List[str]] = None, list_name: str = "Backlog",
             label: Optional[str] = None, labels: Optional[List[str]] = None,
             desc: Optional[str] = None,
             checklist: Optional[List[str]] = None,
             checklists: Optional[List[dict]] = None) -> dict:
    """F3 — add a card with member / due / dependencies / label(s) / desc / checklist(s).

    label(s) should be one of the board's label names:
      Team 1, Team 2, Team 3, All Teams, Milestone, Handoff, Reviewer.
    checklist: list of strings -> one checklist named "Subtasks".
    checklists: list of {"name": str, "items": [str, ...]} -> MULTIPLE named
      checklists on the same card (e.g. Design, Implement, Test).
    Both may be provided; each is added as its own checklist.
    """
    board = _board()
    lst = next((l for l in board.list_lists() if l.name == list_name),
               board.list_lists()[0])
    card = lst.add_card(title)
    if due:
        card.set_due(datetime.fromisoformat(due))
    if member:
        try:
            m = next((mm for mm in board.get_members() if mm.full_name == member), None)
            if m:
                card.add_member(m)
        except Exception:
            pass
    if deps:
        card.description = (card.description or "") + "\n" + "،".join("Depends: " + d for d in deps)
    applied = []
    wanted = [lab for lab in ([label] if label else (labels or [])) if lab]
    if wanted:
        board_labels = {_norm(lab.name): lab for lab in board.get_labels()}
        for lab in wanted:
            lab_obj = board_labels.get(_norm(lab))
            if lab_obj:
                try:
                    card.add_label(lab_obj)
                    applied.append(lab_obj.name)
                except Exception:
                    pass
    # Optional description.
    if desc and not card.description:
        try:
            card.description = desc
        except Exception:
            pass
    # Optional checklist(s) (via direct API for reliability).
    # Build the list of {"name", "items"} groups: explicit `checklists` win,
    # plus any flat `checklist` list becomes its own "Subtasks" group.
    groups = list(checklists or [])
    if checklist:
        groups = groups + [{"name": "Subtasks", "items": checklist}]
    for g in groups:
        name = (g.get("name") or "Subtasks").strip() or "Subtasks"
        items = list(g.get("items") or [])
        if not items:
            continue
        try:
            _add_checklist_api(card.id, items, name=name)
        except Exception:
            pass
    return {"id": card.id, "title": card.name, "list": list_name,
            "labels": applied}


def _add_checklist_api(card_id: str, items: List[str], name: str = "Subtasks"):
    """Add a named Trello checklist to a card via the REST API (more reliable than py-trello)."""
    import urllib.request, urllib.parse
    from config import TRELLO_API_KEY, TRELLO_TOKEN
    base = "https://api.trello.com/1"
    q = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    # create checklist
    data = urllib.parse.urlencode({**q, "name": name,
                                   "idCard": card_id}).encode()
    req = urllib.request.Request(f"{base}/checklists?{urllib.parse.urlencode(q)}",
                                 data=data, method="POST")
    import json
    with urllib.request.urlopen(req) as r:
        cl = json.load(r)
    checklist_id = cl["id"]
    # add each item
    for item in items:
        d = urllib.parse.urlencode({**q, "name": item,
                                    "idChecklist": checklist_id}).encode()
        req = urllib.request.Request(f"{base}/checklists/{checklist_id}/checkItems?{urllib.parse.urlencode(q)}",
                                     data=d, method="POST")
        try:
            urllib.request.urlopen(req)
        except Exception:
            pass


def update_status(task_id: str, status: str) -> dict:
    """F3 — move a card to another list (Backlog/In Progress/Blocked/Done...)."""
    board = _board()
    card = board.get_card(task_id)

    # If caller gave the TRELLO-N id string, strip the prefix to the real id.
    if str(task_id).lower().startswith("trello-"):
        task_id = str(task_id).split("-", 1)[1]

    resolved = _resolve_list_name(status)
    target = next((l for l in board.list_lists()
                   if l.name.lower() == resolved.lower()), None)
    if target:
        card.change_list(target.id)
        return {"id": task_id, "status": resolved, "ok": True}
    return {"id": task_id, "status": status, "ok": False, "error": "list not found"}


def mark_done_by_title(title: str) -> dict:
    """F3 — find a card by title (any list) and move it to Done. Returns a result dict."""
    board = _board()
    target_title = (title or "").strip().lower()
    if not target_title:
        return {"ok": False, "error": "no title given"}
    for lst in board.list_lists():
        for card in lst.list_cards():
            if (card.name or "").strip().lower() == target_title:
                done = next((l for l in board.list_lists()
                             if l.name.lower() == "done"), None)
                if done is not None:
                    card.change_list(done.id)
                    return {"ok": True, "title": card.name, "list": "Done"}
                return {"ok": False, "error": "'Done' list not found on board"}
    return {"ok": False, "error": f"no card titled '{title}'"}

    """Extract TRELLO-N from a commit message."""
    m = re.search(r"TRELLO[-_ ]?(\d+)", msg, flags=re.I)
    return f"TRELLO-{m.group(1)}" if m else None


def close_if_message_claims(msg: str) -> List[dict]:
    """F3 — if a commit says 'closes TRELLO-N', move that task to Done."""
    m = re.search(r"closes?\s*TRELLO[-_ ]?(\d+)", msg, flags=re.I)
    if not m:
        return []
    return [update_status(f"TRELLO-{m.group(1)}", "Done")]


def reminders_pending(now: Optional[datetime] = None, lead_hours=(24, 6, 2)) -> List[dict]:
    """F3 — due-date reminders within the lead-time windows."""
    now = now or datetime.utcnow()
    out = []
    for task in get_tasks():
        if not task.get("due"):
            continue
        due = datetime.fromisoformat(task["due"])
        delta = (due - now).total_seconds() / 3600
        for h in lead_hours:
            if 0 <= (h - delta) <= 1:
                out.append({**task, "remind_hrs": h})
    return out


def dependency_conflicts(tasks: Optional[List[dict]] = None) -> List[dict]:
    """F3 — alert when a task is overdue while another task depends on it."""
    tasks = tasks or get_tasks()
    by_id = {t["id"]: t for t in tasks}
    conflicts = []
    for t in tasks:
        for dep in _parse_deps(t.get("desc", "")):
            dep_task = by_id.get(dep)
            if dep_task and dep_task["list"] != "Done":
                if dep_task.get("due") and datetime.fromisoformat(dep_task["due"]) < datetime.utcnow():
                    conflicts.append({
                        "blocked": t["title"], "dependency": dep_task["title"],
                        "reason": "dependency overdue / not done"})
    return conflicts


def _parse_deps(desc: str) -> List[str]:
    return re.findall(r"Depends:\s*([A-Za-z0-9-]+)", desc or "")