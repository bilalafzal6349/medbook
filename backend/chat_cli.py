"""Chat with the bot in the terminal (no web server needed).

    python chat_cli.py            # interactive; add --debug to see NLU output and decisions
    python chat_cli.py --debug "salam" "mujhe kal skin specialist chahiye" "subah" ...
"""
import argparse
import json

from clinic_db import Clinic
from llm_agent import make_dialogue_manager
from nlu import NLU

ap = argparse.ArgumentParser()
ap.add_argument("--debug", action="store_true")
ap.add_argument("turns", nargs="*")
a = ap.parse_args()
clinic = Clinic()
dm = make_dialogue_manager(NLU(clinic.doctors()), clinic)   # MEDBOOK_DM=llm|rules|auto


def run(t):
    r = dm.handle("cli", t)
    print(f"\nUSER: {t}")
    if a.debug:
        n = r["nlu"]
        print(f"  [nlu] {n['intent']} ({n['intent_conf']}) dept={n.get('department')} ({n.get('department_conf')}) "
              f"slots={json.dumps(n['slots'], ensure_ascii=False)} rules={n['rules']}")
        for c in r.get("tool_calls", []):
            print(f"  [tool] {c['name']}({json.dumps(c['input'], ensure_ascii=False)}) -> "
                  f"{json.dumps(c['output'], ensure_ascii=False, default=str)[:300]}")
        for x in r["trace"]:
            print(f"  [dm] {x}")
    print("BOT:", r["reply"].replace("\n", "\n     "))


if a.turns:
    for t in a.turns:
        run(t)
else:
    while True:
        try:
            t = input("\n> ").strip()
        except EOFError:
            break
        if t:
            run(t)
