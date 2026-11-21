"""Voice text handling: transcript cleanup (what Whisper writes -> what the NLU rules expect) and
reply text for the Urdu TTS. No models are loaded here."""
import voice
from nlu import REF_RE, rule_slots


def test_spoken_digits_become_phone():
    t = voice.clean_transcript("میرا نمبر صفر تین صفر صفر ایک دو تین چار پانچ چھ سات ہے۔")
    assert t == "میرا نمبر 03001234567 ہے"
    assert {"label": "PHONE", "value": "03001234567"} in rule_slots(t)


def test_booking_number_spoken_as_letters_and_digits():
    for said in ("ایم بی 1042 کینسل کرنی ہے", "ایم بی ایک صفر چار دو کینسل کرنی ہے", "MB 1042 کینسل کرنی ہے"):
        t = voice.clean_transcript(said)
        assert REF_RE.search(t).group(0) == "MB-1042", said


def test_phone_in_groups_and_urdu_digits():
    assert voice.clean_transcript("0300 123 4567") == "03001234567"
    assert voice.clean_transcript("میرا نمبر ۰۳۲۱۱۲۳۴۵۶۷") == "میرا نمبر 03211234567"


def test_small_numbers_are_left_alone():
    # "two days", "ten o'clock": fewer than four digit words is ordinary speech, not a number to join
    assert voice.clean_transcript("مجھے دو دن سے بخار ہے") == "مجھے دو دن سے بخار ہے"
    assert voice.clean_transcript("کل دس بجے") == "کل دس بجے"


def test_hallucination_filter():
    assert voice.is_hallucination("ویڈیو دیکھنے کا شکریہ")
    assert not voice.is_hallucination("مجھے کل ڈاکٹر سے ملنا ہے")


def test_number_words():
    assert voice.number_words(0) == "صفر"
    assert voice.number_words(23) == "تئیس"
    assert voice.number_words(99) == "ننانوے"
    assert voice.number_words(150) == "ایک سو پچاس"
    assert voice.number_words(2026) == "دو ہزار چھبیس"


def test_speakable_reply():
    s = voice.speakable("ہو گیا! آپ کا بکنگ نمبر MB-1042 ہے۔ پیر، 23 نومبر صبح 10:30۔")
    assert "ایم بی ایک صفر چار دو" in s
    assert "تئیس نومبر" in s and "دس بج کر تیس منٹ" in s
    assert not any(c.isdigit() for c in s) and "MB" not in s
    assert "ایک ایک دو دو" in voice.speakable("فوراً 1122 پر کال کریں")
    assert voice.speakable("اپنا موبائل نمبر بتا دیں (03xx-xxxxxxx)۔") == "اپنا موبائل نمبر بتا دیں ۔"
    assert voice.speakable("صبح 9:00") == "صبح نو بجے"


def test_only_urdu_script_is_spoken():
    assert voice.can_speak("آپ کی بکنگ ہو گئی ہے")
    assert not voice.can_speak("Aap ki booking ho gayi hai")


def test_misheard_doctor_names_snap_back():
    names = ["ڈاکٹر شازیہ کنول", "ڈاکٹر طارق محمود", "ڈاکٹر عدیل قریشی", "ڈاکٹر احمد رضا"]
    fix = lambda t: voice.snap_doctor_names(t, [n.replace("ڈاکٹر ", "") for n in names])  # noqa: E731
    assert "ڈاکٹر شازیہ کنول" in fix("کیا ڈاکٹر شازیق کمول، پچیس تاریخ")
    assert "ڈاکٹر طارق محمود" in fix("ڈاکٹر، ڈارک، محمود، کب سے کب تک")
    assert "ڈاکٹر عدیل قریشی" in fix("یا ڈاکٹر ڈیل، کریشی، جمعہ")
    # ordinary words after "doctor" are left alone
    for t in ("مجھے کل کسی ڈاکٹر سے ملنا ہے", "بچوں کے ڈاکٹر کا وقت", "ڈاکٹر کو دکھاؤں"):
        assert fix(t) == t
