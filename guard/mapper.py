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
