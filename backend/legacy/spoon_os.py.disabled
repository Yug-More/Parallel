from typing import Dict
from openai import OpenAI
from config import CLIENTS, OPENAI_MODEL

TEAM = ["yug", "sean", "severin", "nayab"]
NAMES = {"yug":"Yug","sean":"Sean","severin":"Severin","nayab":"Nayab"}

def _chat_as(agent_id: str, sys_ctx: str, asker: str, prompt: str, temperature=0.35) -> str:
    client: OpenAI = CLIENTS[agent_id]
    name = NAMES.get(agent_id, agent_id.title())
    msgs = [
        {"role":"system","content": sys_ctx},
        {"role":"system","content": f"You are {name}. Provide your perspective."},
        {"role":"user","content": f"{asker} asks:\n{prompt}"},
    ]
    resp = client.chat.completions.create(model=OPENAI_MODEL, messages=msgs, temperature=temperature)
    return resp.choices[0].message.content

def ask_one(asker: str, prompt: str, sys_ctx: str, target: str) -> Dict[str,str]:
    return {target: _chat_as(target, sys_ctx, asker, prompt, 0.35)}

def ask_team(asker: str, prompt: str, sys_ctx: str) -> Dict[str,str]:
    return {m: _chat_as(m, sys_ctx, asker, prompt, 0.4) for m in TEAM}

def synthesize(asker: str, prompt: str, sys_ctx: str, drafts: Dict[str,str]) -> str:
    msgs = [
        {"role":"system","content":"You are the coordinator. Synthesize drafts into one clear answer with 2–5 next steps."},
        {"role":"system","content": sys_ctx},
        {"role":"user","content": f"Latest human message from {asker}:\n{prompt}"},
    ]
    for who, text in drafts.items():
        label = NAMES.get(who, who.title())
        msgs.append({"role":"assistant","content": f"{label} draft:\n{text}"})
    client = CLIENTS["coordinator"]
    resp = client.chat.completions.create(model=OPENAI_MODEL, messages=msgs, temperature=0.35)
    return resp.choices[0].message.content
