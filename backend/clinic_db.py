"""Clinic schedule (PostgreSQL in deployment, SQLite for tests and the laptop demo): departments, doctors, weekly duty hours and appointments.

Free slots are not stored. They are computed from each doctor's duty hours minus the
appointments already booked, so the bot can never offer a slot that does not exist and
two patients can never get the same slot (UNIQUE index on doctor + date + time).

    python clinic_db.py --reset      # rebuild the demo database with seed bookings
"""
import argparse
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "data_gen"))
from lexicons import DOCTORS  # noqa: E402

from db import INTEGRITY_ERRORS, Database  # noqa: E402

DB_PATH = Path(os.environ.get("MEDBOOK_DB", HERE / "data" / "clinic.db"))
PKT = timezone(timedelta(hours=5))   # Pakistan has no daylight saving
SLOT_MIN = 20
BOOKING_WINDOW_DAYS = 60

DEPARTMENTS = {
    # key: (English name, Roman Urdu name, Urdu name, fee in PKR)
    "general_physician": ("General Physician", "General Physician (aam doctor)", "جنرل فزیشن", 1500),
    "cardiology": ("Cardiology", "Cardiology (dil ke mahir)", "امراض قلب", 3000),
    "dermatology": ("Dermatology", "Dermatology (jild ke mahir)", "جلد کے ماہر", 2500),
    "ent": ("ENT", "ENT (naak kaan gala)", "ناک کان گلا", 2000),
    "gastroenterology": ("Gastroenterology", "Gastroenterology (pait aur maiday ke mahir)", "معدہ و جگر", 2500),
    "orthopedics": ("Orthopedics", "Orthopedics (haddi jor ke mahir)", "ہڈی جوڑ", 2500),
    "gynecology": ("Gynecology", "Gynecology (lady doctor)", "گائنی", 2500),
    "pediatrics": ("Pediatrics", "Pediatrics (bachon ke doctor)", "بچوں کے ماہر", 2000),
}

# Duty pattern per doctor: (weekdays Mon=0, start hour, end hour). Two doctors per department,
# one morning and one evening, so most requests have an answer and some do not (for the demo).
SHIFTS = [
    ([0, 1, 2, 3, 4, 5], 10, 14),   # first doctor of each department: Mon-Sat morning
    ([0, 2, 4], 17, 21),            # second doctor: Mon/Wed/Fri evening
]
GP_EXTRA = ([1, 3, 5], 16, 20)      # second GP also Tue/Thu/Sat evening

SCHEMA = """
CREATE TABLE IF NOT EXISTS departments (
    key TEXT PRIMARY KEY, name_en TEXT, name_roman TEXT, name_urdu TEXT, fee INTEGER);
CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY, name_roman TEXT, name_urdu TEXT, department TEXT REFERENCES departments(key));
CREATE TABLE IF NOT EXISTS duty (
    doctor_id INTEGER REFERENCES doctors(id), weekday INTEGER, start_min INTEGER, end_min INTEGER);
CREATE TABLE IF NOT EXISTS appointments (
    ref TEXT PRIMARY KEY, doctor_id INTEGER REFERENCES doctors(id), day {DATE}, start_min INTEGER,
    patient_name TEXT, phone TEXT, age TEXT, reason TEXT,
    status TEXT DEFAULT 'booked', created_at {TS}, updated_at {TS}, session_id TEXT, lang TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_patient_per_slot
    ON appointments(doctor_id, day, start_min) WHERE status = 'booked';
CREATE INDEX IF NOT EXISTS appointments_by_day ON appointments(day, status);
CREATE INDEX IF NOT EXISTS appointments_by_phone ON appointments(phone, status);
CREATE TABLE IF NOT EXISTS reminders (
    ref TEXT REFERENCES appointments(ref), kind TEXT, channel TEXT, status TEXT, detail TEXT,
    message TEXT, created_at {TS}, PRIMARY KEY (ref, kind))
"""
TABLES = ["reminders", "appointments", "duty", "doctors", "departments"]   # drop order (foreign keys)
TYPES = {"sqlite": {"DATE": "TEXT", "TS": "TEXT"}, "postgres": {"DATE": "DATE", "TS": "TIMESTAMP"}}

