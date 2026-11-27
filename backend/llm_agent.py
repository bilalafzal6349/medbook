"""LLM dialogue manager: an LLM runs the conversation, calling the clinic database through tools.

Pipeline for every user message
    1. XLM-R (nlu.py) parses the message: intent, department, slots. This always runs.
    2. Safety layer: an emergency keyword stops everything and returns the Rescue 1122 reply.
       The LLM is not called for that message.
    3. The LLM gets the message plus the XLM-R output (as hints) and talks to the user. It reads and
       writes the schedule only through the tools below, which call clinic_db.Clinic.
    4. Guards in code (the LLM cannot talk its way past them):
         - Slots: a booking can only use a slot_id that search_slots returned in this chat and that is
           still free in the database. The LLM never types a doctor/day/time to book.
         - Confirmation: book / cancel / reschedule happen in two steps. propose_* checks the request
           and the system shows the user a fixed summary; confirm_pending writes it only if the
           user's very next message is a "yes" (checked in code with the same yes/no rules as the
           rule-based manager, plus the XLM-R "confirm" intent).
         - Booking numbers: any MB-xxxx in the LLM's reply that is not in the database is removed.
         - The database keeps its own guards (row lock + UNIQUE index on doctor/day/time).

Switch (see make_dialogue_manager)
    MEDBOOK_DM=auto (default)  LLM if an API key is configured, else the rule-based manager
    MEDBOOK_DM=llm | rules     force one
    MEDBOOK_LLM_PROVIDER=anthropic (default, model claude-haiku-5-5, needs ANTHROPIC_API_KEY)
    MEDBOOK_LLM_PROVIDER=openai  any OpenAI-compatible server: Gemini, Groq, local Ollama, ...
                                 needs MEDBOOK_LLM_BASE_URL, MEDBOOK_LLM_MODEL (+ MEDBOOK_LLM_API_KEY)
"""
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from clinic_db import normalize_phone, normalize_ref, now_pkt, valid_phone
from dialogue import NO_RE, ROUTE_CONF_MIN, YES_RE, DialogueManager
from nlu import ROUTING_INTENTS
from normalize import parse_date, parse_time
from replies import CLINIC_FACTS, STATUS, WEEKDAY_NAMES, detect_lang, fmt_date, fmt_days, fmt_time, say
from routing import route
from sessions import make_store

DEFAULT_MODEL = "claude-haiku-5-5"
MAX_TOOL_ROUNDS = 8          # LLM calls per user message, at most
MAX_OFFERS = 4
SEARCH_DAYS = 14
YES_CONF_MIN = 0.50          # XLM-R "confirm" confidence that counts as a yes
REF_IN_TEXT_RE = re.compile(r"\bMB-?\d{4}\b", re.I)
TASKS = ["none", "book", "cancel", "reschedule", "check", "info"]
AWAITING = ["none", "DEPARTMENT", "DATE", "TIME", "PATIENT_NAME", "PHONE", "APPOINTMENT_ID",
            "slot_choice", "confirm", "task_for_ref", "other"]

# ============================================================================ prompt + tools

SYSTEM_PROMPT = """You are MedBook, the appointment assistant of MedBook Clinic in Lahore, Pakistan.
Patients write in Roman Urdu, Urdu script, English, or a mix. You book, cancel, reschedule and check
appointments, route a described symptom to the right department, and answer questions about the clinic.

How to work
- Every user message comes with a <context> block: the current date and time, the reply language, the
  output of the clinic's own NLU model (XLM-R: intent, department, slots, with dates already resolved),
  and any pending action. Treat XLM-R as a strong hint, not as truth: if the user's words clearly say
  something else, follow the words.
- Use tools for every fact about doctors, slots, bookings, fees and timings. Never make up a doctor,
  a time, a fee or a booking number (MB-xxxx).
- Booking needs: a department or doctor, a day, a time preference, the patient's name and an 11-digit
  Pakistani mobile number (03xxxxxxxxx). Ask for what is missing, one or two things at a time. Age and
  the reason for the visit are optional.
- Call search_slots to find free slots. Offer at most 3 or 4, numbered, so the user can answer "1" or
  "doosra wala". Only slots that search_slots returned can be booked, by their slot_id.
- Writing to the schedule is two steps. First call propose_booking / propose_cancel / propose_reschedule.
  The system then shows the user a summary and asks for a yes. Only when the user's NEXT message agrees
  ("ji", "haan", "ok", "جی ہاں") call confirm_pending. If they say no or change something, do not
  confirm; ask what to change, search again if needed, and propose again.
- After confirm_pending succeeds, tell the user the booking number from the tool result.
- Cancel / reschedule / check: get the booking number (MB-xxxx) or the phone number used to book, then
  find_appointment. Reschedule keeps the department; search slots for the new day and time.

Routing a symptom (when the user describes a problem instead of naming a department)
- Use the routing hint in the context. A child of 12 or under goes to pediatrics. Gynecology is only for
  women. When unsure, use general_physician; never guess a specialist.
- Do not diagnose or suggest medicines. For medical advice say a doctor will help at the visit.

Safety
- If the message sounds like an emergency (unconscious, not breathing, heavy bleeding, chest pain with
  sweating, stroke signs, poisoning, suicide talk), tell them to call 1122 or go to the nearest emergency
  department right away. Do not try to book in that case.

Language and style
- Reply in the language given in the context: "urdu" means Urdu script; "roman" means Roman Urdu with
  English words mixed in the way Pakistani patients write. Short, warm, clear sentences. No markdown.
- Use the doctor names and the formatted day/time that the tools return for that language.

Output
- When you are done with tools for this message, answer with JSON only:
  {"reply": "<what to say to the user>", "task": one of none|book|cancel|reschedule|check|info,
   "awaiting": what you are waiting for: none|DEPARTMENT|DATE|TIME|PATIENT_NAME|PHONE|APPOINTMENT_ID|
   slot_choice|confirm|task_for_ref|other}
  Use task "none" and awaiting "none" when nothing is in progress (for example after a booking is done)."""

