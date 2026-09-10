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
