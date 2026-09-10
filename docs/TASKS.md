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
