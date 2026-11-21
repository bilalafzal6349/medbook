from datetime import date

import pytest

from normalize import parse_date, parse_time

MON = date(2026, 11, 23)   # a Monday


@pytest.mark.parametrize("text,start,end", [
    ("kal", "2026-11-24", None), ("کل", "2026-11-24", None), ("tomorrow", "2026-11-24", None),
    ("parson", "2026-11-25", None), ("پرسوں", "2026-11-25", None), ("aaj", "2026-11-23", None),
    ("jumma", "2026-11-27", None), ("جمعہ", "2026-11-27", None), ("Friday", "2026-11-27", None),
    ("agle somwar", "2026-11-30", None), ("اگلے پیر", "2026-11-30", None), ("next Monday", "2026-11-30", None),
    ("hafta", "2026-11-28", None), ("ہفتہ", "2026-11-28", None),
    ("25 tareekh", "2026-11-25", None), ("پچیس تاریخ", "2026-11-25", None), ("1 tareekh", "2026-12-01", None),
    ("2 December", "2026-12-02", None), ("دو دسمبر", "2026-12-02", None), ("یکم دسمبر", "2026-12-01", None),
    ("28 Nov", "2026-11-28", None), ("5/12", "2026-12-05", None), ("1st December", "2026-12-01", None),
    ("do din baad", "2026-11-25", None), ("تین دن بعد", "2026-11-26", None),
    ("agle hafte", "2026-11-30", "2026-12-05"), ("اگلے ہفتے", "2026-11-30", "2026-12-05"),
    ("is hafte", "2026-11-23", "2026-11-28"), ("agle mahine", "2026-12-01", "2026-12-31"),
])
def test_dates(text, start, end):
    d = parse_date(text, MON)
    assert d is not None, text
    assert d.start.isoformat() == start
    assert d.end.isoformat() == (end or start)


def test_unknown_date():
    assert parse_date("jab marzi", MON) is None


def hm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


@pytest.mark.parametrize("text,start,end,exact", [
    ("subah 10 baje", "10:00", "10:01", True), ("صبح دس بجے", "10:00", "10:01", True),
    ("shaam 5 baje", "17:00", "17:01", True), ("شام پانچ بجے", "17:00", "17:01", True),
    ("dopahar 2 baje", "14:00", "14:01", True), ("saade 9 baje", "09:30", "09:31", True),
    ("ساڑھے نو بجے", "09:30", "09:31", True), ("paune 6 baje", "17:45", "17:46", True),
    ("dhai baje", "14:30", "14:31", True), ("3:30 pm", "15:30", "15:31", True), ("10 am", "10:00", "10:01", True),
    ("11 baje", "11:00", "11:01", True), ("5 pm", "17:00", "17:01", True),
    ("subah", "09:00", "12:00", False), ("shaam ko", "16:00", "20:00", False), ("evening", "16:00", "20:00", False),
    ("4 baje ke baad", "16:00", "21:00", False), ("after 4", "16:00", "21:00", False),
    ("چار بجے کے بعد", "16:00", "21:00", False), ("12 baje se pehle", "09:00", "12:00", False),
    ("before 12", "09:00", "12:00", False), ("shaam 6 se 7 ke beech", "18:00", "19:00", False),
    ("Zuhr ke baad", "13:30", "16:00", False), ("koi bhi", "09:00", "21:00", False),
])
def test_times(text, start, end, exact):
    t = parse_time(text)
    assert t is not None, text
    assert (hm(t.start), hm(t.end), t.exact) == (start, end, exact)


def test_first_last_slot():
    assert parse_time("first slot").pick == "first"
    assert parse_time("last slot").pick == "last"
