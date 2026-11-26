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
    r = talk(dm, ["29 tareekh ko general physician chahiye", "subah"])[-1]   # 29 Nov 2026 is a Sunday
    assert "band" in r["reply"]
    assert all(o for o in dm.sessions["t"].offers)


def test_doctor_off_day(dm):
    # Dr. Waseem Akram (ENT, evening) works Mon/Wed/Fri only; 24 Nov is a Tuesday
    r = talk(dm, ["Dr Waseem Akram se kal appointment chahiye", "shaam ko"])[-1]
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


# ---------------------------------------------------------------- stuck / confused patients
TO_NAME = ["kal dil ke doctor ka appointment chahiye", "subah 11 baje"]


def test_dont_know_name_explains_and_never_stores_it(dm):
    rs = talk(dm, TO_NAME + ["nahi pata", "nahi pata mujhy", "nae pata mujhy"])
    assert rs[1]["state"]["awaiting"] == "PATIENT_NAME"
    for r in rs[2:]:
        assert "baghair booking nahi ho sakti" in r["reply"]
        assert r["state"]["awaiting"] == "PATIENT_NAME"
        assert "PATIENT_NAME" not in r["state"]["slots"]
    assert "rehne do" not in rs[2]["reply"]          # first try: just the reason
    assert "rehne do" in rs[3]["reply"] and "call" in rs[3]["reply"]   # then a way out


def test_confused_question_explains_step_not_out_of_scope(dm):
    for q in ["kea ho gea ha", "kya hua", "samjha nahi", "ye kea kr raha ha"]:
        dm.reset("c")
        r = talk(dm, TO_NAME + [q], sid="c")[-1]
        assert "Main aap ki appointment book kar raha hoon" in r["reply"], q
        assert "Dawai ya tashkhees" not in r["reply"], q
        assert "naam" in r["reply"] and r["state"]["awaiting"] == "PATIENT_NAME", q


def test_same_reply_never_three_times_in_a_row(dm):
    rs = talk(dm, TO_NAME + ["nahi pata"] * 6)
    replies = [r["reply"] for r in rs]
    for a, b, c in zip(replies, replies[1:], replies[2:]):
        assert not (a == b == c), a


def test_stop_words_drop_the_booking(dm):
    r = talk(dm, TO_NAME + ["nahi pata", "rehne do"])[-1]
    assert "koi booking nahi ki gayi" in r["reply"]
    assert r["state"]["task"] is None


def test_name_after_dont_know_still_books(dm):
    rs = talk(dm, TO_NAME + ["nahi pata", "Ali Raza", "03001234567", "haan"])
    assert rs[3]["state"]["slots"].get("PATIENT_NAME") == "Ali Raza"
    assert refs_in(rs[-1]["reply"])
    assert_no_invented_refs(dm, rs)


def test_dont_know_phone_explains(dm):
    r = talk(dm, TO_NAME + ["Ali Raza", "pata nahi"])[-1]
    assert "Mobile number ke baghair booking nahi ho sakti" in r["reply"]
    assert r["state"]["awaiting"] == "PHONE"


def test_dont_know_time_and_department_use_defaults(dm):
    r = talk(dm, ["kal appointment chahiye", "pata nahi"])[-1]
    assert r["state"]["department"] == "general_physician"
    dm.reset("t2")
    r = talk(dm, ["kal dil ke doctor ka appointment chahiye", "pata nahi"], sid="t2")[-1]
    assert r["state"]["awaiting"] != "TIME"
