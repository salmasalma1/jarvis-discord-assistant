"""integrations/discord_bot.py — Discord glue with a discoverable slash-command menu.

The bot shows the user what it can do via slash commands (type "/" to see the
menu). Every command is intentionally obvious so the team knows how to ask.
Replies come from the LLM (user's language); module strings stay English.

Trello (F3) and GitHub (F2) are wired here so the menu is real:
  /tasks   /dotask   -> Trello (trello_fn)
  /commit  -> GitHub  (gh_fn)
  /review  /guard    -> review against blueprint (review_fn, guard_hook)
"""
import asyncio
import os
from typing import Callable, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import (
    DISCORD_TOKEN,
    OWNER_ROLES,
    ALERT_CHANNEL,
    REVIEW_ROLE,
    ALLOWED_CHANNEL,
    MEMBER_MAP,
    REPO_URL,
    TRELLO_BOARD_URL,
    DOCS_URL,
    BOT_CHANNELS,
    POST_INTRO_ON_BOOT,
    RAG_INGEST_PASSWORD,
)

import json as _json
import os as _os

# Track which users already received the one-time registration reminder.
_REG_SENT_USERS = {}


JARVIS_BOT_VERSION = "2026-09-08.7"
# Verbose debug logging (echoes every message to terminal + jarvis.log).
# Set JARVIS_DEBUG=0 in .env to disable; default ON because the owner likes it.
_DEBUG = os.getenv("JARVIS_DEBUG", "1") == "1"