# Bookings that exist before the demo starts, so cancel / check / reschedule can be shown
# with the booking numbers used in the dataset (MB-1042 and so on).
SEED_BOOKINGS = [
    ("MB-1042", "Dr. Ahmed Raza", 2, 11 * 60, "Ali Raza", "03001234567"),
    ("MB-2210", "Dr. Nadia Hussain", 3, 12 * 60, "Ayesha", "03211234567"),
    ("MB-0087", "Dr. Rabia Aslam", 1, 10 * 60 + 20, "Hamza", "03337654321"),
    ("MB-3315", "Dr. Kamran Shah", 4, 13 * 60, "Fatima Noor", "03459876543"),
    ("MB-4521", "Dr. Usman Ghani", 2, 10 * 60, "Bilal Ahmed", "03134567890"),
    ("MB-7781", "Dr. Farhan Butt", 5, 11 * 60 + 40, "Sana Khan", "03125556677"),
]


def now_pkt():
    fixed = os.environ.get("MEDBOOK_NOW")   # e.g. 2026-11-23T09:00 for repeatable tests
    if fixed:
        return datetime.fromisoformat(fixed)
    return datetime.now(PKT).replace(tzinfo=None)


def _now():
    return now_pkt().replace(microsecond=0)


def _as_date(v):
    return v if isinstance(v, date) and not isinstance(v, datetime) else date.fromisoformat(str(v)[:10])


def connect(path=None, url=None):
    """Open the database, create tables, seed if empty. An explicit SQLite `path` (tests, simulations) wins;
    otherwise PostgreSQL if DATABASE_URL is set, else the SQLite file at MEDBOOK_DB."""
    if path is not None and url is None:
        url = ""
    database = Database(url=url, sqlite_path=path or DB_PATH)
    create_schema(database)
    if not database.one("SELECT 1 AS x FROM doctors LIMIT 1"):
        seed(database)
    return database


def create_schema(database):
    database.script(SCHEMA.format(**TYPES[database.kind]))
    if database.kind == "sqlite":   # demo databases made before the lang column existed
        cols = {r["name"] for r in database.q("PRAGMA table_info(appointments)")}
        if "lang" not in cols:
            database.run("ALTER TABLE appointments ADD COLUMN lang TEXT")


def seed(database):
    with database.transaction() as tx:
        for k, (en, ro, ur, fee) in DEPARTMENTS.items():
            tx.run("INSERT INTO departments VALUES (?,?,?,?,?) ON CONFLICT (key) DO NOTHING", (k, en, ro, ur, fee))
        seen = {}
        for i, (names, dept) in enumerate(DOCTORS, start=1):
            tx.run("INSERT INTO doctors VALUES (?,?,?,?)", (i, names["roman"], names["urdu"], dept))
            n = seen.get(dept, 0)
            seen[dept] = n + 1
            shifts = [SHIFTS[min(n, 1)]] + ([GP_EXTRA] if dept == "general_physician" and n == 1 else [])
            for days, a, b in shifts:
                for wd in days:
                    tx.run("INSERT INTO duty VALUES (?,?,?,?)", (i, wd, a * 60, b * 60))
        today = now_pkt().date()
        for ref, doc, plus, start, name, phone in SEED_BOOKINGS:
            did = tx.one("SELECT id FROM doctors WHERE name_roman=?", (doc,))["id"]
            day = today + timedelta(days=plus)
            while not tx.one("SELECT 1 AS x FROM duty WHERE doctor_id=? AND weekday=? AND start_min<=? AND end_min>?",
                             (did, day.weekday(), start, start)):
                day += timedelta(days=1)
            tx.run("INSERT INTO appointments (ref, doctor_id, day, start_min, patient_name, phone, status,"
                   " created_at, session_id, lang) VALUES (?,?,?,?,?,?,'booked',?,'seed','roman')",
                   (ref, did, day, start, name, phone, _now()))


