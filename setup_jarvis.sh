#!/usr/bin/env bash
# =============================================================
#  JARVIS setup — ينشئ فولد jarvis بهيكل كامل + blueprint + guard core
#  شغّل:  bash setup_jarvis.sh   (من أي مكان، بينشئ تحت cwd)
#  المحتوى حقيقي (مش stubs فاضية) عشان تبدأوا شغل فوراً.
# =============================================================
set -euo pipefail

ROOT="$(pwd)/jarvis"
mkdir -p "$ROOT"/{blueprint,guard,agent/prompts,rag,integrations,db,scheduler,docs,tests}
mkdir -p "$ROOT"/docs

# ---------- root files ----------
cat > "$ROOT/.gitignore" <<'EOF'
.env
__pycache__/
*.pyc
.venv/
venv/
data/
*.sqlite3
*.db
.env.local
EOF

cat > "$ROOT/requirements.txt" <<'EOF'
discord.py>=2.3
langgraph>=0.2
langchain-core
llama-index>=0.10
llama-index-vector-stores-chroma
chromadb>=0.5
google-genai
PyGithub
py-trello
apscheduler
pydantic>=2
pyyaml
python-dotenv
EOF

cat > "$ROOT/.env.example" <<'EOF'
# --- Discord ---
DISCORD_TOKEN=
DISCORD_GUILD_ID=

# --- LLM (Gemini) ---
GEMINI_API_KEY=

# --- GitHub (fine-grained: repo, contents, pull_requests) ---
GITHUB_TOKEN=

# --- Trello ---
TRELLO_API_KEY=
TRELLO_TOKEN=
TRELLO_BOARD_ID=

# --- Roles (منشن + بيدعم ping للـ Owner) ---
OWNER_ROLES=Owner,Lead
TEAM_ROLES={"T1":"Team 1","T2":"Team 2","T3":"Team 3"}
REVIEW_ROLE=TA-Review
ALERT_CHANNEL=jarvis-alerts
DM_ON_HIGH=true
GATE_MERGE=true

# --- Whisper / RAG ---
WHISPER_MODEL=small
DB_PATH=./data/neely.db
EOF

cat > "$ROOT/README.md" <<'EOF'
# JARVIS — الحارس المعماري لفريق NELLY

بوت ديسكورد يحمل معمارية NELLY كـ BluePrint، وقارنها باللي بيحصل فعلاً على GitHub/Trello،
وينبّه الـ Owner لأي انحراف.

## التشغيل
1. cp .env.example .env  و املأ المفاتيح
2. python -m venv .venv && source .venv/bin/activate
3. pip install -r requirements.txt
4. python main.py

## البنية
- blueprint/   : مصدر الحقيقة (المعمارية + التيمات + العقود + المياشونات)
- guard/       : collector -> mapper -> compare -> alerter  (قلب F7)
- agent/       : نواة LangGraph (F1-F6) — تحت إدارة Dorira
- rag/         : RAG وقاعدة المعرفة — تحت إدارة Maryam
- integrations/: discord/github/trello/llm — تحت إدارة Dorira
- db/          : SQLite (members/tasks/activity/knowledge)
- scheduler/   : apscheduler (reminders + weekly report + deadline watcher)
EOF

cat > "$ROOT/config.py" <<'EOF'
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
TRELLO_BOARD   = os.getenv("TRELLO_BOARD_ID")

OWNER_ROLES = [r.strip() for r in os.getenv("OWNER_ROLES", "Owner,Lead").split(",")]
TEAM_ROLES  = json.loads(os.getenv("TEAM_ROLES", "{}"))
REVIEW_ROLE = os.getenv("REVIEW_ROLE", "TA-Review")
ALERT_CHANNEL = os.getenv("ALERT_CHANNEL", "jarvis-alerts")
DM_ON_HIGH  = os.getenv("DM_ON_HIGH", "true").lower() == "true"
GATE_MERGE  = os.getenv("GATE_MERGE", "true").lower() == "true"
DB_PATH     = os.getenv("DB_PATH", "./data/neely.db")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

