# Real-message test set: template, labelling guide, scoring

This folder holds everything needed to turn real messages (from classmates, family, or real clinic chats)
into a test set and score both models on it. It is **test only**: never train on these rows.

```
real_test/
  real_messages_template.csv   empty sheet, one row per message (UTF-8, opens in Excel / Google Sheets)
  LABELLING_GUIDE.md           this file
  score_real.py                scores baseline + XLM-R, model alone and model + backstop, by writing style
```

## 1. Collecting (short version)

Ask each person for 5 to 10 messages, "the way you would actually WhatsApp a clinic". Describe the
situation, not the words: say "you want to see a doctor for something you or your family really had",
not "you have a skin rash". Let them pick Roman Urdu, Urdu script, English or a mix. Cover a spread:
new booking (own complaint, a child, an elderly parent), a named doctor, cancel, move to another day,
check a booking, clinic timings / fee / location, one emergency, greetings and goodbyes, and one
off-topic question (e.g. medicine dose). Ask them to use **fake names and phone numbers**.

Paste each message, exactly as written (do not fix spelling, spacing or emoji), into the `text` column.

## 2. The sheet columns

| column | who fills it | what goes in it |
|---|---|---|
| `id` | you | anything unique: `r001`, `r002`, ... (left empty, the script numbers rows) |
| `participant` | you | `p01`, `p02`, ... (no real names). Used only to count people. |
| `scenario` | you, optional | short note of what you asked for (`book_child`, `cancel`, ...) |
| `text` | participant | the raw message, untouched |
| `labelled_text` | you | the same text with slots marked as `[value](SLOT)`. Leave empty if the message has no slots. |
| `intent` | you | one intent from the list below |
| `department` | you | one department, or `none` |
| `reported_style` | participant, optional | how they think they typed it: `roman`, `urdu`, `english`, `mixed` |
| `exclude` | you | `1` to keep a row in the sheet but out of the scores (spam, two requests in one, unreadable) |
| `notes` | you | anything, e.g. why a label was hard |

`labelled_text` must be **exactly** `text` plus the brackets. The script checks this and lists every row
where the two differ, so a typo while labelling cannot silently change the test message.

The writing style used in the score breakdown is detected from the text (same rule as the training data):
`urdu` = Urdu script only, `roman` = Latin letters only (Roman Urdu or English), `mixed` = both. If
participants filled `reported_style`, the script also gives a second breakdown by that column, which is the
only way to separate pure English from Roman Urdu.

## 3. Intents (from `data_gen/schema.py`)

Pick the intent of the **whole message**. When a message does two things, use the first rule that fits:
emergency > cancel / reschedule / check > book > doctor_availability > describe_symptom > clinic_info > the rest.

| intent | use when | example |
|---|---|---|
| `emergency` | any sign of danger: unconscious, can't breathe, heavy bleeding, chest pain that is severe or sudden, stroke signs, poisoning, seizure, accident, self-harm. **When in doubt, emergency.** | "ammi behosh ho gayi hain" |
| `book_appointment` | asks for a new appointment, even with no details | "kal ka time mil sakta hai?" |
| `reschedule_appointment` | move an existing booking | "MB-1042 wali appointment Monday kar dein" |
| `cancel_appointment` | cancel an existing booking | "meri appointment cancel kar dein" |
| `check_appointment` | ask about an existing booking | "mera appointment kis time hai?" |
| `doctor_availability` | asks when a doctor / department sits, without asking to book | "Dr Kamran kis din aate hain?" |
| `describe_symptom` | only describes a complaint, no request | "do din se pait mein dard hai" |
| `inform` | a bare answer: a name, date, number on its own | "0301 1234567", "parson" |
| `confirm` / `deny` | yes / no on its own | "ji theek hai" / "nahi ye wala nahi" |
| `clinic_info` | timings, fee, address, parking, lab, insurance | "fee kitni hai?" |
| `greet` / `goodbye` | only a greeting or a goodbye. "Salam, kal ka time chahiye" is `book_appointment`. | "AoA", "shukriya Allah hafiz" |
| `out_of_scope` | diagnosis, medicine or dose questions, chit-chat, anything else | "panadol kitni leni hai?" |

## 4. Department

