"""scheduler/jobs.py — apscheduler (reminders + weekly report + deadline monitor).

Run via main.py; do not run this file directly.
"""
import asyncio
from datetime import datetime, timedelta

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    _HAS_APS = True
except Exception:
    _HAS_APS = False

_scheduler = None


def _create():
    global _scheduler
    if not _HAS_APS:
        return None
    _scheduler = AsyncIOScheduler()
    return _scheduler


def start(notify=None, report=None):
    """Register jobs: deadline reminders hourly + weekly report (Friday).
    notify: async (task) -> None ; report: async () -> str"""
    sched = _create()
    if sched is None:
        print("apscheduler not installed — jobs run manually.")
        return None

    async def _deadline_scan():
        from integrations.trello import reminders_pending
        try:
            for task in await asyncio.to_thread(reminders_pending):
                if notify:
                    await notify(task)
        except Exception as e:
            print("reminder scan error:", e)

    async def _weekly():
        if report:
            text = await report()
            print("Weekly report:", text[:200])

    async def _sources_scan():
        "Daily scan of open sources; post relevant finds to the sources channel."
        from integrations.sources import scan_sources, format_item, is_relevant
        try:
            found = await scan_sources(limit=8)
            relevant = [f for f in found if is_relevant(f)]
            if relevant and notify:
                msg = "🔎 **Today's source finds:**\n\n" + \
                      "\n\n".join(format_item(f) for f in relevant)
                # notify is the deadline-notifier; use it to deliver to channel.
                await notify({"title": "source finds", "due": None, "note": msg})
        except Exception as e:
            print("source scan error:", e)

    sched.add_job(_deadline_scan, "interval", hours=1)
    sched.add_job(_weekly, "cron", day_of_week="fri", hour=18)
    sched.add_job(_sources_scan, "cron", hour=9)  # once a day at 09:00
    sched.start()
    return sched


async def weekly_report(store=None) -> str:
    """Build a readable weekly team report from the activity log (F5)."""
    if store is None:
        return "No store provided — DB not configured."
    try:
        metrics = await asyncio.to_thread(store.get_weekly_metrics)
    except Exception as e:
        return f"report error: {e}"
    lines = ["📊 **Weekly team report**"]
    if not metrics:
        lines.append("_No activity recorded this week yet._")
        return "\n".join(lines)
    lines.append("Member | Queries | Tasks | Commits | Score")
    lines.append("-" * 44)
    for row in metrics:
        name = row.get("name") or "?"
        q = row.get("queries") or 0
        t = row.get("tasks") or 0
        c = row.get("commits") or 0
        s = row.get("score") or 0
        lines.append(f"{name} | {q} | {t} | {c} | {s}")
    return "\n".join(lines)