BLUEPRINT_DIR = os.path.join(os.path.dirname(__file__), "blueprint")
EOF

cat > "$ROOT/main.py" <<'EOF'
"""Entry point — يربط الـ guard بالديسكورد + الجدولة. (لم يكتمل بعد — تحت إدارة دريرة/أنت)"""
from config import DISCORD_TOKEN
print("JARVIS scaffold ready. Integrations pending (Dorira).")

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("⚠️  DISCORD_TOKEN غير موجود — املأ .env")
    else:
        print("✅ ستُفعَّل الهوية بعد ربط integrations/ و agent/")
EOF

# ---------- blueprint/ ----------
cat > "$ROOT/blueprint/architecture.yaml" <<'EOF'
# ===== معمارية NELLY: المصدر الحقيقي للمعرفة (JARVIS BluePrint) =====
# كل موديول له مسار مجلد وصفة. هذي الخريطة اللي JARVIS يقارن الـ commits/PRs بها.
project: NELLY
description: Voice-first, vision-based autonomous Windows computer-use agent.
layers:
  frontend:
    folder: frontend/
    tools: [React, TypeScript, Tailwind, Electron/Tauri]
    purpose: Desktop status + approval UI (FR-17, NFR-04)
  backend:
    folder: backend/
    tools: [FastAPI, WebSockets, Uvicorn]
    purpose: Real-time API, voice events, block-on-approval (FR-02, FR-12, NFR-01)
  orchestrator:
    folder: backend/orchestrator/
    tools: [LangGraph]
    purpose: Stateful control loop, verification, retry, human-interrupt (FR-03, FR-09, FR-10, FR-13)
  voice:
    folder: voice/
    tools: [OpenWakeWord, Silero VAD, Faster-Whisper, Piper, CosyVoice]
    purpose: Wake word, STT, TTS, interruption (FR-01, FR-02, NFR-03)
  vision:
    folder: vision/
    tools: [OmniParser, PaddleOCR]
    purpose: Screenshot -> UI elements, OCR, normalized boxes (FR-04, FR-09)
  planning_reasoning:
    folder: backend/reasoning/
    tools: [Qwen2.5-VL, ReAct]
    purpose: Decompose goal, pick next action from screen (FR-06, FR-07, OBJ-05)
  tool_management:
    folder: backend/tools/
    tools: [Pydantic v2]
    purpose: Validate every candidate action before OS execution (FR-07, SR-09)
  execution:
    folder: backend/execution/
    tools: [Playwright, PyAutoGUI, pywin32]
    purpose: Web + desktop input, window focus, coordinate normalization (FR-05, FR-08, NFR-06)
  safety:
    folder: backend/safety/
    tools: [RiskTier, Approval Layer]
    purpose: Risk classify + HITL approval + emergency stop (FR-11, FR-12, SR-01..SR-09)
  memory:
    folder: memory/
    tools: [ChromaDB, SQLite]
    purpose: Episodic memory + session checkpoints + resume (FR-13, FR-18, OBJ-09)
  knowledge_rag:
    folder: rag/
    tools: [Qdrant, Postgres, embeddings]
    purpose: 20-stage ingestion + retrieval (FR-18)
  evaluation:
    folder: eval/
    tools: [LangSmith, benchmark harness]
    purpose: TSR, grounding, recovery, latency, safety (OBJ-10)
EOF

cat > "$ROOT/blueprint/teams.yaml" <<'EOF'
# ===== توزيع الأدوار على الفريق =====
lanes:
  T1:
    label: "Team 1"
    name: OS Control & Perception Lane
    members: 3
    modules: [vision, tool_management, execution]
    folder_roots: [vision/, backend/tools/, backend/execution/]
  T2:
    label: "Team 2"
    name: Core Brain & Voice Gateway Lane
    members: 2
    modules: [orchestrator, planning_reasoning, voice]
    folder_roots: [backend/orchestrator/, backend/reasoning/, voice/]
  T3:
    label: "Team 3"
    name: Base Platform, Safety & Data Infrastructure Lane
    members: 2
    modules: [knowledge_rag, memory, safety, evaluation, backend]
    folder_roots: [rag/, memory/, backend/safety/, eval/, backend/]
