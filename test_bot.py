# ============================================================
# MINIMAL DÉTERMINISTIC TEST — no JARVIS, no agent, no LLM, no config.
# If this replies "PONG", Discord receiving+replying WORKS on your setup,
# and the bug is inside JARVIS logic. If it does NOT, the problem is
# Discord permissions / intents / environment — not the model.
# Run with:  python test_bot.py
# ============================================================
import asyncio, os, sys, traceback, datetime

# Load DISCORD_TOKEN straight from .env (no JARVIS import chain).
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN") or ""
LOG = "test_bot.log"
VER = "1.0"

def log(*a):
    s = " ".join(str(x) for x in a)
    print("[" + datetime.datetime.now().strftime("%H:%M:%S") + "] " + s)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass

import discord
from discord.ext import commands

# Enable EVERYTHING to rule out intent problems.
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!!", intents=intents)

@bot.event
async def on_ready():
    log(f"[READY] test bot v{VER} connected as {bot.user}")
    log(f"[READY] message_content intent = {intents.message_content}")
    log(f"[READY] guilds = {[g.name for g in bot.guilds]}")
    log("=== READY (try sending a message in owner_chat) ===")

@bot.event
async def on_message(message):
    try:
        log(f"[GOT] ch={getattr(message.channel,'name','?')} from={message.author} content={ (message.content or '')[:60]!r}")
    except Exception as e:
        log("[got-log-error]", e)
    if message.author.bot:
        return
    try:
        await message.channel.send("PONG")
        log("[SENT] PONG reply")
    except Exception as e:
        log("[SEND-ERROR]", e)

async def main():
    if not TOKEN:
        log("[FATAL] DISCORD_TOKEN not found in .env")
        return
    log(f"Starting test bot v{VER}, token tail = ...{TOKEN[-5:]}")
    try:
        await bot.start(TOKEN)
    except Exception as e:
        log("[FATAL] start failed:", e)
        traceback.print_exc()

if __name__ == "__main__":
    log("=== TEST BOT START (v%s) ===" % VER)
    asyncio.run(main())
