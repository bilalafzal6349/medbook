"""Everything the bot says, in Roman Urdu ("roman") and Urdu script ("urdu").

The reply language follows the user's last message: mostly Urdu script -> Urdu, otherwise
Roman Urdu (which already mixes in English words, as patients do).
Clinic facts (address, phone, timings) are demo values; change them in CLINIC_FACTS.
"""
import re

ARABIC_RE = re.compile(r"[؀-ۿ]")
LATIN_RE = re.compile(r"[A-Za-z]")


def detect_lang(text, previous="roman"):
    a, l = len(ARABIC_RE.findall(text)), len(LATIN_RE.findall(text))
    if a == 0 and l == 0:
        return previous          # "03001234567", "MB-1042": keep the language we were using
    return "urdu" if a > l else "roman"


WEEKDAY_NAMES = {
    "roman": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "urdu": ["پیر", "منگل", "بدھ", "جمعرات", "جمعہ", "ہفتہ", "اتوار"],
}
MONTH_NAMES = {
    "roman": ["", "January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December"],
    "urdu": ["", "جنوری", "فروری", "مارچ", "اپریل", "مئی", "جون", "جولائی", "اگست", "ستمبر", "اکتوبر",
             "نومبر", "دسمبر"],
}


def fmt_date(d, lang):
    return f"{WEEKDAY_NAMES[lang][d.weekday()]}، {d.day} {MONTH_NAMES[lang][d.month]}" if lang == "urdu" \
        else f"{WEEKDAY_NAMES[lang][d.weekday()]}, {d.day} {MONTH_NAMES[lang][d.month]}"


def fmt_time(m, lang):
    h, mn = divmod(m, 60)
    if lang == "urdu":
        part = "صبح" if h < 12 else "دوپہر" if h < 16 else "شام" if h < 19 else "رات"
        return f"{part} {h % 12 or 12}:{mn:02d}"
    return f"{h % 12 or 12}:{mn:02d} {'AM' if h < 12 else 'PM'}"


def fmt_days(weekdays, lang):
    names = [WEEKDAY_NAMES[lang][d] for d in sorted(set(weekdays))]
    return ("، " if lang == "urdu" else ", ").join(names)


CLINIC_FACTS = {
    "name": "MedBook Clinic",
    "address": {"roman": "MedBook Clinic, 12-B Main Boulevard, Gulberg III, Lahore (demo address)",
                "urdu": "میڈبک کلینک، 12-بی مین بلیوارڈ، گلبرگ تھری، لاہور (ڈیمو پتہ)"},
    "phone": "042-111-633-266 (demo)",
}

