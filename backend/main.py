"""MedBook API: NLU + dialogue manager + clinic database behind HTTP.

    uvicorn main:app --reload --port 8000

Endpoints
    GET  /api/health                  which NLU engine is loaded, voice on/off
    POST /api/chat    {session_id, text}   -> reply, NLU output, dialogue state, decision trace
    POST /api/reset   {session_id}
    POST /api/voice   multipart: audio (+ session_id)  -> transcript + same as /api/chat  (voice.py, Whisper)
    POST /api/tts     {text}  Urdu-script text -> audio/wav  (voice.py, MMS-TTS)
    GET  /api/doctors, /api/appointments   for the demo side panel (phones masked if MEDBOOK_ADMIN_TOKEN is set)
  Staff (header X-Admin-Token when MEDBOOK_ADMIN_TOKEN is set; open in the laptop demo)
    GET  /api/admin/schedule?day=YYYY-MM-DD every doctor's slots that day: free / booked (patient) / past
    POST /api/admin/appointments/{ref}/cancel
    GET  /api/admin/reminders               reminder log;  POST /api/admin/reminders/run  send due ones now
    POST /api/admin/reset-db                rebuild the demo database

Storage: PostgreSQL if DATABASE_URL is set (else SQLite), sessions in Redis if REDIS_URL is set (else memory).
"""
import os
import tempfile
import uuid
from datetime import date

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel

import clinic_db
import reminders
import voice as vc
from clinic_db import Clinic
from dialogue import DialogueManager
from nlu import NLU
from replies import fmt_time

app = FastAPI(title="MedBook API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("MEDBOOK_CORS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])

clinic = Clinic()
nlu = NLU(clinic.doctors())
dm = DialogueManager(nlu, clinic)

# ----------------------------------------------------------------------------- voice (optional, see voice.py)
vc.set_vocabulary([d.get("name_urdu") for d in clinic.doctors()])
if os.environ.get("MEDBOOK_VOICE_PRELOAD") == "1":
    vc.preload()


# ----------------------------------------------------------------------------- routes
class ChatIn(BaseModel):
    text: str
    session_id: str | None = None


class ResetIn(BaseModel):
    session_id: str


def jsonable(x):
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, list):
        return [jsonable(v) for v in x]
    if isinstance(x, date):
        return x.isoformat()
    return x


@app.get("/api/health")
def health():
    return {"ok": True, "nlu_engine": nlu.engine_name,
            "model_dir": getattr(nlu.engine, "model_dir", None),
            "voice": vc.asr_available(), "tts": vc.tts_available(), "whisper_model": vc.WHISPER_MODEL,
            "db": clinic.db.describe(), "sessions": dm.sessions.describe(),
            "reminders": os.environ.get("MEDBOOK_REMINDER_PROVIDER", "log"),
            "now": clinic_db.now_pkt().isoformat(timespec="minutes")}


@app.post("/api/chat")
def chat(body: ChatIn):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "empty message")
    sid = body.session_id or uuid.uuid4().hex
    return jsonable({"session_id": sid, **dm.handle(sid, text[:500])})


@app.post("/api/reset")
def reset(body: ResetIn):
    dm.reset(body.session_id)
    return {"ok": True}


@app.post("/api/voice")
async def voice(audio: UploadFile = File(...), session_id: str = Form(None)):
    if not vc.asr_available():
        raise HTTPException(501, "Voice is off: pip install faster-whisper \"av<16\", then restart the backend.")
    data = await audio.read()
    if len(data) > 10_000_000:
        raise HTTPException(413, "Recording too long (10 MB max, about a minute).")
    suffix = os.path.splitext(audio.filename or "")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        path = f.name
    try:
        text, raw, info = await run_in_threadpool(vc.transcribe, path)
    except Exception as e:
        raise HTTPException(422, f"Could not read the recording ({type(e).__name__}).")
    finally:
        os.unlink(path)
    if not text:
        raise HTTPException(422, "No speech heard in the recording.")
    sid = session_id or uuid.uuid4().hex
    out = await run_in_threadpool(dm.handle, sid, text[:500])
    return jsonable({"session_id": sid, "transcript": text, "transcript_raw": raw, "asr": info,
                     "asr_language": info["language"], **out})


class TTSIn(BaseModel):
    text: str


