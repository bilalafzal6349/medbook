"""Rule-based dialogue manager: slot filling, department routing, booking / cancel /
reschedule / check against the clinic database, with an explicit confirmation before any write.

Design rules (worth stating in the report):
  1. The bot only offers slots returned by Clinic.free_slots, and only quotes booking numbers
     returned by Clinic.book / Clinic.appointment. Nothing is invented by the model.
  2. Nothing is written to the database without a "yes" to a summary of exactly what will be written.
  3. An emergency (model intent OR keyword rule) stops every task and points to Rescue 1122.
  4. Low-confidence routing falls back to General Physician, never to a guessed specialist.
  5. The user can correct any slot at any time ("nahi, parson") and the plan is rebuilt.

One DialogueManager serves all sessions; each session has its own State.
"""
import re
from dataclasses import dataclass, field
from datetime import timedelta

from clinic_db import Clinic, normalize_phone, normalize_ref, now_pkt, valid_phone
from lexicons import DEPARTMENT_NAMES
from normalize import ANY_TIME_RE, DateValue, TimeValue, parse_date, parse_time
from routing import keyword_department, route
from sessions import make_store
from replies import CLINIC_FACTS, FAQ, FAQ_DEFAULT, STATUS, detect_lang, fmt_date, fmt_days, fmt_time, say

ROUTE_CONF_MIN = 0.40          # below this, route to General Physician instead of a specialist
SEARCH_DAYS = 14               # how far ahead to look for alternatives
MAX_OFFERS = 3
SWITCH_CONF_MIN = 0.75
SYMPTOM_FALLBACK_CONF = 0.60   # department-head confidence needed to read a stray "no" as a symptom
CANCEL_RE = re.compile(r"cancel|cansel|cancle|khatam kar|منسوخ|کینسل|ختم کر", re.I)
BOOKING_RE = re.compile(r"booking|appointment|apointment|appt|\bmb[\s-]?\d|بکنگ|اپائنٹمنٹ|وقت|ٹائم", re.I)
CHANGE_RE = re.compile(r"badal|badl|change|tabdeel|tabdil|shift|koi aur|کوئی اور|تبدیل|بدل", re.I)

TASK_OF_INTENT = {"book_appointment": "book", "cancel_appointment": "cancel",
                  "reschedule_appointment": "reschedule", "check_appointment": "check"}

YES_RE = re.compile(r"^\W*(ji|jee|g|haan|han|haa|ha|yes|yeah|yep|ok|okay|theek|thik|thk|sahi|done|kar do|kar dein|"
                    r"zaroor|bilkul|confirm|جی|ہاں|ٹھیک|درست|بالکل|ضرور|صحیح|اوکے)\b", re.I)
NO_RE = re.compile(r"^\W*(nahi|nai|nhi|nahin|no|nope|mat|na|cancel karo rehne do|rehne do|نہیں|نا|مت|رہنے دیں)\b", re.I)
ORDINALS = [  # offer index -> words
    r"\b(1|pehla|pehli|pehle wala|pehle wali|first|ek|one)\b|پہلا|پہلی|پہلے والا|ایک|۱",
    r"\b(2|doosra|dusra|doosri|dusri|second|two)\b|دوسرا|دوسری|۲",
    r"\b(3|teesra|tisra|teesri|third|teen|three)\b|تیسرا|تیسری|تین|۳",
]


@dataclass
class State:
    lang: str = "roman"
    task: str = None                 # book | cancel | reschedule | check
    slots: dict = field(default_factory=dict)   # raw strings as the user wrote them
    department: str = None
    dept_source: str = None          # doctor | named | symptom | fallback | appointment
    doctor_id: int = None
    date: DateValue = None
    time: TimeValue = None
    ref: str = None                  # existing appointment (cancel / reschedule / check)
    chosen: dict = None              # slot the user agreed to / that was free as asked
    offers: list = field(default_factory=list)
    awaiting: str = None             # confirm | slot_choice | <SLOT> | task_for_ref
    turns: int = 0

    def reset_task(self):
        lang, turns = self.lang, self.turns
        self.__init__()
        self.lang, self.turns = lang, turns

    def public(self, clinic):
        """JSON-safe view for the UI debug panel."""
        doc = clinic.doctor(self.doctor_id) if self.doctor_id else None
        return {
            "task": self.task, "awaiting": self.awaiting, "lang": self.lang,
            "department": self.department, "dept_source": self.dept_source,
            "doctor": doc["name_roman"] if doc else None,
            "date": None if not self.date else
            (self.date.start.isoformat() if self.date.exact else f"{self.date.start}..{self.date.end}"),
            "time": None if not self.time else
            f"{self.time.start // 60:02d}:{self.time.start % 60:02d}-{self.time.end // 60:02d}:{self.time.end % 60:02d}",
            "slots": dict(self.slots), "ref": self.ref,
            "chosen": None if not self.chosen else
            {"doctor_id": self.chosen["doctor_id"], "day": self.chosen["day"].isoformat(),
             "time": f"{self.chosen['start_min'] // 60:02d}:{self.chosen['start_min'] % 60:02d}"},
            "offers": len(self.offers),
        }


