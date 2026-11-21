"""Load test: many patients chatting with MedBook at the same time.

Each simulated patient opens a new session and plays one whole conversation (booking in Roman Urdu or Urdu
script, a symptom question, doctor timings, fees, check / cancel by booking number), waiting 1 to 3 seconds
between messages like a person typing. Every chat turn is one POST /api/chat, reported by turn type.

At the end the test reads every appointment from the backend and fails the run if any doctor has two
"booked" appointments in the same slot (the proposal's zero-double-booking requirement, now under load).

    pip install locust
    locust -f locustfile.py --host http://localhost:8000 --headless -u 50 -r 10 -t 2m \
           --csv results/u50 --html results/u50.html
Environment: MEDBOOK_ADMIN_TOKEN (to read full appointments), LOADTEST_THINK="1,3" (seconds between messages).
"""
import os
import random
import uuid
from collections import Counter

from locust import HttpUser, between, events, task

THINK = tuple(float(x) for x in os.environ.get("LOADTEST_THINK", "1,3").split(","))
TOKEN = os.environ.get("MEDBOOK_ADMIN_TOKEN", "")
NAMES = ["Ali Raza", "Ayesha Khan", "Hamza", "Fatima Noor", "Bilal Ahmed", "Sana", "Usman", "Zainab", "Hira", "Omar"]
NAMES_UR = ["فاطمہ نور", "علی رضا", "عائشہ", "حمزہ", "زینب"]


def phone():
    return f"03{random.randint(0, 4)}{random.randint(0, 9)}{random.randint(1000000, 9999999)}"


def book_roman():
    dept = random.choice(["skin specialist", "ENT specialist", "dil ke doctor", "bachon ke doctor", "general physician",
                          "haddi ke doctor", "pait ke doctor", "lady doctor"])
    day = random.choice(["kal", "parson", "agle somwar", "jumay ko", "budh ko"])
    when = random.choice(["subah", "shaam ko", "subah 11 baje", "koi bhi time"])
    return [("greet", "salam"), ("book", f"mujhe {day} {dept} ko dikhana hai"), ("time", when),
            ("choose", random.choice(["1", "2", "pehla wala"])), ("name", random.choice(NAMES)),
            ("phone", phone()), ("confirm", "ji haan")]


def book_urdu():
    day = random.choice(["کل", "پرسوں"])
    return [("book", f"مجھے {day} دل کے ڈاکٹر سے ملنا ہے"), ("time", random.choice(["صبح", "صبح دس بجے", "شام کو"])),
            ("choose", "1"), ("name", f"میرا نام {random.choice(NAMES_UR)} ہے"), ("phone", phone()), ("confirm", "جی ہاں")]


def symptom():
    return [("symptom", random.choice(["mere bete ko 3 din se bukhar hai", "pait mein dard hai aur ulti ho rahi hai",
                                        "skin par kharish ho rahi hai", "kaan mein dard hai", "گھٹنوں میں درد رہتا ہے"])),
            ("time", "kal subah"), ("choose", "1")]


def info():
    return [("info", random.choice(["Dr Kamran kab baithte hain?", "کلینک کی fee کتنی ہے؟", "clinic kahan hai?",
                                    "ENT ki fee kitni hai", "Dr Ayesha aaj available hain?", "Sunday ko clinic khula hai?"]))]


def check_or_cancel():
    ref = random.choice(["MB-1042", "MB-2210", "MB-0087", "MB-3315", "MB-4521", "MB-7781", "MB-9999"])
    return random.choice([[("check", f"{ref} ka status batayein")],
                          [("cancel", f"{ref} cancel karni hai"), ("confirm", "nahi rehne do")],
                          [("check", "booking number yaad nahi, number 03459876543 hai, check karna hai")]])


def emergency():
    return [("emergency", random.choice(["abbu behosh ho gaye hain", "seene mein shadeed dard hai saans nahi aa raha"]))]


class Patient(HttpUser):
    wait_time = between(*THINK)

    def converse(self, turns, flow):
        sid = uuid.uuid4().hex
        for kind, text in turns:
            with self.client.post("/api/chat", json={"session_id": sid, "text": text}, name=f"chat:{kind}",
                                  catch_response=True) as r:
                if r.status_code != 200:
                    r.failure(f"HTTP {r.status_code}")
                    return
                body = r.json()
                if not body.get("reply"):
                    r.failure("empty reply")
                    return
                if flow == "emergency" and "1122" not in body["reply"]:
                    r.failure("emergency not detected")
            self.wait()
        self.client.post("/api/reset", json={"session_id": sid}, name="reset")

    @task(5)
    def booking(self):
        self.converse(book_roman() if random.random() < 0.6 else book_urdu(), "book")

    @task(2)
    def symptom(self):
        self.converse(symptom(), "symptom")

    @task(2)
    def info(self):
        self.converse(info(), "info")

    @task(2)
    def check_or_cancel(self):
        self.converse(check_or_cancel(), "check")

    @task(1)
    def emergency(self):
        self.converse(emergency(), "emergency")

    @task(1)
    def health(self):
        self.client.get("/api/health", name="health")


@events.test_stop.add_listener
def no_double_booking(environment, **_):
    import requests
    host = environment.host or "http://localhost:8000"
    rows = requests.get(f"{host}/api/appointments", headers={"X-Admin-Token": TOKEN}, timeout=30).json()
    booked = Counter((a["doctor"], a["day"], a["time"]) for a in rows if a["status"] == "booked")
    doubles = {k: n for k, n in booked.items() if n > 1}
    made = sum(1 for a in rows if a["source"] == "chat" and a["status"] == "booked")
    print(f"\n[check] {len(rows)} appointments in the database, {made} booked through chat during the test, "
          f"{len(doubles)} double-booked slots")
    if doubles:
        print("[check] DOUBLE BOOKINGS:", doubles)
        environment.process_exit_code = 1
