"""LLM dialogue manager (llm_agent.py) with a scripted fake LLM, so the tests need no API key.
They check the code-level guards: only real slots, no write without the user's yes, no invented
booking numbers, the emergency hard stop, and the rules/LLM switch. Clock: Mon 23 Nov 2026 09:00."""
import json
import types

import pytest

from clinic_db import Clinic
from dialogue import DialogueManager
from llm_agent import (AnthropicProvider, LLMDialogueManager, ToolCall, Step, make_dialogue_manager,
                       parse_final)
from nlu import NLU


class Scripted:
    """Plays back LLM steps. Each step is ("tools", [(name, args), ...]) or ("final", reply, task, awaiting).
    An args value may be a function of the previous tool outputs (to use a slot_id the search returned)."""
    name, model = "scripted", "scripted"

    def __init__(self):
        self.queue, self.calls, self.outputs = [], 0, []

    def add(self, *steps):
        self.queue.extend(steps)

    def chat(self, system, tools, messages):
        self.calls += 1
        last = messages[-1]
        if last["role"] == "tool_results":
            self.outputs = [json.loads(x) for x in last["content"]]
        step = self.queue.pop(0)
        if step[0] == "tools":
            calls = [ToolCall(f"c{self.calls}_{i}", n, a(self.outputs) if callable(a) else a)
                     for i, (n, a) in enumerate(step[1])]
            return Step("", calls, {"role": "assistant", "content": "tools"}, {"input": 100, "output": 10})
        text = json.dumps({"reply": step[1], "task": step[2], "awaiting": step[3]})
        return Step(text, [], {"role": "assistant", "content": text}, {"input": 100, "output": 20})

    def user_message(self, text):
        return {"role": "user", "content": text}

    def assistant_text(self, text):
        return {"role": "assistant", "content": text}

    def tool_results(self, pairs):
        return [{"role": "tool_results", "content": [out for _, out, _ in pairs]}]


@pytest.fixture(scope="module")
def nlu():
    return NLU(Clinic().doctors())


@pytest.fixture()
def llm(nlu, tmp_path):
    return LLMDialogueManager(nlu, Clinic(tmp_path / "c.db"), Scripted())


def booked(dm):
    return [a for a in dm.clinic.all_appointments() if a["status"] == "booked" and a["session_id"] != "seed"]


def first_slot(outs):
    return outs[0]["slots"][0]["slot_id"]


def offer_and_propose(dm):
    p = dm.provider
    p.add(("tools", [("search_slots", {"department": "dermatology", "date_from": "2026-11-24",
                                       "time_from": "10:00", "time_to": "13:00"})]),
          ("final", "Ye slots free hain: 1, 2, 3", "book", "slot_choice"))
    r1 = dm.handle("s", "mujhe kal subah skin specialist ko dikhana hai")
    p.add(("tools", [("propose_booking", lambda o: {"slot_id": "S1", "patient_name": "Ali Raza",
                                                    "phone": "0300-1234567"})]),
          ("final", "Theek hai?", "book", "confirm"))
    r2 = dm.handle("s", "pehla wala, Ali Raza 0300-1234567")
    return r1, r2


def test_book_after_yes(llm):
    r1, r2 = offer_and_propose(llm)
    assert r1["tool_calls"][0]["name"] == "search_slots" and r1["tool_calls"][0]["output"]["slots"]
    assert "Book kar doon?" in r2["reply"]          # fixed summary is always shown
    assert r2["state"]["awaiting"] == "confirm" and not booked(llm)
    llm.provider.add(("tools", [("confirm_pending", {})]), ("final", "Ho gaya!", "none", "none"))
    r3 = llm.handle("s", "ji haan")
    b = booked(llm)
    assert len(b) == 1 and b[0]["department"] == "dermatology" and b[0]["phone"] == "03001234567"
    assert b[0]["ref"] in r3["reply"]               # real number from the database is in the reply
    assert r3["state"]["task"] is None and r3["state"]["awaiting"] is None


def test_confirm_refused_without_yes(llm):
    offer_and_propose(llm)
    llm.provider.add(("tools", [("confirm_pending", {})]), ("final", "Booked!", "none", "none"))
    r = llm.handle("s", "nahi, parson kar dein")
    assert not booked(llm)
    assert r["tool_calls"][0]["error"] and "not a clear yes" in r["tool_calls"][0]["output"]["error"]


def test_confirm_refused_same_turn(llm):
    """propose and confirm in one message: the user never saw the summary."""
    llm.provider.add(("tools", [("search_slots", {"department": "ent", "date_from": "2026-11-24"})]),
                     ("tools", [("propose_booking", {"slot_id": "S1", "patient_name": "Sara", "phone": "03211234567"})]),
                     ("tools", [("confirm_pending", {})]), ("final", "Done", "none", "none"))
    llm.handle("s", "ji kal ENT, Sara 03211234567, book kar dein")
    assert not booked(llm)


