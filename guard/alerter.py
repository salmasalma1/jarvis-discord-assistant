"""Alerter — يبني رسالة التنبيه ويوجهها للـ Owner.
   NOTE: الإرسال الفعلي عبر discord.py (دريرة). هنا نبني الشكل + صياغة القناة/الـ DM."""
from config import OWNER_ROLES, DM_ON_HIGH, GATE_MERGE

def build_alert(dev):
    head = {"high": "🚨 [JARVIS · HIGH]", "medium": "📋 [JARVIS · MEDIUM]",
            "low": "ℹ️ [JARVIS]", "ok": "✅ [JARVIS]"}
    return (f"{head.get(dev.severity, '[JARVIS]')} — {dev.kind}\n"
            f"{dev.message}\n"
            f"الخطورة: {dev.severity.upper()}\n"
            + ("⛔ Merge متوقف حتى موافقة الـ Owner." if dev.severity == "high" and GATE_MERGE else ""))

def owners_mention(members, roles):
    return " ".join(m.mention for m in members if any(r in roles for r in OWNER_ROLES))

def should_dm(dev):
    return DM_ON_HIGH and dev.severity == "high"
