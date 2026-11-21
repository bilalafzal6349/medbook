"""Deployment features: database layer (SQLite and, when available, PostgreSQL), no double-booking under
concurrent requests, reminders, session stores and the staff API. Clock fixed to Mon 23 Nov 2026 09:00.

PostgreSQL / Redis tests run only when these are set (docker compose up db redis gives you both):
    MEDBOOK_TEST_PG_URL=postgresql://medbook:medbook@localhost:5432/medbook
    MEDBOOK_TEST_REDIS_URL=redis://localhost:6379/15
"""
import os
import pickle
import threading
from datetime import date, datetime

import pytest

import reminders
from clinic_db import Clinic
from sessions import MemoryStore, make_store

PG_URL = os.environ.get("MEDBOOK_TEST_PG_URL")
REDIS_URL = os.environ.get("MEDBOOK_TEST_REDIS_URL")
TUE = date(2026, 11, 24)


@pytest.fixture(params=["sqlite"] + (["postgres"] if PG_URL else []))
def clinic(request, tmp_path):
    c = Clinic(tmp_path / "c.db") if request.param == "sqlite" else Clinic(url=PG_URL)
    if request.param == "postgres":
        c.reset()   # clean slate in the shared test database
    yield c
    c.close()


def first_doctor(c, dept="dermatology"):
    return c.doctors(dept)[0]["id"]


def test_schema_and_seed(clinic):
    assert len(clinic.doctors()) == 16 and len(clinic.departments()) == 8
    assert {a["ref"] for a in clinic.all_appointments()} >= {"MB-1042", "MB-2210"}
    assert isinstance(clinic.appointment("mb 1042")["day"], date)


def test_book_cancel_reschedule_roundtrip(clinic):
    did = first_doctor(clinic)
    a = clinic.book(did, TUE, 10 * 60, "Ali", "03007654321", lang="urdu")
    assert a and a["day"] == TUE and a["lang"] == "urdu"
    assert clinic.book(did, TUE, 10 * 60, "Someone else", "03001112222") is None   # slot is taken
    assert not clinic.is_free(did, TUE, 10 * 60)
    moved = clinic.reschedule(a["ref"], did, TUE, 11 * 60)
    assert moved["start_min"] == 11 * 60 and clinic.is_free(did, TUE, 10 * 60)
    assert clinic.cancel(a["ref"]) and clinic.is_free(did, TUE, 11 * 60)
    assert clinic.appointments_by_phone("0300-7654321") == []


def test_no_double_booking_under_concurrency(clinic):
    """30 patients press "yes" for the same slot at the same moment: exactly one booking exists afterwards."""
    did = first_doctor(clinic, "cardiology")
    start = threading.Barrier(30)
    got = []

    def attempt(i):
        start.wait()
        got.append(clinic.book(did, TUE, 12 * 60, f"P{i}", f"0300{i:07d}"))

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wins = [a for a in got if a]
    assert len(wins) == 1
    same_slot = [a for a in clinic.appointments_on(TUE)
                 if a["doctor_id"] == did and a["start_min"] == 12 * 60 and a["status"] == "booked"]
    assert len(same_slot) == 1


class Collect:
    name = "test"

    def __init__(self, fail_for=()):
        self.sent, self.fail_for = [], set(fail_for)

    def send(self, to, message, **meta):
        if to in self.fail_for:
            raise RuntimeError("gateway down")
        self.sent.append((to, message, meta["kind"]))
        return "ok"


def test_reminders_once_per_kind(clinic):
    did = first_doctor(clinic, "ent")
    a = clinic.book(did, TUE, 10 * 60, "Sana", "03001230000", lang="roman")
    p = Collect()
    now = datetime(2026, 11, 23, 12, 0)   # 22 hours before -> day_before
    res = reminders.run_due(clinic, p, now)
    mine = [r for r in res if r["ref"] == a["ref"]]
    assert [r["kind"] for r in mine] == ["day_before"] and mine[0]["to"] == "+923001230000"
    assert "MedBook" in p.sent[0][1] and a["ref"] in p.sent[0][1]
    assert not [r for r in reminders.run_due(clinic, p, now) if r["ref"] == a["ref"]]   # not twice
    later = datetime(2026, 11, 24, 8, 0)   # 2 hours before -> same_day
    assert [r["kind"] for r in reminders.run_due(clinic, p, later) if r["ref"] == a["ref"]] == ["same_day"]
    assert not [r for r in reminders.run_due(clinic, p, later) if r["ref"] == a["ref"]]