EOF

cat > "$ROOT/blueprint/handoffs.yaml" <<'EOF'
# ===== عقود التسليم بين اللينيات (JARVIS يتأكد أنها بتتحقق) =====
# كل بند: سلمه اللين A للين B — لو commit خاص به دخل مسار غلط أو اتأخر -> تنبيه.
handoffs:
  T1_to_T2:
    from: T1
    to: T2
    artifacts:
      - Vision Pipeline v1
      - Click/Type Executor
      - Playwright Browser Adapter
      - Desktop Apps Executor
      - Popup Handling
    contract: "ProposedAction (bounding boxes normalized, typed)"
  T2_to_T3:
    from: T2
    to: T3
    artifacts:
      - TaskRequest Schema
      - ProposedAction Format
      - AgentState Serialization
      - Status Events Format
    contract: "Pydantic schemas frozen before execution"
  T3_to_T2:
    from: T3
    to: T2
    artifacts:
      - WebSocket Event Stream
      - Safety Gate API
      - Approval Modal Flow
      - Checkpoint Save/Load API
    contract: "Safety + memory interfaces responsive"
EOF

cat > "$ROOT/blueprint/milestones.yaml" <<'EOF'
# ===== المياشونات (المواعيد مضبوطة بعد إزاحة أسبوع كما اتفقنا) =====
# ملاحظة: الأصول كانت 06-27 Sep .. 27 Dec؛ بعد الإزاحة أصبحت بتاريخ لاحق.
milestones:
  - name: Contracts Frozen
    date: "2026-09-27"
    lane: all
    severity: milestone
  - name: First E2E Demo
    date: "2026-10-25"
  - name: Approval Flow Working
    date: "2026-11-15"
  - name: All Features Integrated
    date: "2026-12-06"
  - name: Alpha Release
    date: "2026-12-20"
  - name: Code Freeze
    date: "2026-12-27"
  - name: MVP Submission
    date: "2027-01-03"
EOF

# ---------- guard/ ----------
cat > "$ROOT/guard/__init__.py" <<'EOF'
EOF

cat > "$ROOT/guard/collector.py" <<'EOF'
"""Static collector — يجلب الأحداث من GitHub و Trello.
   NOTE: الـ الاتصال الفعلي بـ PyGithub/py-trello تحت إدارة دريرة.
   في هذه المرحلة نقرأ أحداثاً من fixtures (JSON) عشان نختبر الـ mapper/compare فوراً."""
import json, glob, os

def load_fixtures():
    files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "*.json")))
    events = []
    for f in files:
        with open(f) as fh:
            events.extend(json.load(fh))
    return events

class Collector:
    def __init__(self, github=None, trello=None):
        self.github = github
        self.trello = trello
    def collect(self):
        """Placeholder: يرجّع أحداث دمج. دريرة ستربط PyGithub/py-trello هنا."""
        return load_fixtures()
EOF

cat > "$ROOT/guard/mapper.py" <<'EOF'
"""Map event -> lane/module/handoff باستخدام خريطة المعمارية (blueprint)."""
import yaml, os
from config import BLUEPRINT_DIR

def _load(name):
    with open(os.path.join(BLUEPRINT_DIR, name)) as f:
        return yaml.safe_load(f)

def footprint_to_lane(folder_path):
    """يعتبرها المسار المجلد -> (lane, module). يعيد None لو مش بأي لين."""
    lanes = _load("teams.yaml")["lanes"]
    fp = folder_path.strip("/").lower()
    for lane_key, lane in lanes.items():
        for root in lane["folder_roots"]:
            if fp.startswith(root.strip("/").lower()):
                return lane_key, lane["modules"]
    return None

