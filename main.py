"""main.py — JARVIS entry point.

Wires the agent core + tools + guard + scheduler and connects the Discord bot.
Run:  python main.py   (set the token in .env)
"""
import asyncio
from typing import Callable, Optional

from config import DISCORD_TOKEN, GEMINI_KEY, SOURCES_CHANNEL


# ---------- helper: turn a sync tool into an async one ----------
def _async(func: Callable) -> Callable:
    """Wrap a sync callable as async (runs in a thread)."""
    async def wrapper(state):
        try:
            return await asyncio.to_thread(func, state)
        except Exception as e:
            return {"error": str(e)}
    return wrapper


# ---------- scheduler week report ----------
async def scheduler_report(store) -> str:
    """Fallback weekly summary from the DB store."""
    try:
        return await asyncio.to_thread(lambda: str(store.get_weekly_metrics())[:300])
    except Exception as e:
        return f"report error: {e}"


# ---------- helper: build a diff/context slice for /review ----------
def _diff_of(target: str) -> str:
    """Return a small context snippet for the review (a file or a task name).

    If target is empty or not found, return a generic architecture summary so
    /review still gives useful output rather than failing."""
    import os
    if target and os.path.exists(target):
        with open(target, "r", encoding="utf-8", errors="ignore") as fh:
            return f"# file: {target}\n" + fh.read()[:3000]
    if target:
        return (f"[review] no local file matched '{target}' — provide a relative "
                f"path in the repo checkout for a diff review.")
    return ("[review] no target given. Provide a file path to review a change "
            "against the 7-layer architecture.")


# ---------- boot status ----------
async def bootstrap() -> str:
    from agent.graph import AgentRunner
    from integrations import github as gh, trello as tr
    from integrations.llm import generate
    from db import store
    from config import GITHUB_TOKEN, TRELLO_API_KEY

    tool_map = {
        "git": _async(lambda s: gh.submit_code(
            files={}, message_tokens=s.get("messages", [{"content": ""}])[-1].get("content", "").split(),
            linked_task=None)),
        "trello": _async(lambda s: tr.get_tasks()[:20]),
    }
    runner = AgentRunner(tool_map=tool_map, llm=generate)

    # NOTE: the apscheduler is intentionally NOT started at boot because it
    # shares the asyncio event loop with the Discord gateway and broke message
    # reception. (Reminders/report can run later on demand.)
    lines = [
        "Core: AgentRunner (intent -> tool -> reply)",
        f"LLM: {'Gemini enabled' if GEMINI_KEY else 'local (no Gemini key)'}",
        f"Discord bot: {'enabled' if DISCORD_TOKEN else 'DISCORD_TOKEN required'}",
        f"GitHub F2: {'enabled' if GITHUB_TOKEN else 'GITHUB_TOKEN required'}",
        f"Trello F3: {'enabled' if TRELLO_API_KEY else 'TRELLO keys required'}",
        "Guard F7: collector/mapper/compare/alerter ready",
        "Review: review_against_architecture (F6) ready",
    ]
    return "\n".join(lines)


