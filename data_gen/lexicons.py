"""Slot value lexicons, by writing style.

roman = Roman Urdu (Latin script), urdu = Urdu script, en = English words that
people drop into either script (used by roman and mixed styles).
Symptom lists should be checked once by a doctor or receptionist.
"""

PATIENT_NAME = {
    "roman": ["Ali Raza", "Ayesha", "Muhammad Usman", "Fatima Noor", "Hamza", "Sana Khan", "Bilal Ahmed",
              "Zainab", "Imran Ali", "Hira", "Abdullah", "Maryam Iqbal", "Ahmed", "Usman Tariq", "Nimra",
              "Saad Javed", "Rabia", "Zeeshan Haider", "Kiran Shahzad", "Faisal", "Mehwish", "Asad Mehmood",
              "Iqra Saleem", "Hassan Raza", "Sadia", "Waqas", "Amna Riaz", "Junaid Akhtar", "Mahnoor",
              "Shahid Iqbal", "Noor Fatima", "Talha", "Areeba Khan", "Kashif Ali", "Uzma", "Danish",
              "Ghulam Rasool", "Shabana", "Nasreen Akhtar", "Arslan"],
    "urdu": ["علی رضا", "عائشہ", "محمد عثمان", "فاطمہ نور", "حمزہ", "ثنا خان", "بلال احمد", "زینب",
             "عمران علی", "حرا", "عبداللہ", "مریم اقبال", "احمد", "عثمان طارق", "نمرہ", "سعد جاوید", "رابعہ",
             "ذیشان حیدر", "کرن شہزاد", "فیصل", "مہوش", "اسد محمود", "اقرا سلیم", "حسن رضا", "سعدیہ",
             "وقاص", "آمنہ ریاض", "جنید اختر", "ماہ نور", "شاہد اقبال", "نور فاطمہ", "طلحہ", "غلام رسول",
             "شبانہ", "نسرین اختر", "ارسلان"],
}

# female patient names (used when the department is gynecology, so a male name is never booked there)
FEMALE_NAMES = {"Ayesha", "Fatima Noor", "Sana Khan", "Zainab", "Hira", "Maryam Iqbal", "Nimra", "Rabia",
                "Kiran Shahzad", "Mehwish", "Iqra Saleem", "Sadia", "Amna Riaz", "Mahnoor", "Noor Fatima",
                "Areeba Khan", "Uzma", "Shabana", "Nasreen Akhtar",
                "عائشہ", "فاطمہ نور", "ثنا خان", "زینب", "حرا", "مریم اقبال", "نمرہ", "رابعہ", "کرن شہزاد", "مہوش",
                "اقرا سلیم", "سعدیہ", "آمنہ ریاض", "ماہ نور", "نور فاطمہ", "شبانہ", "نسرین اختر"}

AGE = {
    "roman": ["5 saal", "8 saal", "2 saal", "45 saal", "60 saal", "30 saal", "6 mahine", "12 saal",
              "70 saal", "25 saal", "3 saal", "35 years", "50 years", "1 saal", "10 saal", "15 saal",
              "18 saal", "14 years"],
    "urdu": ["پانچ سال", "آٹھ سال", "دو سال", "45 سال", "60 سال", "تیس سال", "چھ مہینے", "بارہ سال",
             "70 سال", "پچیس سال", "تین سال", "ایک سال", "دس سال", "پندرہ سال", "اٹھارہ سال"],
}
# age value -> years, so a CHILD phrase plus a stated AGE can be routed by age (12 or under -> pediatrics),
# the same rule the backend router uses (routing.CHILD_MAX_AGE).
_URDU_NUM = {"پانچ": 5, "آٹھ": 8, "دو": 2, "تیس": 30, "چھ": 6, "بارہ": 12, "پچیس": 25, "تین": 3, "ایک": 1,
             "دس": 10, "پندرہ": 15, "اٹھارہ": 18}


def age_in_years(value: str) -> float:
    n, unit = value.split()[0], value.split()[-1]
    n = int(n) if n.isdigit() else _URDU_NUM[n]
    return n / 12 if unit in ("mahine", "مہینے") else n


CHILD_MAX_AGE = 12