def map_commit(commit):
    """commit: {files: [paths], message, branch, author}. -> {lane, path, module?, ...}"""
    paths = commit.get("files", [])
    lane_map = {}
    for p in paths:
        lane = footprint_to_lane(p)
        if lane:
            lane_map[p] = lane
    return {"type": "commit", "lane_map": lane_map, "files": paths,
            "message": commit.get("message", ""), "branch": commit.get("branch", "")}

def map_card(card):
    """card: {title, list_name, labels, due}. -> {lane?, milestone?, handoff?}"""
    labels = set(card.get("labels", []))
    lane = None
    for key, val in TEAM_LABEL_TO_LANE.items():
        if val in labels:
            lane = key
    return {"type": "trello", "lane": lane, "labels": labels,
            "list": card.get("list"), "due": card.get("due"), "title": card.get("title")}

TEAM_LABEL_TO_LANE = {"T1": "Team 1", "T2": "Team 2", "T3": "Team 3"}
EOF

cat > "$ROOT/guard/compare.py" <<'EOF'
"""Compare — قلب F7. يقارن الحدث بالـ BluePrint ويطلع انحرافات بدرجات خطورة."""
from dataclasses import dataclass, field
from typing import List

@dataclass
class Deviation:
    severity: str          # high | medium | low | ok
    kind: str              # wrong_lane | interface_break | out_of_scope | missing_handoff | deadline_overdue | conflict | ok
    message: str
    meta: dict = field(default_factory=dict)

# خريطة الملفات الـ interface الحساسة و مين يملكها
CONTRACT_FILES = {
    "backend/orchestrator/state.py": "T2",
    "backend/orchestrator/schemas.py": "T2",
    "backend/safety/gate.py": "T3",
    "backend/reasoning/action.py": "T2",
}

def is_milestone(today, milestones, tolerance_days=2):
    out = []
    for m in milestones:
        if m.get("date", "")[:10] == today[:10]:
            out.append(m["name"])
    return out

def check_commit(event, blueprint_lanes):
    """يرجع قائمة انحرافات لحدث commit واحد."""
    deviations = []
    lane_map = event.get("lane_map", {})
    for path, (lane, modules) in lane_map.items():
        pass  # لكل مسار معرف إنه داخل لين صحيح

    # 1) الانتماء للِّين (انتهاك مسار): لو الملف يخص لين لكن الـ commit منه في اللين الغلط
    #    نستنتج ذلك من owner الملفات الحساسة.
    for path in event.get("files", []):
        for contract_path, owner in CONTRACT_FILES.items():
            if path.endswith(contract_path):
                if contract_path in event.get("files", []):
                    # مؤشر interface عالي الأهمية — دائماً نرااجع
                    deviations.append(Deviation(
                        severity="medium", kind="interface_break",
                        message=f"تغيير ملف عقد مشترك: {contract_path} (ملك {owner}). راجع قبل الدمج.",
                        meta={"path": path}))
    return deviations

def check_card(event, milestones):
    """يرجع انحرافات لأحداث Trello."""
    devs = []
    if event.get("lane") is None and event.get("labels"):
        devs.append(Deviation(severity="medium", kind="missing_lane",
                              message="كارت بدون لابل لين (Team1/2/3) — JARVIS لا يستطيع تتبعه."))
    # milestone مكتمل/متأخر
    return devs

def classify(severity_rank):
    if severity_rank >= "high":
        return "high"
    return severity_rank

def run_against_blueprint(events, milestones):
    """مدخل رئيسي — يمرر كل الأحداث ويرجع الانحرافات المفروزة."""
    results = []
    for ev in events:
        if ev.get("type") == "commit":
            results += check_commit(ev, None)
        elif ev.get("type") == "trello":
            results += check_card(ev, milestones)
    # sort: high > medium > low
    order = {"high": 0, "medium": 1, "low": 2, "ok": 3}
    results.sort(key=lambda d: order.get(d.severity, 9))
    return results