def _log(*a):
    """Log to both stderr and a persistent file so we can always see what the
    bot is doing even if the terminal is closed."""
    line = " ".join(str(x) for x in a)
    print(line, file=_sys.stderr)
    try:
        with open("jarvis.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


import sys as _sys


_INTRO = (
    "🤖 **JARVIS — Smart Team Assistant for NELLY**\n"
    "I help the team manage tasks (Trello), code (GitHub), architecture checks, "
    "and answer questions about the project.\n\n"
    "**Talk to me:** mention `@JARVIS` or say `Hi JARVIS`.\n\n"
    "**Quick commands:**\n"
    "`/help` — full command list\n"
    "`/links` — repo, Trello board & docs links\n"
    "`/tasks` — show Trello tasks\n"
    "`/dotask <title> <team>` — add a task\n"
    "`/ask <question>` — ask a project question\n"
    "`/report` — weekly report\n"
    "`/register <name> <email> <trello> <github>` — register yourself\n\n"
    "**Tip:** you can give me several tasks in one message, e.g:\n"
    "`@JARVIS add tasks: build vision (Team 1, due 2026-09-20); fix login (Team 2, due 2026-09-25)`\n\n"
    "I also reply in your language (English/Arabic) and stay inside the NELLY scope."
)


def build_bot(agent_runner, alert_hook: Optional[Callable] = None,
              trello_fn=None, gh_fn=None, review_fn=None,
              dotask_fn=None, guard_hook=None, scaffold_fn=None,
              notify=None, bulk_fn=None):
    """Wire Discord events + a slash-command menu to the agent runner.

    trello_fn  -> get_tasks() (list of dicts)             used by /tasks
    dotask_fn  -> add_task(title, member, due, list_name) used by /dotask
    gh_fn      -> submit_code(files, tokens, ...)         used by /commit
    review_fn  -> review_against_architecture(diff, ...)  used by /review
    guard_hook -> run an architecture check                used by /guard
    """
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    def _is_owner(member) -> bool:
        return member and any(r.name in OWNER_ROLES for r in member.roles)

    def _allowed(ctx, guild) -> bool:
        # Legacy guard kept for compatibility (slash commands always allowed).
        return True

    def _should_respond(message) -> bool:
        """Reply gate — JARVIS only speaks when it is genuinely addressed:
          (a) it is a DM / private chat with the bot, OR
          (b) the message @mentions the bot, OR
          (c) the channel is one of the bot's own channels (BOT_CHANNELS).
        Everything else is ignored so the bot never spams a general channel.
        Slash commands (/) still work everywhere regardless."""
        # (a) DM / private chat
        if message.guild is None:
            return True
        # (b) explicitly mentioned
        if bot.user and any(m.id == bot.user.id for m in message.mentions):
            return True
        # (c) one of the bot's dedicated channels
        chan = (getattr(message.channel, "name", "") or "").lower()
        if chan and chan in [c.lower() for c in BOT_CHANNELS]:
            return True
        return False

    # ---------------- slash-command menu (the discoverable "options") ----------------
    @bot.tree.command(name="help", description="What can JARVIS do?")
    async def help_cmd(interaction):
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message(
                "This bot is currently limited to the allowed channel.", ephemeral=True)
            return
        text = (
            "🤖 **JARVIS — what can I help you with?**\n"
            "Type `/` to pick a command, or `!ping` to verify I'm alive.\n\n"
            "**Core commands:**\n"
            "`/help` — this menu\n"
            "`/links` — repo, Trello board & docs links\n"
            "`/ask <question>` — ask the project (RAG/scoped Q&A)\n"
            "`/tasks` — show active Trello tasks & deadlines\n"
            "`/dotask <title> [member] [list]` — add a task to Trello\n"
            "`/report` — weekly productivity report\n"
            "`/commit <files...> <msg>` — submit code (commit+push+conventional)\n"
            "`/review <path|task>` — review a change against the architecture (F7)\n"
            "`/guard` — run a full architecture check (F7)\n"
            "`/scaffold [repo]` — Owner: fill the NELLY 7-layer structure into the repo\n"
            "`/meeting <audio>` — summarize a meeting recording\n\n"
            "**Owner-only:**\n"
            "`/alert <message>` — raise a manual architecture alert\n"
            "`/remember <fact>` — teach me a project fact (persists)​\n"
            "`/ingest-doc <password> <file>` — add a Chapter/doc to the RAG index (password)"
        )
        await interaction.response.send_message(text, ephemeral=True)

    @bot.tree.command(name="links", description="Show the repo, Trello board & docs links")
    async def links_cmd(interaction):
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message(
                "This bot is currently limited to the allowed channel.", ephemeral=True)
            return
        lines = ["🔗 **JARVIS — project links:**"]
        if TRELLO_BOARD_URL:
            lines.append(f"📋 **Trello board:** {TRELLO_BOARD_URL}")
        if REPO_URL:
            lines.append(f"🐙 **Repo (GitHub):** {REPO_URL}")
        # Only show Docs when it's a real link AND distinct from the repo — so we
        # never show a duplicate / placeholder that looks wrong.
        if DOCS_URL and DOCS_URL.rstrip("/") != REPO_URL.rstrip("/"):
            lines.append(f"📚 **Docs:** {DOCS_URL}")
        lines.append("")
        lines.append("`/tasks` — see the board's tasks and deadlines from here.")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @bot.tree.command(name="meeting", description="Summarise a meeting audio file (transcribe + summary)")
    async def meeting_cmd(interaction, audio: discord.Attachment):
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message("Restricted channel.", ephemeral=True)
            return
        await interaction.response.defer()
        name = (audio.filename or "").lower()
        if not name.endswith((".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mpeg")):
            await interaction.followup.send(
                "Please attach an audio file (.mp3/.wav/.m4a/.ogg/.flac).")
            return
        try:
            path = f"/tmp/{audio.filename}"
            await audio.save(path)
            from integrations.voice import summarize_audio, _fmt_summary
            data = await summarize_audio(path)
            await interaction.followup.send(_fmt_summary(data))
        except Exception as exc:
            await interaction.followup.send(f"⚠️ meeting error: {exc}")

    @bot.tree.command(name="meeting-pdf", description="Summarise a meeting audio file and send a PDF report")
    async def meeting_pdf_cmd(interaction, audio: discord.Attachment):
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message("Restricted channel.", ephemeral=True)
            return
        await interaction.response.defer()
        name = (audio.filename or "").lower()
        if not name.endswith((".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mpeg")):
            await interaction.followup.send(
                "Please attach an audio file (.mp3/.wav/.m4a/.ogg/.flac).")
            return
        try:
            path = f"/tmp/{audio.filename}"
            await audio.save(path)
            from integrations.voice import summarize_audio
            data = await summarize_audio(path)
            if data.get("error"):
                await interaction.followup.send(f"⚠️ {data['error']}")
                return
            from integrations.report_pdf import generate_report_pdf
            pdf_path = generate_report_pdf(data)
            await interaction.followup.send(file=discord.File(pdf_path))
        except Exception as exc:
            await interaction.followup.send(f"⚠️ meeting-pdf error: {exc}")

    @bot.tree.command(name="merge", description="Combine several meeting audio parts into ONE summary PDF")
    async def merge_cmd(interaction,
                        part1: discord.Attachment, part2: discord.Attachment,
                        part3: discord.Attachment = None, part4: discord.Attachment = None):
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message("Restricted channel.", ephemeral=True)
            return
        await interaction.response.defer()
        parts = [p for p in (part1, part2, part3, part4) if p is not None]
        try:
            from integrations.voice import transcribe_file
            transcripts = []
            for i, p in enumerate(parts, 1):
                path = f"/tmp/merge_{i}_{p.filename}"
                await p.save(path)
                t = await asyncio.to_thread(transcribe_file, path)
                transcripts.append(f"=== Part {i} ({p.filename}) ===\n{t}")
            combined = "\n\n".join(transcripts)
            if not combined.strip():
                await interaction.followup.send(
                    "No transcript produced. Make sure the files are valid audio and "
                    "faster-whisper/ffmpeg are installed.")
                return
            # Summarise the combined text once, then emit ONE PDF.
            from integrations.voice import _summarize_with_llm, _fallback_summary
            data = await _summarize_with_llm(combined) or _fallback_summary(combined)
            data["source"] = "Merged meeting ({} part(s))".format(len(parts))
            from integrations.report_pdf import generate_report_pdf
            pdf = generate_report_pdf(data)
            await interaction.followup.send(file=discord.File(pdf),
                                            content="📄 One PDF for the full meeting:")
        except Exception as exc:
            await interaction.followup.send(f"⚠️ merge error: {exc}")

    @bot.tree.command(name="ask", description="Ask a project question (scoped RAG)")
    async def ask_cmd(interaction, question: str):
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message("Restricted channel.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            # Ground the answer with the RAG index (EN docs + AR query).
            from rag import service as rag
            context = await rag.build_context(question, top_k=6)
            from integrations.llm import generate, JARVIS_RULES
            if context:
                grounded = (
                    f"Answer the question using ONLY the context below. It may come "
                    f"from MULTIPLE sources (project docs + similar/related projects "
                    f"you have been given). If more than one source is relevant, "
                    f"combine them and ORDER the answer by how useful/relevant each is "
                    f"to our NELLY project (most relevant first). Do NOT name any file "
                    f"or say where it came from — just answer clearly.\n"
                    f"If the context does not contain the answer, say you don't know.\n"
                    f"Reply in the same language as the question.\n\n"
                    f"CONTEXT:\n{context}\n\nQUESTION:\n{question}"
                )
                text = await generate(grounded, system=JARVIS_RULES)
            else:
                # RAG not ready (not indexed / no Gemini) -> fall back gracefully.
                text = await generate(question, system=JARVIS_RULES)
            # If Gemini is out of quota/error, still answer from the docs.
            if context and any(t in (text or "") for t in _NO_LLM_TAGS):
                text = _context_answer(context, question,
                                       lang_note="Based on the project documentation:")
            await interaction.followup.send(text or "(no reply)")
        except Exception as e:
            await interaction.followup.send(f"JARVIS error: {e}")

    @bot.tree.command(name="tasks", description="Show active tasks & deadlines")
    async def tasks_cmd(interaction):
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message("Restricted channel.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            if trello_fn:
                rows = trello_fn() or []
                if not rows:
                    await interaction.followup.send("No tasks found.")
                    return
                lines = [f"**{t.get('title')}** — `{t.get('list')}`"
                         + (f" · due {t.get('due')}" if t.get("due") else "")
                         + (f" · 👤 {', '.join(t['members'])}" if t.get("members") else "")
                         for t in rows[:15]]
                await interaction.followup.send("\n".join(lines))
            else:
                await interaction.followup.send("Trello hook not configured yet.")
        except Exception as e:
            await interaction.followup.send(f"tasks error: {e}")

    @bot.tree.command(name="dotask", description="Add a task to Trello")
    async def dotask_cmd(interaction, title: str,
                         member: str = "", list_name: str = "Backlog",
                         label: str = "", due: str = ""):
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message("Restricted channel.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            if not dotask_fn:
                await interaction.followup.send("Trello hook not configured yet.")
                return
            due_val = due.split("T")[0] if due else None
            res = dotask_fn(title, member or None, list_name, label or None,
                            due=due_val)
            added_lbl = f" · 🏷 {', '.join(res.get('labels', []))}" if res.get("labels") else ""
            due_txt = f" · 📅 {res.get('due')}" if res.get("due") else ""
            await interaction.followup.send(
                f"✅ Task added: **{res.get('title')}** → `{res.get('list')}`"
                f"{added_lbl}{due_txt}")
        except Exception as e:
            await interaction.followup.send(f"dotask error: {e}")

    @bot.tree.command(name="done", description="Move a Trello task to Done (by title)")
    async def done_cmd(interaction, title: str):
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message("Restricted channel.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            from integrations.trello import mark_done_by_title
            res = await asyncio.to_thread(mark_done_by_title, title)
            if res.get("ok"):
                await interaction.followup.send(
                    f"✅ **{res['title']}** moved to **Done** 🎉")
            else:
                await interaction.followup.send(f"⚠️ {res.get('error')}")
        except Exception as exc:
            await interaction.followup.send(f"done error: {exc}")

    @bot.tree.command(name="commit", description="Submit code (commit+push)")
    async def commit_cmd(interaction, files: str, message: str):
        """files: comma/space separated relative paths (in the repo).
        The current file contents are read from the workspace; this is a
        thin wrapper the team uses to push a set of files with a good message."""
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message("Restricted channel.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            if not gh_fn:
                await interaction.followup.send("GitHub hook not configured yet.")
                return
            # resolve the file list
            from integrations import github as _gh
            fpaths = [p.strip() for p in files.replace(",", " ").split() if p.strip()]
            res = await _gh_submit(fpaths, message)
            await interaction.followup.send(
                f"✅ Committed to `{res.get('branch')}` ({len(fpaths)} file(s)).\n"
                f"Message: `{res.get('message')}`\nAuthor: `{res.get('author')}`")
        except Exception as e:
            await interaction.followup.send(f"commit error: {e}")

    @bot.tree.command(name="review", description="Review a change against the architecture")
    async def review_cmd(interaction, target: str = ""):
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message("Restricted channel.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            if not review_fn:
                await interaction.followup.send("Review hook not configured yet.")
                return
            res = await review_fn(target)
            await interaction.followup.send(res.get("text", "(no review)"))
        except Exception as e:
            await interaction.followup.send(f"review error: {e}")

    @bot.tree.command(name="register", description="Register your name/email/trello/github so JARVIS knows you")
    async def register_cmd(interaction, name: str, email: str,
                           trello_user: str = "", github_user: str = ""):
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message("Restricted channel.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            store = _load_members()
            store[str(interaction.user.id)] = {
                "name": name, "email": email,
                "trello_user": trello_user, "github_user": github_user,
                "discord_name": interaction.user.name,
            }
            _save_members(store)
            await interaction.followup.send(
                f"✅ Registered **{name}**! Now I know you and will attribute commits to you 🙌")
        except Exception as e:
            await interaction.followup.send(f"register error: {e}")

    @bot.tree.command(name="ingest-doc", description="Owner: upload a project doc (Chapter..) into the RAG index (password-protected)")
    async def ingest_doc_cmd(interaction, password: str, document: discord.Attachment):
        if not RAG_INGEST_PASSWORD:
            await interaction.response.send_message(
                "Ingest is disabled (RAG_INGEST_PASSWORD not set in .env).", ephemeral=True)
            return
        if password != RAG_INGEST_PASSWORD:
            await interaction.response.send_message(
                "🔒 Wrong password — I can't accept that document.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            raw = await document.read()
            from rag import service as rag
            # PDFs (thesis chapters) are parsed + chunked per-page for provenance.
            n = await rag.ingest_file(document.filename, raw)
            if n == 0:
                await interaction.followup.send(
                    "Couldn't read text from the file. Send a `.pdf` / `.md` / `.txt` file.")
                return
            await interaction.followup.send(
                f"✅ Ingested **{document.filename}** into the RAG index "
                f"({n} chunks). Ask me with `/ask ...` about its content.")
        except Exception as e:
            await interaction.followup.send(f"ingest error: {e}")

    @bot.tree.command(name="sources", description="Owner: list the curated trusted sources")
    async def sources_cmd(interaction):
        if not _is_owner(interaction.user):
            await interaction.response.send_message(
                "Only the Owner/Lead may run this.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            from integrations.sources import list_sources, format_item
            curated = list_sources()
            if not curated:
                await interaction.followup.send(
                    "No curated sources yet. Add them with `/addsource <url> [title]`.")
                return
            await interaction.followup.send(
                f"🔎 **{len(curated)} trusted source(s):**\n\n" +
                "\n\n".join(format_item({"type": "repo", "title": s.get("title", ""),
                                          "link": s.get("url", ""), "note": s.get("category", "")})
                            for s in curated))
        except Exception as exc:
            await interaction.followup.send(f"sources error: {exc}")

    @bot.tree.command(name="addsource", description="Owner: add a trusted source (repo/article/link) to the list")
    async def addsource_cmd(interaction, url: str, title: str = "", category: str = "general"):
        if not _is_owner(interaction.user):
            await interaction.response.send_message(
                "Only the Owner/Lead may run this.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            from integrations.sources import add_source
            res = await asyncio.to_thread(add_source, url, title, category)
            if res.get("ok"):
                note = " (already in list)" if res.get("dup") else " added ✅"
                await interaction.followup.send(
                    f"🔖 **{res['title']}**{note}\n{url}")
            else:
                await interaction.followup.send(f"⚠️ {res.get('error')}")
        except Exception as exc:
            await interaction.followup.send(f"addsource error: {exc}")

    @bot.tree.command(name="remember", description="Teach JARVIS a fact/project detail (reusable in answers)")
    async def remember_cmd(interaction, fact: str):
        if not _is_owner(interaction.user):
            await interaction.response.send_message(
                "Only the Owner/Lead may teach me.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            from rag import service as rag
            await rag.remember(fact)
            await interaction.followup.send(
                f"✅ Got it — I'll remember that:\n> {fact}\n\n"
                f"Ask me later with `/ask ...` and I'll use it.")
        except Exception as e:
            await interaction.followup.send(f"remember error: {e}")

    @bot.tree.command(name="scaffold", description="Owner: fill the NELLY 7-layer structure into the repo")
    async def scaffold_cmd(interaction, repo: str = ""):
        if not _is_owner(interaction.user):
            await interaction.response.send_message(
                "Only the Owner/Lead may use this.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            if not scaffold_fn:
                await interaction.followup.send("Scaffold hook not configured yet.")
                return
            res = scaffold_fn(repo or None)
            if res.get("ok"):
                await interaction.followup.send(
                    f"✅ Scaffold **{res.get('repo')}**\n"
                    f"Added: `{len(res.get('added', []))}` files · "
                    f"Already present: `{len(res.get('updated', []))}`")
            else:
                await interaction.followup.send(f"⚠️ {res.get('error')}")
        except Exception as e:
            await interaction.followup.send(f"scaffold error: {e}")

    @bot.tree.command(name="guard", description="Run a full architecture check (F7)")
    async def guard_cmd(interaction):
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message("Restricted channel.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            if guard_hook:
                out = await guard_hook()
                await interaction.followup.send(out)
            else:
                await interaction.followup.send("Guard hook not configured yet.")
        except Exception as e:
            await interaction.followup.send(f"guard error: {e}")

    @bot.tree.command(name="report", description="Weekly productivity report")
    async def report_cmd(interaction):
        if not _allowed(interaction, interaction.guild):
            await interaction.response.send_message("Restricted channel.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            from scheduler.jobs import weekly_report
            from db import store
            out = await weekly_report(store)
            await interaction.followup.send(out)
        except Exception as e:
            await interaction.followup.send(f"report error: {e}")

    @bot.tree.command(name="alert", description="Owner: raise a manual architecture alert")
    async def alert_cmd(interaction, message: str):
        if not _is_owner(interaction.user):
            await interaction.response.send_message(
                "Only the Owner/Lead may use this.", ephemeral=True)
            return
        if alert_hook:
            from guard.compare import Deviation
            await interaction.response.send_message(alert_hook(Deviation(
                severity="high", kind="manual", message=message)))
        else:
            await interaction.response.send_message("Alert hook not configured.")

    # The channel where architecture alerts / task events are delivered to the
    # Owner + Leaders. Defaults to ALLOWED_CHANNEL (owner_chat in your setup).
    bot.alert_channel = ALERT_CHANNEL or ALLOWED_CHANNEL or "owner_chat"
    bot.alert_hook = alert_hook or _noop
    bot.task_notify = notify or _noop

    async def _post_boot_intro():
        """Post the one-time self-introduction to the owner/leader channel."""
        try:
            target = bot.alert_channel
            for guild in bot.guilds:
                for ch in guild.channels:
                    if (getattr(ch, "name", "") or "").lower() == target:
                        await ch.send(_INTRO)
                        _log("[intro] posted to", target)
                        return
        except Exception as e:
            _log("[intro-error]", e)

    @bot.event
    async def on_ready():
        """Positive confirmation we are truly online + sync slash commands."""
        print("===== JARVIS SUCCESSFULLY CONNECTED =====")
        print("JARVIS version:", JARVIS_BOT_VERSION)
        print("JARVIS is online and ready:", bot.user)
        print(f"[JARVIS] intents -> message_content={intents.message_content} "
              f"members={intents.members} guilds={intents.guilds}")
        print(f"[JARVIS] guilds={[g.name for g in bot.guilds]}")
        for g in bot.guilds:
            chans = [c.name for c in g.channels if getattr(c, 'name', None)]
            print(f"[JARVIS] guild '{g.name}' visible channels: {chans}")
        # Sync slash commands for EACH guild immediately so they show up fast.
        # (Global sync can lag; per-guild sync is instant.)
        for g in bot.guilds:
            try:
                await bot.tree.sync(guild=g)
                print(f"[JARVIS] synced slash commands for guild '{g.name}'.")
            except Exception as e:
                print(f"[JARVIS] sync error on '{g.name}': {e}")
        try:
            await bot.tree.sync()
            print(f"[JARVIS] synced {len(bot.tree.get_commands())} slash commands (global).")
        except Exception as e:
            print(f"[JARVIS] command sync error: {e}")
        # Post a one-time self-introduction on boot only if enabled (default OFF —
        # keep the owner chat clean; intro still appears on "who are you" / /help).
        if POST_INTRO_ON_BOOT and not getattr(bot, "_intro_sent", False):
            await _post_boot_intro()
            bot._intro_sent = True

    # ---------------- plain message handling (mention / reply / !cmd) ----------------
    @bot.event
    async def on_message(message):
        # Debug: echo every message (ON by default; set JARVIS_DEBUG=0 to mute).
        try:
            _log("[msg] ch=%s author=%s mentions=%s content=%r" % (
                getattr(message.channel, "name", "?"),
                message.author, bool(message.mentions),
                (message.content or "")[:60]))
        except Exception:
            pass

        if message.author.bot:
            return

        # ---------------- REPLY GATE ----------------
        # Only speak when genuinely addressed (@mention / DM / bot's own channel).
        # Anything else is ignored so JARVIS never spams a general channel.
        if not _should_respond(message):
            await bot.process_commands(message)
            return

        for att in message.attachments:
            await _handle_attachment(message, att)

        # ---------------- SMART handling: understand what the user wants ----------------
        try:
            from agent.smart import classify, parse_tasks
            intent = classify(message.content)
            _log(f"[intent] -> {intent}")

            # 1) Introduced / "who are you" -> self-introduction (English).
            if intent == "introduce":
                await message.channel.send(_INTRO)
                await bot.process_commands(message)
                return

            # 2) Greeting -> short friendly reply (not a task request).
            if intent == "greeting":
                await message.channel.send("👋 Hi! What do you need? Type `/` for commands.")
                await bot.process_commands(message)
                return

            # 3) Task request -> parse + create MANY cards in one message.
            if intent == "add_tasks" and bulk_fn:
                tasks = parse_tasks(message.content)
                _log(f"[tasks] parsed {len(tasks)} cards")
                if tasks:
                    results = await _with_timeout(asyncio.to_thread(bulk_fn, tasks),
                                                  timeout=45)
                    ok = [r for r in results if r.get("ok")]
                    bad = [r for r in results if not r.get("ok")]
                    lines = [f"✅ Added **{r['title']}** → `{r['list']}`"
                             + (f" · 🏷 {', '.join(r.get('labels', []))}" if r.get('labels') else "")
                             + (f" · 📅 {r.get('due')}" if r.get('due') else "")
                             for r in ok]
                    if bad:
                        lines.append(f"⚠️ Failed: {', '.join(b['title'] for b in bad)}")
                    await message.channel.send("\n".join(lines) or "No valid tasks found.")
                    await bot.process_commands(message)
                    return

            # 4) Register reminder — at most ONCE per user (per session).
            if not _REG_SENT_USERS.get(str(message.author.id)):
                reg = _register_or_greeting(message.author)
                if reg:
                    await message.channel.send(reg)
                    _REG_SENT_USERS[str(message.author.id)] = True

            # 5) Question / other -> smart reply via Gemini (background enhance).
            ack = await message.channel.send("🤖 ...")
            state = {
                "messages": [{"role": "user", "content": message.content}],
                "user_id": str(message.author.id),
                "guild_id": str(message.guild.id if message.guild else ""),
                "channel_id": str(message.channel.id),
            }
            async def _enhance():
                try:
                    from integrations.llm import generate, JARVIS_RULES
                    from rag import service as rag
                    context = await rag.build_context(message.content, top_k=6)
                    if context:
                        prompt = (
                            f"Answer using ONLY the context below. The context is "
                            f"NELLY project documentation — do NOT name any file "
                            f"(no .yaml/.pdf/blueprint). Just answer. If the context "
                            f"does not contain the answer, say you don't know.\n"
                            f"Reply in the same language as the question.\n\n"
                            f"CONTEXT:\n{context}\n\nQUESTION:\n{message.content}"
                        )
                        text = await generate(prompt, system=JARVIS_RULES)
                    else:
                        reply = await _with_timeout(agent_runner.run(state), timeout=30)
                        text = reply.get("reply_text", "")
                    if context and any(t in (text or "") for t in _NO_LLM_TAGS):
                        text = _context_answer(context, message.content)
                    if text:
                        await ack.edit(content=text)
                        _log(f"[enhance] -> {text[:80]}")
                except Exception as e:
                    _log("[enhance-error]", e)
            bot.loop.create_task(_enhance())
        except Exception as e:
            _log("[smart-error]", e)
            try:
                await message.channel.send(f"JARVIS error: {e}")
            except Exception:
                pass

        await bot.process_commands(message)

    async def _handle_attachment(message, att):
        name = (att.filename or "").lower()
        if name.endswith((".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mpeg")):
            path = f"/tmp/{att.filename}"
            await att.save(path)
            await message.channel.send(
                f"🎙 Received `{att.filename}` — transcribing & summarising…")
            try:
                from integrations.voice import summarize_audio, _fmt_summary
                data = await summarize_audio(path)
                await message.channel.send(_fmt_summary(data))
            except Exception as exc:
                await message.channel.send(f"⚠️ Voice summarise error: {exc}")
        else:
            await message.channel.send(f"Received attachment `{att.filename}`.")

    @bot.command(name="jarvis")
    async def jarvis_cmd(ctx):
        """@JARVIS ... — the bot's own, non-conflicting entry point."""
        await ctx.send("JARVIS is alive and ready. 🤖")

    bot.alert_hook = alert_hook or _noop
    return bot


def _member_file() -> str:
    return _os.getenv("MEMBER_MAP_FILE", "member_map.json")


def _load_members() -> dict:
    try:
        with open(_member_file(), "r", encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return dict(MEMBER_MAP)


def _save_members(store: dict) -> None:
    try:
        with open(_member_file(), "w", encoding="utf-8") as fh:
            _json.dump(store, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _whoami(author) -> dict:
    """Return the member record for a Discord user, or {} if unknown."""
    store = _load_members()
    return store.get(str(author.id), {})


def _register_or_greeting(author) -> Optional[str]:
    """If the user is known, nothing to do. If unknown, ask them to register."""
    rec = _whoami(author)
    if rec.get("name"):
        return None  # known
    name = getattr(author, "display_name", None) or getattr(author, "name", "")
    return (
        f"👋 Hi {name}! Please register so I know you:\n"
        "Type: `/register <name> <email> <trello_user> <github_user>`\n"
        "Example: `/register Maryam maryam@uni.edu maryam_t maryam-gh`\n"
        "After that I'll know where to place your tasks and attribute commits to you."
    )


async def _with_timeout(coro, timeout: float = 25, default=None):
    """Await a coroutine but give up (returning {}) after `timeout` seconds,
    so a slow/hung LLM never makes JARVIS silently stop replying."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return {}


def _is_wake(content: str) -> bool:
    """True if the message is a bare greeting to JARVIS (so it replies 'alive').
    Only matches a SHORT greeting at the start — not any sentence that merely
    contains the word 'jarvis'."""
    low = (content or "").strip().lower()
    if not low or len(low) > 80:
        return False
    return low.startswith(("hi jarvis", "hey jarvis", "hello jarvis",
                           "يا جارفيس", "اهلا جارفيس", "أهلا جارفيس",
                           "هاي جارفيس")) or low in ("jarvis", "جارفيس")


async def _gh_submit(fpaths, message):
    """Read current file contents from the repo checkout and submit them."""
    from integrations.github import submit_code
    import os
    files = {}
    for p in fpaths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as fh:
                files[p] = fh.read()
    if not files:
        raise RuntimeError("None of the given files exist in the workspace.")
    res = submit_code(files, message.split(), summarize=message)
    return res


def _noop(*args, **kwargs):
    return None


# Detects a Gemini quota/error placeholder so callers can fall back to the docs.
_NO_LLM_TAGS = ("[NO_LLM]", "[Gemini error]", "[local engine]")


def _context_answer(context: str, question: str, lang_note: str = "Based on the project documentation:") -> str:
    """Fallback: answer directly from the retrieved RAG context (no LLM).
    Flattens the chunks into a readable, sourced reply when Gemini is down."""
    import re
    ctx = (context or "").strip()
    if not ctx:
        return ""
    # Strip the "[doc, p.N] 'text'" wrapper into plain "- doc (p.N): text" lines.
    parts = []
    for m in re.finditer(r"\[([^\]]+)\]\s*'?(.*?)'?(?=\n\[|\Z)", ctx, flags=re.S):
        loc = m.group(1).strip()
        text = m.group(2).strip()
        if text:
            parts.append(f"• **{loc}:** {text[:400]}")
    body = "\n".join(parts) if parts else ctx
    return f"{lang_note}\n{body}\n\n_(Gemini is out of quota right now, so this is the raw documentation.)_"


async def run_bot(bot):
    await bot.login(DISCORD_TOKEN)
    await bot.connect()


def start_bot(bot):
    asyncio.run(bot.run(DISCORD_TOKEN))