DEPT_KEYS = ["general_physician", "cardiology", "dermatology", "ent", "gastroenterology", "orthopedics",
             "gynecology", "pediatrics"]

TOOLS = [
    {"name": "search_slots",
     "description": "Free appointment slots, from the clinic database. Give a department or a doctor_id, and a "
                    "date range. Optionally a time window (24h HH:MM). Returns up to 4 slots spread over "
                    "days/doctors, each with a slot_id, and notes (e.g. doctor not on duty that day). If nothing "
                    "is free in the range it looks up to 14 days further and says so.",
     "input_schema": {"type": "object", "properties": {
         "department": {"type": "string", "enum": DEPT_KEYS},
         "doctor_id": {"type": "integer"},
         "date_from": {"type": "string", "description": "YYYY-MM-DD"},
         "date_to": {"type": "string", "description": "YYYY-MM-DD, inclusive; defaults to date_from"},
         "time_from": {"type": "string", "description": "HH:MM, 24h"},
         "time_to": {"type": "string", "description": "HH:MM, 24h"}},
         "required": ["date_from"]}},
    {"name": "list_doctors",
     "description": "Doctors of the clinic (all, or one department) with id, names, duty days, hours and fee.",
     "input_schema": {"type": "object", "properties": {
         "department": {"type": "string", "enum": DEPT_KEYS}}}},
    {"name": "find_appointment",
     "description": "Look up existing bookings by booking number (MB-1234) or by the phone number used to book.",
     "input_schema": {"type": "object", "properties": {
         "ref": {"type": "string"}, "phone": {"type": "string"}}}},
    {"name": "clinic_info",
     "description": "Clinic address, phone, opening hours, weekly holiday, and consultation fee per department.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "propose_booking",
     "description": "Step 1 of booking. Checks the slot is still free and the details are valid, then the system "
                    "shows the user a summary to confirm. Nothing is written yet.",
     "input_schema": {"type": "object", "properties": {
         "slot_id": {"type": "string", "description": "from search_slots"},
         "patient_name": {"type": "string"},
         "phone": {"type": "string"},
         "age": {"type": "string"},
         "reason": {"type": "string", "description": "symptom or reason for the visit, short"}},
         "required": ["slot_id", "patient_name", "phone"]}},
    {"name": "propose_cancel",
     "description": "Step 1 of cancelling a booking. Checks it exists and can be cancelled; the system asks the user "
                    "to confirm.",
     "input_schema": {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"]}},
    {"name": "propose_reschedule",
     "description": "Step 1 of moving a booking to a new slot (same department). The system asks the user to confirm.",
     "input_schema": {"type": "object", "properties": {
         "ref": {"type": "string"}, "slot_id": {"type": "string", "description": "from search_slots"}},
         "required": ["ref", "slot_id"]}},
    {"name": "confirm_pending",
     "description": "Step 2: carry out the proposed booking / cancel / reschedule. Only call this when the user's "
                    "latest message says yes to the summary. The system refuses otherwise.",
     "input_schema": {"type": "object", "properties": {}}},
]

REPLY_SCHEMA = {"type": "object", "properties": {
    "reply": {"type": "string"},
    "task": {"type": "string", "enum": TASKS},
    "awaiting": {"type": "string", "enum": AWAITING}},
    "required": ["reply", "task", "awaiting"], "additionalProperties": False}


# ============================================================================ providers

@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Step:
    """One LLM response, provider-neutral."""
    text: str
    tool_calls: list
    assistant_message: dict          # appended to the history as-is
    usage: dict = field(default_factory=dict)
    stop_reason: str = ""


class AnthropicProvider:
    """Claude through the official SDK. History keeps the response content blocks unchanged
    (thinking blocks included), as the API expects."""
    name = "anthropic"

    def __init__(self, model=None, effort=None, client=None):
        import anthropic
        self.anthropic = anthropic
        self.client = client or anthropic.Anthropic(max_retries=3, timeout=60.0)
        self.model = model or os.environ.get("MEDBOOK_LLM_MODEL") or DEFAULT_MODEL
        self.effort = effort or os.environ.get("MEDBOOK_LLM_EFFORT") or "low"
        self.json_schema = os.environ.get("MEDBOOK_LLM_JSON", "schema") == "schema"

    def chat(self, system, tools, messages):
        kw = dict(model=self.model, max_tokens=4000, system=system, tools=tools, messages=messages,
                  cache_control={"type": "ephemeral"},   # system + tools are the same every call
                  output_config={"effort": self.effort})
        if self.json_schema:
            kw["output_config"] = dict(kw["output_config"], format={"type": "json_schema", "schema": REPLY_SCHEMA})
        try:
            r = self.client.messages.create(**kw)
        except self.anthropic.BadRequestError as e:
            if not self.json_schema or "format" not in str(e):
                raise
            self.json_schema = False   # model/server without structured outputs: the prompt asks for JSON anyway
            kw["output_config"] = {"effort": self.effort}
            r = self.client.messages.create(**kw)
        calls = [ToolCall(b.id, b.name, dict(b.input or {})) for b in r.content if b.type == "tool_use"]
        text = "".join(b.text for b in r.content if b.type == "text")
        u = r.usage
        usage = {"input": u.input_tokens, "output": u.output_tokens,
                 "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                 "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}
        return Step(text, calls, {"role": "assistant", "content": [b.to_dict() for b in r.content]}, usage,
                    r.stop_reason or "")

    def user_message(self, text):
        return {"role": "user", "content": text}

    def assistant_text(self, text):
        return {"role": "assistant", "content": text}

    def tool_results(self, pairs):
        return [{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c.id, "content": out, **({"is_error": True} if err else {})}
            for c, out, err in pairs]}]


