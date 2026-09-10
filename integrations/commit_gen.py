"""integrations/commit_gen.py — Conventional Commit generator + branch chooser.

Classifies a diff -> type/scope -> message, and picks the branch automatically.
Offline and deterministic; Gemini is optional for a richer body.
"""
import re
from typing import Optional, Tuple

# Path-substring -> (commit type, description).
TYPE_RULES = [
    (("test", "tests", "spec", ".test."), "test", "tests"),
    (("docs", "readme", ".md"), "docs", "docs"),
    ((".github", "ci", "dockerfile", "workflow"), "ci", "ci"),
    (("makefile", "package.json", "requirements.txt", "pyproject", "dependencies"), "chore", "chore"),
    (("fix", "bug", "patch", "hotfix"), "fix", "bugfix"),
    (("refactor", "cleanup"), "refactor", "refactor"),
]

# Keyword hints in the message/branch if the path didn't decide.
MSG_TYPE_HINTS = {
    "feat": ("add", "feature", "implement", "new", "support", "create"),
    "fix": ("fix", "bug", "resolve", "correct", "patch", "repair", "error"),
    "refactor": ("refactor", "restructure", "clean", "improve"),
}


def _detect_type(paths, message_tokens):
    for substrings, ttype, _ in TYPE_RULES:
        if any(any(s in p.lower() for s in substrings) for p in paths):
            return ttype
    full = " ".join(message_tokens).lower()
    for ttype, hints in MSG_TYPE_HINTS.items():
        if any(h in full for h in hints):
            return ttype
    return "chore"


def module_scope(paths, folder_to_module=None):
    """Infer scope (module) from the first changed path, or from the architecture map."""
    if folder_to_module:
        for p in paths:
            for root, mod in folder_to_module.items():
                if p.startswith(root.strip("/")):
                    return mod
    if not paths:
        return None
    parts = [s for s in paths[0].split("/") if s]
    return parts[0] if parts else None


def choose_branch(linked_task, current_branch, message, is_feature=True):
    """Automatic branch choice: feature/<task>, fix/<task>, else dev."""
    if linked_task:
        task = linked_task.replace("TRELLO-", "").replace("TASK-", "").lower()
        base = "feature" if is_feature else ("fix" if "fix" in message.lower() else "dev")
        return f"{base}/{task}"
    return "dev" if (current_branch in ("main", None, "")) else current_branch


def generate_message(paths, message_tokens, linked_task=None, pr_ref=None,
                     summarize: Optional[str] = None) -> Tuple[str, dict]:
    """Build a Conventional message (offline). summarize is optional Gemini text."""
    type2 = _detect_type(paths, message_tokens)
    scope = module_scope(paths)
    title = _title_from(type2, scope, message_tokens)
    body = summarize or f"- {', '.join(paths)}"
    lines = [title, "", body]
    if linked_task:
        lines += ["", f"closes {linked_task}"]
    if pr_ref:
        lines += ["", f"Refs: {pr_ref}"]
    return "\n".join(lines), {"type": type2, "scope": scope, "title": title}


def _title_from(type2, scope, tokens):
    """Standard: type(scope): subject  (<~72 chars)."""
    subject = " ".join(tokens[:7]).strip().lower()
    if not subject:
        subject = f"{type2} change in {scope or 'project'}".lower()
    for w in ("add ", "implement ", "create "):
        if subject.startswith(w):
            subject = subject[len(w):]
            break
    subject = re.sub(r"\s+", " ", subject)[:72]
    sc = f"({scope})" if scope else ""
    return f"{type2}{sc}: {subject}"


if __name__ == "__main__":
    diff_paths = ["backend/orchestrator/state.py", "backend/reasoning/action.py"]
    msg, meta = generate_message(diff_paths,
                                 ["add", "checkpoint", "resume", "for", "interrupted", "tasks"],
                                 linked_task="TRELLO-42", pr_ref="#214")
    print(msg)
    print("meta:", meta)