def test_stale_pending_refused(llm):
    offer_and_propose(llm)
    llm.provider.add(("final", "Kuch aur?", "book", "confirm"))
    llm.handle("s", "fees kitni hai")
    llm.provider.add(("tools", [("confirm_pending", {})]), ("final", "Done", "none", "none"))
    llm.handle("s", "ji")
    assert not booked(llm)


def test_invented_slot_refused(llm):
    llm.provider.add(("tools", [("propose_booking", {"slot_id": "S9", "patient_name": "Ali", "phone": "03001234567"})]),
                     ("final", "ok", "book", "confirm"))
    r = llm.handle("s", "kal 11 baje Dr Kamran, Ali 03001234567")
    assert "unknown slot_id" in r["tool_calls"][0]["output"]["error"]
    assert r["state"]["pending"] is None


def test_bad_phone_refused(llm):
    llm.provider.add(("tools", [("search_slots", {"department": "ent", "date_from": "2026-11-24"})]),
                     ("tools", [("propose_booking", {"slot_id": "S1", "patient_name": "Ali", "phone": "12345"})]),
                     ("final", "number?", "book", "PHONE"))
    r = llm.handle("s", "kal ENT, Ali 12345")
    assert "phone" in r["tool_calls"][1]["output"]["error"]


def test_invented_ref_removed(llm):
    llm.provider.add(("final", "Aapki booking MB-9999 ho gayi aur MB-1042 bhi theek hai", "none", "none"))
    r = llm.handle("s", "meri booking ka kya hua")
    assert "MB-9999" not in r["reply"] and "MB-1042" in r["reply"]


def test_emergency_keyword_skips_llm(llm):
    r = llm.handle("s", "abbu behosh ho gaye hain")
    assert "1122" in r["reply"] and llm.provider.calls == 0


def test_cancel_flow(llm):
    llm.provider.add(("tools", [("find_appointment", {"ref": "MB-1042"})]),
                     ("tools", [("propose_cancel", {"ref": "MB-1042"})]), ("final", "Cancel kar doon?", "cancel", "confirm"))
    llm.handle("s", "MB-1042 cancel karni hai")
    llm.provider.add(("tools", [("confirm_pending", {})]), ("final", "Ho gaya", "none", "none"))
    r = llm.handle("s", "haan")
    assert llm.clinic.appointment("MB-1042")["status"] == "cancelled" and "MB-1042" in r["reply"]


def test_reschedule_needs_same_department(llm):
    a = llm.clinic.appointment("MB-1042")
    other = "cardiology" if a["department"] != "cardiology" else "ent"
    llm.provider.add(("tools", [("search_slots", {"department": other, "date_from": "2026-11-25"})]),
                     ("tools", [("propose_reschedule", {"ref": "MB-1042", "slot_id": "S1"})]),
                     ("final", "?", "reschedule", "slot_choice"))
    r = llm.handle("s", "MB-1042 parson kar dein")
    assert "pick a" in r["tool_calls"][1]["output"]["error"]


def test_llm_error_keeps_chat_alive(llm):
    def boom(*a):
        raise RuntimeError("network down")
    llm.provider.chat = boom
    r = llm.handle("s", "salam")
    assert "dobara" in r["reply"] and any("LLM error" in t for t in r["trace"])
    assert llm.sessions.get("s").messages == []      # broken turn not kept


def test_switch_defaults_to_rules_without_key(nlu, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("MEDBOOK_DM", "auto")
    monkeypatch.setenv("MEDBOOK_LLM_PROVIDER", "anthropic")
    dm = make_dialogue_manager(nlu, Clinic(tmp_path / "x.db"))
    assert isinstance(dm, DialogueManager) and dm.mode == "rules"


def test_parse_final():
    assert parse_final('{"reply": "hi", "task": "book", "awaiting": "DATE"}') == \
        {"reply": "hi", "task": "book", "awaiting": "DATE"}
    assert parse_final("plain text")["reply"] == "plain text"


def test_anthropic_provider_request_shape():
    """The real provider class against a stub SDK client: request fields and history format."""
    sent = {}

    def block(**kw):
        b = types.SimpleNamespace(**kw)
        b.to_dict = lambda: dict(kw)
        return b

    def create(**kw):
        sent.update(kw)
        return types.SimpleNamespace(
            content=[block(type="tool_use", id="tu1", name="list_doctors", input={"department": "ent"})],
            usage=types.SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
                                        cache_creation_input_tokens=0),
            stop_reason="tool_use")
    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
    p = AnthropicProvider(model="claude-haiku-5-5", client=client)
    step = p.chat("sys", [{"name": "x", "description": "d", "input_schema": {"type": "object"}}],
                  [p.user_message("hi")])
    assert sent["model"] == "claude-haiku-5-5" and sent["output_config"]["format"]["type"] == "json_schema"
    assert "thinking" not in sent and "temperature" not in sent
    assert step.tool_calls[0].name == "list_doctors" and step.assistant_message["content"][0]["id"] == "tu1"
    res = p.tool_results([(step.tool_calls[0], "{}", False)])
    assert res[0]["content"][0] == {"type": "tool_result", "tool_use_id": "tu1", "content": "{}"}