class OpenAICompatProvider:
    """Any server with an OpenAI-style /chat/completions endpoint and function calling:
    Gemini (https://generativelanguage.googleapis.com/v1beta/openai), Groq (https://api.groq.com/openai/v1),
    a local Ollama (http://localhost:11434/v1) running e.g. qwen2.5:7b."""
    name = "openai"

    def __init__(self, base_url=None, model=None, api_key=None):
        import httpx
        self.base = (base_url or os.environ["MEDBOOK_LLM_BASE_URL"]).rstrip("/")
        self.model = model or os.environ["MEDBOOK_LLM_MODEL"]
        key = api_key or os.environ.get("MEDBOOK_LLM_API_KEY", "")
        self.http = httpx.Client(timeout=120, headers={"Authorization": f"Bearer {key}"} if key else {})

    def chat(self, system, tools, messages):
        body = {"model": self.model, "temperature": 0.2,
                "messages": [{"role": "system", "content": system}] + messages,
                "tools": [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                            "parameters": t["input_schema"]}} for t in tools]}
        r = self.http.post(self.base + "/chat/completions", json=body)
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0]["message"]
        calls = []
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(tc["id"], tc["function"]["name"], args if isinstance(args, dict) else {}))
        keep = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            keep["tool_calls"] = msg["tool_calls"]
        u = data.get("usage") or {}
        return Step(msg.get("content") or "", calls, keep,
                    {"input": u.get("prompt_tokens", 0), "output": u.get("completion_tokens", 0)},
                    data["choices"][0].get("finish_reason", ""))

    def user_message(self, text):
        return {"role": "user", "content": text}

    def assistant_text(self, text):
        return {"role": "assistant", "content": text}

    def tool_results(self, pairs):
        return [{"role": "tool", "tool_call_id": c.id, "content": out} for c, out, _ in pairs]


def make_provider():
    kind = os.environ.get("MEDBOOK_LLM_PROVIDER", "anthropic").lower()
    return OpenAICompatProvider() if kind in ("openai", "openai_compat", "ollama", "groq", "gemini") \
        else AnthropicProvider()


def llm_configured():
    kind = os.environ.get("MEDBOOK_LLM_PROVIDER", "anthropic").lower()
    if kind == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    return bool(os.environ.get("MEDBOOK_LLM_BASE_URL") and os.environ.get("MEDBOOK_LLM_MODEL"))


def make_dialogue_manager(nlu, clinic, sessions=None):
    """The LLM manager when MEDBOOK_DM=llm, or =auto (default) with a key set; otherwise the rule manager."""
    mode = os.environ.get("MEDBOOK_DM", "auto").lower()
    if mode == "llm" or (mode == "auto" and llm_configured()):
        try:
            dm = LLMDialogueManager(nlu, clinic, make_provider(), sessions=sessions)
            print(f"[dm] LLM dialogue manager ({dm.provider.name}, {dm.provider.model})", flush=True)
            return dm
        except Exception as e:   # SDK not installed, missing setting, ...
            if mode == "llm":
                raise
            print(f"[dm] LLM not usable ({e!r}); using the rule-based manager", flush=True)
    dm = DialogueManager(nlu, clinic, sessions)
    dm.mode = "rules"
    return dm