PHONE = {
    "roman": ["0300-1234567", "03211234567", "0333 7654321", "0345-9876543", "03134567890", "0312-5556677",
              "03004445566", "0331 2223344", "0346-1112233", "03017778899", "+92 300 1234567", "0322-8889900"],
}
PHONE["urdu"] = PHONE["roman"]

DATE = {
    "roman": ["kal", "parson", "aaj", "agle hafte", "Monday", "jumma", "25 tareekh", "2 December",
              "somwar", "mangal", "budh", "jumeraat", "hafta", "itwaar", "agle somwar", "is jumme",
              "28 tareekh", "1 tareekh", "agle mahine", "do din baad", "teen din baad",
              "30 November", "5 December", "is hafte"],
    "urdu": ["کل", "پرسوں", "آج", "اگلے ہفتے", "پیر", "سوموار", "منگل", "بدھ", "جمعرات", "جمعہ", "ہفتہ",
             "اتوار", "پچیس تاریخ", "اس جمعے", "دو دسمبر", "اگلے پیر", "اٹھائیس تاریخ", "اگلے مہینے",
             "دو دن بعد", "تین دن بعد", "اسی ہفتے", "یکم دسمبر", "30 نومبر"],
    "en": ["tomorrow", "Monday", "next week", "Friday", "25th", "Tuesday", "Wednesday", "Thursday",
           "Saturday", "Sunday", "next Monday", "day after tomorrow", "28 Nov", "5/12", "this Friday",
           "today", "1st December"],
}

TIME = {
    "roman": ["subah 10 baje", "shaam 5 baje", "dopahar 2 baje", "raat 8 baje", "subah", "shaam ko",
              "4 baje ke baad", "11 baje", "saade 9 baje", "dopahar ko", "subah sawere", "dhai baje",
              "paune 6 baje", "3 baje", "shaam 6 se 7 ke beech", "12 baje se pehle", "Zuhr ke baad"],
    "urdu": ["صبح دس بجے", "شام پانچ بجے", "دوپہر دو بجے", "رات آٹھ بجے", "صبح", "شام کو", "چار بجے کے بعد",
             "گیارہ بجے", "ساڑھے نو بجے", "دوپہر کو", "صبح سویرے", "ڈھائی بجے", "پونے چھ بجے", "تین بجے",
             "بارہ بجے سے پہلے", "ظہر کے بعد"],
    "en": ["10 am", "5 pm", "3:30 pm", "morning", "evening", "11:00", "9:30 am", "afternoon",
           "after 4", "before 12", "6 pm", "first slot", "last slot"],
}

# doctor name -> department, so a DOCTOR mention also gives a routing label
DOCTORS = [
    ({"roman": "Dr. Ahmed Raza", "urdu": "ڈاکٹر احمد رضا"}, "cardiology"),
    ({"roman": "Dr. Shazia Kanwal", "urdu": "ڈاکٹر شازیہ کنول"}, "cardiology"),
    ({"roman": "Dr. Saima Malik", "urdu": "ڈاکٹر صائمہ ملک"}, "gynecology"),
    ({"roman": "Dr. Farah Naz", "urdu": "ڈاکٹر فرح ناز"}, "gynecology"),
    ({"roman": "Dr. Kamran Shah", "urdu": "ڈاکٹر کامران شاہ"}, "orthopedics"),
    ({"roman": "Dr. Adeel Qureshi", "urdu": "ڈاکٹر عدیل قریشی"}, "orthopedics"),
    ({"roman": "Dr. Nadia Hussain", "urdu": "ڈاکٹر نادیہ حسین"}, "dermatology"),
    ({"roman": "Dr. Sobia Anwar", "urdu": "ڈاکٹر صوبیہ انور"}, "dermatology"),
    ({"roman": "Dr. Tariq Mehmood", "urdu": "ڈاکٹر طارق محمود"}, "ent"),
    ({"roman": "Dr. Waseem Akram", "urdu": "ڈاکٹر وسیم اکرم"}, "ent"),
    ({"roman": "Dr. Farhan Butt", "urdu": "ڈاکٹر فرحان بٹ"}, "gastroenterology"),
    ({"roman": "Dr. Naveed Iqbal", "urdu": "ڈاکٹر نوید اقبال"}, "gastroenterology"),
    ({"roman": "Dr. Rabia Aslam", "urdu": "ڈاکٹر رابعہ اسلم"}, "pediatrics"),
    ({"roman": "Dr. Hina Jamil", "urdu": "ڈاکٹر حنا جمیل"}, "pediatrics"),
    ({"roman": "Dr. Usman Ghani", "urdu": "ڈاکٹر عثمان غنی"}, "general_physician"),
    ({"roman": "Dr. Sajid Hameed", "urdu": "ڈاکٹر ساجد حمید"}, "general_physician"),
]
# short forms people type ("Dr Ahmed", "Kamran Shah sahab")
DOCTOR_SHORT_ROMAN = {
    "Dr. Ahmed Raza": ["Dr Ahmed", "doctor Ahmed Raza"], "Dr. Saima Malik": ["Dr Saima", "doctor Saima"],
    "Dr. Kamran Shah": ["Dr Kamran", "Kamran Shah sahab"], "Dr. Nadia Hussain": ["Dr Nadia"],
    "Dr. Tariq Mehmood": ["Dr Tariq"], "Dr. Farhan Butt": ["Dr Farhan", "Farhan Butt sahab"],
    "Dr. Rabia Aslam": ["Dr Rabia"], "Dr. Usman Ghani": ["Dr Usman", "Usman Ghani sahab"],
}

