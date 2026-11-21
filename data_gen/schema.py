"""MedBook NLU schema: intents, slot types, departments.

Single source of truth. The generator, the model heads and the dialogue manager
all import from here so labels never drift apart.
"""

INTENTS = {
    "greet": "Opening the chat (salam, hello, AoA).",
    "goodbye": "Ending the chat (Allah hafiz, shukriya bye).",
    "book_appointment": "Wants a new appointment. May carry any slot.",
    "reschedule_appointment": "Move an existing appointment to a new date/time.",
    "cancel_appointment": "Cancel an existing appointment.",
    "check_appointment": "Ask about the status/time of an existing appointment.",
    "doctor_availability": "Ask when a doctor or department is available.",
    "describe_symptom": "Describes a complaint without explicitly asking to book.",
    "inform": "Bare answer to a bot question (a name, a date, a phone number).",
    "confirm": "Yes / agree (ji haan, theek hai, kar dein).",
    "deny": "No / disagree / correction trigger (nahi, ye nahi).",
    "clinic_info": "Timings, fee, location, parking, etc.",
    "emergency": "Possible emergency. Bot must stop booking and point to Rescue 1122.",
    "out_of_scope": "Anything else (diagnosis, medicine dosage, chit-chat).",
}

# BIO tags are built from these: B-DATE, I-DATE, ... plus "O".
SLOTS = {
    "PATIENT_NAME": "Patient's name.",
    "AGE": "Patient's age, e.g. '5 saal', 'پانچ سال'.",
    "PHONE": "Pakistani mobile number.",
    "DATE": "Relative or absolute date: kal, parson, Monday, 25 tareekh, کل.",
    "TIME": "Time or part of day: subah 10 baje, 3:30 pm, شام.",
    "DOCTOR": "Doctor's name, with or without 'Dr.'.",
    "DEPARTMENT": "Department named explicitly (skin specialist, dil ka doctor).",
    "SYMPTOM": "Complaint phrase (seene mein dard, بخار).",
    "APPOINTMENT_ID": "Booking reference, e.g. MB-1042.",
}

DEPARTMENTS = [
    "general_physician",  # fallback when routing confidence is low
    "cardiology",
    "dermatology",
    "ent",
    "gastroenterology",
    "orthopedics",
    "gynecology",
    "pediatrics",
]
NO_DEPARTMENT = "none"  # rows that carry no routing signal

SCRIPTS = ["roman", "urdu", "mixed"]  # mixed = Urdu script + Latin-script English
SOURCES = ["template", "llm", "noise", "human"]


def bio_labels():
    labels = ["O"]
    for s in SLOTS:
        labels += [f"B-{s}", f"I-{s}"]
    return labels


INTENT2ID = {k: i for i, k in enumerate(INTENTS)}
TAG2ID = {t: i for i, t in enumerate(bio_labels())}
DEPT2ID = {d: i for i, d in enumerate(DEPARTMENTS + [NO_DEPARTMENT])}