R = {
    "greet": {
        "roman": "Walaikum salam! Main MedBook hoon. Appointment book, cancel ya change karni ho to bata dein, "
                 "ya apni takleef likh dein, main sahi doctor bata doon ga.",
        "urdu": "وعلیکم السلام! میں میڈبک ہوں۔ اپائنٹمنٹ بک، منسوخ یا تبدیل کرنی ہو تو بتا دیں، "
                "یا اپنی تکلیف لکھ دیں، میں صحیح ڈاکٹر بتا دوں گا۔"},
    "bye": {"roman": "Allah hafiz, sehat ka khayal rakhein.", "urdu": "اللہ حافظ، صحت کا خیال رکھیں۔"},
    "emergency": {
        "roman": "Ye emergency lag rahi hai. Foran 1122 par call karein ya qareebi hospital ki emergency mein "
                 "jayen. Is chat se appointment ka intezar na karein.",
        "urdu": "یہ ایمرجنسی لگ رہی ہے۔ فوراً 1122 پر کال کریں یا قریبی ہسپتال کی ایمرجنسی میں جائیں۔ "
                "اس چیٹ سے اپائنٹمنٹ کا انتظار نہ کریں۔"},
    "emergency_soft": {"roman": "Agar haalat itni sangeen nahi hai, to {dept} ka appointment bhi le sakte hain.",
                       "urdu": "اگر حالت اتنی سنگین نہیں ہے تو {dept} کی اپائنٹمنٹ بھی لے سکتے ہیں۔"},
    "out_of_scope": {
        "roman": "Maaf kijiye, main sirf appointments aur clinic ki maloomat mein madad kar sakta hoon. "
                 "Dawai ya tashkhees ke liye doctor se mashwara karein.",
        "urdu": "معذرت، میں صرف اپائنٹمنٹ اور کلینک کی معلومات میں مدد کر سکتا ہوں۔ "
                "دوائی یا تشخیص کے لیے ڈاکٹر سے مشورہ کریں۔"},
    "not_understood": {
        "roman": "Maaf kijiye, samajh nahi aaya. Aap appointment book, cancel, reschedule ya check kar sakte hain.",
        "urdu": "معذرت، سمجھ نہیں آیا۔ آپ اپائنٹمنٹ بک، منسوخ، تبدیل یا چیک کر سکتے ہیں۔"},
    # ---- questions
    "ask_DEPARTMENT": {"roman": "Kis doctor ya department ko dikhana hai? Ya apni takleef bata dein.",
                       "urdu": "کس ڈاکٹر یا شعبے کو دکھانا ہے؟ یا اپنی تکلیف بتا دیں۔"},
    "ask_DATE": {"roman": "Kis din aana chahenge?", "urdu": "کس دن آنا چاہیں گے؟"},
    "ask_TIME": {"roman": "Kis waqt aana pasand karenge? (subah, dopahar, shaam ya koi khaas time)",
                 "urdu": "کس وقت آنا پسند کریں گے؟ (صبح، دوپہر، شام یا کوئی خاص وقت)"},
    "ask_PATIENT_NAME": {"roman": "Patient ka naam bata dein.", "urdu": "مریض کا نام بتا دیں۔"},
    "ask_PHONE": {"roman": "Apna mobile number bata dein (03xx-xxxxxxx).",
                  "urdu": "اپنا موبائل نمبر بتا دیں (03xx-xxxxxxx)۔"},
    "ask_APPOINTMENT_ID": {"roman": "Apna booking number bata dein (MB-xxxx). Yaad nahi to booking wala mobile number bata dein.",
                           "urdu": "اپنا بکنگ نمبر بتا دیں (MB-xxxx)۔ یاد نہیں تو بکنگ والا موبائل نمبر بتا دیں۔"},
    "ask_task": {"roman": "Is booking ke saath kya karna hai: check, cancel ya reschedule?",
                 "urdu": "اس بکنگ کے ساتھ کیا کرنا ہے: چیک، منسوخ یا تبدیل؟"},
    "ask_change": {"roman": "Theek hai, abhi kuch save nahi kiya. Kya badalna hai: din, waqt ya doctor?",
                   "urdu": "ٹھیک ہے، ابھی کچھ محفوظ نہیں کیا۔ کیا تبدیل کرنا ہے: دن، وقت یا ڈاکٹر؟"},
    # ---- patient cannot answer / is confused
    "need_PATIENT_NAME": {
        "roman": "Patient ke naam ke baghair booking nahi ho sakti, kyunke booking aur doctor ki list mein naam likha jata hai. "
                 "Jis ka appointment hai us ka naam likh dein (sirf pehla naam bhi chalega, jaise: Ali).",
        "urdu": "مریض کے نام کے بغیر بکنگ نہیں ہو سکتی، کیونکہ بکنگ اور ڈاکٹر کی فہرست میں نام لکھا جاتا ہے۔ "
                "جس کی اپائنٹمنٹ ہے اس کا نام لکھ دیں (صرف پہلا نام بھی چلے گا، جیسے: علی)۔"},
    "need_PHONE": {
        "roman": "Mobile number ke baghair booking nahi ho sakti, isi number par booking ki tasdeeq aur reminder aata hai. "
                 "Koi bhi chalta hua number likh dein (03xx-xxxxxxx).",
        "urdu": "موبائل نمبر کے بغیر بکنگ نہیں ہو سکتی، اسی نمبر پر بکنگ کی تصدیق اور یاد دہانی آتی ہے۔ "
                "کوئی بھی چالو نمبر لکھ دیں (03xx-xxxxxxx)۔"},
    "need_APPOINTMENT_ID": {
        "roman": "Koi baat nahi. Booking number yaad nahi to wo mobile number likh dein jis se booking ki thi, main dhoond loon ga.",
        "urdu": "کوئی بات نہیں۔ بکنگ نمبر یاد نہیں تو وہ موبائل نمبر لکھ دیں جس سے بکنگ کی تھی، میں ڈھونڈ لوں گا۔"},
    "dontknow_DATE": {"roman": "Koi baat nahi, main sab se qareeb khali din dekh leta hoon.",
                      "urdu": "کوئی بات نہیں، میں سب سے قریب خالی دن دیکھ لیتا ہوں۔"},
    "dontknow_TIME": {"roman": "Koi baat nahi, main koi bhi khali waqt dekh leta hoon.",
                      "urdu": "کوئی بات نہیں، میں کوئی بھی خالی وقت دیکھ لیتا ہوں۔"},
    "dontknow_DEPARTMENT": {"roman": "Koi baat nahi, pehle General Physician ko dikha dein, wo zaroorat ho to specialist ko refer kar denge.",
                            "urdu": "کوئی بات نہیں، پہلے جنرل فزیشن کو دکھا دیں، وہ ضرورت ہو تو اسپیشلسٹ کو ریفر کر دیں گے۔"},
    "way_out": {"roman": "Agar abhi ye nahi bata sakte to \"rehne do\" likh dein, booking rok doon ga aur aap baad mein dobara kar sakte hain. "
                         "Ya clinic ke staff se baat karne ke liye {phone} par call karein.",
                "urdu": "اگر ابھی یہ نہیں بتا سکتے تو \"رہنے دیں\" لکھ دیں، میں بکنگ روک دوں گا اور آپ بعد میں دوبارہ کر سکتے ہیں۔ "
                        "یا کلینک کے عملے سے بات کرنے کے لیے {phone} پر کال کریں۔"},
    "explain_task_book": {"roman": "Main aap ki appointment book kar raha hoon.", "urdu": "میں آپ کی اپائنٹمنٹ بک کر رہا ہوں۔"},
    "explain_task_cancel": {"roman": "Main aap ki booking cancel karne mein madad kar raha hoon.",
                            "urdu": "میں آپ کی بکنگ منسوخ کرنے میں مدد کر رہا ہوں۔"},
    "explain_task_reschedule": {"roman": "Main aap ki booking ka din/waqt badalne mein madad kar raha hoon.",
                                "urdu": "میں آپ کی بکنگ کا دن/وقت بدلنے میں مدد کر رہا ہوں۔"},
    "explain_task_check": {"roman": "Main aap ki booking check kar raha hoon.", "urdu": "میں آپ کی بکنگ چیک کر رہا ہوں۔"},
    "explain_have": {"roman": "Ab tak: {items}.", "urdu": "اب تک: {items}۔"},
    "explain_PATIENT_NAME": {
        "roman": "Ab sirf patient ka naam chahiye, kyunke naam ke baghair booking nahi ho sakti. Jaise: Ali, ya Fatima Khan.",
        "urdu": "اب صرف مریض کا نام چاہیے، کیونکہ نام کے بغیر بکنگ نہیں ہو سکتی۔ جیسے: علی، یا فاطمہ خان۔"},
    "explain_PHONE": {
        "roman": "Ab mobile number chahiye, isi par booking ki tasdeeq aur reminder aata hai. Jaise: 0300-1234567.",
        "urdu": "اب موبائل نمبر چاہیے، اسی پر بکنگ کی تصدیق اور یاد دہانی آتی ہے۔ جیسے: 0300-1234567۔"},
    "explain_DATE": {"roman": "Ab ye batayen ke kis din aana hai. Jaise: kal, parson, Monday. Pata na ho to \"koi bhi\" likh dein.",
                     "urdu": "اب یہ بتائیں کہ کس دن آنا ہے۔ جیسے: کل، پرسوں، پیر۔ معلوم نہ ہو تو \"کوئی بھی\" لکھ دیں۔"},
    "explain_TIME": {"roman": "Ab ye batayen ke kis waqt aana hai. Jaise: subah, shaam, 5 baje. Pata na ho to \"koi bhi\" likh dein.",
                     "urdu": "اب یہ بتائیں کہ کس وقت آنا ہے۔ جیسے: صبح، شام، پانچ بجے۔ معلوم نہ ہو تو \"کوئی بھی\" لکھ دیں۔"},
    "explain_DEPARTMENT": {"roman": "Ab ye batayen ke kis doctor ko dikhana hai, ya apni takleef likh dein (jaise: sar dard, bukhar). "
                                    "Pata na ho to main General Physician ke paas bhej doon ga.",
                           "urdu": "اب یہ بتائیں کہ کس ڈاکٹر کو دکھانا ہے، یا اپنی تکلیف لکھ دیں (جیسے: سر درد، بخار)۔ "
                                   "معلوم نہ ہو تو میں جنرل فزیشن کے پاس بھیج دوں گا۔"},
    "explain_APPOINTMENT_ID": {"roman": "Ab booking number chahiye (MB-xxxx). Yaad nahi to booking wala mobile number likh dein.",
                               "urdu": "اب بکنگ نمبر چاہیے (MB-xxxx)۔ یاد نہیں تو بکنگ والا موبائل نمبر لکھ دیں۔"},
    "explain_confirm": {"roman": "Upar likhi booking save karne se pehle aap ki haan chahiye. \"Haan\" likhein to book kar doon, "
                                 "\"nahi\" likhein to kuch badal sakte hain.",
                        "urdu": "اوپر لکھی بکنگ محفوظ کرنے سے پہلے آپ کی ہاں چاہیے۔ \"ہاں\" لکھیں تو بک کر دوں، "
                                "\"نہیں\" لکھیں تو کچھ بدل سکتے ہیں۔"},
    "explain_slot_choice": {"roman": "Upar khali slots ki list hai. Jo theek lage us ka number likh dein (1, 2, 3), ya koi aur din bata dein.",
                            "urdu": "اوپر خالی اوقات کی فہرست ہے۔ جو ٹھیک لگے اس کا نمبر لکھ دیں (1، 2، 3)، یا کوئی اور دن بتا دیں۔"},
    # ---- bad values
    "bad_DATE": {"roman": "Ye din samajh nahi aaya ({value}). Jaise: kal, parson, Monday, 25 tareekh.",
                 "urdu": "یہ دن سمجھ نہیں آیا ({value})۔ جیسے: کل، پرسوں، پیر، پچیس تاریخ۔"},
    "past_DATE": {"roman": "Ye din guzar chuka hai. Aaj ya aage ka koi din bata dein.",
                  "urdu": "یہ دن گزر چکا ہے۔ آج یا آگے کا کوئی دن بتا دیں۔"},
    "bad_TIME": {"roman": "Ye waqt samajh nahi aaya ({value}). Jaise: subah 10 baje, shaam ko, 4 baje ke baad.",
                 "urdu": "یہ وقت سمجھ نہیں آیا ({value})۔ جیسے: صبح دس بجے، شام کو، چار بجے کے بعد۔"},
    "bad_PHONE": {"roman": "Ye number theek nahi lag raha ({value}). 11 hindson wala mobile number likhein, jaise 0300-1234567.",
                  "urdu": "یہ نمبر درست نہیں لگ رہا ({value})۔ گیارہ ہندسوں والا موبائل نمبر لکھیں، جیسے 0300-1234567۔"},
    "ref_not_found": {"roman": "Booking number {ref} hamare record mein nahi mila. Dobara check kar ke bata dein.",
                      "urdu": "بکنگ نمبر {ref} ہمارے ریکارڈ میں نہیں ملا۔ دوبارہ چیک کر کے بتا دیں۔"},
    "phone_not_found": {"roman": "Is number ({phone}) par koi aane wali booking nahi mili. Booking number bata dein.",
                        "urdu": "اس نمبر ({phone}) پر کوئی آنے والی بکنگ نہیں ملی۔ بکنگ نمبر بتا دیں۔"},
    "phone_many": {"roman": "Is number par ye bookings hain: {items}. Kaunsi wali?",
                   "urdu": "اس نمبر پر یہ بکنگز ہیں: {items}۔ کون سی والی؟"},
    "already_cancelled": {"roman": "Booking {ref} pehle hi cancel ho chuki hai.",
                          "urdu": "بکنگ {ref} پہلے ہی منسوخ ہو چکی ہے۔"},
    "past_appointment": {"roman": "Booking {ref} ki tareekh ({when}) guzar chuki hai, ise badla nahi ja sakta.",
                         "urdu": "بکنگ {ref} کی تاریخ ({when}) گزر چکی ہے، اسے تبدیل نہیں کیا جا سکتا۔"},
    # ---- routing and slots
    "route": {"roman": "Aapki takleef ke hisaab se {dept} behtar rahega.",
              "urdu": "آپ کی تکلیف کے حساب سے {dept} بہتر رہے گا۔"},
    "route_unsure": {"roman": "Takleef se department pakka nahi pata chala, is liye pehle General Physician ko dikha dein, "
                              "wo zaroorat ho to specialist ko refer kar denge.",
                     "urdu": "تکلیف سے شعبہ پکا معلوم نہیں ہوا، اس لیے پہلے جنرل فزیشن کو دکھا دیں، "
                             "وہ ضرورت ہو تو اسپیشلسٹ کو ریفر کر دیں گے۔"},
    "doctor_off": {"roman": "{doctor} {day} ko nahi baithte. Unke din: {days}.",
                   "urdu": "{doctor} {day} کو نہیں بیٹھتے۔ ان کے دن: {days}۔"},
    "closed_day": {"roman": "{day} ko clinic band hota hai (Itwaar ki chutti).",
                   "urdu": "{day} کو کلینک بند ہوتا ہے (اتوار کی چھٹی)۔"},
    "dept_off": {"roman": "{day} ko {dept} ke doctor nahi baithte. Din: {days}.",
                 "urdu": "{day} کو {dept} کے ڈاکٹر نہیں بیٹھتے۔ دن: {days}۔"},
    "exact_taken": {"roman": "{time} ka slot khali nahi hai.", "urdu": "{time} کا وقت خالی نہیں ہے۔"},
    "none_in_window": {"roman": "{day} ko is waqt koi slot khali nahi.", "urdu": "{day} کو اس وقت کوئی وقت خالی نہیں۔"},
    "none_on_day": {"roman": "{day} ko koi slot khali nahi.", "urdu": "{day} کو کوئی وقت خالی نہیں۔"},
    "none_at_all": {"roman": "Agle {n} din mein koi slot khali nahi mila. Koi aur department ya doctor try karein?",
                    "urdu": "اگلے {n} دن میں کوئی وقت خالی نہیں ملا۔ کوئی اور شعبہ یا ڈاکٹر دیکھیں؟"},
    "offer": {"roman": "Ye slots khali hain:\n{items}\nKaunsa theek hai? (number likh dein)",
              "urdu": "یہ اوقات خالی ہیں:\n{items}\nکون سا ٹھیک ہے؟ (نمبر لکھ دیں)"},
    "offer_one": {"roman": "{doctor} ke paas {day} {time} khali hai. Ye theek hai?",
                  "urdu": "{doctor} کے پاس {day} {time} خالی ہے۔ یہ ٹھیک ہے؟"},
    "slot_held": {"roman": "{doctor}, {day} {time} khali hai.", "urdu": "{doctor}، {day} {time} خالی ہے۔"},
    "pick_again": {"roman": "Inme se number chun lein (1, 2, 3), ya koi aur din/waqt bata dein.",
                   "urdu": "ان میں سے نمبر چن لیں (1، 2، 3)، یا کوئی اور دن/وقت بتا دیں۔"},
    # ---- confirmations
    "confirm_book": {"roman": "Confirm kar dein:\n{doctor} ({dept})\n{day}, {time}\nPatient: {name}, {phone}\nBook kar doon?",
                     "urdu": "تصدیق کر دیں:\n{doctor} ({dept})\n{day}، {time}\nمریض: {name}، {phone}\nکیا بک کر دوں؟"},
    "confirm_cancel": {"roman": "Booking {ref}: {doctor}, {day} {time} ({name}). Cancel kar doon?",
                       "urdu": "بکنگ {ref}: {doctor}، {day} {time} ({name})۔ کیا منسوخ کر دوں؟"},
    "confirm_reschedule": {"roman": "Booking {ref} ko {old} se badal kar {doctor}, {day} {time} kar doon?",
                           "urdu": "بکنگ {ref} کو {old} سے بدل کر {doctor}، {day} {time} کر دوں؟"},
    "yes_no": {"roman": "Ji haan ya nahi mein bata dein.", "urdu": "جی ہاں یا نہیں میں بتا دیں۔"},
    # ---- results
    "booked": {"roman": "Ho gaya! Aapka booking number {ref} hai.\n{doctor}, {day} {time}. 15 minute pehle aa jayen.",
               "urdu": "ہو گیا! آپ کا بکنگ نمبر {ref} ہے۔\n{doctor}، {day} {time}۔ پندرہ منٹ پہلے آ جائیں۔"},
    "cancelled": {"roman": "Booking {ref} cancel ho gayi hai.", "urdu": "بکنگ {ref} منسوخ ہو گئی ہے۔"},
    "rescheduled": {"roman": "Ho gaya! Booking {ref} ab {doctor}, {day} {time} par hai.",
                    "urdu": "ہو گیا! بکنگ {ref} اب {doctor}، {day} {time} پر ہے۔"},
    "status": {"roman": "Booking {ref}: {doctor} ({dept}), {day} {time}, patient {name}. Status: {status}.",
               "urdu": "بکنگ {ref}: {doctor} ({dept})، {day} {time}، مریض {name}۔ صورتحال: {status}۔"},
    "slot_gone": {"roman": "Maaf kijiye, ye slot abhi abhi kisi aur ne le liya.",
                  "urdu": "معذرت، یہ وقت ابھی ابھی کسی اور نے لے لیا۔"},
    "aborted": {"roman": "Theek hai, koi booking nahi ki gayi. Aur koi madad?",
                "urdu": "ٹھیک ہے، کوئی بکنگ نہیں کی گئی۔ اور کوئی مدد؟"},
    "anything_else": {"roman": "Aur koi madad chahiye?", "urdu": "اور کوئی مدد چاہیے؟"},
    # ---- availability
    "availability": {"roman": "{doctor} ({dept}) ke din: {days}, {hours}.",
                     "urdu": "{doctor} ({dept}) کے دن: {days}، {hours}۔"},
    "next_free": {"roman": "Agla khali slot: {day} {time}.", "urdu": "اگلا خالی وقت: {day} {time}۔"},
    "book_hint": {"roman": "Booking karni ho to din bata dein.", "urdu": "بکنگ کرنی ہو تو دن بتا دیں۔"},
}