# explicit department mentions
DEPARTMENT_NAMES = {
    "general_physician": {"roman": ["general physician", "GP", "aam doctor", "family doctor", "medical specialist",
                                    "medicine wale doctor"],
                          "urdu": ["جنرل فزیشن", "عام ڈاکٹر", "فیملی ڈاکٹر", "میڈیسن والے ڈاکٹر"]},
    "cardiology": {"roman": ["dil ka doctor", "cardiologist", "heart specialist", "cardiology", "dil ke mahir"],
                   "urdu": ["دل کے ڈاکٹر", "امراض قلب", "دل کے ماہر", "کارڈیالوجسٹ"]},
    "dermatology": {"roman": ["skin specialist", "jild ka doctor", "dermatologist", "skin doctor", "skin wale doctor"],
                    "urdu": ["جلد کے ڈاکٹر", "سکن سپیشلسٹ", "جلد کے ماہر", "سکن ڈاکٹر"]},
    "ent": {"roman": ["ENT specialist", "kaan naak gala ka doctor", "ENT", "ENT wale doctor", "kaan ka doctor"],
            "urdu": ["ناک کان گلے کے ڈاکٹر", "ای این ٹی", "کان کے ڈاکٹر", "ناک کان گلے کے ماہر"]},
    "gastroenterology": {"roman": ["pait ka doctor", "gastro specialist", "gastroenterologist", "maiday ka doctor",
                                   "gastro"],
                         "urdu": ["معدے کے ڈاکٹر", "پیٹ کے ڈاکٹر", "معدے کے ماہر", "گیسٹرو"]},
    "orthopedics": {"roman": ["haddiyon ka doctor", "orthopedic", "ortho specialist", "bone specialist",
                              "haddi jor ka doctor"],
                    "urdu": ["ہڈیوں کے ڈاکٹر", "آرتھوپیڈک", "ہڈی جوڑ کے ماہر", "ہڈیوں کے ماہر"]},
    "gynecology": {"roman": ["lady doctor", "gynae", "gynecologist", "gynae specialist", "aurton ki doctor"],
                   "urdu": ["لیڈی ڈاکٹر", "گائنی", "خواتین کی ڈاکٹر", "گائناکالوجسٹ"]},
    "pediatrics": {"roman": ["bachon ka doctor", "child specialist", "pediatrician", "bachon ke specialist",
                             "child doctor"],
                   "urdu": ["بچوں کے ڈاکٹر", "چائلڈ سپیشلسٹ", "بچوں کے ماہر", "بچوں کی ڈاکٹر"]},
}