def department_from_name(value):
    """'skin specialist' / 'دل کے ڈاکٹر' / 'ENT' -> department key, from the lexicon plus keywords."""
    v = value.lower().strip()
    for key, by_style in DEPARTMENT_NAMES.items():
        for names in by_style.values():
            for n in names:
                if n.lower() == v or (len(n) > 3 and n.lower() in v):
                    return key
    keywords = [
        ("cardiology", r"dil|heart|cardio|دل|قلب"), ("dermatology", r"skin|jild|derma|جلد|سکن"),
        ("ent", r"\bent\b|kaan|naak|gala|throat|کان|ناک|گلے|(ای )?این ٹی"),
        ("gastroenterology", r"pait|pet\b|gastro|maid|stomach|پیٹ|معد|گیسٹرو"),
        ("orthopedics", r"haddi|bone|ortho|jor|ہڈی|ہڈیوں|آرتھو"),
        ("gynecology", r"gyn|lady|aurat|women|گائنی|لیڈی|خواتین"),
        ("pediatrics", r"bach|child|pedia|kids|بچوں|بچے|چائلڈ"),
        ("general_physician", r"general|\bgp\b|aam|family|medicine|physician|جنرل|عام|فیملی|میڈیسن"),
    ]
    for key, pat in keywords:
        if re.search(pat, v):
            return key
    return None


