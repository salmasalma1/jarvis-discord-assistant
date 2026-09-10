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