# symptom phrases -> department (adult patient)
SYMPTOMS = {
    "general_physician": {
        "roman": ["bukhar", "nazla zukam", "kamzori", "jism mein dard", "khansi", "fever", "flu", "thakawat",
                  "sar dard", "chakkar", "sugar barh gayi", "halka bukhar", "body pain", "typhoid",
                  "kamzori aur chakkar"],
        "urdu": ["بخار", "نزلہ زکام", "کمزوری", "جسم میں درد", "کھانسی", "تھکاوٹ", "سر درد", "چکر",
                 "شوگر بڑھ گئی", "ہلکا بخار", "ٹائیفائیڈ", "فلو"]},
    "cardiology": {
        "roman": ["seene mein dard", "dil ki dharkan tez", "BP high", "saans phoolna", "chest pain",
                  "dil ghabrata hai", "blood pressure kam", "seene pe bojh", "palpitations",
                  "seedhi chadhne pe saans phoolti", "baayein baazu mein dard"],
        "urdu": ["سینے میں درد", "دل کی دھڑکن تیز", "بلڈ پریشر زیادہ", "سانس پھولنا", "دل گھبراتا ہے",
                 "بلڈ پریشر کم", "سینے پر بوجھ", "بائیں بازو میں درد"]},
    "dermatology": {
        "roman": ["skin pe daane", "kharish", "pimples", "baal girna", "skin allergy", "chehre pe daag",
                  "jild pe dhabbe", "eczema", "dandruff", "nakhun ka infection", "skin rash", "jild khushk"],
        "urdu": ["جلد پر دانے", "خارش", "کیل مہاسے", "بال گرنا", "چہرے پر داغ", "جلد پر دھبے", "خشکی",
                 "ناخن کا انفیکشن", "جلد کی الرجی", "جلد خشک"]},
    "ent": {
        "roman": ["kaan mein dard", "gala kharab", "naak band", "kam sunai dena", "throat infection",
                  "kaan behna", "tonsils", "naksir", "awaaz baith gayi", "sinus", "kaan mein seeti",
                  "nigalne mein takleef"],
        "urdu": ["کان میں درد", "گلا خراب", "ناک بند", "کم سنائی دینا", "کان بہنا", "ٹانسلز", "نکسیر",
                 "آواز بیٹھ گئی", "سائنس", "نگلنے میں تکلیف"]},
    "gastroenterology": {
        "roman": ["pait mein dard", "ulti", "dast", "acidity", "qabz", "maiday mein jalan", "gas",
                  "bhook nahi lagti", "khatti dakaarein", "pait phoolna", "ulcer", "jigar ka masla", "piliya"],
        "urdu": ["پیٹ میں درد", "الٹی", "دست", "تیزابیت", "قبض", "معدے میں جلن", "گیس", "بھوک نہیں لگتی",
                 "کھٹی ڈکاریں", "پیٹ پھولنا", "یرقان", "جگر کا مسئلہ"]},
    "orthopedics": {
        "roman": ["ghutne mein dard", "kamar dard", "haddi toot gayi", "joron mein dard", "back pain",
                  "gardan mein dard", "kandhe mein dard", "moch aa gayi", "sciatica", "eri mein dard",
                  "haath ki haddi mein dard", "knee pain"],
        "urdu": ["گھٹنے میں درد", "کمر درد", "ہڈی ٹوٹ گئی", "جوڑوں میں درد", "گردن میں درد",
                 "کندھے میں درد", "موچ آ گئی", "ایڑی میں درد", "پاؤں کی ہڈی میں درد"]},
    "gynecology": {
        "roman": ["periods irregular", "pregnancy checkup", "mahwari ka masla", "pregnancy test",
                  "periods mein zyada dard", "pregnancy ka ultrasound", "PCOS",
                  "delivery ki date", "periods band"],
        "urdu": ["ماہواری بے قاعدہ", "حمل کا چیک اپ", "ماہواری کا مسئلہ", "حمل کا ٹیسٹ",
                 "ماہواری میں زیادہ درد", "حمل کا الٹراساؤنڈ", "ڈیلیوری کی تاریخ"]},
}

# symptoms that make sense for a child (routes to pediatrics when CHILD is present)
CHILD_SYMPTOMS = {
    "roman": ["bukhar", "khansi", "nazla zukam", "dast", "ulti", "kaan mein dard", "gala kharab",
              "pait mein dard", "skin pe daane", "kharish", "fever", "tez bukhar", "saans mein khar khar"],
    "urdu": ["بخار", "کھانسی", "نزلہ زکام", "دست", "الٹی", "کان میں درد", "گلا خراب", "پیٹ میں درد",
             "جلد پر دانے", "خارش", "تیز بخار"],
}

