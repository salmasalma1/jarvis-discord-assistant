"""integrations/github.py — PyGithub wrapper for F2 (auto commit/push/branch/PR).

Provides: init_repo, submit_code (Commit + Push + Conventional message with
automatic branch selection), create_pr.
The commit message generator lives in integrations/commit_gen.py.
"""
import base64
from typing import Dict, List, Optional

from config import GITHUB_TOKEN

from integrations.commit_gen import generate_message, choose_branch

try:
    from github import Github
    _HAS_PYGITHUB = True
except Exception:
    _HAS_PYGITHUB = False


# Repo path <-> canonical NELLY layer name (used for Conventional scope and review).
FOLDER_TO_MODULE = {
    "frontend": "frontend",
    "backend/orchestrator": "orchestrator",
    "backend/reasoning": "reasoning",
    "backend/tools": "tool_management",
    "backend/execution": "execution",
    "backend/safety": "safety",
    "backend": "backend",
    "voice": "voice",
    "vision": "vision",
    "memory": "memory",
    "rag": "rag",
    "eval": "eval",
}


def _gh():
    if not GITHUB_TOKEN or not _HAS_PYGITHUB:
        raise RuntimeError("GITHUB_TOKEN missing or PyGithub not installed")
    return Github(GITHUB_TOKEN)


def init_repo(name: str, description: str = "", is_private: bool = True,
              org: Optional[str] = None) -> dict:
    """F2 — create repo + scaffold the NELLY 7-layer structure."""
    gh = _gh()
    user = gh.get_user() if not org else gh.get_organization(org)
    repo = user.create_repo(name, description=description, private=is_private, auto_init=True)
    _add_files(repo, _REPO_STRUCTURE)
    return {"name": repo.name, "url": repo.html_url, "structure": list(_REPO_STRUCTURE.keys())}


_REPO_STRUCTURE = {
    "frontend/README.md": "# NELLY Frontend (React + TS)\n",
    "backend/README.md": "# NELLY Backend (FastAPI)\n",
    "backend/orchestrator/README.md": "# LangGraph orchestrator\n",
    "backend/reasoning/README.md": "# Qwen2.5-VL / ReAct\n",
    "backend/tools/README.md": "# Pydantic validation\n",
    "backend/execution/README.md": "# Playwright / PyAutoGUI\n",
    "backend/safety/README.md": "# Risk-tier + approval\n",
    "voice/README.md": "# WakeWord / VAD / Whisper / Piper\n",
    "vision/README.md": "# OmniParser + PaddleOCR\n",
    "memory/README.md": "# ChromaDB + SQLite\n",
    "rag/README.md": "# RAG (Qdrant/Postgres)\n",
    "eval/README.md": "# LangSmith benchmark\n",
    "docs/ARCHITECTURE.md": "# 7-layer architecture\n",
    ".gitignore": ".env\n__pycache__/\n*.db\n.venv/\n",
}


def _add_files(repo, structure: Dict[str, str]):
    for path in structure:
        try:
            repo.create_file(path, "chore: scaffold %s" % path, structure[path],
                             branch=repo.default_branch)
        except Exception:
            pass  # file may already exist


def submit_code(files: Dict[str, str], message_tokens: List[str],
                linked_task: Optional[str] = None, current_branch: str = "dev",
                summarize: Optional[str] = None,
                author_name: Optional[str] = None,
                author_email: Optional[str] = None) -> dict:
    """F2 — commit + push a set of files with a Conventional message and
    automatic branch selection. files: {relative_path: content}.

    IMPORTANT — attribution: when a team member (e.g. Maryam) submits code,
    pass author_name / author_email so the commit is attributed to THAT member
    (not to the bot). Anyone reading the repo sees who actually did the work.
    """
    from email.utils import parseaddr

    if not files:
        raise ValueError("No files provided to submit.")
    gh = _gh()
    repo = _find_repo()
    paths = list(files.keys())

    branch = choose_branch(linked_task, current_branch, " ".join(message_tokens))
    _ensure_branch(repo, branch)

    msg, meta = generate_message(paths, message_tokens, linked_task=linked_task,
                                 summarize=summarize)

    # Build the author + committer dicts for PyGithub (required for HTTPS auth).
    author = committer = None
    if author_name and author_email:
        author = {"name": author_name, "email": author_email}
        committer = {"name": author_name, "email": author_email}

    for path, content in files.items():
        try:
            repo.create_file(path, msg, content, branch=branch,
                             author=author, committer=committer)
        except Exception:
            for f in repo.get_contents(path, ref=branch):
                try:
                    repo.update_file(path, msg, content, f.sha, branch=branch,
                                     author=author, committer=committer)
                    break
                except Exception:
                    pass
    return {"branch": branch, "message": msg, "meta": meta, "files": paths,
            "author": author_name or "JARVIS"}


def _find_repo(name: Optional[str] = None):
    gh = _gh()
    if name:
        try:
            return gh.get_repo(name)
        except Exception:
            pass
    repos = gh.get_user().get_repos()
    return repos[0] if repos else None


def ensure_scaffold(name: Optional[str] = None) -> dict:
    """Add any missing NELLY structure files to an EXISTING repo (no rebuild).

    Unlike init_repo (which creates a NEW repo), this fills the 7-layer
    skeleton into a repo you already made manually — so the bot can add
    files to the repo whenever you want it to, without recreating it."""
    gh = _gh()
    repo = _find_repo(name)
    if repo is None:
        return {"ok": False, "error": "No repo found to scaffold."}
    added, updated = [], []
    existing = {}
    try:
        for f in repo.get_contents(""):
            existing[f.path] = f.sha
    except Exception:
        pass
    for path, content in _REPO_STRUCTURE.items():
        if path in existing:
            updated.append(path)
            continue
        try:
            repo.create_file(path, "chore: scaffold %s" % path, content,
                             branch=repo.default_branch)
            added.append(path)
        except Exception:
            pass
    return {"ok": True, "repo": repo.full_name, "added": added,
            "updated": updated}


def _ensure_branch(repo, branch: str):
    try:
        repo.get_branch(branch)
    except Exception:
        src = repo.get_branch(repo.default_branch)
        repo.create_git_ref(ref=f"refs/heads/{branch}", sha=src.commit.sha)


def create_pr(title: str, head: str, base: str = "main", body: str = "") -> dict:
    gh = _gh()
    repo = _find_repo()
    pr = repo.create_pull(title, head, base, body=body, draft=True)
    return {"number": pr.number, "url": pr.html_url}