STATUS = {"booked": {"roman": "confirmed", "urdu": "پکی"}, "cancelled": {"roman": "cancelled", "urdu": "منسوخ"}}

FAQ = [  # (keywords, roman answer, urdu answer); first match wins
    (r"fee|fees|charges|kitne paise|kitni raqam|فیس|پیسے",
     "Consultation fee: {fees}.", "مشورہ فیس: {fees}۔"),
    (r"timing|time kya|kitne baje|kab khul|kab band|open|khula|khulta|hours|کب کھل|کھلا|ٹائمنگ|timing|اوقات|چھٹی|chutti|holiday|band",
     "Clinic Monday se Saturday subah 10 se raat 9 baje tak khula hai. Itwaar (Sunday) chutti hoti hai.",
     "کلینک پیر سے ہفتہ صبح دس سے رات نو بجے تک کھلا ہے۔ اتوار کو چھٹی ہوتی ہے۔"),
    (r"address|kahan|location|pata|کہاں|پتہ|ایڈریس|address",
     "Address: {address}.", "پتہ: {address}۔"),
    (r"parking|پارکنگ",
     "Ji, clinic ke saath free parking hai.", "جی، کلینک کے ساتھ مفت پارکنگ موجود ہے۔"),
    (r"payment|card|jazzcash|easypaisa|online|ادائیگی|کارڈ|payment",
     "Cash, debit/credit card, JazzCash aur Easypaisa sab chalte hain.",
     "کیش، ڈیبٹ/کریڈٹ کارڈ، جاز کیش اور ایزی پیسہ سب چلتے ہیں۔"),
    (r"report|رپورٹ",
     "Aam lab reports 24 ghante mein mil jati hain, kuch tests mein 2 se 3 din lagte hain.",
     "عام لیب رپورٹیں چوبیس گھنٹے میں مل جاتی ہیں، کچھ ٹیسٹوں میں دو سے تین دن لگتے ہیں۔"),
    (r"lab|test|ٹیسٹ|لیب",
     "Ji, clinic mein lab hai, subah 8 se raat 8 baje tak sample diya ja sakta hai.",
     "جی، کلینک میں لیب ہے، صبح آٹھ سے رات آٹھ بجے تک سیمپل دیا جا سکتا ہے۔"),
    (r"number|phone|contact|نمبر|فون|رابطہ",
     "Clinic ka number: {phone}.", "کلینک کا نمبر: {phone}۔"),
]
FAQ_DEFAULT = ("Clinic Monday se Saturday subah 10 se raat 9 baje tak khula hai. Address: {address}. Number: {phone}.",
               "کلینک پیر سے ہفتہ صبح دس سے رات نو بجے تک کھلا ہے۔ پتہ: {address}۔ نمبر: {phone}۔")


def say(key, lang, **kw):
    return R[key][lang].format(**kw)
