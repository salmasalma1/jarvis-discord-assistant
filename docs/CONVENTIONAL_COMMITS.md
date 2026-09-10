# 📐 دليل رسائل الـ Conventional Commits (مرجع دريرة — F2)

بخّص من `integrations/commit_gen.py`. الصيغة المعيارية:

```
<type>(<scope>): <subject>
```

| type | متى | أمثلة |
|---|---|---|
| `feat` | ميزة جديدة | `feat(vision): add normalized bounding box to ProposedAction` |
| `fix` | إصلاح خلل | `fix(orchestrator): stop infinite retry after popup` |
| `refactor` | إعادة هيكلة بلا تغيير سلوك | `refactor(reasoning): extract next-action selector` |
| `docs` | توثيق | `docs(handoffs): freeze TaskRequest schema` |
| `test` | اختبارات | `test(execution): add DPI 150% click test` |
| `ci` | CI/build | `ci: pin deps with hash check` |
| `chore` | تبعيات/بناء | `chore: add pyproject` |

## قواعد
- **scope** = الموديول (من خريطة المعمارية): `vision`, `orchestrator`, `safety`, `rag`...
- **subject**: فعل أمر بـ lowercase، ≤ ~72 حرف، بدون نقطة آخر.
- **جسم** (اختياري) يكمل الـ "لماذا".
- **closes `TRELLO-N`** يسدّ المهمة تلقائياً في Trello (F3).
- **Refs: #PR** يربط بالـ PR.

## الاختيار التلقائي للفرع (من `choose_branch`)
- مهمة مرتبطة → `feature/<task>`
- إصلاح مرتبط → `fix/<task>`
- بلا مهمة على `main` → `dev`

## الربط بـ Gemini (اختياري)
أرسل `diff_paths + summary` إلى `generate_message(..., summarize=<نص من Gemini>)`
ليوسّع الجسم بوصف أوضح؛ **مع ذلك فالـ title و type و scope محسوبة محلياً** — لا اعتماد على الـ LLM في الصحة.