class DialogueManager:
    def __init__(self, nlu, clinic=None, sessions=None):
        self.nlu = nlu
        self.clinic = clinic or Clinic()
        self.sessions = sessions if sessions is not None else make_store()   # memory, or Redis if REDIS_URL

    # ================================================================== entry point
    def handle(self, session_id, text):
        st = self.sessions.get(session_id) or State()
        st.turns += 1
        st.lang = detect_lang(text, st.lang)
        p = self.nlu.parse(text)
        trace = []                           # what the manager decided, for the debug panel
        out = self._turn(st, text, p, trace, session_id)
        self.sessions.save(session_id, st)
        reply = "\n".join(x for x in out if x)
        return {"reply": reply, "nlu": p, "state": st.public(self.clinic), "trace": trace}

    def reset(self, session_id):
        self.sessions.pop(session_id, None)

    # ================================================================== one turn
    def _turn(self, st, text, p, trace, sid):
        L = st.lang
        intent = p["intent"]
        slots = self._collect_slots(p)

        # 1) safety first
        if intent == "emergency":
            st.reset_task()
            if p["rules"].get("emergency"):          # keyword rule: hard stop
                trace.append("emergency (keyword rule): task dropped")
                return [say("emergency", L)]
            # model-only emergency: safety advice first, then let the user book if it is not urgent.
            # (Free-form tests showed the model calls some ordinary symptoms emergencies.)
            d, conf = self.nlu.department_of(text)
            dept, how, why = route(text, d, conf, ROUTE_CONF_MIN)
            trace.append(f"emergency (model only, {p['intent_conf']:.2f}): advice given, booking offered; "
                         f"routing ({how}): {why}")
            st.task = "book"
            st.department, st.dept_source = dept, ("fallback" if how == "fallback" else "symptom")
            st.awaiting = "DATE"
            return [say("emergency", L), say("emergency_soft", L, dept=self._dept_name(st.department, L)),
                    say("ask_DATE", L)]

        # 2) yes / no words win over a low-confidence model when we asked a yes/no question
        if st.awaiting in ("confirm", "slot_choice", "offer_one") and len(text.split()) <= 6:
            if YES_RE.search(text) and intent != "deny" and not NO_RE.search(text):
                if intent != "confirm":
                    trace.append(f"rule: '{text}' read as confirm (model said {intent})")
                intent = "confirm"
            elif NO_RE.search(text) and intent not in ("deny",):
                trace.append(f"rule: '{text}' read as deny (model said {intent})")
                intent = "deny"

        # 2b) task keywords the model sometimes mixes up (cancel vs reschedule vs book)
        if intent in ("book_appointment", "reschedule_appointment", "check_appointment", "inform"):
            if CANCEL_RE.search(text) and not CHANGE_RE.search(text):
                if intent != "cancel_appointment":
                    trace.append(f"rule: cancel keyword (model said {intent})")
                intent = "cancel_appointment"
            elif intent in ("book_appointment", "inform") and st.task is None and CHANGE_RE.search(text) \
                    and BOOKING_RE.search(text):
                trace.append(f"rule: change-my-booking wording read as reschedule (model said {intent})")
                intent = "reschedule_appointment"

        # 2c) a "no"/bare answer with nothing pending is often a symptom the model misread
        #     ("periods do mahine se nahi aaye"): use the department head if it is confident
        if st.task is None and st.awaiting is None and intent in ("deny", "inform", "confirm") and not slots \
                and len(text.split()) >= 3:
            d, conf = self.nlu.department_of(text)
            kd, _ = keyword_department(text)
            if kd or conf >= SYMPTOM_FALLBACK_CONF:
                trace.append(f"rule: nothing pending, department head {d} ({conf:.2f}) -> describe_symptom "
                             f"(model said {intent})")
                intent = "describe_symptom"
                p = dict(p, department=d, department_conf=conf)

        # 3) small talk that does not touch the task
        if intent == "goodbye" and not slots:
            st.reset_task()
            return [say("bye", L)]
        if intent == "greet" and not slots and st.task is None:
            return [say("greet", L)]
        if intent == "out_of_scope":
            return [say("out_of_scope", L)] + self._reask(st)
        if intent == "clinic_info":
            return [self._faq(st, text, slots, p)] + self._reask(st)

        # 4) answers to a pending question
        if st.awaiting == "confirm":
            if intent == "confirm" and not self._changes_slots(slots):
                return self._execute(st, trace, sid)
            if intent == "deny" and not self._changes_slots(slots):
                trace.append("deny without new values: ask what to change")
                if st.task == "cancel":
                    st.reset_task()
                    return [say("aborted", L)]
                st.chosen, st.awaiting = None, "change"
                return [say("ask_change", L)]
        if st.awaiting in ("confirm", "offer_one") and not slots and not CHANGE_RE.search(text) \
                and intent not in ("confirm", "deny") and intent not in TASK_OF_INTENT:
            trace.append(f"unclear answer to a yes/no question ({intent}); asking again")
            return [say("yes_no", L)]
        wants_change = bool(CHANGE_RE.search(text)) and st.task in ("book", "reschedule")
        if (st.awaiting == "change" or (wants_change and st.awaiting in ("confirm", "slot_choice", "offer_one"))) \
                and not self._changes_slots(slots):
            r = self._change_request(st, text, intent, trace)
            if r:
                return r
        if st.awaiting in ("slot_choice", "offer_one") and st.offers and len(text.split()) <= 3:
            # "1", "pehla wala", "دوسرا": a short ordinal picks an offer even if the model tagged the
            # number as a DATE ("1" -> 1st of the month) or TIME
            low = text.lower().strip()
            for i, pat in enumerate(ORDINALS[:len(st.offers)]):
                if re.search(pat, low) and not re.search(r"tareekh|tarikh|تاریخ|baje|بجے|:", low):
                    pick = st.offers[i]
                    st.chosen, st.offers, st.awaiting = pick, [], None
                    trace.append(f"short ordinal '{text}': picked offer {i + 1}")
                    return self._advance(st, trace)
        if st.awaiting in ("slot_choice", "offer_one") and not (set(slots) - {"TIME"}):
            pick = self._pick_offer(st, text, intent, slots)
            if pick is not None:
                st.chosen, st.offers, st.awaiting = pick, [], None
                trace.append(f"picked offer {pick['day']} {pick['start_min']}")
                return self._advance(st, trace)
            if intent == "deny":
                trace.append("offers declined: ask for another day")
                st.offers, st.awaiting, st.date, st.time = [], "DATE", None, None
                st.slots.pop("DATE", None)
                st.slots.pop("TIME", None)
                return [say("ask_DATE", L)]
            if intent in ("confirm", "inform") and "TIME" not in slots:
                return [say("pick_again", L)]
        if st.awaiting == "task_for_ref" and intent in TASK_OF_INTENT:
            st.task = TASK_OF_INTENT[intent]

        # 5) start or switch task
        new_task = TASK_OF_INTENT.get(intent)
        if intent == "describe_symptom" and st.task is None:
            new_task = "book"
        if intent == "doctor_availability":
            return self._availability(st, p, slots, trace)
        if new_task and st.task and new_task != st.task and st.awaiting and not slots \
                and p["intent_conf"] < SWITCH_CONF_MIN:
            trace.append(f"ignored weak switch to {new_task} ({p['intent_conf']:.2f}) while waiting for {st.awaiting}")
            return self._reask(st) or self._advance(st, trace)
        if new_task and new_task != st.task:
            if st.task:
                trace.append(f"task switch {st.task} -> {new_task}")
            st.reset_task()
            st.task = new_task
            trace.append(f"task = {new_task}")
        if st.task is None:
            if not slots and not p["rules"].get("doctor_id"):
                if intent == "confirm":
                    return [say("anything_else", L)]
                if intent == "deny":
                    return [say("anything_else", L)]
                if intent == "greet":
                    return [say("greet", L)]
                return [say("not_understood", L)]
            labels = set(slots)
            if labels <= {"APPOINTMENT_ID", "PHONE"}:
                st.slots.update(slots)
                st.awaiting = "task_for_ref"
                return [say("ask_task", L)]
            st.task = "book"
            trace.append("no task yet, slots given: assume booking")

        # 6) fill slots from this message
        notes = self._apply(st, p, slots, trace, intent)
        if notes and notes[0] is None:   # a hard error message was returned
            return notes[1:]
        return notes + self._advance(st, trace)

    def _change_request(self, st, text, intent, trace):
        """'time badal dein', 'din change karna hai', 'doctor koi aur': clear that part and ask again."""
        L = st.lang
        low = text.lower()
        st.offers = []
        if re.search(r"\bdin\b|date|tareekh|tarikh|\bday\b|دن|تاریخ", low):
            trace.append("change request: date")
            st.date, st.chosen, st.awaiting = None, None, "DATE"
            st.slots.pop("DATE", None)
            return [say("ask_DATE", L)]
        if re.search(r"waqt|time|tym|baje|وقت|ٹائم", low):
            trace.append("change request: time")
            st.time, st.chosen, st.awaiting = None, None, "TIME"
            st.slots.pop("TIME", None)
            return [say("ask_TIME", L)]
        if re.search(r"doctor|\bdr\b|department|ڈاکٹر|شعبہ", low) and st.task == "book":
            trace.append("change request: doctor")
            st.doctor_id = st.department = st.dept_source = st.chosen = None
            st.awaiting = "DEPARTMENT"
            return [say("ask_DEPARTMENT", L)]
        if re.search(r"naam|name|نام", low) and st.task == "book":
            st.slots.pop("PATIENT_NAME", None)
            st.awaiting = "PATIENT_NAME"
            return [say("ask_PATIENT_NAME", L)]
        if re.search(r"number|phone|mobile|نمبر|فون", low) and st.task == "book":
            st.slots.pop("PHONE", None)
            st.awaiting = "PHONE"
            return [say("ask_PHONE", L)]
        if intent == "deny" and st.awaiting == "change":
            st.reset_task()
            return [say("aborted", L)]
        if st.awaiting != "change":
            st.chosen, st.awaiting = None, "change"
            return [say("ask_change", L)]
        return None

    # ================================================================== slot filling
    def _collect_slots(self, p):
        """Last value per label (a reschedule like '1 tareekh wali ko 28 tareekh pe' keeps the new date)."""
        out = {}
        for s in p["slots"]:
            out[s["label"]] = s["value"]
        return out

    def _changes_slots(self, slots):
        return bool(set(slots) & {"DATE", "TIME", "DOCTOR", "DEPARTMENT", "SYMPTOM", "PATIENT_NAME", "PHONE"})

    def _apply(self, st, p, slots, trace, intent):
        L = st.lang
        notes = []
        # --- awaiting a bare answer the model could not tag ("Ali", "kal", "koi bhi")
        if st.awaiting == "PATIENT_NAME" and "PATIENT_NAME" not in slots and intent in ("inform", "book_appointment") \
                and not slots and 1 <= len(p["text"].split()) <= 4:
            slots["PATIENT_NAME"] = re.sub(r"^(mera naam|naam|name|my name is|میرا نام)\s+|\s+(hai|ہے)$", "",
                                           p["text"].strip(), flags=re.I).strip(" .,")
            trace.append("bare answer taken as PATIENT_NAME")
        if st.awaiting == "TIME" and "TIME" not in slots and ANY_TIME_RE.search(p["text"]):
            slots["TIME"] = "koi bhi"
        if st.awaiting == "DATE" and "DATE" not in slots and ANY_TIME_RE.search(p["text"]):
            today = now_pkt().date()
            st.date, st.chosen = DateValue(today, today + timedelta(days=SEARCH_DAYS - 1), "any"), None
            trace.append(f"'any day' read as {today}..{st.date.end}")

        # --- doctor
        did = p["rules"].get("doctor_id")
        if "DOCTOR" in slots and not did:
            did = self.nlu.doctors.find(slots["DOCTOR"]) or self.nlu.doctors.find("Dr " + slots["DOCTOR"])
        if did and not (st.task == "reschedule" and st.ref):
            if did != st.doctor_id:
                doc = self.clinic.doctor(did)
                st.doctor_id, st.department, st.dept_source = did, doc["department"], "doctor"
                st.chosen = None
                trace.append(f"doctor -> {doc['name_roman']} ({doc['department']})")
        elif "DOCTOR" in slots and not did:
            trace.append(f"doctor '{slots['DOCTOR']}' not in clinic list; ignored")

        # --- department: explicit name > model routing (symptom) > keep
        if st.task == "book" and st.dept_source != "doctor":
            dept, src = None, None
            if "DEPARTMENT" in slots:
                dept, src = department_from_name(slots["DEPARTMENT"]), "named"
            if not dept and (p.get("department") or "SYMPTOM" in slots or st.awaiting == "DEPARTMENT"):
                d, conf = (p.get("department"), p.get("department_conf", 0.0)) if p.get("department") \
                    else self.nlu.department_of(p["text"])
                other = set(slots) & {"DATE", "TIME", "PATIENT_NAME", "PHONE", "AGE", "APPOINTMENT_ID"}
                if "SYMPTOM" in slots or "DEPARTMENT" in slots or (intent == "describe_symptom" and not st.department) \
                        or (st.awaiting == "DEPARTMENT" and not other):
                    dept, how, why = route(p["text"], d, conf, ROUTE_CONF_MIN)
                    src = "fallback" if how == "fallback" else "symptom"
                    trace.append(f"routing ({how}): {why}")
            if dept and dept != st.department:
                st.department, st.dept_source = dept, src
                st.doctor_id, st.chosen = None, None
                if src == "symptom":
                    notes.append(say("route", L, dept=self._dept_name(dept, L)))
                elif src == "fallback":
                    notes.append(say("route_unsure", L))

        # --- date / time
        if "DATE" in slots:
            dv = parse_date(slots["DATE"], now_pkt().date())
            if dv is None:
                trace.append(f"date '{slots['DATE']}' not understood")
                st.awaiting = "DATE"
                return [None, say("bad_DATE", L, value=slots["DATE"])]
            if dv.end < now_pkt().date():
                return [None, say("past_DATE", L)]
            st.date, st.chosen = dv, None
            st.slots["DATE"] = slots["DATE"]
            trace.append(f"date '{slots['DATE']}' -> {dv.start}..{dv.end}")
        if "TIME" in slots:
            tv = parse_time(slots["TIME"])
            if tv is None:
                trace.append(f"time '{slots['TIME']}' not understood")
                st.awaiting = "TIME"
                return [None, say("bad_TIME", L, value=slots["TIME"])]
            st.time, st.chosen = tv, None
            st.slots["TIME"] = slots["TIME"]
            trace.append(f"time '{slots['TIME']}' -> {tv.start}-{tv.end} min")

        # --- patient details
        for k in ("PATIENT_NAME", "AGE", "SYMPTOM"):
            if k in slots:
                st.slots[k] = slots[k]
        if "PHONE" in slots:
            if not valid_phone(slots["PHONE"]):
                st.awaiting = "PHONE"
                return [None, say("bad_PHONE", L, value=slots["PHONE"])]
            st.slots["PHONE"] = normalize_phone(slots["PHONE"])
        if "APPOINTMENT_ID" in slots:
            st.slots["APPOINTMENT_ID"] = normalize_ref(slots["APPOINTMENT_ID"])
            if st.ref and st.ref != st.slots["APPOINTMENT_ID"]:
                st.ref = None
        return notes

    # ================================================================== planning
    def _advance(self, st, trace):
        """Ask for the next missing thing, or put a confirmation in front of the user."""
        if st.task == "book":
            return self._advance_book(st, trace)
        return self._advance_existing(st, trace)

    def _advance_book(self, st, trace):
        L = st.lang
        if not st.department:
            st.awaiting = "DEPARTMENT"
            return [say("ask_DEPARTMENT", L)]
        if not st.date:
            st.awaiting = "DATE"
            return [say("ask_DATE", L)]
        if not st.time:
            if not self._works_on(st):
                # closed / off day (e.g. a Sunday): say so now, not after asking for a time
                st.time = parse_time("koi bhi")
                trace.append("asked day is off for everyone: no time question, offering other days")
            else:
                st.awaiting = "TIME"
                return [say("ask_TIME", L)]
        msgs = []
        if not st.chosen:
            res = self._find_slot(st, trace)
            if res is not None:
                return res
            doc = self.clinic.doctor(st.chosen["doctor_id"])
            msgs.append(say("slot_held", L, doctor=self._doc_name(doc, L), day=fmt_date(st.chosen["day"], L),
                            time=fmt_time(st.chosen["start_min"], L)))
        if not st.slots.get("PATIENT_NAME"):
            st.awaiting = "PATIENT_NAME"
            return msgs + [say("ask_PATIENT_NAME", L)]
        if not st.slots.get("PHONE"):
            st.awaiting = "PHONE"
            return msgs + [say("ask_PHONE", L)]
        c = st.chosen
        doc = self.clinic.doctor(c["doctor_id"])
        st.awaiting = "confirm"
        return [say("confirm_book", L, doctor=self._doc_name(doc, L), dept=self._dept_name(doc["department"], L, short=True),
                    day=fmt_date(c["day"], L), time=fmt_time(c["start_min"], L),
                    name=st.slots["PATIENT_NAME"], phone=st.slots["PHONE"])]

    def _works_on(self, st):
        """False when the asked exact day is one the doctor (or every doctor of the department) is off."""
        d = st.date
        if not d or not d.exact:
            return True
        doctors = [st.doctor_id] if st.doctor_id else [x["id"] for x in self.clinic.doctors(st.department)]
        wds = {x["weekday"] for did in doctors for x in self.clinic.duty(did)}
        return d.start.weekday() in wds

    def _find_slot(self, st, trace):
        """Set st.chosen when the request can be met as asked, else offer alternatives.
        Returns None when a slot was chosen, else the messages to send."""
        L = st.lang
        doctors = [st.doctor_id] if st.doctor_id else [d["id"] for d in self.clinic.doctors(st.department)]
        d, t = st.date, st.time
        notes = []
        if st.doctor_id and d.exact:   # doctor not on duty on the asked weekday
            wds = {x["weekday"] for x in self.clinic.duty(st.doctor_id)}
            if d.start.weekday() not in wds:
                doc = self.clinic.doctor(st.doctor_id)
                notes.append(say("doctor_off", L, doctor=self._doc_name(doc, L),
                                 day=fmt_date(d.start, L), days=fmt_days(wds, L)))
        elif d.exact:                  # nobody in the department works that weekday (e.g. Sunday)
            wds = {x["weekday"] for did in doctors for x in self.clinic.duty(did)}
            if d.start.weekday() not in wds:
                notes.append(say("closed_day", L, day=fmt_date(d.start, L)) if d.start.weekday() == 6 else
                             say("dept_off", L, dept=self._dept_name(st.department, L, True),
                                 day=fmt_date(d.start, L), days=fmt_days(wds, L)))
        off_day = bool(notes)
        in_window = self.clinic.free_slots(doctors, d.start, d.end, t.start, t.end)
        trace.append(f"search {len(doctors)} doctor(s) {d.start}..{d.end} "
                     f"{t.start // 60:02d}:{t.start % 60:02d}-{t.end // 60:02d}:{t.end % 60:02d}: {len(in_window)} free")
        if t.pick and in_window:                       # "first slot" / "last slot"
            day0 = [s for s in in_window if s["day"] == in_window[0]["day"]]
            st.chosen = day0[-1] if t.pick == "last" else day0[0]
            return None
        if t.exact:
            if in_window:                              # free exactly as asked
                st.chosen = in_window[0]
                return None
            if not off_day:
                notes.append(say("exact_taken", L, time=fmt_time(t.start, L)))
            candidates = self._nearest(self.clinic.free_slots(doctors, d.start, d.end), t.start)
        else:
            candidates = in_window
            if not candidates:
                candidates = self.clinic.free_slots(doctors, d.start, d.end)
                if candidates and not off_day:
                    notes.append(say("none_in_window", L, day=fmt_date(d.start, L)))
        if not candidates:                              # nothing on the asked day(s): look ahead
            if not notes:
                notes.append(say("none_on_day", L, day=fmt_date(d.start, L)))
            nxt0, nxt1 = d.end + timedelta(days=1), d.end + timedelta(days=SEARCH_DAYS)
            candidates = self.clinic.free_slots(doctors, nxt0, nxt1, t.start, t.end) or \
                self.clinic.free_slots(doctors, nxt0, nxt1)
            if t.exact:
                candidates = self._nearest(candidates, t.start, by_day_first=True)
        if not candidates:
            st.awaiting = "DATE"
            st.date = None
            return notes + [say("none_at_all", L, n=SEARCH_DAYS)]
        offers = self._spread(candidates)
        st.offers = offers
        if len(offers) == 1:
            st.awaiting = "offer_one"
            o = offers[0]
            doc = self.clinic.doctor(o["doctor_id"])
            return notes + [say("offer_one", L, doctor=self._doc_name(doc, L), day=fmt_date(o["day"], L),
                                time=fmt_time(o["start_min"], L))]
        st.awaiting = "slot_choice"
        return notes + [say("offer", L, items=self._offer_lines(offers, L))]

    @staticmethod
    def _nearest(slots, minute, by_day_first=True):
        """Closest times to the asked minute, on the earliest day that has any."""
        if not slots:
            return []
        first_day = min(s["day"] for s in slots)
        pool = [s for s in slots if s["day"] == first_day] if by_day_first else slots
        return sorted(sorted(pool, key=lambda s: abs(s["start_min"] - minute))[:MAX_OFFERS],
                      key=lambda s: s["start_min"])

    @staticmethod
    def _spread(slots):
        """Up to 3 offers, preferring different days / doctors / times rather than 3 consecutive slots."""
        picked, seen = [], set()
        for s in slots:
            key = (s["day"], s["doctor_id"], s["start_min"] // 60)
            if key in seen:
                continue
            seen.add(key)
            picked.append(s)
            if len(picked) == MAX_OFFERS:
                break
        for s in slots:   # fill up if the spread rule left fewer than 3
            if len(picked) >= MAX_OFFERS:
                break
            if s not in picked:
                picked.append(s)
        return sorted(picked, key=lambda s: (s["day"], s["start_min"]))

    def _offer_lines(self, offers, L):
        lines = []
        for i, o in enumerate(offers, 1):
            doc = self.clinic.doctor(o["doctor_id"])
            sep = "، " if L == "urdu" else ", "
            lines.append(f"{i}. {self._doc_name(doc, L)}{sep}{fmt_date(o['day'], L)} {fmt_time(o['start_min'], L)}")
        return "\n".join(lines)

    def _pick_offer(self, st, text, intent, slots):
        if not st.offers:
            return None
        if st.awaiting == "offer_one" and intent == "confirm":
            return st.offers[0]
        low = text.lower()
        for i, pat in enumerate(ORDINALS[:len(st.offers)]):
            if re.search(pat, low):
                return st.offers[i]
        if "TIME" in slots:
            tv = parse_time(slots["TIME"])
            if tv:
                for o in st.offers:
                    if tv.start <= o["start_min"] < max(tv.end, tv.start + 1):
                        return o
        if intent == "confirm" and len(st.offers) == 1:
            return st.offers[0]
        return None

    # ---------------------------------------------------------------- cancel / reschedule / check
    def _advance_existing(self, st, trace):
        L = st.lang
        if not st.ref:
            ref = st.slots.get("APPOINTMENT_ID")
            if not ref and st.slots.get("PHONE"):
                found = self.clinic.appointments_by_phone(st.slots["PHONE"])
                trace.append(f"lookup by phone: {len(found)} booking(s)")
                if not found:
                    phone = st.slots.pop("PHONE")
                    st.awaiting = "APPOINTMENT_ID"
                    return [say("phone_not_found", L, phone=self._phone_mask(phone))]
                if len(found) > 1:
                    st.awaiting = "APPOINTMENT_ID"
                    items = ", ".join(f"{a['ref']} ({fmt_date(a['day'], L)})" for a in found)
                    return [say("phone_many", L, items=items)]
                ref = found[0]["ref"]
            if not ref:
                st.awaiting = "APPOINTMENT_ID"
                return [say("ask_APPOINTMENT_ID", L)]
            a = self.clinic.appointment(ref)
            if not a:
                trace.append(f"{ref} not in database")
                st.slots.pop("APPOINTMENT_ID", None)
                st.awaiting = "APPOINTMENT_ID"
                return [say("ref_not_found", L, ref=ref)]
            st.ref = a["ref"]
            trace.append(f"found {a['ref']} ({a['status']})")
        a = self.clinic.appointment(st.ref)
        doc = self.clinic.doctor(a["doctor_id"])
        info = dict(ref=a["ref"], doctor=self._doc_name(doc, L), dept=self._dept_name(doc["department"], L, True),
                    day=fmt_date(a["day"], L), time=fmt_time(a["start_min"], L), name=a["patient_name"],
                    status=STATUS[a["status"]][L])
        if st.task == "check":
            st.reset_task()
            return [say("status", L, **info)]
        if a["status"] == "cancelled":
            st.reset_task()
            return [say("already_cancelled", L, ref=a["ref"])]
        if a["day"] < now_pkt().date():
            st.reset_task()
            return [say("past_appointment", L, ref=a["ref"], when=info["day"])]
        if st.task == "cancel":
            st.awaiting = "confirm"
            return [say("confirm_cancel", L, **info)]
        # reschedule: same doctor, new date/time
        st.doctor_id, st.department, st.dept_source = a["doctor_id"], doc["department"], "appointment"
        if not st.date:
            st.awaiting = "DATE"
            return [say("ask_DATE", L)]
        if not st.time:
            if not self._works_on(st):
                # closed / off day (e.g. a Sunday): say so now, not after asking for a time
                st.time = parse_time("koi bhi")
                trace.append("asked day is off for everyone: no time question, offering other days")
            else:
                st.awaiting = "TIME"
                return [say("ask_TIME", L)]
        msgs = []
        if not st.chosen:
            res = self._find_slot(st, trace)
            if res is not None:
                return res
        c = st.chosen
        st.awaiting = "confirm"
        return msgs + [say("confirm_reschedule", L, ref=a["ref"], old=f"{info['day']} {info['time']}",
                           doctor=self._doc_name(self.clinic.doctor(c["doctor_id"]), L),
                           day=fmt_date(c["day"], L), time=fmt_time(c["start_min"], L))]

    # ================================================================== writes (only after "yes")
    def _execute(self, st, trace, sid):
        L = st.lang
        if st.task == "book":
            c = st.chosen
            a = self.clinic.book(c["doctor_id"], c["day"], c["start_min"], st.slots["PATIENT_NAME"],
                                 st.slots["PHONE"], st.slots.get("AGE"), st.slots.get("SYMPTOM"), sid, lang=L)
            if not a:
                trace.append("slot taken between offer and confirm")
                st.chosen, st.awaiting = None, None
                return [say("slot_gone", L)] + self._advance(st, trace)
            trace.append(f"DB insert {a['ref']}")
            doc = self.clinic.doctor(a["doctor_id"])
            st.reset_task()
            return [say("booked", L, ref=a["ref"], doctor=self._doc_name(doc, L), day=fmt_date(a["day"], L),
                        time=fmt_time(a["start_min"], L))]
        if st.task == "cancel":
            ref = st.ref
            ok = self.clinic.cancel(ref)
            trace.append(f"DB cancel {ref}: {ok}")
            st.reset_task()
            return [say("cancelled", L, ref=ref) if ok else say("already_cancelled", L, ref=ref)]
        if st.task == "reschedule":
            c = st.chosen
            a = self.clinic.reschedule(st.ref, c["doctor_id"], c["day"], c["start_min"])
            if not a:
                st.chosen, st.awaiting = None, None
                return [say("slot_gone", L)] + self._advance(st, trace)
            trace.append(f"DB update {a['ref']} -> {a['day']} {a['start_min']}")
            doc = self.clinic.doctor(a["doctor_id"])
            st.reset_task()
            return [say("rescheduled", L, ref=a["ref"], doctor=self._doc_name(doc, L), day=fmt_date(a["day"], L),
                        time=fmt_time(a["start_min"], L))]
        st.reset_task()
        return [say("anything_else", L)]

    # ================================================================== info answers
    def _availability(self, st, p, slots, trace):
        """'Dr Kamran kab baithte hain?' / 'skin specialist kal hain?' Answer from duty table + next free slot."""
        L = st.lang
        did = p["rules"].get("doctor_id") or (self.nlu.doctors.find(slots["DOCTOR"]) if "DOCTOR" in slots else None)
        if did:
            docs = [self.clinic.doctor(did)]
        else:
            dept = department_from_name(slots["DEPARTMENT"]) if "DEPARTMENT" in slots else None
            if not dept and p.get("department") and p.get("department_conf", 0) >= ROUTE_CONF_MIN:
                dept = p["department"]
            if not dept:
                st.awaiting = "DEPARTMENT"
                if st.task is None:
                    st.task = "book"
                return [say("ask_DEPARTMENT", L)]
            docs = self.clinic.doctors(dept)
        today = now_pkt().date()
        dv = parse_date(slots.get("DATE", ""), today) if "DATE" in slots else None
        out = []
        for doc in docs:
            duty = self.clinic.duty(doc["id"])
            hours = sorted({(x["start_min"], x["end_min"]) for x in duty})
            hrs = ("، " if L == "urdu" else ", ").join(f"{fmt_time(a, L)} - {fmt_time(b, L)}" for a, b in hours)
            out.append(say("availability", L, doctor=self._doc_name(doc, L), dept=self._dept_name(doc["department"], L, True),
                           days=fmt_days([x["weekday"] for x in duty], L), hours=hrs))
        ids = [d["id"] for d in docs]
        start, end = (dv.start, dv.end) if dv else (today, today + timedelta(days=SEARCH_DAYS))
        free = self.clinic.free_slots(ids, start, end, limit=1) or \
            self.clinic.free_slots(ids, today, today + timedelta(days=SEARCH_DAYS), limit=1)
        if free:
            f = free[0]
            out.append(say("next_free", L, day=fmt_date(f["day"], L), time=fmt_time(f["start_min"], L)))
        # carry the doctor/department into a booking the user can continue
        if st.task in (None, "book"):
            st.task = "book"
            st.department = docs[0]["department"]
            st.dept_source = "doctor" if did else "named"
            st.doctor_id = did
            if dv:
                st.date = dv
                st.slots["DATE"] = slots["DATE"]
            st.chosen = None
            tv = parse_time(slots["TIME"]) if "TIME" in slots else None
            if tv:
                st.time = tv
                st.slots["TIME"] = slots["TIME"]
            trace.append("availability answered; booking kept open with this doctor/department")
            if not st.date:
                st.awaiting = "DATE"
                out.append(say("book_hint", L))
            else:   # a day was named: carry on as a booking (off day -> alternatives now, else time or offers)
                out.extend(self._advance_book(st, trace))
        return out

    def _faq(self, st, text, slots, p):
        L = st.lang
        low = text.lower()
        fees = None
        did = p["rules"].get("doctor_id")
        dept = self.clinic.doctor(did)["department"] if did else \
            (department_from_name(slots["DEPARTMENT"]) if "DEPARTMENT" in slots else None)
        if dept:
            dd = self.clinic.department(dept)
            fees = f"{self._dept_name(dept, L, True)}: Rs. {dd['fee']}"
        else:
            fees = ", ".join(f"{self._dept_name(d['key'], L, True)} Rs. {d['fee']}" for d in self.clinic.departments())
        kw = dict(fees=fees, address=CLINIC_FACTS["address"][L], phone=CLINIC_FACTS["phone"])
        # "kya kal clinic khula hai?" -> answer for that day
        if "DATE" in slots:
            dv = parse_date(slots["DATE"], now_pkt().date())
            if dv and dv.exact and not re.search(r"fee|فیس", low):
                if dv.start.weekday() == 6:
                    return ("{day} ko clinic band hai (Itwaar ki chutti)." if L == "roman"
                            else "{day} کو کلینک بند ہے (اتوار کی چھٹی)۔").format(day=fmt_date(dv.start, L))
                return ("Ji, {day} ko clinic subah 10 se raat 9 baje tak khula hai." if L == "roman"
                        else "جی، {day} کو کلینک صبح دس سے رات نو بجے تک کھلا ہے۔").format(day=fmt_date(dv.start, L))
        for pat, ro, ur in FAQ:
            if re.search(pat, low):
                return (ro if L == "roman" else ur).format(**kw)
        return (FAQ_DEFAULT[0] if L == "roman" else FAQ_DEFAULT[1]).format(**kw)

    def _reask(self, st):
        """After a side question, repeat the question the task is waiting on."""
        if not st.task or not st.awaiting:
            return []
        key = {"DEPARTMENT": "ask_DEPARTMENT", "DATE": "ask_DATE", "TIME": "ask_TIME",
               "PATIENT_NAME": "ask_PATIENT_NAME", "PHONE": "ask_PHONE", "APPOINTMENT_ID": "ask_APPOINTMENT_ID",
               "confirm": "yes_no", "slot_choice": "pick_again", "offer_one": "yes_no",
               "change": "ask_change", "task_for_ref": "ask_task"}.get(st.awaiting)
        return [say(key, st.lang)] if key else []

    # ================================================================== names
    def _doc_name(self, doc, L):
        return doc["name_urdu"] if L == "urdu" else doc["name_roman"]

    def _dept_name(self, key, L, short=False):
        d = self.clinic.department(key)
        return d["name_urdu"] if L == "urdu" else (d["name_en"] if short else d["name_roman"])

    @staticmethod
    def _phone_mask(p):
        return p[:4] + "****" + p[-3:] if len(p) >= 8 else p