def test_reminders_skip_cancelled_and_reset_on_reschedule(clinic):
    did = first_doctor(clinic, "orthopedics")
    keep = clinic.book(did, TUE, 10 * 60, "Hamza", "03001230001", lang="urdu")
    gone = clinic.book(did, TUE, 10 * 60 + 20, "Zara", "03001230002")
    clinic.cancel(gone["ref"])
    p = Collect()
    now = datetime(2026, 11, 23, 12, 0)
    refs = {r["ref"] for r in reminders.run_due(clinic, p, now)}
    assert keep["ref"] in refs and gone["ref"] not in refs
    assert any("یاد دہانی" in m for _, m, _ in p.sent)   # Urdu patient gets an Urdu SMS
    clinic.reschedule(keep["ref"], did, TUE, 11 * 60)
    assert keep["ref"] in {r["ref"] for r in reminders.run_due(clinic, p, now)}   # new time, new reminder


def test_failed_reminder_is_recorded(clinic):
    did = first_doctor(clinic, "pediatrics")
    a = clinic.book(did, TUE, 10 * 60, "Ali", "03009999999")
    res = reminders.run_due(clinic, Collect(fail_for={"+923009999999"}), datetime(2026, 11, 23, 12, 0))
    assert [r["status"] for r in res if r["ref"] == a["ref"]] == ["failed"]
    log = {(r["ref"], r["status"]) for r in reminders.recent(clinic)}
    assert (a["ref"], "failed") in log


def test_day_schedule(clinic):
    did = first_doctor(clinic, "gynecology")
    clinic.book(did, TUE, 10 * 60, "Ayesha", "03001230003")
    cols = {c["doctor"]["id"]: c for c in clinic.day_schedule(TUE)}
    states = {s["start_min"]: s["state"] for s in cols[did]["slots"]}
    assert states[10 * 60] == "booked" and states[10 * 60 + 20] == "free" and len(states) == 12   # 10:00-14:00


# ----------------------------------------------------------------------------- sessions
def _state_after_turns(store):
    from dialogue import DialogueManager
    from nlu import NLU
    import tempfile
    from pathlib import Path
    c = Clinic(Path(tempfile.mkdtemp()) / "s.db")
    dm = DialogueManager(NLU(c.doctors()), c, sessions=store)
    dm.handle("s1", "mujhe kal skin specialist ko dikhana hai")
    dm.handle("s1", "subah")
    return dm


def test_memory_store_state_pickles():
    dm = _state_after_turns(MemoryStore())
    st = pickle.loads(pickle.dumps(dm.sessions["s1"]))
    assert st.department == "dermatology" and st.date.start == TUE and st.turns == 2


def test_make_store_defaults_to_memory():
    assert make_store("").kind == "memory"


@pytest.mark.skipif(not REDIS_URL, reason="MEDBOOK_TEST_REDIS_URL not set")
def test_redis_store_survives_a_new_manager():
    store = make_store(REDIS_URL)
    store.clear()
    dm = _state_after_turns(store)
    assert store["s1"].department == "dermatology"
    from dialogue import DialogueManager
    dm2 = DialogueManager(dm.nlu, dm.clinic, sessions=make_store(REDIS_URL))   # e.g. another worker
    r = dm2.handle("s1", "1")
    assert r["state"]["department"] == "dermatology" and store["s1"].turns == 3
    store.clear()


# ----------------------------------------------------------------------------- staff API
@pytest.fixture(scope="module")
def api():
    from fastapi.testclient import TestClient
    import main
    return main, TestClient(main.app)


def test_admin_schedule_open_without_token(api):
    main, client = api
    main.ADMIN_TOKEN = ""
    r = client.get("/api/admin/schedule", params={"day": "2026-11-24"})
    assert r.status_code == 200
    body = r.json()
    assert body["weekday"] == "Tuesday" and body["totals"]["doctors_on_duty"] >= 8
    assert client.get("/api/health").json()["db"].startswith("sqlite:")


def test_admin_token_required_and_phones_masked(api):
    main, client = api
    main.ADMIN_TOKEN = "s3cret"
    try:
        assert client.get("/api/admin/schedule").status_code == 401
        assert client.get("/api/admin/schedule", headers={"X-Admin-Token": "s3cret"}).status_code == 200
        public = client.get("/api/appointments").json()
        assert all("*" in a["phone"] for a in public)
        staff = client.get("/api/appointments", headers={"X-Admin-Token": "s3cret"}).json()
        assert all("*" not in a["phone"] for a in staff)
        assert client.post("/api/admin/reset-db").status_code == 401
    finally:
        main.ADMIN_TOKEN = ""


def test_admin_cancel_and_reminder_routes(api):
    main, client = api
    r = client.post("/api/admin/appointments/MB-1042/cancel")
    assert r.status_code == 200 and r.json()["appointment"]["status"] == "cancelled"
    assert client.post("/api/admin/appointments/MB-0000/cancel").status_code == 404
    assert "log" in client.get("/api/admin/reminders").json()
    assert isinstance(client.post("/api/admin/reminders/run").json()["sent"], list)
    assert client.post("/api/admin/reset-db").json()["ok"]
    assert client.get("/api/appointments").json()[0]["status"] == "booked"