Fill a department only when the message carries a routing signal (a complaint, a department name, a
doctor's name, or a child). Otherwise write `none`. Rows with `none` are left out of department accuracy.

| department | signal |
|---|---|
| `cardiology` | heart, chest pain, BP, palpitations, breathless on stairs |
| `dermatology` | skin, itching, rash, pimples, hair fall, nails, dandruff |
| `ent` | ear, nose, throat, tonsils, voice, sinus, swallowing |
| `gastroenterology` | stomach, acidity, vomiting, loose motions, constipation, liver, jaundice |
| `orthopedics` | bones, joints, knee, back, neck, shoulder, sprain, fracture |
| `gynecology` | periods, pregnancy, delivery, PCOS, "lady doctor" |
| `pediatrics` | the patient is a child: **stated age 12 or under**, or a child word (beta, beti, bachi, baby) with no age. A child with a clearly gynecology complaint stays gynecology. |
| `general_physician` | fever, cough, flu, weakness, headache, sugar, body pain, or "any doctor" with a general complaint |

Rules that keep labels consistent:

* A **named doctor** decides the department: label the doctor's department (see `data_gen/lexicons.py`
  `DOCTORS`), even if the complaint points elsewhere. Note the conflict in `notes`.
* A **named department** beats the complaint ("pait dard hai, skin wale ko dikhana hai" is dermatology).
* **Age beats family words.** "Chota bhai, age 45, bukhar" is `general_physician`, not pediatrics. The
  training data has a known bug here; do not copy it.
* Complaints from two specialties with no department named: pick the one the person stresses most and
  write `two complaints` in `notes`.

## 5. Slots

Mark each slot with `[value](SLOT)`. Slot names: `PATIENT_NAME`, `AGE`, `PHONE`, `DATE`, `TIME`, `DOCTOR`,
`DEPARTMENT`, `SYMPTOM`, `APPOINTMENT_ID`. Follow the existing free-form set
(`data_gen/freeform_test.txt`), which uses these boundaries:

* `DATE`: the date words only. `[kal](DATE)`, `[next Tuesday](DATE)`, `[11 tareekh](DATE)`, `[aaj hi](DATE)`.
  Not "ko" / "ka" after it.
* `TIME`: `[shaam](TIME)`, `[subah 9 baje](TIME)`, `[Zuhr ke baad](TIME)`. "kal shaam" is two slots:
  `[kal](DATE) [shaam](TIME)`.
* `AGE`: number plus unit. `[4 saal](AGE)`, `[6 mahine](AGE)`, `[دو سال](AGE)`.
* `DOCTOR`: include the title. `[Dr Kamran](DOCTOR)`, `[ڈاکٹر احمد رضا](DOCTOR)`. Not "sahab" / "se".
* `DEPARTMENT`: the whole naming phrase. `[skin wale doctor](DEPARTMENT)`, `[dil ke doctor](DEPARTMENT)`,
  `[ENT wale](DEPARTMENT)`, `[لیڈی ڈاکٹر](DEPARTMENT)`. A plain "doctor" is not a department.
* `SYMPTOM`: the complaint phrase without the verb "hai / ho raha hai". `[seene mein dard](SYMPTOM)`,
  `[ghutna bohat dukh raha](SYMPTOM)`. Two separate complaints are two slots.
* `PATIENT_NAME`: the name only, `[Sajjad Hussain](PATIENT_NAME)`, not "mera naam".
* `PHONE`: the whole number with its dashes or spaces. `APPOINTMENT_ID`: `[MB-1042](APPOINTMENT_ID)`.

A slot must cover whole words: `[bukhar](SYMPTOM)` is fine, `[bukh](SYMPTOM)ar` is not (the script warns).

## 6. Scoring

```bash
cd medbook/real_test
python score_real.py real_messages.csv                  # both models, writes ../results/real_v1/
python score_real.py real_messages.csv --engines xlmr   # one model
python score_real.py real_messages.csv --e2e            # also full booking chats started by each real message
python score_real.py real_messages.csv --check          # only validate the labels, no models
```

Needs the backend requirements (`backend/requirements.txt`: torch, transformers, scikit-learn,
sklearn-crfsuite). XLM-R weights come from `results/xlmr_final/model` (change with `--model_dir`).

Outputs in `results/real_v1/`:

* `scores_<engine>.json`: same layout as `results/xlmr_v1/scores.json` (`overall`, `mixed`, `roman`, `urdu`,
  each with `n`, `intent_acc`, `intent_macro_f1`, `dept_top1_acc`, `slot_entity_f1`), under three keys:
  `real` (model alone), `real_with_backstop` (model plus the backend's rules: emergency keywords,
  phone / booking-number regex, doctor names, and the keyword/age department router), and
  `real_by_reported_style`. Plus `emergency` (recall and false alarms) and `n_people`.
* `errors_<engine>.jsonl`: every row with any mistake, gold next to prediction, for the error analysis chapter.
* `summary.md`: one table comparing both models, ready for the report or slides.
* `e2e_<engine>.json` (with `--e2e`): booking success when each real booking message opens a simulated chat
  (same simulator as `backend/simulate.py`; follow-up answers come from the held-out test split).

Report the "model alone" numbers as the model's score and "with backstop" as the system's score.
With fewer than about 30 rows in a style, say the number is indicative only.
