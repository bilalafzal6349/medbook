"""End-to-end dialogue tests: real NLU (baseline or XLM-R) + dialogue manager + a fresh SQLite database.
Clock is fixed to Monday 23 Nov 2026 09:00 (see conftest.py)."""
import os
import re
from pathlib import Path

import pytest

from clinic_db import Clinic
from dialogue import DialogueManager
from nlu import NLU


@pytest.fixture(scope="module")
def nlu():
    return NLU(Clinic().doctors())


@pytest.fixture()
def dm(nlu, tmp_path):
    return DialogueManager(nlu, Clinic(tmp_path / "clinic.db"))


def talk(dm, turns, sid="t"):
    out = []
    for t in turns:
        out.append(dm.handle(sid, t))
    return out


def refs_in(text):
    return re.findall(r"MB-\d{4}", text)


def assert_no_invented_refs(dm, results):
    """Every booking number the bot says must exist in the database."""
    for r in results:
        for ref in refs_in(r["reply"]):
            assert dm.clinic.appointment(ref) is not None, f"bot quoted unknown {ref}: {r['reply']}"


def booked(dm):
    return [a for a in dm.clinic.all_appointments() if a["status"] == "booked" and a["session_id"] != "seed"]


def test_book_roman(dm):
    rs = talk(dm, ["salam", "mujhe kal skin specialist ko dikhana hai", "subah", "2", "Ali Raza", "0300-1234567", "ji haan"])
    assert "MB-" in rs[-1]["reply"]
    b = booked(dm)
    assert len(b) == 1 and b[0]["department"] == "dermatology" and b[0]["day"].isoformat() == "2026-11-24"
    assert b[0]["patient_name"] == "Ali Raza" and b[0]["phone"] == "03001234567"
    assert_no_invented_refs(dm, rs)


def test_book_urdu_with_correction(dm):
    rs = talk(dm, ["مجھے کل دل کے ڈاکٹر سے ملنا ہے", "صبح دس بجے", "میرا نام فاطمہ نور ہے", "03211234567",
                   "نہیں، پرسوں کر دیں", "جی ہاں"])
    assert "بکنگ نمبر" in rs[-1]["reply"]
    b = booked(dm)
    assert len(b) == 1 and b[0]["day"].isoformat() == "2026-11-25" and b[0]["start_min"] == 600
    assert b[0]["department"] == "cardiology"


def test_symptom_routing_child(dm):
    r = talk(dm, ["mere bete ko 3 din se bukhar hai"])[0]
    assert r["state"]["department"] == "pediatrics"
    assert r["state"]["task"] == "book"


def test_no_write_without_yes(dm):
    talk(dm, ["mujhe kal ENT specialist chahiye", "subah 11 baje", "Hamza", "03001112233"])
    assert booked(dm) == []
    rs = talk(dm, ["nahi"])
    assert booked(dm) == []
    assert rs[-1]["state"]["awaiting"] == "change"


def test_cancel_and_unknown_ref(dm):
    rs = talk(dm, ["MB-9999 cancel karni hai"])
    assert "nahi mila" in rs[0]["reply"]
    rs = talk(dm, ["MB-1042 cancel kar dein", "haan"])
    assert "cancel ho gayi" in rs[-1]["reply"]
    assert dm.clinic.appointment("MB-1042")["status"] == "cancelled"


def test_reschedule_keeps_ref_and_doctor(dm):
    before = dm.clinic.appointment("MB-7781")
    rs = talk(dm, ["MB-7781 ko reschedule karna hai", "agle somwar", "subah", "1", "haan"])
    after = dm.clinic.appointment("MB-7781")
    assert after["doctor_id"] == before["doctor_id"]
    assert after["day"].isoformat() == "2026-11-30"
    assert_no_invented_refs(dm, rs)


def test_check_by_phone(dm):
    r = talk(dm, ["booking number yaad nahi, number 03459876543 hai, check karna hai"])[0]
    assert "MB-3315" in r["reply"]


def test_emergency_stops_booking(dm):
    rs = talk(dm, ["mujhe kal ENT specialist chahiye", "subah 11 baje", "abbu behosh ho gaye hain"])
    assert "1122" in rs[-1]["reply"]
    assert rs[-1]["state"]["task"] is None
    assert booked(dm) == []


@pytest.mark.parametrize("text", ["seene mein shadeed dard hai aur saans nahi aa rahi", "بچے نے زہر پی لیا ہے",
                                  "accident ho gaya hai sar pe chot lagi hai", "ammi ko lagta hai stroke hua hai"])
def test_emergency_recall(dm, text):
    assert "1122" in talk(dm, [text])[0]["reply"]


def test_sunday_closed(dm):
    # 29 Nov 2026 is a Sunday: said at once, without asking for a time first
    r = talk(dm, ["29 tareekh ko general physician chahiye"])[-1]
    assert "band" in r["reply"]
    assert dm.sessions["t"].awaiting in ("slot_choice", "offer_one")
    assert all(o for o in dm.sessions["t"].offers)


def test_doctor_off_day(dm):
    # Dr. Waseem Akram (ENT, evening) works Mon/Wed/Fri only; 24 Nov is a Tuesday
    r = talk(dm, ["Dr Waseem Akram se kal appointment chahiye"])[-1]
    assert "nahi baithte" in r["reply"]


def test_same_slot_cannot_be_booked_twice(dm):
    flow = ["mujhe kal skin specialist ko dikhana hai", "subah 10 baje", "Ali", "03001234567"]
    talk(dm, flow, sid="a")
    talk(dm, flow, sid="b")           # both were told 10:00 is free
    ra = talk(dm, ["haan"], sid="a")[0]
    rb = talk(dm, ["haan"], sid="b")[0]
    assert "MB-" in ra["reply"]
    assert "kisi aur ne le liya" in rb["reply"]
    assert len(booked(dm)) == 1


def test_out_of_scope_reasks(dm):
    rs = talk(dm, ["mujhe kal ENT specialist chahiye", "bukhar ki dawai konsi lun?"])
    assert "doctor se mashwara" in rs[-1]["reply"]
    assert rs[-1]["state"]["task"] == "book"


def test_department_name_as_whisper_writes_it():
    # Whisper often drops the first letter of "ای این ٹی" (ENT); the name must still be read as ENT
    from dialogue import department_from_name
    assert department_from_name("این ٹی") == "ent"
    assert department_from_name("ای این ٹی") == "ent"