@app.post("/api/tts")
async def tts(body: TTSIn):
    """Urdu-script reply -> WAV (Meta MMS-TTS). Roman Urdu text is refused with 415."""
    if not vc.tts_available():
        raise HTTPException(501, "Spoken replies are off: pip install torch transformers, or MEDBOOK_TTS=0 is set.")
    text = body.text.strip()[:600]
    if not vc.can_speak(text):
        raise HTTPException(415, "Only Urdu-script replies can be spoken.")
    try:
        wav = await run_in_threadpool(vc.synthesize, text)
    except ValueError:
        raise HTTPException(415, "Nothing to say in this text.")
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "max-age=3600"})


@app.get("/api/doctors")
def doctors():
    out = []
    for d in clinic.doctors():
        duty = clinic.duty(d["id"])
        out.append({**d, "days": sorted({x["weekday"] for x in duty}),
                    "hours": sorted({f"{fmt_time(x['start_min'], 'roman')} - {fmt_time(x['end_min'], 'roman')}"
                                     for x in duty})})
    return out


ADMIN_TOKEN = os.environ.get("MEDBOOK_ADMIN_TOKEN", "")


def is_staff(token):
    return not ADMIN_TOKEN or token == ADMIN_TOKEN


def require_staff(x_admin_token: str = Header(default="")):
    if not is_staff(x_admin_token):
        raise HTTPException(401, "Staff only: send the X-Admin-Token header.")


def mask_phone(p):
    return (p[:4] + "*****" + p[-2:]) if p and len(p) > 6 else p


def appt_json(a, staff=True):
    return {"ref": a["ref"], "doctor": a["doctor_roman"], "doctor_id": a["doctor_id"],
            "department": a["department"], "day": a["day"].isoformat(), "start_min": a["start_min"],
            "time": fmt_time(a["start_min"], "roman"), "patient": a["patient_name"],
            "phone": a["phone"] if staff else mask_phone(a["phone"]), "age": a.get("age"),
            "reason": a.get("reason"), "status": a["status"], "lang": a.get("lang"),
            "source": "seed" if a["session_id"] == "seed" else "chat"}


@app.get("/api/appointments")
def appointments(x_admin_token: str = Header(default="")):
    staff = is_staff(x_admin_token)
    return [appt_json(a, staff) for a in clinic.all_appointments()]


# ----------------------------------------------------------------------------- staff view
@app.get("/api/admin/schedule", dependencies=[Depends(require_staff)])
def admin_schedule(day: date | None = None):
    day = day or clinic_db.now_pkt().date()
    cols = []
    for c in clinic.day_schedule(day):
        cols.append({"doctor": c["doctor"], "department": clinic.department(c["doctor"]["department"])["name_en"],
                     "shifts": [f"{fmt_time(x['start_min'], 'roman')} - {fmt_time(x['end_min'], 'roman')}"
                                for x in c["shifts"]],
                     "slots": [{"start_min": s["start_min"], "time": fmt_time(s["start_min"], "roman"),
                                "state": s["state"],
                                "appointment": appt_json(s["appointment"]) if s["appointment"] else None}
                               for s in c["slots"]],
                     "cancelled": [appt_json(a) for a in c["cancelled"]]})
    booked = sum(1 for c in cols for s in c["slots"] if s["state"] == "booked")
    free = sum(1 for c in cols for s in c["slots"] if s["state"] == "free")
    return {"day": day.isoformat(), "weekday": day.strftime("%A"), "doctors": cols,
            "totals": {"booked": booked, "free": free, "doctors_on_duty": len(cols)}}


@app.post("/api/admin/appointments/{ref}/cancel", dependencies=[Depends(require_staff)])
def admin_cancel(ref: str):
    if not clinic.appointment(ref):
        raise HTTPException(404, f"No booking {ref}")
    return {"ok": clinic.cancel(ref), "appointment": appt_json(clinic.appointment(ref))}


@app.get("/api/admin/reminders", dependencies=[Depends(require_staff)])
def admin_reminders(limit: int = 50):
    return {"provider": os.environ.get("MEDBOOK_REMINDER_PROVIDER", "log"),
            "due_now": [{"ref": a["ref"], "kind": k} for a, k in reminders.due(clinic)],
            "log": reminders.recent(clinic, limit)}


@app.post("/api/admin/reminders/run", dependencies=[Depends(require_staff)])
def admin_run_reminders():
    return {"sent": reminders.run_due(clinic)}


@app.post("/api/admin/reset-db", dependencies=[Depends(require_staff)])
def reset_db():
    clinic.reset()
    dm.sessions.clear()
    return {"ok": True, "appointments": len(clinic.all_appointments())}