class Clinic:
    """All schedule reads and writes the dialogue manager is allowed to do.

    Every method takes an optional `tx`, so several calls can share one transaction (Clinic.book)."""

    def __init__(self, path=None, url=None):
        self.db = connect(path, url)

    def _d(self, tx):
        return tx or self.db

    def reset(self):
        """Delete everything and rebuild the demo data (doctors, duty hours, seed bookings)."""
        self.db.drop_all(TABLES)
        create_schema(self.db)
        seed(self.db)

    def close(self):
        self.db.close()

    # ---------------------------------------------------------------- lookups
    def departments(self):
        return self.db.q("SELECT * FROM departments ORDER BY key")

    def department(self, key):
        return self.db.one("SELECT * FROM departments WHERE key=?", (key,))

    def doctors(self, department=None):
        q = "SELECT * FROM doctors" + (" WHERE department=?" if department else "") + " ORDER BY id"
        return self.db.q(q, (department,) if department else ())

    def doctor(self, doctor_id):
        return self.db.one("SELECT * FROM doctors WHERE id=?", (doctor_id,))

    def duty(self, doctor_id, tx=None):
        return self._d(tx).q(
            "SELECT weekday, start_min, end_min FROM duty WHERE doctor_id=? ORDER BY weekday, start_min",
            (doctor_id,))

    # ---------------------------------------------------------------- slots
    def free_slots(self, doctor_ids, start_day, end_day, t_start=0, t_end=24 * 60, limit=50, tx=None):
        """Free slots as dicts {doctor_id, day (date), start_min}, sorted by day then time."""
        d = self._d(tx)
        now = now_pkt()
        start_day = max(start_day, now.date())
        end_day = min(end_day, now.date() + timedelta(days=BOOKING_WINDOW_DAYS))
        if start_day > end_day or not doctor_ids:
            return []
        duty = {did: self.duty(did, tx) for did in doctor_ids}
        booked = {(r["doctor_id"], _as_date(r["day"]), r["start_min"]) for r in d.q(
            "SELECT doctor_id, day, start_min FROM appointments WHERE day>=? AND day<=? AND status='booked'",
            (start_day, end_day))}
        out = []
        day = start_day
        while day <= end_day and len(out) < limit:
            for did in doctor_ids:
                for x in duty[did]:
                    if x["weekday"] != day.weekday():
                        continue
                    for m in range(x["start_min"], x["end_min"], SLOT_MIN):
                        if not (t_start <= m < t_end) or (did, day, m) in booked:
                            continue
                        if day == now.date() and m <= now.hour * 60 + now.minute + 30:
                            continue   # need 30 minutes notice for same-day slots
                        out.append({"doctor_id": did, "day": day, "start_min": m})
            day += timedelta(days=1)
        out.sort(key=lambda s: (s["day"], s["start_min"], s["doctor_id"]))
        return out[:limit]

    def is_free(self, doctor_id, day, start_min, tx=None):
        return any(s["doctor_id"] == doctor_id and s["start_min"] == start_min
                   for s in self.free_slots([doctor_id], day, day, tx=tx))

    def _lock_doctor(self, tx, doctor_id):
        """Row-level lock: concurrent bookings for the same doctor queue up here until COMMIT.
        (SQLite has no row locks; BEGIN IMMEDIATE already serialises every writer.)"""
        if self.db.kind == "postgres":
            tx.one("SELECT id FROM doctors WHERE id=? FOR UPDATE", (doctor_id,))

    # ---------------------------------------------------------------- appointments
    def _new_ref(self, tx):
        rng = random.SystemRandom()
        while True:
            ref = f"MB-{rng.randint(1000, 9999)}"
            if not tx.one("SELECT 1 AS x FROM appointments WHERE ref=?", (ref,)):
                return ref

    def book(self, doctor_id, day, start_min, patient_name, phone, age=None, reason=None, session_id=None,
             lang=None):
        """Insert a booking. Returns the appointment, or None if the slot was taken meanwhile.

        Check and insert run in one transaction with the doctor's row locked, and the partial UNIQUE index
        on (doctor, day, time) is a second guard, so two patients can never hold the same slot."""
        try:
            with self.db.transaction() as tx:
                self._lock_doctor(tx, doctor_id)
                if not self.is_free(doctor_id, day, start_min, tx=tx):
                    return None
                ref = self._new_ref(tx)
                tx.run("INSERT INTO appointments (ref, doctor_id, day, start_min, patient_name, phone, age, reason,"
                       " status, created_at, session_id, lang) VALUES (?,?,?,?,?,?,?,?,'booked',?,?,?)",
                       (ref, doctor_id, day, start_min, patient_name, phone, age, reason, _now(), session_id, lang))
        except INTEGRITY_ERRORS:
            return None
        return self.appointment(ref)

    def appointment(self, ref):
        a = self.db.one(
            "SELECT a.*, d.name_roman AS doctor_roman, d.name_urdu AS doctor_urdu, d.department "
            "FROM appointments a JOIN doctors d ON d.id = a.doctor_id WHERE upper(a.ref)=upper(?)",
            (normalize_ref(ref),))
        if not a:
            return None
        a["day"] = _as_date(a["day"])
        return a

    def appointments_by_phone(self, phone):
        rows = self.db.q(
            "SELECT ref FROM appointments WHERE phone=? AND status='booked' AND day>=? ORDER BY day, start_min",
            (normalize_phone(phone), now_pkt().date()))
        return [self.appointment(r["ref"]) for r in rows]

    def cancel(self, ref):
        return self.db.run("UPDATE appointments SET status='cancelled', updated_at=? "
                           "WHERE upper(ref)=upper(?) AND status='booked'", (_now(), normalize_ref(ref))) == 1

    def reschedule(self, ref, doctor_id, day, start_min):
        try:
            with self.db.transaction() as tx:
                self._lock_doctor(tx, doctor_id)
                if not self.is_free(doctor_id, day, start_min, tx=tx):
                    return None
                n = tx.run("UPDATE appointments SET doctor_id=?, day=?, start_min=?, updated_at=? "
                           "WHERE upper(ref)=upper(?) AND status='booked'",
                           (doctor_id, day, start_min, _now(), normalize_ref(ref)))
                if n == 1:   # a moved appointment gets fresh reminders for its new time
                    tx.run("DELETE FROM reminders WHERE ref=?", (normalize_ref(ref),))
        except INTEGRITY_ERRORS:
            return None
        return self.appointment(ref) if n == 1 else None

    def all_appointments(self):
        return self._appointments("SELECT ref FROM appointments ORDER BY day, start_min")

    def appointments_on(self, day):
        return self._appointments("SELECT ref FROM appointments WHERE day=? ORDER BY start_min", (day,))

    def _appointments(self, sql, params=()):
        return [self.appointment(r["ref"]) for r in self.db.q(sql, params)]

    # ---------------------------------------------------------------- staff view
    def day_schedule(self, day):
        """Every doctor on duty that day with every 20-minute slot: free, booked (with patient) or past."""
        now = now_pkt()
        booked = {(a["doctor_id"], a["start_min"]): a for a in self.appointments_on(day) if a["status"] == "booked"}
        cancelled = [a for a in self.appointments_on(day) if a["status"] == "cancelled"]
        out = []
        for doc in self.doctors():
            shifts = [x for x in self.duty(doc["id"]) if x["weekday"] == day.weekday()]
            if not shifts:
                continue
            slots = []
            for x in shifts:
                for m in range(x["start_min"], x["end_min"], SLOT_MIN):
                    a = booked.get((doc["id"], m))
                    past = datetime.combine(day, datetime.min.time()) + timedelta(minutes=m) < now
                    slots.append({"start_min": m, "state": "booked" if a else ("past" if past else "free"),
                                  "appointment": a})
            out.append({"doctor": doc, "shifts": shifts, "slots": slots,
                        "cancelled": [a for a in cancelled if a["doctor_id"] == doc["id"]]})
        return out


def normalize_ref(ref):
    """'mb 6610', 'MB6610', 'mb-6610' -> 'MB-6610'."""
    import re
    m = re.search(r"(\d{3,5})", ref or "")
    return f"MB-{m.group(1)}" if m else (ref or "").upper()


def normalize_phone(phone):
    """'+92 300 1234567', '0300-1234567' -> '03001234567'."""
    import re
    digits = re.sub(r"\D", "", (phone or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
    if digits.startswith("92") and len(digits) == 12:
        digits = "0" + digits[2:]
    return digits


def valid_phone(phone):
    p = normalize_phone(phone)
    return len(p) == 11 and p.startswith("03")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete and rebuild the demo database")
    a = ap.parse_args()
    c = Clinic()
    if a.reset:
        c.reset()
    print(f"{c.db.describe()}: {len(c.doctors())} doctors, {len(c.all_appointments())} appointments")
    for ap_ in c.all_appointments():
        print(f"  {ap_['ref']}  {ap_['day']}  {ap_['start_min'] // 60:02d}:{ap_['start_min'] % 60:02d}  "
              f"{ap_['doctor_roman']}  {ap_['patient_name']}  {ap_['status']}")
