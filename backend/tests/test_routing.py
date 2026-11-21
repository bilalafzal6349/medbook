"""Keyword router rules that the dataset labels (data_gen) must agree with."""
import pytest

from routing import keyword_department


@pytest.mark.parametrize("text, dept", [
    ("mere chote bhai ko bukhar hai", "pediatrics"),                       # child word, no age
    ("mere chote bhai ki umar 8 saal hai, usay khansi hai", "pediatrics"),  # age 12 or under
    ("mere chote bhai ki umar 45 saal hai, usay khansi hai", "general_physician"),  # adult sibling
    ("میرے بھانجے کی عمر 45 سال ہے، اسے پیٹ میں درد ہے", "gastroenterology"),
    ("meri beti ki umar 12 saal hai, kaan mein dard hai", "pediatrics"),
    ("meri beti ki umar 25 saal hai, kaan mein dard hai", "ent"),
])
def test_child_word_follows_age(text, dept):
    assert keyword_department(text)[0] == dept


@pytest.mark.parametrize("text", [
    "منگل کو ڈاکٹر عثمان غنی سے ملنا ہے",   # Tuesday contains نگل (swallow)
    "early morning slot chahiye",          # 'early' starts with 'ear'
    "دماغ کا ڈاکٹر",                       # دماغ contains داغ (spot)
])
def test_no_keyword_inside_other_words(text):
    assert keyword_department(text)[0] != "ent" and keyword_department(text)[0] != "dermatology"


def test_swallowing_still_ent():
    assert keyword_department("نگلنے میں تکلیف ہے")[0] == "ent"