CHILD = {  # family words that point to pediatrics when no age (or an age of 12 or under) is given
    "roman": ["mere bete", "meri beti", "mere bachay", "mere chote bhai", "meri baby", "mere bhanje",
              "meri bhatiji", "mere 3 saal ke bete", "meri choti behan", "hamare bachay"],
    "urdu": ["میرے بیٹے", "میری بیٹی", "میرے بچے", "میرے چھوٹے بھائی", "میری چھوٹی بہن", "میرے بھانجے",
             "ہمارے بچے", "میری بھتیجی"],
}
# CHILD phrases that can also describe an adult ("mere chote bhai, 25 saal"). Used when the stated age is over 12.
CHILD_CAN_BE_ADULT = {
    "roman": ["mere bete", "meri beti", "mere chote bhai", "mere bhanje", "meri bhatiji", "meri choti behan"],
    "urdu": ["میرے بیٹے", "میری بیٹی", "میرے چھوٹے بھائی", "میری چھوٹی بہن", "میرے بھانجے", "میری بھتیجی"],
}
# CHILD phrases that already carry an age; not used when the template has its own {AGE}.
CHILD_WITH_AGE = {"mere 3 saal ke bete"}

# adult department for each CHILD_SYMPTOM, used when the "child" is over 12
CHILD_SYMPTOM_ADULT_DEPT = {
    "bukhar": "general_physician", "khansi": "general_physician", "nazla zukam": "general_physician",
    "fever": "general_physician", "tez bukhar": "general_physician", "saans mein khar khar": "general_physician",
    "dast": "gastroenterology", "ulti": "gastroenterology", "pait mein dard": "gastroenterology",
    "kaan mein dard": "ent", "gala kharab": "ent", "skin pe daane": "dermatology", "kharish": "dermatology",
    "بخار": "general_physician", "کھانسی": "general_physician", "نزلہ زکام": "general_physician",
    "تیز بخار": "general_physician", "دست": "gastroenterology", "الٹی": "gastroenterology",
    "پیٹ میں درد": "gastroenterology", "کان میں درد": "ent", "گلا خراب": "ent", "جلد پر دانے": "dermatology",
    "خارش": "dermatology",
}

APPOINTMENT_ID = {"roman": ["MB-1042", "MB-2210", "MB-0087", "MB-3315", "MB-4521", "MB-0930", "MB-7781",
                            "MB-1206", "mb-5503", "MB 6610"]}
APPOINTMENT_ID["urdu"] = APPOINTMENT_ID["roman"]

# Phrases that MUST be caught by the emergency rules (also used for the recall test).
EMERGENCY = {
    "roman": ["seene mein shadeed dard hai aur saans nahi aa rahi", "abbu behosh ho gaye hain",
              "bohat khoon beh raha hai ruk nahi raha", "accident ho gaya hai sar pe chot lagi hai",
              "ammi ko lagta hai stroke hua hai munh terha ho gaya", "bachay ne zeher pi liya hai",
              "dada ji ko heart attack lag raha hai", "saans bilkul nahi aa rahi", "dora par raha hai",
              "bachay ka sar phat gaya hai khoon nahi ruk raha", "nana ji gir gaye aur hosh nahi aa raha",
              "seene mein bohat tez dard hai aur paseena aa raha hai", "ammi ne bohat saari goliyan kha li hain",
              "bachay ko current lag gaya hai", "bohat buri tarah jal gaya hai"],
    "urdu": ["سینے میں شدید درد ہے اور سانس نہیں آ رہی", "ابو بے ہوش ہو گئے ہیں", "بہت خون بہہ رہا ہے رک نہیں رہا",
             "ایکسیڈنٹ ہو گیا ہے سر پر چوٹ لگی ہے", "بچے نے زہر پی لیا ہے", "دادا جی کو دل کا دورہ پڑا ہے",
             "سانس بالکل نہیں آ رہی", "امی کو فالج کا حملہ لگ رہا ہے", "بچے کو کرنٹ لگ گیا ہے",
             "نانا جی گر گئے اور ہوش نہیں آ رہا", "دورہ پڑ رہا ہے"],
}