# ---------- run the live bot ----------
async def run_forever():
    from integrations.discord_bot import build_bot
    from agent.graph import AgentRunner
    from integrations.llm import generate, review_against_architecture
    from integrations import github as gh, trello as tr
    from config import GEMINI_KEY, GITHUB_TOKEN, TRELLO_API_KEY

    # Build agent wired to the LLM (Gemini) so JARVIS replies intelligently.
    runner = AgentRunner(llm=generate)

    # Wire the real F2/F3/F7 hooks into the slash-command menu. Each hook is
    # a small sync wrapper (so the menu works once the matching token is set).
    def _hook(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    trello_fn = None
    if TRELLO_API_KEY:
        trello_fn = lambda: tr.get_tasks()
    dotask_fn = None
    if TRELLO_API_KEY:
        def _default_checklist_for(title: str) -> tuple:
            """Return (desc, checklist) hints from the blueprint for a task title."""
            desc, checklist = "", []
            t = title.lower()
            CHECK = {
                "vision": "Implement the vision pipeline; normalize boxes; return JSON.",
                "paddle": "OCR + normalized coords; align to element frame.",
                "pydantic": "Define Pydantic v2 action schemas; validate before execution.",
                "orchestrator": "LangGraph loop; verify; retry; human-interrupt.",
                "reasoning": "Qwen2.5-VL ReAct; decompose goal; pick next action.",
                "voice": "Wake word + VAD + STT/TTS pipeline.",
                "rag": "20-stage ingestion; hybrid retrieval; cross-language (EN/AR).",
                "memory": "ChromaDB episodic + session checkpoints.",
                "safety": "RiskTier + approval layer + emergency stop.",
                "eval": "LangSmith benchmark harness; metrics report.",
                "backend": "FastAPI; WebSocket; approval events.",
            }
            for k, v in CHECK.items():
                if k in t:
                    desc = v
                    break
            checklist = [
                "Read the NELLY architecture (blueprint/architecture.yaml)",
                "Implement the module for the assigned lane",
                "Write tests for the acceptance criteria",
                "Run /guard to check architecture compliance",
                "Submit via the team lead / /commit",
            ]
            return desc, checklist

        def _auto_due_for_label(label):
            """Return an ISO due date for a task based on its milestone label."""
            import datetime
            # milestone due dates (from blueprint/milestones.yaml)
            M = {
                "milestone": "2026-09-27T23:59:00.000Z",   # Contracts Frozen
                "reviewer / ta": "2026-10-25T23:59:00.000Z",  # First E2E Demo
                "handoff": "2026-11-15T23:59:00.000Z",     # Approval Flow
            }
            from integrations.trello import _norm
            key = _norm(label or "")
            if key in [ _norm(k) for k in ("milestone","reviewer / ta","handoff") ]:
                return M.get(next((k for k in M if _norm(k)==key), None))
            return None

        def dotask_fn(title, member=None, list_name="Backlog", label=None,
                      due=None, checklists=None):
            desc, checklist = _default_checklist_for(title)
            # Auto-milestone due date if not provided (from blueprint milestones).
            if not due:
                due = _auto_due_for_label(label)
            # If the caller supplied explicit named checklists, use those as the
            # primary groups; otherwise fall back to the default "Subtasks".
            groups = list(checklists or [])
            if not groups and checklist:
                groups = [{"name": "Subtasks", "items": checklist}]
            return tr.add_task(title, member=member, list_name=list_name,
                               label=label, desc=desc, checklists=groups,
                               due=due)

        def bulk_fn(tasks):
            """Create MULTIPLE Trello cards from a list of task dicts."""
            results = []
            for t in tasks:
                title = (t.get("title") or "New task").strip()
                label = t.get("label")
                lst = t.get("list_name") or "Backlog"
                due = (t.get("due") or "").strip() or None
                # Optional multiple named checklists carried on the task dict.
                checklists = t.get("checklists") or []
                try:
                    res = dotask_fn(title, None, lst, label, due=due,
                                    checklists=checklists)
                    cl_note = f" · ✔ {len(checklists)} checklist(s)" if checklists else ""
                    results.append({"title": res.get("title"), "list": lst,
                                    "labels": res.get("labels", []), "ok": True,
                                    "due": res.get("due"), "cl": cl_note})
                except Exception as e:
                    results.append({"title": title, "list": lst, "ok": False,
                                    "error": str(e)})
            return results
    gh_fn = None
    if GITHUB_TOKEN:
        def _gh_submit(files, msg, author_id=None):
            # Attribute the commit to the actual member (from member_map) when known.
            author_name, author_email = None, None
            if author_id:
                import json as _j, os as _o
                try:
                    with open(_o.getenv("MEMBER_MAP_FILE", "member_map.json")) as fh:
                        mm = _j.load(fh)
                    rec = mm.get(str(author_id), {})
                    author_name = rec.get("name")
                    author_email = rec.get("email")
                except Exception:
                    pass
            return gh.submit_code(files, msg.split(), summarize=" ".join(msg.split()),
                                  author_name=author_name, author_email=author_email)
        gh_fn = lambda files, msg: _gh_submit(files, msg)
    scaffold_fn = None
    if GITHUB_TOKEN:
        # Bot fills the NELLY 7-layer structure into the (already created) repo.
        scaffold_fn = lambda repo="": gh.ensure_scaffold(repo or None)

    reviewer = None
    if GEMINI_KEY:
        reviewer = lambda target="": review_against_architecture(
            _diff_of(target))

    # Alerts + task/reminder events land in the owner/leader channel.
    alert_channel_name = "owner_chat"  # Owner/Leaders read here.

    async def _post_to_channel(text: str):
        if not bot.guilds:
            return
        for guild in bot.guilds:
            for ch in guild.channels:
                if (getattr(ch, "name", "") or "").lower() == alert_channel_name:
                    try:
                        await ch.send(text)
                        return
                    except Exception:
                        pass

    async def _alert_hook(dev):
        text = f"🚨 **{dev.kind}** (severity: {dev.severity})\n{dev.message}\n"
        await _post_to_channel(text)
        return text

    # Source finds go to the dedicated SOURCES_CHANNEL; deadline reminders to alert channel.
    source_channel_name = SOURCES_CHANNEL or "jarvis-sources"

    async def _post_to_named(text: str, channel_name: str):
        if not bot.guilds:
            return
        for guild in bot.guilds:
            for ch in guild.channels:
                if (getattr(ch, "name", "") or "").lower() == channel_name:
                    try:
                        await ch.send(text)
                        return
                    except Exception:
                        pass

    async def _notify_task(task):
        # Source finds carry a "note" (no due). Route those to the sources channel.
        if task.get("note") and not task.get("due"):
            await _post_to_named(task["note"], source_channel_name)
            return
        text = (f"⏰ **Deadline reminder** — `{task.get('title')}` "
                f"(due {task.get('due')}).")
        await _post_to_named(text, alert_channel_name)

    # Build the bot with the live alert/notify hooks wired to owner_chat.
    bot = build_bot(runner, alert_hook=_alert_hook, trello_fn=trello_fn,
                    dotask_fn=dotask_fn, gh_fn=gh_fn, review_fn=reviewer,
                    scaffold_fn=scaffold_fn, notify=_notify_task,
                    bulk_fn=bulk_fn)

    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set. Add it to .env.")

    # We are already inside the asyncio loop (asyncio.run(main())). So we MUST
    # use await bot.start() — NOT bot.run() (bot.run calls asyncio.run() itself,
    # which cannot run from inside a running loop -> "running event loop" error).
    print("Starting Discord bot ... mention @JARVIS or say 'Hi JARVIS'.")
    try:
        await bot.start(DISCORD_TOKEN)
        print("JARVIS session ended (disconnected).")
    except KeyboardInterrupt:
        print("Stopped by user (Ctrl+C).")
        raise
    except Exception as e:
        print(f"[JARVIS] connection error: {e}")
        await asyncio.sleep(10)


async def main():
    print("================ JARVIS boot ================")
    print(await bootstrap())
    print("==============================================")
    if DISCORD_TOKEN:
        await run_forever()
    else:
        print("DISCORD_TOKEN not set — set it in .env to connect the bot.")


if __name__ == "__main__":
    asyncio.run(main())