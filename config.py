"""JARVIS config — يقرأ من البيئة و يعرّف الأدوار."""
import os, json
from dotenv import load_dotenv
load_dotenv()

DISCORD_TOKEN  = os.getenv("DISCORD_TOKEN")
DISCORD_GUILD  = os.getenv("DISCORD_GUILD_ID")
GEMINI_KEY     = os.getenv("GEMINI_API_KEY")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN   = os.getenv("TRELLO_TOKEN")
TRELLO_BOARD   = os.getenv("TRELLO_BOARD_ID", "I82K5JMO")

# Public links shared by /links so the team can always find things.
# Baked-in defaults (your real repo + Trello board) — overridable via .env.
REPO_URL         = os.getenv("REPO_URL", "https://github.com/salmasalma1/NELLY")
TRELLO_BOARD_URL = os.getenv("TRELLO_BOARD_URL", "https://trello.com/b/I82K5JMO/grad-prj")
# Docs default to the repo's docs/ folder; only shown if it is a REAL, distinct link.
DOCS_URL         = os.getenv("DOCS_URL", "").strip()
# Auto build the Trello board URL from the board ID if the full URL is missing.
if not TRELLO_BOARD_URL and TRELLO_BOARD:
    TRELLO_BOARD_URL = f"https://trello.com/b/{TRELLO_BOARD}"

OWNER_ROLES = [r.strip() for r in os.getenv("OWNER_ROLES", "Owner,Lead").split(",")]
# Board labels that map to reviewer/TA review (matches your Trello board).
REVIEWER_LABEL = os.getenv("REVIEWER_LABEL", "Reviewer / TA")
# Canonical team label names (match your Trello board).
TEAM_LABELS = ["Team 1", "Team 2", "Team 3", "All Teams", "Milestone", "Handoff",
               REVIEWER_LABEL]
# Restrict the bot to a single channel (e.g. "#owner") while you test.
# Leave empty to allow all channels. Set to a channel name (with or without #).
ALLOWED_CHANNEL = os.getenv("ALLOWED_CHANNEL", "").lstrip("#").strip().lower()
TEAM_ROLES  = json.loads(os.getenv("TEAM_ROLES", "{}"))
REVIEW_ROLE = os.getenv("REVIEW_ROLE", "TA-Review")
ALERT_CHANNEL = os.getenv("ALERT_CHANNEL", "owner_chat")  # where Owner/Leaders get alerts
# Channels where JARVIS is allowed to reply to normal (un@mentioned) messages.
# Still replies everywhere when @JARVIS'd or in a DM. Leave empty to reply only on
# mention/DM. Defaults to the alert channel.
# Channels where JARVIS is allowed to reply to normal (un-@mentioned) messages.
# Default EMPTY = reply ONLY on @JARVIS mention + DM (no spam in any channel).
# Set to a dedicated bot channel (e.g. "jarvis") to also allow plain chat there.
BOT_CHANNELS = [c.strip().lstrip("#") for c in os.getenv("BOT_CHANNELS", "").split(",") if c.strip()]
# Post the self-introduction to the owner/alert channel on boot. Default OFF
# (so the owner chat stays clean); the intro is still sent on "who are you" / /help.
POST_INTRO_ON_BOOT = os.getenv("POST_INTRO_ON_BOOT", "0").lower() == "1"
# Password required to ingest a document into the RAG index (/ingest-doc).
# Only the owner + whoever she trusts (the one who knows the password) may upload.
# Leave empty to DISABLE the /ingest-doc command entirely.
RAG_INGEST_PASSWORD = os.getenv("RAG_INGEST_PASSWORD", "")
# Channel where JARVIS posts discovered external sources / newsletter items.
SOURCES_CHANNEL = os.getenv("SOURCES_CHANNEL", "repo")
DM_ON_HIGH  = os.getenv("DM_ON_HIGH", "true").lower() == "true"
GATE_MERGE  = os.getenv("GATE_MERGE", "true").lower() == "true"
DB_PATH     = os.getenv("DB_PATH", "./data/neely.db")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

# Member map: discord_id -> {name, email, trello_user, github_user, team}
# Seed with known users; JARVIS fills the rest by ASKING the member when it
# first talks to them (so it learns who it is talking to and can attribute
# their commits to them, and know who completed a task).
MEMBER_MAP = json.loads(os.getenv("MEMBER_MAP", "{}"))

BLUEPRINT_DIR = os.path.join(os.path.dirname(__file__), "blueprint")