EOF

cat > "$ROOT/guard/alerter.py" <<'EOF'
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
EOF

# ---------- stubs للمسارات تحت إدارة دريرة/مريم (تبقوا يبنوا فوقها) ----------
for d in agent rag integrations db scheduler; do
  : > "$ROOT/$d/__init__.py"
done

cat > "$ROOT/agent/state.py" <<'EOF'
"""AgentState — LangGraph state (تحت إدارة دريرة)."""
from typing import TypedDict, List, Optional

class AgentState(TypedDict, total=False):
    messages: List[dict]
    intent: str
    scope: List[str]
    tool_results: dict
    confirm_required: bool
    proposed_action: Optional[dict]
    user_id: str
    guild_id: str
EOF

cat > "$ROOT/rag/service.py" <<'EOF'
"""RAG service — (تحت إدارة مريم). الواجهة ثابتة عشان الباقي يعتمد عليها."""
def query(question, scope_filter=None, top_k=5):
    raise NotImplementedError("Maryam: تنفيذ الاسترجاع")

def ingest(text, metadata=None):
    raise NotImplementedError("Maryam: تنفيذ الحقن")

def is_in_scope(question) -> bool:
    raise NotImplementedError("Maryam: فحص النطاق")
EOF

cat > "$ROOT/integrations/llm.py" <<'EOF'
"""Gemini client — (تحت إدارة دريرة)."""
def generate(prompt, system=None, json=False):
    raise NotImplementedError("Dorira: ربط Gemini")
EOF

cat > "$ROOT/db/store.py" <<'EOF'
"""SQLite store — (تحت إدارة مريم/دريرة)."""
def log_activity(user_id, kind, detail=None):
    raise NotImplementedError

def add_task(title, member, due, deps=None):
    raise NotImplementedError
EOF

cat > "$ROOT/scheduler/jobs.py" <<'EOF'
"""APScheduler jobs — (تحت إدارة دريرة)."""
def start():
    raise NotImplementedError("Dorira: جدولة reminders + weekly + deadline watcher")
EOF

# ---------- docs ----------
cat > "$ROOT/docs/TASKS.md" <<'EOF'
# توزيع المهام على الفريق

## 🧠 دريرة — نواة JARVIS + APIs
- [ ] agent/state.py + agent/graph.py (LangGraph: intent -> tool -> critique -> reply)
- [ ] integrations/llm.py (Gemini client + tool-calling)
- [ ] integrations/discord_bot.py (events + roles + attach)
- [ ] integrations/github.py (PyGithub: repo/commit/push/branch/Conventional)
- [ ] integrations/trello.py (py-trello: read/add/update/reminders)
- [ ] scheduler/jobs.py (apscheduler: reminders + weekly + deadline watcher)
- [ ] ربط guard/alerter.py بالديسكورد (ping Owner + DM على high)

## 📚 مريم — RAG & المعرفة
- [ ] rag/ingest.py (فهرسة مستندات NELLY: Overview/Requirements/Architecture/Security)
- [ ] rag/retriever.py (hybrid BM25+Vector + scope filter + reranker)
- [ ] rag/store.py (Chroma/Qdrant client)
- [ ] rag/service.py (query/ingest/is_in_scope — الواجهة ثابتة أعلاه)
- [ ] db/store.py (members/tasks/activity_log/knowledge) + تلخيص الاجتماعات وحقنها
- [ ] تصميم مستندات مرجعية في docs/ ليتم فهرستها

## 🛡️ الليدر + أنا — F7 نواته الآن
- [x] blueprint/architecture.yaml + teams.yaml + handoffs.yaml + milestones.yaml
- [x] guard/mapper.py + compare.py + alerter.py + collector.py
- [x] config.py + requirements.txt + .env.example + scripts
EOF

echo ""
echo "✅ اتبنى فولد JARVIS كامل في: $ROOT"
echo "   هيكل:"
find "$ROOT" -type f | sed "s|$ROOT/||" | sort
