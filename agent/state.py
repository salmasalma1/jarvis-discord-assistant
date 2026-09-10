"""agent/state.py — LangGraph state schema (T2 core).

Holds the state for each Discord message as it flows: intent -> tool ->
critique -> reply. Expandable — add nodes/edges as needed.
"""
from typing import List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    # Conversation history for this session.
    messages: List[dict]
    # Classified intent: rag | git | trello | meeting | product | guard | off_scope
    intent: str
    # Allowed scope (from project docs / lane references).
    scope: List[str]
    # Tool outputs for the current step.
    tool_results: dict
    # Whether the proposed action needs user confirmation first.
    confirm_required: bool
    # Details of the proposed action (when confirmation is needed).
    proposed_action: Optional[dict]
    # Context metadata.
    user_id: str
    guild_id: str
    channel_id: str
    # Guard deviations observed — injected so the agent can react.
    guard_report: Optional[dict]
    # Final reply sent back to Discord.
    reply_text: Optional[str]


# ---------- Intent classification (offline heuristic; can be upgraded to Gemini) ----------
_INTENT_HINTS = {
    "git":       ["commit", "push", "repo", "branch", "pull request", "code"],
    "trello":    ["task", "card", "due", "deadline", "trello", "todo", "status"],
    "meeting":   ["meeting", "summary", "audio", "recording", "transcript", "social"],
    "rag":       ["what", "how", "why", "explain", "document", "architecture", "docs"],
    "product":   ["report", "score", "weekly", "product", "member", "activity"],
    "guard":     ["alert", "deviation", "blueprint", "handoff", "conflict", "owner"],
}


def classify_intent(text: str) -> str:
    """Simple offline intent classifier (works on EN or AR keywords)."""
    t = text.lower()
    # Arabic keyword hints for Arabic queries.
    ar_hints = {
        "git": ["كود", "كوميت", "رفع", "ريبو", "فرع"],
        "trello": ["مهمة", "تاسك", "موعد", "مهام", "حالة"],
        "meeting": ["اجتماع", "تسجيل", "ملخص", "صوت"],
        "rag": ["ايه", "ازاي", "ليه", "اشرح", "وثيقة", "معماري"],
        "product": ["تقرير", "نقاط", "اسبوعي", "عضو"],
        "guard": ["تنبيه", "انحراف", "بلو", "owner", "تعارض"],
    }
    best, best_score = "rag", 0
    for intent, hints in _INTENT_HINTS.items():
        score = sum(1 for h in hints if h in t)
        if score > best_score:
            best, best_score = intent, score
    for intent, hints in ar_hints.items():
        score = sum(1 for h in hints if h in t)
        if score > best_score:
            best, best_score = intent, score
    return best