# ============================================================================ state

@dataclass
class LLMState:
    lang: str = "roman"
    messages: list = field(default_factory=list)      # provider-format history
    offered: dict = field(default_factory=dict)       # slot_id -> {doctor_id, day (iso), start_min}
    next_slot: int = 1
    pending: dict = None                              # {"action", ..., "turn", "summary"}
    task: str = None
    awaiting: str = None
    turns: int = 0
    usage: dict = field(default_factory=lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
                                                 "llm_calls": 0})


# ============================================================================ manager

class LLMDialogueManager:
    mode = "llm"

    def __init__(self, nlu, clinic, provider, sessions=None):
        self.nlu = nlu
        self.clinic = clinic
        self.provider = provider
        self.sessions = sessions if sessions is not None else make_store()

    def reset(self, session_id):
        self.sessions.pop(session_id, None)

    # ------------------------------------------------------------------ one user message
    def handle(self, session_id, text):
        st = self.sessions.get(session_id) or LLMState()
        st.turns += 1
        st.lang = detect_lang(text, st.lang)
        L = st.lang
        p = self.nlu.parse(text)
        trace, calls = [], []
        t0 = time.time()

        # 1) safety layer: emergency keyword -> fixed reply, LLM not called
        if p["rules"].get("emergency"):
            reply = say("emergency", L)
            trace.append(f"emergency keyword '{p['rules']['emergency']}': fixed 1122 reply, LLM not called")
            st.pending, st.task, st.awaiting = None, None, None
            st.messages += [self.provider.user_message(self._context(st, p, text)), self.provider.assistant_text(
                json.dumps({"reply": reply, "task": "none", "awaiting": "none"}, ensure_ascii=False))]
            return self._out(session_id, st, reply, p, trace, calls, t0)

        prefix = []
        if p["intent"] == "emergency":   # model-only emergency: safety advice first, the LLM may still help
            prefix.append(say("emergency", L))
            trace.append(f"XLM-R says emergency ({p['intent_conf']:.2f}) without a keyword: 1122 advice shown first")

        # 2) LLM turn with tools
        history = list(st.messages)
        history.append(self.provider.user_message(self._context(st, p, text, emergency_shown=bool(prefix))))
        turn = {"proposed": None, "done": None, "is_yes": self._is_yes(text, p)}
        final = None
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                step = self.provider.chat(SYSTEM_PROMPT, TOOLS, history)
                self._count(st, step.usage)
                history.append(step.assistant_message)
                if not step.tool_calls:
                    final = step.text
                    break
                pairs = []
                for c in step.tool_calls:
                    out, err = self._run_tool(st, c, turn, trace, session_id)
                    calls.append({"name": c.name, "input": c.args, "output": out, "error": err})
                    pairs.append((c, json.dumps(out, ensure_ascii=False, default=str), err))
                history += self.provider.tool_results(pairs)
            else:
                trace.append(f"stopped after {MAX_TOOL_ROUNDS} LLM calls")
        except Exception as e:   # network, quota, bad response: keep the chat usable
            trace.append(f"LLM error: {type(e).__name__}: {str(e)[:200]}")
            if turn["done"] is None:   # nothing written: forget this turn so the history stays valid
                reply = "\n".join(prefix + [self._busy(L)])
                return self._out(session_id, st, reply, p, trace, calls, t0)
            final = None
        st.messages = history

        # 3) the reply, with code-level fixes
        parsed = parse_final(final)
        reply = parsed["reply"]
        if not reply and turn["done"] is None and turn["proposed"] is None:
            reply = say("not_understood", L)
        st.task = None if parsed["task"] == "none" else parsed["task"]
        st.awaiting = None if parsed["awaiting"] == "none" else parsed["awaiting"]
        if turn["proposed"]:   # the user must see exactly what will be written
            summary = turn["proposed"]["summary"]
            if summary not in reply:
                reply = (reply + "\n" + summary).strip()
                trace.append("guard: appended the fixed confirmation summary")
            st.awaiting = "confirm"
        if turn["done"]:
            msg = turn["done"]["message"]
            ref = turn["done"].get("ref")
            if ref and ref not in reply:
                reply = (msg + "\n" + reply).strip() if reply else msg
                trace.append("guard: added the booking result from the database")
        reply = self._strip_invented_refs(reply, trace)
        if prefix:
            reply = "\n".join(prefix + [reply])
        return self._out(session_id, st, reply, p, trace, calls, t0)

    def _out(self, sid, st, reply, p, trace, calls, t0):
        self.sessions.save(sid, st)
        return {"reply": reply, "nlu": p, "state": self._public(st), "trace": trace, "tool_calls": calls,
                "mode": "llm", "ms": round((time.time() - t0) * 1000)}

    @staticmethod
    def _busy(L):
        return ("Maaf kijiye, abhi system mein masla hai. Thori dair baad dobara likhein, ya clinic ko "
                f"{CLINIC_FACTS['phone']} par call karein." if L == "roman" else
                f"معذرت، ابھی سسٹم میں مسئلہ ہے۔ تھوڑی دیر بعد دوبارہ لکھیں، یا کلینک کو {CLINIC_FACTS['phone']} پر کال کریں۔")

    def _count(self, st, usage):
        st.usage["llm_calls"] += 1
        for k, v in (usage or {}).items():
            st.usage[k] = st.usage.get(k, 0) + (v or 0)

    def _public(self, st):
        pend = st.pending
        return {"mode": "llm", "model": getattr(self.provider, "model", None), "task": st.task,
                "awaiting": st.awaiting, "lang": st.lang,
                "pending": None if not pend else {k: pend[k] for k in pend if k not in ("summary",)},
                "offers": len(st.offered), "llm_calls": st.usage["llm_calls"],
                "tokens": {"input": st.usage["input"] + st.usage.get("cache_read", 0) + st.usage.get("cache_write", 0),
                           "output": st.usage["output"]}}

    # ------------------------------------------------------------------ context for the LLM
    def _context(self, st, p, text, emergency_shown=False):
        now = now_pkt()
        today = now.date()
        lines = [f"now: {WEEKDAY_NAMES['roman'][today.weekday()]} {today.isoformat()} "
                 f"{now.hour:02d}:{now.minute:02d} (Pakistan time). Clinic closed on Sunday.",
                 f"reply_language: {st.lang}"]
        x = f"XLM-R: intent={p['intent']} ({p['intent_conf']:.2f})"
        if p.get("department"):
            x += f", department={p['department']} ({p.get('department_conf', 0):.2f})"
        lines.append(x)
        for s in p["slots"]:
            extra = ""
            if s["label"] == "DATE":
                dv = parse_date(s["value"], today)
                extra = f" -> {dv.start}" + (f"..{dv.end}" if dv and not dv.exact else "") if dv else " -> not understood"
            elif s["label"] == "TIME":
                tv = parse_time(s["value"])
                extra = f" -> {tv.start // 60:02d}:{tv.start % 60:02d}-{tv.end // 60:02d}:{tv.end % 60:02d}" if tv \
                    else " -> not understood"
            elif s["label"] == "PHONE":
                extra = f" -> {normalize_phone(s['value'])}" + ("" if valid_phone(s["value"]) else " (not a valid mobile)")
            lines.append(f"  slot {s['label']}: '{s['value']}'{extra}")
        if p["intent"] in ROUTING_INTENTS or any(s["label"] == "SYMPTOM" for s in p["slots"]):
            d, conf = (p.get("department"), p.get("department_conf", 0.0)) if p.get("department") \
                else self.nlu.department_of(text)
            dept, how, why = route(text, d, conf, ROUTE_CONF_MIN)
            lines.append(f"routing hint: {dept} ({how}: {why})")
        did = p["rules"].get("doctor_id")
        if did:
            doc = self.clinic.doctor(did)
            lines.append(f"doctor named: {doc['name_roman']} (id {did}, {doc['department']})")
        if emergency_shown:
            lines.append("system: XLM-R flagged a possible emergency and the 1122 advice was already shown above "
                         "your reply. If it is not urgent you may help book.")
        if st.pending:
            lines.append(f"pending action waiting for the user's yes: {st.pending['action']} "
                         f"(proposed last turn: {st.pending['turn'] == st.turns - 1})")
        return "<context>\n" + "\n".join(lines) + "\n</context>\n" + text

    @staticmethod
    def _is_yes(text, p):
        if NO_RE.search(text) or p["intent"] == "deny":
            return False
        if YES_RE.search(text):
            return True
        return p["intent"] == "confirm" and p["intent_conf"] >= YES_CONF_MIN

    # ------------------------------------------------------------------ tools
    def _run_tool(self, st, c, turn, trace, sid):
        fn = getattr(self, "_t_" + c.name, None)
        if fn is None:
            trace.append(f"unknown tool {c.name}")
            return {"error": f"no tool called {c.name}"}, True
        try:
            out = fn(st, c.args, turn, trace, sid)
        except (ValueError, KeyError, TypeError) as e:
            trace.append(f"{c.name}: bad input ({e})")
            return {"error": f"bad input: {e}"}, True
        err = isinstance(out, dict) and "error" in out
        if err:
            trace.append(f"{c.name} refused: {out['error']}")
        return out, err

    def _slot_view(self, s, L):
        doc = self.clinic.doctor(s["doctor_id"])
        return {"doctor_id": doc["id"], "doctor": doc["name_urdu"] if L == "urdu" else doc["name_roman"],
                "department": doc["department"], "date": s["day"].isoformat(),
                "day": fmt_date(s["day"], L), "time": fmt_time(s["start_min"], L)}

    def _register(self, st, s):
        for sid_, v in st.offered.items():   # same slot offered again keeps its id
            if v == {"doctor_id": s["doctor_id"], "day": s["day"].isoformat(), "start_min": s["start_min"]}:
                return sid_
        sid_ = f"S{st.next_slot}"
        st.next_slot += 1
        st.offered[sid_] = {"doctor_id": s["doctor_id"], "day": s["day"].isoformat(), "start_min": s["start_min"]}
        return sid_

    def _t_search_slots(self, st, a, turn, trace, sid):
        L = st.lang
        today = now_pkt().date()
        d0 = date.fromisoformat(a["date_from"])
        d1 = date.fromisoformat(a.get("date_to") or a["date_from"])
        if d1 < d0:
            d0, d1 = d1, d0
        if d1 < today:
            return {"error": f"{d1} is in the past; today is {today}"}
        if a.get("doctor_id"):
            doc = self.clinic.doctor(int(a["doctor_id"]))
            if not doc:
                return {"error": f"no doctor with id {a['doctor_id']}; use list_doctors"}
            ids = [doc["id"]]
        elif a.get("department"):
            ids = [d["id"] for d in self.clinic.doctors(a["department"])]
            if not ids:
                return {"error": f"unknown department {a['department']}"}
        else:
            return {"error": "give a department or a doctor_id"}
        t0 = _minutes(a.get("time_from"), 0)
        t1 = _minutes(a.get("time_to"), 24 * 60)
        if t1 <= t0:   # one exact time: look around it
            t1 = t0 + 1
        notes = []
        if d0 == d1:
            wds = {x["weekday"] for i in ids for x in self.clinic.duty(i)}
            if d0.weekday() not in wds:
                notes.append(("clinic closed on Sunday" if d0.weekday() == 6 else
                              f"no duty on {WEEKDAY_NAMES['roman'][d0.weekday()]}") +
                             f"; duty days: {fmt_days(wds, 'roman')}")
        found = self.clinic.free_slots(ids, d0, d1, t0, t1)
        if not found and (t0 > 0 or t1 < 24 * 60):
            found = self.clinic.free_slots(ids, d0, d1)
            if found:
                notes.append("nothing free in that time window; these are other times the same day(s)")
                if t1 - t0 <= 60:   # an exact time: nearest first
                    found = sorted(found, key=lambda s: (s["day"], abs(s["start_min"] - t0)))
        if not found:
            n0, n1 = d1 + timedelta(days=1), d1 + timedelta(days=SEARCH_DAYS)
            found = self.clinic.free_slots(ids, n0, n1, t0, t1) or self.clinic.free_slots(ids, n0, n1)
            if found:
                notes.append(f"nothing free {d0}..{d1}; these are the next free slots")
        offers = _spread(found, MAX_OFFERS)
        trace.append(f"search_slots {len(ids)} doctor(s) {d0}..{d1} "
                     f"{t0 // 60:02d}:{t0 % 60:02d}-{min(t1, 1439) // 60:02d}:{min(t1, 1439) % 60:02d}: "
                     f"{len(found)} free, offering {len(offers)}")
        return {"slots": [dict(slot_id=self._register(st, s), **self._slot_view(s, L)) for s in offers],
                "notes": notes or None}

    def _t_list_doctors(self, st, a, turn, trace, sid):
        L = st.lang
        out = []
        for d in self.clinic.doctors(a.get("department")):
            duty = self.clinic.duty(d["id"])
            hours = sorted({(x["start_min"], x["end_min"]) for x in duty})
            dept = self.clinic.department(d["department"])
            out.append({"id": d["id"], "name": d["name_urdu"] if L == "urdu" else d["name_roman"],
                        "name_roman": d["name_roman"], "department": d["department"],
                        "days": fmt_days([x["weekday"] for x in duty], L),
                        "hours": [f"{fmt_time(x, L)} - {fmt_time(y, L)}" for x, y in hours], "fee_pkr": dept["fee"]})
        trace.append(f"list_doctors {a.get('department') or 'all'}: {len(out)}")
        return {"doctors": out}

    def _appt_view(self, a, L):
        doc = self.clinic.doctor(a["doctor_id"])
        return {"ref": a["ref"], "doctor": doc["name_urdu"] if L == "urdu" else doc["name_roman"],
                "doctor_id": doc["id"], "department": doc["department"], "date": a["day"].isoformat(),
                "day": fmt_date(a["day"], L), "time": fmt_time(a["start_min"], L), "patient": a["patient_name"],
                "status": a["status"], "status_text": STATUS[a["status"]][L],
                "in_past": a["day"] < now_pkt().date()}

    def _t_find_appointment(self, st, a, turn, trace, sid):
        L = st.lang
        if a.get("ref"):
            ap = self.clinic.appointment(a["ref"])
            trace.append(f"find_appointment {normalize_ref(a['ref'])}: {'found' if ap else 'not found'}")
            return {"appointments": [self._appt_view(ap, L)] if ap else [],
                    "note": None if ap else f"no booking {normalize_ref(a['ref'])}"}
        if a.get("phone"):
            if not valid_phone(a["phone"]):
                return {"error": "not a valid Pakistani mobile number (03xxxxxxxxx)"}
            found = self.clinic.appointments_by_phone(a["phone"])
            trace.append(f"find_appointment by phone: {len(found)}")
            return {"appointments": [self._appt_view(x, L) for x in found],
                    "note": "only upcoming bookings are listed" if found else "no upcoming booking for this number"}
        return {"error": "give ref or phone"}

    def _t_clinic_info(self, st, a, turn, trace, sid):
        L = st.lang
        trace.append("clinic_info")
        return {"name": CLINIC_FACTS["name"], "address": CLINIC_FACTS["address"][L], "phone": CLINIC_FACTS["phone"],
                "open": "Monday to Saturday, 10 AM to 9 PM", "closed": "Sunday",
                "lab": "sample collection 8 AM to 8 PM",
                "fees_pkr": {d["key"]: d["fee"] for d in self.clinic.departments()}}

    # ---- writes, step 1
    def _offered_slot(self, st, slot_id):
        o = st.offered.get(str(slot_id).strip().upper())
        if not o:
            return None, {"error": f"unknown slot_id {slot_id}: only slot_ids returned by search_slots can be used"}
        day = date.fromisoformat(o["day"])
        if not self.clinic.is_free(o["doctor_id"], day, o["start_min"]):
            return None, {"error": "that slot is no longer free; search again"}
        return {"doctor_id": o["doctor_id"], "day": day, "start_min": o["start_min"]}, None

    def _propose(self, st, turn, trace, pending):
        pending["turn"] = st.turns
        st.pending = pending
        turn["proposed"] = pending
        trace.append(f"proposed {pending['action']}; waiting for the user's yes")
        return {"ok": True, "summary_shown_to_user": pending["summary"],
                "next": "Ask the user to confirm. Call confirm_pending only after they say yes."}

    def _t_propose_booking(self, st, a, turn, trace, sid):
        L = st.lang
        slot, err = self._offered_slot(st, a.get("slot_id"))
        if err:
            return err
        name = (a.get("patient_name") or "").strip()
        if len(name) < 2:
            return {"error": "patient_name missing"}
        if not valid_phone(a.get("phone")):
            return {"error": "phone must be an 11-digit Pakistani mobile number starting with 03"}
        phone = normalize_phone(a["phone"])
        doc = self.clinic.doctor(slot["doctor_id"])
        summary = say("confirm_book", L, doctor=doc["name_urdu"] if L == "urdu" else doc["name_roman"],
                      dept=self.clinic.department(doc["department"])["name_urdu" if L == "urdu" else "name_en"],
                      day=fmt_date(slot["day"], L), time=fmt_time(slot["start_min"], L), name=name, phone=phone)
        return self._propose(st, turn, trace, {
            "action": "book", "doctor_id": slot["doctor_id"], "day": slot["day"].isoformat(),
            "start_min": slot["start_min"], "patient_name": name, "phone": phone,
            "age": (str(a.get("age")).strip() or None) if a.get("age") else None,
            "reason": (a.get("reason") or "").strip() or None, "summary": summary})

    def _existing(self, ref):
        ap = self.clinic.appointment(ref or "")
        if not ap:
            return None, {"error": f"no booking {normalize_ref(ref or '')}"}
        if ap["status"] != "booked":
            return None, {"error": f"{ap['ref']} is already cancelled"}
        if ap["day"] < now_pkt().date():
            return None, {"error": f"{ap['ref']} was on {ap['day']}, already past"}
        return ap, None

    def _t_propose_cancel(self, st, a, turn, trace, sid):
        L = st.lang
        ap, err = self._existing(a.get("ref"))
        if err:
            return err
        v = self._appt_view(ap, L)
        dept = self.clinic.department(v["department"])["name_urdu" if L == "urdu" else "name_en"]
        summary = say("confirm_cancel", L, ref=ap["ref"], doctor=v["doctor"], dept=dept, day=v["day"],
                      time=v["time"], name=ap["patient_name"], status=v["status_text"])
        return self._propose(st, turn, trace, {"action": "cancel", "ref": ap["ref"], "summary": summary})

    def _t_propose_reschedule(self, st, a, turn, trace, sid):
        L = st.lang
        ap, err = self._existing(a.get("ref"))
        if err:
            return err
        slot, err = self._offered_slot(st, a.get("slot_id"))
        if err:
            return err
        new_doc = self.clinic.doctor(slot["doctor_id"])
        if new_doc["department"] != ap["department"]:
            return {"error": f"{ap['ref']} is a {ap['department']} booking; pick a {ap['department']} slot"}
        if (slot["doctor_id"], slot["day"], slot["start_min"]) == (ap["doctor_id"], ap["day"], ap["start_min"]):
            return {"error": "that is the current time of the booking"}
        old = self._appt_view(ap, L)
        summary = say("confirm_reschedule", L, ref=ap["ref"], old=f"{old['day']} {old['time']}",
                      doctor=new_doc["name_urdu"] if L == "urdu" else new_doc["name_roman"],
                      day=fmt_date(slot["day"], L), time=fmt_time(slot["start_min"], L))
        return self._propose(st, turn, trace, {
            "action": "reschedule", "ref": ap["ref"], "doctor_id": slot["doctor_id"], "day": slot["day"].isoformat(),
            "start_min": slot["start_min"], "summary": summary})

    # ---- writes, step 2
    def _t_confirm_pending(self, st, a, turn, trace, sid):
        L = st.lang
        pend = st.pending
        if not pend:
            return {"error": "nothing to confirm; call a propose_* tool first"}
        if pend["turn"] != st.turns - 1:
            return {"error": "the summary was not shown in your previous message; propose again and ask the user"}
        if not turn["is_yes"]:
            return {"error": "the user's latest message is not a clear yes; ask them to confirm or say what to change"}
        st.pending = None
        if pend["action"] == "book":
            ap = self.clinic.book(pend["doctor_id"], date.fromisoformat(pend["day"]), pend["start_min"],
                                  pend["patient_name"], pend["phone"], pend.get("age"), pend.get("reason"), sid, lang=L)
            if not ap:
                trace.append("DB insert refused: slot taken meanwhile")
                return {"error": "the slot was taken by someone else just now; search again and offer other slots"}
            v = self._appt_view(ap, L)
            msg = say("booked", L, ref=ap["ref"], doctor=v["doctor"], day=v["day"], time=v["time"])
        elif pend["action"] == "cancel":
            ok = self.clinic.cancel(pend["ref"])
            if not ok:
                return {"error": f"{pend['ref']} could not be cancelled (already cancelled?)"}
            ap = self.clinic.appointment(pend["ref"])
            msg = say("cancelled", L, ref=ap["ref"])
        else:
            ap = self.clinic.reschedule(pend["ref"], pend["doctor_id"], date.fromisoformat(pend["day"]),
                                        pend["start_min"])
            if not ap:
                trace.append("DB update refused: slot taken meanwhile")
                return {"error": "the new slot was taken just now; search again"}
            v = self._appt_view(ap, L)
            msg = say("rescheduled", L, ref=ap["ref"], doctor=v["doctor"], day=v["day"], time=v["time"])
        trace.append(f"DB {pend['action']} {ap['ref']} (after the user's yes)")
        st.offered = {}
        turn["done"] = {"action": pend["action"], "ref": ap["ref"], "message": msg}
        return {"ok": True, "ref": ap["ref"], "message_for_user": msg}

    # ------------------------------------------------------------------ reply checks
    def _strip_invented_refs(self, reply, trace):
        def fix(m):
            ref = normalize_ref(m.group(0))
            if self.clinic.appointment(ref):
                return m.group(0)
            trace.append(f"guard: removed booking number {m.group(0)} (not in the database)")
            return "[?]"
        return REF_IN_TEXT_RE.sub(fix, reply or "")


