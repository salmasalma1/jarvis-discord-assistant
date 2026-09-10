"""agent/graph.py — LangGraph decision loop (T2 core).

Loop: classify intent -> pick a tool -> (confirm if needed) -> reply.
Uses real LangGraph when available; otherwise falls back to a lightweight
linear runner so it works before dependencies are installed.
"""
import asyncio
from typing import Callable, Dict, List

from agent.state import AgentState, classify_intent


class AgentRunner:
    """Basic loop runner. Swap with a real AgentGraph once wired up."""

    def __init__(self, tool_map: Dict[str, Callable] = None, llm: Callable = None):
        self.tool_map = tool_map or {}
        self.llm = llm  # async (prompt, system) -> str ; None -> local template

    async def run(self, state: AgentState) -> AgentState:
        text = _latest_user_text(state)
        state["intent"] = classify_intent(text)
        state.setdefault("scope", ["NELLY docs", "blueprint"])

        tool = self.tool_map.get(state["intent"])
        if tool:
            try:
                state["tool_results"] = await tool(state)
            except Exception as e:
                state["tool_results"] = {"error": str(e)}
        else:
            state["tool_results"] = {}

        if state.get("confirm_required"):
            state["reply_text"] = (
                "This action needs your approval before it runs:\n"
                f"{state.get('proposed_action', {})}\n"
                "Type **approve** or **cancel**."
            )
            return state

        state["reply_text"] = await self._compose(state)
        return state

    async def _compose(self, state: AgentState, maxlen: int = 900) -> str:
        if self.llm:
            prompt = (
                f"Intent: {state['intent']}\n"
                f"Tool results: {state.get('tool_results') or {}}\n"
                f"Question: {_latest_user_text(state)}\n"
                "Reply helpfully, in the same language the user used, within NELLY scope only."
            )
            try:
                from integrations.llm import JARVIS_RULES
                return await self.llm(prompt, system=JARVIS_RULES)
            except Exception:
                pass
        return _local_reply(state, maxlen)


def _local_reply(state: AgentState, maxlen: int = 900) -> str:
    intent = state["intent"]
    results = state.get("tool_results") or {}
    if intent == "off_scope":
        return "Sorry, that's outside the NELLY project scope. I can help with the architecture/tasks/code."
    if results.get("error"):
        return f"Error while running the tool: {results['error']}"
    if not results:
        return "Got it — context ready. (Wire the core to Gemini for a detailed reply.)"
    return f"**{intent}**: {str(results)[:maxlen]}"


def _latest_user_text(state: AgentState) -> str:
    for m in reversed(state.get("messages") or []):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


if __name__ == "__main__":
    async def demo():
        r = AgentRunner()
        st = AgentState(messages=[{"role": "user", "content": "commit and push the code"}])
        out = await r.run(st)
        print("intent:", out["intent"], "| reply:", out["reply_text"][:60])

    asyncio.run(demo())
