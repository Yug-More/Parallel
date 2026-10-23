from typing import Dict, TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from openai import OpenAI

from config import CLIENTS, OPENAI_MODEL

# ----- State schema required by StateGraph -----
class TeamState(TypedDict, total=False):
    sys_ctx: str
    asker: str
    prompt: str
    mode: Optional[str]
    target: Optional[str]
    drafts: Dict[str, str]
    synthesis: str

TEAM = ["yug", "sean", "severin", "nayab"]
NAMES = {"yug": "Yug", "sean": "Sean", "severin": "Severin", "nayab": "Nayab"}

def _chat_as(agent_id: str, sys_ctx: str, asker: str, prompt: str, temperature: float = 0.35) -> str:
    client: OpenAI = CLIENTS[agent_id]
    name = NAMES.get(agent_id, agent_id.title())
    msgs = [
        {"role": "system", "content": sys_ctx},
        {"role": "system", "content": f"You are {name}. Provide your perspective."},
        {"role": "user", "content": f"{asker} asks:\n{prompt}"},
    ]
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=msgs,
        temperature=temperature,
    )
    return resp.choices[0].message.content

# ----- Nodes -----
def node_ask_one(state: TeamState) -> TeamState:
    target = state.get("target") or "yug"
    text = _chat_as(target, state["sys_ctx"], state["asker"], state["prompt"], 0.35)
    return {"drafts": {target: text}}

def node_ask_team(state: TeamState) -> TeamState:
    drafts: Dict[str, str] = {}
    for member in TEAM:
        drafts[member] = _chat_as(member, state["sys_ctx"], state["asker"], state["prompt"], 0.4)
    return {"drafts": drafts}

def node_synthesize(state: TeamState) -> TeamState:
    drafts = state.get("drafts", {})
    msgs = [
        {"role": "system", "content": "You are the coordinator. Synthesize drafts into one clear answer with 2–5 next steps."},
        {"role": "system", "content": state["sys_ctx"]},
        {"role": "user", "content": f"Latest human message from {state['asker']}:\n{state['prompt']}"},
    ]
    for who, text in drafts.items():
        label = NAMES.get(who, who.title())
        msgs.append({"role": "assistant", "content": f"{label} draft:\n{text}"})

    client: OpenAI = CLIENTS["coordinator"]
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=msgs,
        temperature=0.35,
    )
    return {"synthesis": resp.choices[0].message.content}

# ----- Wrapper to match main.py expectations -----
class _Compiled:
    def __init__(self, graph):
        self._graph = graph
        self._app = graph.compile()

    def invoke(self, inputs: Dict):
        return self._app.invoke(inputs)

    async def ainvoke(self, inputs: Dict):
        return await self._app.ainvoke(inputs)

class TeamGraph:
    def __init__(self):
        self._entry = "ask_team"

    def set_entry_point(self, name: str):
        if name not in ("ask_one", "ask_team", "synthesize"):
            raise ValueError(f"Unknown entry point: {name}")
        self._entry = name

    def compile(self):
        g = StateGraph(state_schema=TeamState)

        if self._entry == "ask_one":
            g.add_node("ask_one", node_ask_one)
            g.add_edge(START, "ask_one")
            g.add_edge("ask_one", END)

        elif self._entry == "ask_team":
            g.add_node("ask_team", node_ask_team)
            g.add_edge(START, "ask_team")
            g.add_edge("ask_team", END)

        elif self._entry == "synthesize":
            g.add_node("synthesize", node_synthesize)
            g.add_edge(START, "synthesize")
            g.add_edge("synthesize", END)

        return _Compiled(g)

def build_team_graph() -> TeamGraph:
    return TeamGraph()