# ============================================================================ helpers

def _minutes(hhmm, default):
    if not hhmm:
        return default
    m = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*$", str(hhmm))
    if not m:
        raise ValueError(f"time '{hhmm}' is not HH:MM")
    return min(int(m.group(1)) * 60 + int(m.group(2) or 0), 24 * 60)


def _spread(slots, n):
    """Up to n offers on different days / doctors / hours rather than n back-to-back slots."""
    picked, seen = [], set()
    for s in slots:
        key = (s["day"], s["doctor_id"], s["start_min"] // 60)
        if key not in seen:
            seen.add(key)
            picked.append(s)
        if len(picked) == n:
            break
    for s in slots:
        if len(picked) >= n:
            break
        if s not in picked:
            picked.append(s)
    return sorted(picked, key=lambda s: (s["day"], s["start_min"]))


def parse_final(text):
    """The LLM's last message as {"reply", "task", "awaiting"}. Plain text (no JSON) is used as the reply."""
    out = {"reply": "", "task": "none", "awaiting": "none"}
    if not text:
        return out
    t = text.strip()
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict) and isinstance(d.get("reply"), str):
                out["reply"] = d["reply"].strip()
                out["task"] = d.get("task") if d.get("task") in TASKS else "none"
                out["awaiting"] = d.get("awaiting") if d.get("awaiting") in AWAITING else "other"
                return out
        except json.JSONDecodeError:
            pass
    out["reply"] = t
    out["awaiting"] = "other"
    return out
