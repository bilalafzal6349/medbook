"""Automated appointment reminders (proposal: "Send automated appointment reminders to patients").

Two reminders per booking, in the language the patient chatted in:
    day_before   when the appointment is 3 to 24 hours away
    same_day     when it is less than 3 hours away
Each (booking, kind) is claimed with an INSERT into the `reminders` table before anything is sent. The primary
key on (ref, kind) means a reminder goes out at most once, even with several reminder workers running.
Rescheduling deletes a booking's reminder rows, so the new time gets fresh reminders; cancelled bookings get none.

Delivery is pluggable (MEDBOOK_REMINDER_PROVIDER):
    log       default. Prints the SMS and stores it in the reminders table (shown on the staff page).
    webhook   POSTs {"to", "message", "ref", "kind"} as JSON to MEDBOOK_SMS_WEBHOOK, for any local SMS gateway.
    twilio    Twilio SMS: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM (a Twilio number).

    python reminders.py --once            # send whatever is due now, then exit
    python reminders.py --loop --every 300
"""
import argparse
import base64
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from clinic_db import Clinic, _now, now_pkt
from replies import fmt_date, fmt_time

log = logging.getLogger("medbook.reminders")
SAME_DAY_HOURS = 3

TEXT = {
    "roman": "MedBook yaad-dihani: {name}, aap ki appointment {doctor} ke saath {day} ko {time} baje hai "
             "(booking {ref}). Cancel ya change karne ke liye MedBook chat par booking number bata dein.",
    "urdu": "میڈبک یاد دہانی: {name}، آپ کی اپائنٹمنٹ {doctor} کے ساتھ {day} کو {time} بجے ہے "
            "(بکنگ {ref})۔ منسوخ یا تبدیل کرنے کے لیے میڈبک چیٹ پر بکنگ نمبر بتا دیں۔",
}


def e164(phone):
    """'03001234567' -> '+923001234567' (Pakistani mobile numbers as stored by the bot)."""
    return "+92" + phone[1:] if phone and phone.startswith("0") else phone


def message_for(a):
    lang = a.get("lang") if a.get("lang") in TEXT else "roman"
    doctor = a["doctor_urdu"] if lang == "urdu" else a["doctor_roman"]
    return TEXT[lang].format(name=a["patient_name"] or "", doctor=doctor, day=fmt_date(a["day"], lang),
                             time=fmt_time(a["start_min"], lang), ref=a["ref"])


# ----------------------------------------------------------------------------- providers
class LogProvider:
    name = "log"

    def send(self, to, message, **meta):
        log.info("SMS to %s: %s", to, message)
        print(f"[reminder] to {to}: {message}", flush=True)
        return "logged"


class WebhookProvider:
    name = "webhook"

    def __init__(self, url=None):
        self.url = url or os.environ["MEDBOOK_SMS_WEBHOOK"]

    def send(self, to, message, **meta):
        body = json.dumps({"to": to, "message": message, **meta}).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return f"HTTP {r.status}"


class TwilioProvider:
    name = "twilio"

    def __init__(self):
        self.sid = os.environ["TWILIO_ACCOUNT_SID"]
        self.token = os.environ["TWILIO_AUTH_TOKEN"]
        self.sender = os.environ["TWILIO_FROM"]

    def send(self, to, message, **meta):
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json"
        data = urllib.parse.urlencode({"To": to, "From": self.sender, "Body": message}).encode()
        auth = base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()
        req = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {auth}"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return "twilio " + json.loads(r.read()).get("sid", "")


PROVIDERS = {"log": LogProvider, "webhook": WebhookProvider, "twilio": TwilioProvider}


def make_provider(name=None):
    return PROVIDERS[(name or os.environ.get("MEDBOOK_REMINDER_PROVIDER", "log")).lower()]()


# ----------------------------------------------------------------------------- the job
def due(clinic, now=None):
    """[(appointment, kind)] for every booked appointment that needs a reminder now and has not had it."""
    now = now or now_pkt()
    out = []
    for day in (now.date(), now.date() + timedelta(days=1)):
        for a in clinic.appointments_on(day):
            if a["status"] != "booked":
                continue
            start = datetime.combine(a["day"], datetime.min.time()) + timedelta(minutes=a["start_min"])
            left = start - now
            if left <= timedelta(0) or left > timedelta(hours=24):
                continue
            out.append((a, "same_day" if left <= timedelta(hours=SAME_DAY_HOURS) else "day_before"))
    sent = {(r["ref"], r["kind"]) for r in clinic.db.q("SELECT ref, kind FROM reminders")}
    return [(a, k) for a, k in out if (a["ref"], k) not in sent and not (k == "day_before" and (a["ref"], "same_day") in sent)]


def run_due(clinic, provider=None, now=None):
    """Send every due reminder once. Returns a list of {ref, kind, to, status, detail}."""
    provider = provider or make_provider()
    results = []
    for a, kind in due(clinic, now):
        msg = message_for(a)
        claimed = clinic.db.run(
            "INSERT INTO reminders (ref, kind, channel, status, message, created_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT (ref, kind) DO NOTHING", (a["ref"], kind, provider.name, "sending", msg, _now()))
        if claimed != 1:
            continue   # another worker got it first
        to = e164(a["phone"])
        try:
            detail, status = provider.send(to, msg, ref=a["ref"], kind=kind), "sent"
        except Exception as e:   # noqa: BLE001 - one bad number must not stop the rest
            detail, status = f"{type(e).__name__}: {e}"[:300], "failed"
            log.warning("reminder %s %s failed: %s", a["ref"], kind, detail)
        clinic.db.run("UPDATE reminders SET status=?, detail=? WHERE ref=? AND kind=?", (status, detail, a["ref"], kind))
        results.append({"ref": a["ref"], "kind": kind, "to": to, "status": status, "detail": detail})
    return results


def recent(clinic, limit=50):
    rows = clinic.db.q("SELECT * FROM reminders ORDER BY created_at DESC LIMIT ?", (int(limit),))
    for r in rows:
        r["created_at"] = str(r["created_at"])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--every", type=int, default=int(os.environ.get("MEDBOOK_REMINDER_EVERY", 300)), help="seconds")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    clinic = Clinic()
    provider = make_provider()
    print(f"reminders: {clinic.db.describe()}, provider={provider.name}", flush=True)
    while True:
        try:
            res = run_due(clinic, provider)
            print(f"{now_pkt():%Y-%m-%d %H:%M} sent {len(res)} reminder(s)", flush=True)
        except Exception as e:   # noqa: BLE001 - keep the worker alive if the database blips
            log.exception("reminder run failed: %s", e)
        if not a.loop:
            break
        time.sleep(a.every)


if __name__ == "__main__":
    main()
