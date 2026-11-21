// Text of the MedBook final report. Every number comes from a file in this repository; the file is named next to it
// in the text or in the table note. [[...]] marks something the team must fill in before submission (shown highlighted).
const F = "docs/report_figures/";

module.exports = {
  meta: {
    students: [["Muhammad Bilal Afzal", "6349-BSAI-23"], ["Rubab Rafique", "6307-BSAI-23"], ["Rida Irfan", "6309-BSAI-23"]],
    date: "[[Month and year of submission]]",
  },

  declaration: [
    ["p", "We declare that this report, *MedBook: A Code-Switched Conversational Agent for Clinic Appointment Scheduling and Department Routing*, and the software, dataset and experiments it describes are our own work, carried out under the supervision of Sir M. Hafeez in the Department of Artificial Intelligence, Government College University, Lahore. Where we have used the work of others, including published papers, open-source software, pre-trained models and AI writing and coding assistants, it is acknowledged in the text and in the references. This work has not been submitted for any other degree or qualification."],
  ],

  certificate: [
    ["p", "This is to certify that the final year project report titled *MedBook: A Code-Switched Conversational Agent for Clinic Appointment Scheduling and Department Routing*, submitted by Muhammad Bilal Afzal (6349-BSAI-23), Rubab Rafique (6307-BSAI-23) and Rida Irfan (6309-BSAI-23), has been examined and found acceptable in partial fulfilment of the requirements for the degree of Bachelor of Science in Artificial Intelligence."],
  ],

  acknowledgements: [
    ["p", "We are grateful to our supervisor, Sir M. Hafeez, for guidance throughout the project, and to the faculty of the Department of Artificial Intelligence, GCU Lahore, for their feedback at the proposal and mid evaluations. We thank the classmates, friends and family members who wrote test messages and recorded voice samples for the evaluation. We also acknowledge the open-source communities behind PyTorch, Hugging Face Transformers, XLM-RoBERTa, Whisper, MMS, FastAPI, Next.js, PostgreSQL and llama.cpp, without whom a project of this scope would not have been possible in one year. [[Add any personal acknowledgements.]]"],
  ],

  abstract: [
    ["p", "Most small and medium private clinics in Pakistan still book appointments by telephone. Booking is limited to opening hours, lines are busy at peak times, and patients are expected to know which specialist they need. The digital platforms that exist are form-based and in English, while many patients write most naturally in Urdu script or in code-switched Roman Urdu. This project builds **MedBook**, a conversational agent that accepts free-form messages in Urdu script, Roman Urdu, English or any mix of them, understands what the patient wants, routes a described complaint to one of eight clinical departments, and books, reschedules, cancels or checks appointments against a live clinic database. A voice mode lets patients speak Urdu and hear the answer."],
    ["p", "Because no labelled code-switched clinic corpus existed, we built one: **8,615 labelled messages** generated from 434 templates (14 intents, 9 slot types, 8 departments), split so that test templates are never seen in training, plus 145 hand-written free-form messages and **600 annotated multi-turn dialogues**. A rule audit and a 300-row hand check found and fixed three systematic labelling errors between dataset v1 and v2. A single **XLM-RoBERTa** encoder with joint intent, department and BIO slot heads reaches **0.96 intent accuracy, 1.00 department accuracy and 0.95 slot F1** on unseen templates, and **0.83 intent accuracy** on free-form text, against 0.67 for a TF-IDF and CRF baseline. A prompted Qwen2.5-7B LLM reaches only 0.74 on the same free-form set (McNemar p ≈ 0.02) and is about 400 times slower on the same CPU. A rule-based dialogue manager adds safety rules (every held-out emergency message is sent to Rescue 1122), a keyword and age backstop for routing (98.2% department accuracy on free-form messages), and slot negotiation from real free slots. In 300 simulated dialogues per setting, task success is 99.7% with free-form openers. With Whisper large-v3-turbo the system transcribes real Urdu speech at 21.4% word error rate and keeps 78.7% intent accuracy from synthetic spoken clinic messages. The deployed stack (Docker, PostgreSQL, Redis, SMS reminders, staff schedule page) served 200 simultaneous simulated patients with a 95th-percentile response time of 39 ms, no failed requests and no double bookings."],
    ["p", "**Keywords:** code-switching, Roman Urdu, task-oriented dialogue, joint intent and slot filling, XLM-RoBERTa, department routing, speech recognition, appointment scheduling."],
  ],

  abbreviations: {
    caption: "Abbreviations used in this report", noCaption: true, widths: [1, 3], left: true,
    header: ["Abbreviation", "Meaning"],
    rows: [
      ["API", "Application programming interface"], ["ASR", "Automatic speech recognition"], ["BIO", "Begin, Inside, Outside tagging scheme for spans"],
      ["CER / WER", "Character / word error rate"], ["CPU / GPU", "Central / graphics processing unit"], ["CRF", "Conditional random field"],
      ["DM", "Dialogue manager"], ["ENT", "Ear, nose and throat"], ["F1", "Harmonic mean of precision and recall"],
      ["FLEURS", "Few-shot Learning Evaluation of Universal Representations of Speech (benchmark)"], ["GP", "General physician"],
      ["LLM", "Large language model"], ["MMS", "Massively Multilingual Speech (Meta)"], ["NLU", "Natural language understanding"],
      ["p95 / p99", "95th / 99th percentile"], ["SNR", "Signal-to-noise ratio"], ["SMS", "Short message service"],
      ["TF-IDF", "Term frequency, inverse document frequency"], ["TTS", "Text to speech"], ["XLM-R", "XLM-RoBERTa, a multilingual transformer encoder"],
    ],
  },

  body: [
    // =====================================================================================================
    ["h1", "Introduction"],
    ["h2", "1.1 Background"],
    ["p", "Appointment scheduling in small and medium private clinics across Pakistan is still handled mainly by telephone, by a receptionist who writes bookings in a paper register. This limits booking to clinic hours, produces engaged lines at peak times, keeps no automatic record of a patient's visits, and sends no reminders. It also assumes that the patient already knows which specialist to see, an assumption that often fails for first-time visitors with a general complaint such as \"chest feels heavy\" or \"my son has had a fever for three days\"."],
    ["p", "The digital platforms in the local market are directory-driven and form-based: the user picks a city, a specialty, a doctor and a slot. Each step assumes medical knowledge and comfort with a structured English interface. A large share of the population communicates most naturally in Urdu, either in Urdu (Perso-Arabic) script or in Roman Urdu, and very often switches between Urdu and English inside one sentence (\"mujhe kal skin specialist ko dikhana hai\"). This *code-switching* is the normal way people text, and it is poorly served by forms and by language technology built for English."],
    ["p", "Recent progress in multilingual transformer models makes it possible to build a conversational agent that reads this kind of text directly. This project applies such models to a concrete, high-value task: letting a patient book a clinic appointment by simply writing or speaking the way they normally would."],

    ["h2", "1.2 Problem Statement"],
    ["p", "Patients of small private clinics in Pakistan cannot book, change or cancel appointments outside clinic hours, and they must already know which department they need. Existing digital alternatives require structured English input. There is no publicly available labelled dataset of code-switched Urdu-English clinic messages, and no open system that understands such messages, routes a described complaint to a department, and completes a verified booking against a real schedule while staying safe in emergencies."],

    ["h2", "1.3 Aims and Objectives"],
    ["p", "The aim of the project is to design, build and evaluate a conversational agent that books clinic appointments from free-form, code-switched Urdu-English input and routes complaints to the right department. The objectives, taken from the approved proposal, and where each is addressed in this report are listed in Table 1.1."],
    ["table", {
      caption: "Project objectives from the proposal and their outcome", widths: [3.2, 1.1, 2.4],
      header: ["Objective", "Status", "Where"],
      rows: [
        ["Accept free-form Urdu script, Roman Urdu, English and mixed text through a web chat", "Done", "Chapters 5 and 6"],
        ["Classify intent and extract symptom, department, doctor, date, time and patient details", "Done", "Sections 5.3, 7.1"],
        ["Recommend a department from a symptom, with a confidence score and a General Physician fallback", "Done", "Sections 5.4, 7.2"],
        ["Multi-turn dialogue with slot filling, confirmation and corrections", "Done", "Sections 5.5, 7.4"],
        ["Offer alternative slots when the requested one is not free", "Done", "Section 5.5"],
        ["Book, reschedule, cancel and check appointments in a live database", "Done", "Sections 5.6, 7.7"],
        ["Send automatic appointment reminders", "Done (SMS; WhatsApp is future work)", "Section 5.7"],
        ["Detect emergencies and direct the user to Rescue 1122", "Done", "Sections 5.5, 7.5"],
        ["Zero double bookings under concurrent access", "Done and tested", "Sections 5.6, 7.7"],
        ["Speech input (listed as future work in the proposal)", "Done as an extension", "Sections 5.8, 7.6"],
      ],
    }],

    ["h2", "1.4 Scope"],
    ["p", "**In scope:** booking, rescheduling, cancellation and status enquiries; symptom-based routing to eight departments (general physician, cardiology, dermatology, ENT, gastroenterology, orthopedics, gynecology and pediatrics); multi-turn dialogue with slot filling and correction handling; Urdu, English and code-switched input; a single clinic with 16 doctors; automated reminders; a staff schedule page; and, beyond the proposal, spoken Urdu input and spoken Urdu replies."],
    ["p", "**Out of scope:** medical diagnosis, treatment, medication or dosage advice; emergency triage (a rule-based safety layer instead detects possible emergencies and points the user to Rescue 1122); payment, insurance and electronic medical record integration; and WhatsApp delivery, which is left as future work (Section 8.3)."],

    ["h2", "1.5 Contributions"],
    ["ul", [
      "**A labelled code-switched clinic dataset** (Chapter 4): 8,615 single-turn messages in three writing styles with intent, department and BIO slot labels, a 145-message free-form test set, and 600 multi-turn dialogues with the belief state after every user turn. The generator, label audit and splits are reproducible from a fixed seed.",
      "**A joint XLM-R model for intent, department and slots** (Sections 5.3 and 7.1) that improves free-form intent accuracy from 0.67 to 0.83 over a strong classical baseline, together with a label-quality study showing how dataset v2 fixes age-based pediatrics routing (0 of 30 to 29 of 30 rows correct).",
      "**A controlled comparison with prompted open LLMs** (Section 7.3): the fine-tuned 270M-parameter encoder beats a 7B instruction-tuned LLM on accuracy (significantly, by McNemar's test) and is about 400 times faster on the same CPU.",
      "**A complete, safe dialogue system** (Chapter 5) that never invents a booking number or slot, handles corrections at any point, and stops for emergencies, evaluated with simulated users and targeted safety tests.",
      "**A voice channel for Urdu** (Sections 5.8 and 7.6) using Whisper and MMS-TTS, with transcript cleanup rules and an evaluation of five Whisper sizes on real and synthetic speech, clean and noisy.",
      "**A deployable system** (Chapter 6 and Section 7.7): Docker Compose stack with PostgreSQL, Redis, an SMS reminder worker and a staff page, load-tested to 200 concurrent simulated patients.",
    ]],

    ["h2", "1.6 Report Organisation"],
    ["p", "Chapter 2 reviews related work on task-oriented dialogue, joint intent and slot models, multilingual and code-switched NLP, LLMs and speech. Chapter 3 states the requirements and the research methodology. Chapter 4 describes how the dataset was built and checked. Chapter 5 presents the system design and Chapter 6 its implementation. Chapter 7 reports every evaluation, and Chapter 8 concludes with limitations and future work."],

    // =====================================================================================================
    ["h1", "Literature Review"],
    ["h2", "2.1 Task-Oriented Dialogue Systems"],
    ["p", "Task-oriented dialogue systems help a user complete a specific goal, such as booking a flight or a table, through conversation. The classic architecture is a pipeline of natural language understanding (NLU), dialogue state tracking, a dialogue policy and response generation [14]. NLU maps each user turn to an *intent* (what the user wants) and *slots* (the values needed to do it); the state tracker accumulates slots across turns; the policy decides the next system action. Benchmarks such as ATIS [10], SNIPS [11] and CLINC150 [12] shaped single-turn NLU research, while the Dialog State Tracking Challenges [15] and MultiWOZ [13] did the same for multi-turn state tracking. Open-source frameworks such as Rasa [16] package this pipeline for practitioners."],
    ["p", "End-to-end neural and LLM-based dialogue systems remove the explicit pipeline, but in domains where actions have real consequences (a booking written into a clinic's schedule) a modular design remains attractive: each component can be tested on its own, the policy can enforce hard rules (never book without explicit confirmation, never invent a slot), and failures are explainable. MedBook follows this modular design and uses learning where it helps most, in understanding noisy, code-switched input."],

    ["h2", "2.2 Joint Intent Detection and Slot Filling"],
    ["p", "Intent detection is a sentence classification task and slot filling a sequence labelling task, usually with BIO tags [22]. Classical systems used separate models, for example a linear classifier over n-gram features for intent and a conditional random field (CRF) [21] for slots. Liu and Lane [8] showed that a single recurrent encoder trained jointly on both tasks improves each, and Goo et al. [9] added a slot gate that lets the intent inform slot decisions. With pre-trained transformers [26], Chen et al. [7] fine-tuned BERT [2] with an intent head on the first token and a slot head on every token, which became the standard strong baseline. MedBook extends this joint design with a third head for department routing, sharing one encoder for all three tasks."],

    ["h2", "2.3 Multilingual Transformers"],
    ["p", "Multilingual encoders are pre-trained on text from many languages with a shared sub-word vocabulary, so that knowledge transfers across languages. XLM-RoBERTa (XLM-R) [1] was trained on 2.5 TB of CommonCrawl text in 100 languages, including Urdu, using a SentencePiece [32] vocabulary of 250,000 tokens. It outperformed earlier multilingual models on cross-lingual classification and labelling, and its base version (270M parameters) is small enough to fine-tune and serve on a CPU. The MASSIVE dataset [6] provides parallel intent and slot data for 51 languages, including Urdu, from the voice assistant domain, and confirms that XLM-R is a strong encoder for multilingual NLU. MASSIVE contains only Urdu script, however, and none of its domains covers clinic scheduling."],

    ["h2", "2.4 Code-Switching and Urdu NLP"],
    ["p", "Code-switching, the alternation between languages within a conversation or a sentence, is the norm in multilingual societies, yet most NLP resources assume a single language [19]. Benchmarks such as GLUECoS [17] and LinCE [18] show that models trained on monolingual data lose accuracy on code-switched text, and that the problem is harder when one language is written in a non-native script. Urdu adds further difficulties [20]: it is written in Perso-Arabic script with optional diacritics and letter variants, and online it is very often written in Roman script with no standard spelling (\"hai\", \"he\", \"h\"; \"bukhar\", \"bukhaar\"). The same message can therefore appear in three different surface forms (Urdu script, Roman Urdu, and Urdu script mixed with English words), and labelled data in all three for a narrow domain is scarce. These observations motivated our three-style dataset design, our spelling-noise augmentation, and our evaluation broken down by writing style."],

    ["h2", "2.5 Large Language Models for NLU"],
    ["p", "Large language models can perform new tasks from instructions and a few examples in the prompt, without fine-tuning [25]. Open instruction-tuned models such as Qwen2.5 [24] are multilingual and can be run locally in 4-bit quantised form with llama.cpp [33]. This raises a practical question for a project like MedBook: is it still worth collecting data and fine-tuning a small encoder, or could a prompted LLM serve as the NLU? Section 7.3 answers this question for our task with a controlled comparison on the same messages and the same scoring."],

    ["h2", "2.6 Speech Recognition and Synthesis for Urdu"],
    ["p", "Whisper [3] is an encoder-decoder speech recogniser trained on 680,000 hours of weakly supervised multilingual audio, available in sizes from tiny (39M parameters) to large. It supports Urdu, but its accuracy on lower-resource languages is far below English, and when the language is not fixed it often writes spoken Urdu in Hindi (Devanagari) script, which a text NLU trained on Urdu cannot read. The FLEURS benchmark [5] provides read speech in 102 languages, including Urdu, and is the standard way to measure word error rate. For the reverse direction, Meta's Massively Multilingual Speech project (MMS) [4] released VITS-based text-to-speech voices for more than 1,100 languages, including Urdu in Perso-Arabic script, which can run offline on a CPU."],

    ["h2", "2.7 Conversational Agents in Healthcare"],
    ["p", "A systematic review of conversational agents in healthcare [27] found that most were rule-based, few were evaluated with patients, and safety was rarely assessed; it recommended that health chatbots be evaluated for patient safety and limited to well-defined tasks. Appointment booking is such a task, but a clinic agent will inevitably receive messages describing emergencies. This motivates our design principle that the agent must never give medical advice, must stop and direct the user to emergency services when danger is signalled, and must say when it is unsure of a routing decision instead of hiding that uncertainty."],

    ["h2", "2.8 Research Gap"],
    ["p", "To our knowledge there is no public labelled dataset or open system for code-switched Urdu-English clinic scheduling. Existing multilingual NLU datasets either lack Roman Urdu and code-switching (MASSIVE) or lack the clinic domain and its routing task. Existing local booking platforms rely on forms. This project fills that gap with a dataset that covers all three writing styles, a joint model that adds department routing to intent and slot filling, an evaluation that separates seen phrasing from genuinely new phrasing, and a complete, safe, deployable dialogue system with a voice channel."],

    // =====================================================================================================
    ["h1", "Requirements and Methodology"],
    ["h2", "3.1 Functional Requirements"],
    ["table", {
      caption: "Functional requirements and how each was met", widths: [0.5, 3, 3],
      header: ["ID", "Requirement (from the proposal)", "Implementation"],
      rows: [
        ["FR1", "Accept free-form code-switched Urdu-English text via a web widget and WhatsApp", "Next.js web chat; the reply follows the user's script. WhatsApp not built (Section 8.3)"],
        ["FR2", "Classify intent and extract symptom, department, doctor, date, time, patient name", "XLM-R joint model: 14 intents, 9 slot types (adds age, phone and booking number)"],
        ["FR3", "Recommend a department with confidence and a GP fallback", "Department head + keyword and age backstop; below 0.40 confidence the bot routes to GP and says why"],
        ["FR4", "Multi-turn state with slot filling, confirmation and corrections", "Rule-based dialogue manager with a belief state; any slot can be corrected until the final \"yes\""],
        ["FR5", "Negotiate alternative slots", "Offers come only from free slots in the database, nearest first"],
        ["FR6", "Create, reschedule, cancel and check appointments in a live database", "SQLite (demo) or PostgreSQL (deployment) with transactional booking"],
        ["FR7", "Automated reminders", "Reminder worker: SMS the day before and on the day, in the patient's script"],
        ["FR8", "Detect emergencies and redirect to emergency services", "Keyword rules plus the model's emergency intent; the user is told to call Rescue 1122"],
        ["FR9 (added)", "Speech input and spoken replies", "Whisper large-v3-turbo with Urdu prompt and cleanup; MMS-TTS Urdu voice"],
        ["FR10 (added)", "Staff view of the schedule", "/admin page with every doctor's slots, cancel button and reminder log"],
      ],
    }],
    ["h2", "3.2 Non-Functional Requirements"],
    ["table", {
      caption: "Non-functional requirements and how each was verified", widths: [1.1, 2.4, 3],
      header: ["Quality", "Requirement", "Verification"],
      rows: [
        ["Reliability", "Zero double bookings under concurrent access, through transactional row-level locking", "30-thread race test on SQLite and PostgreSQL; 1,080 load-test bookings with 0 slots held twice (Section 7.7)"],
        ["Performance", "Acceptable conversational latency", "p95 of 39 ms at 200 concurrent patients (baseline NLU); XLM-R 28 ms per message on CPU"],
        ["Usability", "No medical or technical knowledge needed", "Free-form input in any script; routing from symptoms; replies in the user's script"],
        ["Scalability", "Many concurrent conversations", "Sessions in Redis, so several workers can share them; load test in Section 7.7"],
        ["Privacy", "Anonymised data and secure handling of patient information", "Synthetic training data with fake names and numbers; staff routes behind a token; phone numbers masked on public routes"],
        ["Transparency", "Disclose low-confidence routing", "Below 0.40 department confidence the bot routes to a GP and says it is unsure; the demo panel shows every decision"],
        ["Safety (added)", "Never invent bookings; never give medical advice", "Booking numbers come only from database inserts; out-of-scope intent declines advice; tested in the dialogue tests"],
      ],
    }],

    ["h2", "3.3 Development Methodology"],
    ["p", "The project followed an iterative, evidence-driven process. Each stage produced a measurable artefact and a result that fed the next stage:"],
    ["ol", [
      "**Schema and data.** Define intents, slots and departments once in `data_gen/schema.py`, then build a template-based generator and the v0 sample, the v1 dataset and, after a label audit, the v2 dataset.",
      "**Baseline.** Train a TF-IDF and logistic regression intent classifier, a separate department classifier and a CRF slot tagger, to set the bar any neural model must clear.",
      "**Joint XLM-R model.** Fine-tune one XLM-R encoder with three heads; pick the number of epochs on the validation set only.",
      "**Dialogue manager and demo.** Build the rule-based dialogue manager, clinic database, API and web interface, and test them with unit tests and simulated users.",
      "**Error-driven fixes.** Read every free-form error, add rules where the model was weak (keyword routing backstop, age rule), and fix data bugs found on the way (v2).",
      "**Deployment.** Add PostgreSQL, Redis, Docker, reminders and the staff page; load-test the stack.",
      "**Extensions and comparisons.** Add the voice channel and evaluate it; compare the fine-tuned model with prompted LLMs.",
    ]],
    ["p", "Source code was kept in Git and GitHub throughout. All training ran on a 4-core CPU (and optionally Google Colab), so every result in this report can be reproduced without special hardware."],

    ["h2", "3.4 Evaluation Methodology"],
    ["p", "A template-generated dataset makes it easy to get misleadingly high scores, because a test sentence may differ from a training sentence only in the filled-in values. We therefore used several safeguards:"],
    ["ul", [
      "**Split by template, not by row.** Validation uses 46 templates and test 69 templates that never appear in training, and no exact test sentence occurs in train.",
      "**A free-form test set.** 145 messages written one by one, not from templates, are the most honest test of generalisation. They are used only for testing.",
      "**Model selection on validation only.** The number of epochs was chosen on the validation set; test and free-form sets were scored once at the end.",
      "**Breakdown by writing style.** Every score is also reported for Roman Urdu, Urdu script and mixed text.",
      "**Significance.** With 145 free-form messages one message is 0.7 percentage points, so we treat differences under about 3 points as noise and use McNemar's test [23] for paired comparisons of two models on the same messages.",
      "**Task-level evaluation.** Beyond per-message scores, simulated users play whole dialogues and success is judged in the database, not in the bot's words.",
      "**Placeholders for real data.** Real typed messages and real voice recordings from people are the fairest tests; their results go in Sections 7.8 and 7.9.",
    ]],
    ["p", "Metrics: intent accuracy and macro-averaged F1 over the 14 intents; department top-1 accuracy over messages that carry a routing label; slot entity F1 (exact span and label match, as in the CoNLL convention); and for speech, word and character error rate after normalising punctuation, diacritics, letter variants and digits."],

    // =====================================================================================================
    ["h1", "Dataset Construction"],
    ["p", "No labelled dataset of code-switched clinic messages existed, and collecting and annotating thousands of real patient messages was not possible within the project's time and privacy constraints. We therefore generated a large labelled training set from templates, designed it so that the test sets measure generalisation honestly, and kept a separate set of free-form messages for testing. This chapter describes the schema, the generator, the splits, the quality checks and the label fixes that produced dataset v2, the version used for all final results."],

    ["h2", "4.1 Label Schema"],
    ["p", "The schema is defined once in `data_gen/schema.py` and imported by the generator, the model and the dialogue manager, so labels cannot drift between components. It has 14 intents (Table 4.1), 9 slot types (Table 4.2) and 8 departments plus `none`. A department label is set only for messages that need routing (book_appointment, describe_symptom and doctor_availability)."],
    ["table", {
      caption: "Intents, their meaning and their counts in dataset v2 (train / validation / test / free-form)", widths: [1.6, 3.2, 1.6],
      header: ["Intent", "Meaning", "Train / val / test / free-form"],
      rows: [
        ["book_appointment", "Wants a new appointment; may carry any slot", "1,380 / 210 / 270 / 34"],
        ["reschedule_appointment", "Move an existing appointment", "606 / 90 / 120 / 10"],
        ["cancel_appointment", "Cancel an existing appointment", "395 / 90 / 120 / 8"],
        ["check_appointment", "Ask about an existing appointment", "400 / 41 / 120 / 6"],
        ["doctor_availability", "When a doctor or department is available", "570 / 90 / 120 / 8"],
        ["describe_symptom", "Describes a complaint without asking to book", "720 / 90 / 150 / 21"],
        ["inform", "Bare answer to a question (name, date, phone)", "917 / 120 / 207 / 12"],
        ["confirm", "Yes / agree (ji haan, theek hai)", "173 / 24 / 36 / 8"],
        ["deny", "No / disagree / start of a correction", "364 / 48 / 126 / 7"],
        ["greet", "Opening the chat (salam, AoA)", "16 / 2 / 4 / 4"],
        ["goodbye", "Ending the chat (Allah hafiz)", "14 / 2 / 4 / 4"],
        ["clinic_info", "Timings, fee, location, parking", "342 / 37 / 69 / 7"],
        ["emergency", "Possible emergency; bot must stop and point to 1122", "115 / 15 / 37 / 8"],
        ["out_of_scope", "Diagnosis, medicine dose, chit-chat", "226 / 65 / 70 / 8"],
      ],
      note: "Source: data/dataset_v2/stats.json.",
    }],
    ["table", {
      caption: "Slot types with examples and training counts", widths: [1.5, 3.3, 1],
      header: ["Slot", "Examples", "Train spans"],
      rows: [
        ["DATE", "kal, parson, agle somwar, 25 tareekh, کل", "2,213"], ["TIME", "subah 10 baje, saade 9, شام", "930"],
        ["DOCTOR", "Dr. Ayesha, dr ahmed raza", "1,123"], ["DEPARTMENT", "skin specialist, dil ka doctor", "780"],
        ["SYMPTOM", "seene mein dard, بخار, saans mein khar khar", "1,470"], ["PATIENT_NAME", "Ali Raza, فاطمہ نور", "570"],
        ["AGE", "5 saal, پانچ سال", "243"], ["PHONE", "0300-1234567", "198"], ["APPOINTMENT_ID", "MB-1042, mb 6610", "320"],
      ],
    }],

    ["h2", "4.2 Generation Process"],
    ["p", "The generator (`data_gen/generate.py`, `templates.py`, `lexicons.py`) combines three sources of variety:"],
    ["ul", [
      "**434 templates** written by hand for every intent in all three writing styles, with slot placeholders such as `{DOCTOR} ka appointment {DATE} ke liye`.",
      "**Lexicons** for every slot: 40 patient names, 16 doctors (two per department, matching the clinic database), 9 to 15 symptoms per department in each script, relative and absolute dates, times of day, phone numbers and booking references, plus child words (\"mera beta\", \"میری بیٹی\") and ages.",
      "**Wrappers and noise:** greetings and politeness phrases added at the start or end (\"salam\", \"please\", \"jaldi bata dein\"), and realistic Roman Urdu spelling noise applied to 25% of Roman rows (\"hai\" to \"he\", \"bjy\" for \"baje\").",
    ]],
    ["p", "Each filled template produces the text, its tokens, character spans for every slot, BIO tags aligned with the tokens, the intent, the department, the writing style and the template id. Every row is checked automatically: each span must match its text exactly, tokens and tags must align, and no test sentence may appear in training. The same seed always produces the same files (`build_dataset.py --out ../data/dataset_v2`)."],
    ["p", "An example row (Roman Urdu, booking with a doctor and a date):"],
    ["code", "text:   Dr. Tariq Mehmood ka appointment book kar dein kal ke liye\ntags:   B-DOCTOR I-DOCTOR I-DOCTOR I-DOCTOR O O O O O B-DATE O O\nintent: book_appointment    department: ent    script: roman"],

    ["h2", "4.3 Splits and Test Sets"],
    ["table", {
      caption: "Contents of dataset v2", widths: [1.6, 1, 3.6],
      header: ["Split", "Rows", "What it is"],
      rows: [
        ["Train", "6,238", "Generated from 319 templates"],
        ["Validation", "924", "46 templates never seen in training; used to choose epochs"],
        ["Test", "1,453", "69 templates never seen in training or validation"],
        ["Free-form test", "145", "Written one at a time, not from templates; test only"],
        ["Dialogues", "600", "3,319 labelled user turns, 11.3 turns on average, belief state after every turn"],
      ],
      note: "Single-turn rows by script: 3,933 Roman Urdu, 2,536 Urdu script and 2,146 mixed. Source: README.md and data/dataset_v2/stats.json.",
    }],
    ["p", "The free-form set contains 78 Roman Urdu, 42 Urdu script and 25 mixed messages covering every intent and department. It was written one message at a time with the help of an AI assistant, deliberately using phrasing the templates do not contain. It is therefore a much harder test than the template splits, but it was not written by patients; real messages are collected separately (Section 7.8). The 600 dialogues cover booking (372), reschedule (87), check (55), cancel (49) and emergency (37) tasks in all three styles, and include corrections, slot offers and confirmations."],
    ["fig", { file: F + "fig_intents.png", caption: "Intent distribution over the train, validation and test splits of dataset v2", width: 5.8 }],
    ["fig", { file: F + "fig_scripts.png", caption: "Share of each writing style in each split", width: 5.8 }],
    ["fig", { file: F + "fig_departments.png", caption: "Number of messages with each department label", width: 5.6 }],
    ["p", "The intent distribution is deliberately unbalanced in the way real chats are: booking and inform turns are common, while greet and goodbye have only 16 and 14 training rows. The model compensates with class-weighted loss (Section 5.3)."],

    ["h2", "4.4 Label Audit: from v1 to v2"],
    ["p", "While evaluating routing we found that some department labels in dataset v1 were wrong. A rule audit (`data_gen/audit_labels.py`) and a hand reading of 300 random rows found three systematic slips, all caused by templates that combined slot values without checking that they made sense together (Table 4.4)."],
    ["table", {
      caption: "Labelling errors found in dataset v1 and the rule adopted in v2", widths: [2.6, 1.1, 3],
      header: ["Slip in v1", "Rows (train / test)", "v2 rule"],
      rows: [
        ["Child word with an adult age (\"mere chote bhai ki umar 45 saal\") labelled pediatrics", "48 / 26", "Pediatrics only for an age of 12 or under, or a child word with no age; otherwise the symptom's adult department"],
        ["Male patient sent to gynecology (\"abbu ko periods band hai\")", "25 / 2", "Templates about a man never draw gynecology; gynecology bookings use female names"],
        ["Two ages in one sentence", "5 / 0", "A child phrase carrying its own age is not used when the template has an AGE slot"],
      ],
      note: "v2 also removes repeated wrappers (\"ji ji haan\") and adds ages near the cut-off (10, 14, 15, 18). The audit finds 0 slips in v2.",
    }],
    ["p", "The fix matters: on the 30 v2 test rows with a child word and an age over 12, the model trained on v1 sends all 30 to pediatrics (0% correct), while the model trained on v2 gets 29 of 30 right; both get all 30 rows aged 12 or under right (`results/xlmr_v2/age_routing_check.json`). The same audit found a substring bug in the keyword router (the Urdu word for *swallow*, نگل, matched inside منگل, *Tuesday*), which was fixed and covered by a unit test."],

    ["h2", "4.5 Ethics and Privacy"],
    ["p", "All training data is synthetic: names, phone numbers and booking numbers are invented, and no real patient data was used. Participants who contribute real test messages or recordings are asked to use fake names and numbers, are identified only by codes such as p01, and their data is used only for testing (`real_test/LABELLING_GUIDE.md`). The symptom-to-department mapping is a scheduling aid, not medical advice, and should be reviewed by a doctor before real use."],

    // =====================================================================================================
    ["h1", "System Design"],
    ["h2", "5.1 Architecture"],
    ["p", "MedBook is a modular pipeline (Figure 5.1). The browser talks only to the Next.js frontend, which forwards `/api/*` calls to a FastAPI backend. For each message the backend optionally transcribes speech, runs the NLU model, applies a rule layer, and passes the result to the dialogue manager, which reads and writes the clinic database. Conversation state lives in Redis (or in memory for the laptop demo), and a separate worker sends reminders."],
    ["fig", { file: F + "fig_architecture.png", caption: "System architecture of the deployed MedBook stack", width: 6.2 }],

    ["h2", "5.2 Processing a Message"],
    ["p", "Figure 5.2 shows what happens to one user message. Normalisation converts Urdu digits and recognises dates and times; the NLU produces an intent, a department and slots with confidences; the rule layer can override or add to these; the dialogue manager updates its belief state, decides what is still missing, consults the database, and replies in the user's script. An emergency at any point stops the task."],
    ["fig", { file: F + "fig_dialogue_flow.png", caption: "Processing of one user message", width: 6.2 }],

    ["h2", "5.3 NLU: Joint XLM-R Model"],
    ["p", "The main NLU model (`models/train_xlmr.py`) is one `xlm-roberta-base` encoder with three heads:"],
    ["ul", [
      "**Intent head:** a two-layer classifier (linear, tanh, dropout, linear) on the `<s>` token representation, trained with class-weighted cross-entropy (weight proportional to inverse frequency to the power 0.5, so greet and goodbye count about ten times more than booking).",
      "**Department head:** the same structure on `<s>`, trained only on rows that need routing. An ablation (Table 7.2) showed that training it on all rows, where most labels are `none`, hurt free-form routing.",
      "**Slot head:** a linear layer over the first sub-word of each word, predicting BIO tags for the 9 slot types (19 labels).",
    ]],
    ["p", "The three losses are summed with equal weight. Training uses AdamW with a learning rate of 3e-5 for the encoder and 1e-3 for the heads, a linear schedule with 10% warm-up, batch size 32, maximum length 64 sub-words, gradient clipping at 1.0 and seed 13."],
    ["table", {
      caption: "Training configuration of the final XLM-R runs", widths: [2, 3],
      header: ["Setting", "Value"],
      rows: [["Encoder", "xlm-roberta-base (270M parameters)"], ["Epochs", "5 (chosen on validation)"], ["Batch size / max length", "32 / 64 sub-words"],
        ["Learning rate", "3e-5 encoder, 1e-3 heads, linear decay, 10% warm-up"], ["Class-weight power", "0.5"], ["Hardware and time", "4-core CPU, 42 minutes (main run), 56 minutes (train + val run)"]],
      note: "Source: results/xlmr_v2_main/scores.json and README.md.",
    }],
    ["p", "**Baseline.** For comparison, `models/baseline.py` trains a character n-gram (2 to 5) TF-IDF with logistic regression for intent and for department, and a CRF with lexical features for slots. Character n-grams are a strong choice for noisy Roman Urdu because they are robust to spelling variation."],
    ["p", "**Serving.** The backend loads the newest trained weights automatically, and falls back to the baseline if no weights or no PyTorch are present, so the demo always runs. Inference takes about 28 ms per message on a CPU."],

    ["h2", "5.4 Rule Layer and Department Routing"],
    ["p", "A learned model is not trusted alone for decisions that matter. A rule layer (`backend/nlu.py`, `routing.py`) runs after the model and every rule that fires is logged in the trace shown in the demo:"],
    ["ul", [
      "**Emergency keywords** in all three scripts (behosh, saans nahi aa rahi, zeher, بے ہوش ...) override everything.",
      "**Regular expressions** for phone numbers and booking references (MB-xxxx), and **doctor names** matched against the database.",
      "**Routing order:** an explicit doctor, then an explicitly named department, then the symptom. For a symptom, organ and complaint keywords in Urdu script, Roman Urdu and English, plus a stated age (12 or under means pediatrics), decide when they point to one department; otherwise the model's department head decides.",
      "**Confidence fallback:** below 0.40 department confidence the bot routes to the General Physician and tells the user why, meeting the transparency requirement.",
      "**Dialogue-context rules:** a short ordinal (\"1\", \"pehla wala\") picks an offered slot; short yes/no words answer a yes/no question; a weak task switch (confidence under 0.75) in the middle of a task is ignored.",
    ]],
    ["p", "The keyword backstop was added because XLM-R sent some natural Urdu-script symptoms to the wrong department with full confidence (for example \"گلے میں درد ہے اور بخار\", *sore throat and fever*, went to cardiology; it now goes to ENT). Its effect is measured in Section 7.2."],

    ["h2", "5.5 Dialogue Manager"],
    ["p", "The dialogue manager (`backend/dialogue.py`) is rule-based and keeps a belief state per session: the current task, filled slots, the question being awaited, the user's script, offered slots and any booking reference. Its main policies are:"],
    ["ul", [
      "**Slot order.** Booking needs a department or doctor, a date and a time, then the patient's name and phone. Availability is checked before personal details are asked for, so nobody types their number for a slot that does not exist.",
      "**Date and time understanding** (`normalize.py`): kal, parson, agle somwar, 25 tareekh, دو دسمبر, saade 9, paune 6, 4 baje ke baad, Zuhr ke baad, shaam 6 se 7 ke beech. Hours 1 to 7 without am or pm mean pm, matching clinic hours.",
      "**Slot negotiation.** If the requested time is taken or the doctor is off duty, the bot offers the nearest real free slots; on Sundays it explains the clinic is closed.",
      "**No invented facts.** Offers come only from free slots in the database, booking numbers only from inserts, and nothing is written without a \"yes\" to a full summary.",
      "**Corrections.** Any slot can be changed at any time (\"nahi, parson\", \"time badal dein\") and the plan is rebuilt.",
      "**Emergencies.** When emergency keywords fire, the bot drops the task and tells the user to call Rescue 1122. When only the model predicts an emergency, the bot still gives the 1122 advice first, then offers a booking with the routed department in case it is not urgent, so a false alarm is not a dead end.",
      "**Out of scope.** Requests for diagnosis or medicine doses are politely declined.",
      "**Language of the reply.** A mostly Urdu-script message gets an Urdu-script reply; everything else gets Roman Urdu (`replies.py`).",
    ]],

    ["h2", "5.6 Clinic Database and Concurrency"],
    ["p", "The clinic database (`backend/clinic_db.py`, `db.py`) has five tables: departments, doctors (16, two per department), duty hours (a morning 10 AM to 2 PM and an evening 5 PM to 9 PM shift), appointments in 20-minute slots, and reminders. The same code runs on SQLite for the laptop demo and on PostgreSQL in deployment; SQL is written once and the layer adapts placeholders and types."],
    ["p", "To meet the zero-double-booking requirement, `Clinic.book` and `Clinic.reschedule` perform the availability check and the insert in one transaction after `SELECT ... FROM doctors WHERE id = ? FOR UPDATE`. Two patients confirming slots with the same doctor queue on that row lock, and the second sees the first booking when it re-checks. A partial unique index on (doctor, day, time) for booked rows is a second guard. On SQLite, `BEGIN IMMEDIATE` locks the whole database."],

    ["h2", "5.7 Sessions, Reminders and Staff View"],
    ["p", "Each turn loads the session state, runs the dialogue manager and saves the state with a 30-minute idle timeout, in Redis when configured. Because state is outside the process, several backend workers can serve the same conversation and a restart does not lose a half-finished booking."],
    ["p", "The reminder worker runs every five minutes and sends two SMS per booking: one when the appointment is 3 to 24 hours away and one when it is less than 3 hours away, in Urdu script or Roman Urdu depending on how the patient chatted. A (booking, kind) primary key in the reminders table guarantees each reminder is sent once, even with several workers. Providers are pluggable: a log provider for demos, a webhook for a local SMS gateway, and Twilio. The staff page (`/admin`) shows every doctor's slots for a day, patient details, a cancel button and the reminder log, protected by a staff token."],

    ["h2", "5.8 Voice Channel"],
    ["p", "Voice was listed as future work in the proposal and was added as an extension (`backend/voice.py`):"],
    ["ul", [
      "**Speech to text:** faster-whisper (int8 on CPU) with the language forced to Urdu, because when left to detect the language Whisper often writes spoken Urdu in Hindi script. A short Urdu prompt with clinic words and the 16 doctor names nudges spelling.",
      "**Transcript cleanup** so the existing rules still work: Urdu digits to 0-9; spoken digit sequences to numbers; the spoken letters \"M B\" followed by digits to MB-1042; split phone numbers joined; a misheard doctor name snapped to the closest real name; and phrases Whisper invents on silence (\"سبسکرائب\") removed.",
      "**Text to speech:** Meta MMS-TTS for Urdu (`facebook/mms-tts-urd-script_arabic`), offline on CPU, about 0.5 s per sentence. Times, booking numbers and phone numbers are converted to Urdu words first.",
    ]],

    ["h2", "5.9 API"],
    ["table", {
      caption: "Backend API endpoints", widths: [2.6, 3.6], left: true,
      header: ["Endpoint", "Purpose"],
      rows: [
        ["GET /api/health", "NLU engine, database, session store and reminder provider in use"],
        ["POST /api/chat", "One text turn: reply, NLU output, rules fired, dialogue decisions and state"],
        ["POST /api/voice", "One spoken turn (audio upload): transcript, timing, then the same as /api/chat"],
        ["POST /api/tts", "Urdu text to WAV audio"],
        ["POST /api/reset", "Start a new conversation"],
        ["GET /api/doctors, /api/appointments", "Doctor list; appointment list for the demo panel (phones masked when a staff token is set)"],
        ["GET /api/admin/schedule", "Staff: every doctor's slots for one day"],
        ["POST /api/admin/appointments/{ref}/cancel", "Staff: cancel a booking"],
        ["GET, POST /api/admin/reminders[/run]", "Staff: reminder log; send due reminders now"],
        ["POST /api/admin/reset-db", "Rebuild demo data"],
      ],
    }],

    // =====================================================================================================
    ["h1", "Implementation"],
    ["h2", "6.1 Technology Stack"],
    ["table", {
      caption: "Technology used, compared with the proposal", widths: [1.6, 2.2, 2.6],
      header: ["Layer", "Used", "Note"],
      rows: [
        ["Language", "Python 3.10+, TypeScript", "As proposed"],
        ["NLU", "PyTorch, Hugging Face Transformers, XLM-R; scikit-learn and sklearn-crfsuite for the baseline", "As proposed"],
        ["Speech", "faster-whisper (Whisper large-v3-turbo), MMS-TTS", "Extension"],
        ["Backend", "FastAPI, uvicorn", "As proposed"],
        ["Database", "PostgreSQL 16 (SQLite for the demo)", "As proposed"],
        ["Sessions", "Redis 7", "As proposed"],
        ["Frontend", "Next.js (React)", "React, as proposed, through Next.js"],
        ["Messaging", "SMS via webhook or Twilio", "WhatsApp deferred to future work"],
        ["Deployment", "Docker and Docker Compose", "As proposed"],
        ["Annotation", "Template generator with automatic labels, rule audit, hand review", "Replaced Label Studio, since labels are produced with the text"],
        ["Evaluation", "pytest, Locust, llama.cpp, Matplotlib", "As proposed, plus load and LLM tools"],
      ],
    }],

    ["h2", "6.2 Code Organisation"],
    ["table", {
      caption: "Main modules of the repository", widths: [2.3, 0.8, 3.4], left: true,
      header: ["File or folder", "Lines", "Responsibility"],
      rows: [
        ["data_gen/ (schema, templates, lexicons, generate, build_dataset, audit_labels)", "1,456", "Dataset generation, splits and label audit"],
        ["models/train_xlmr.py, predict_xlmr.py, baseline.py", "", "Training and inference for XLM-R and the baseline"],
        ["models/llm_eval.py, local_eval.py", "", "LLM comparison on the same messages"],
        ["backend/dialogue.py", "774", "Dialogue manager"],
        ["backend/nlu.py, routing.py, normalize.py", "730", "NLU engines, rule layer, keyword routing, dates and times"],
        ["backend/clinic_db.py, db.py, sessions.py", "546", "Clinic schedule, bookings, database layer, session stores"],
        ["backend/main.py, replies.py, reminders.py", "592", "API, bot replies in two scripts, reminder worker"],
        ["backend/voice.py, voice_eval.py", "623", "Speech in and out, voice evaluation"],
        ["backend/simulate.py, route_eval.py, emergency_check.py", "286", "Dialogue simulation and targeted evaluations"],
        ["frontend/app/page.tsx, admin/page.tsx", "512", "Patient chat and staff schedule"],
        ["docker-compose.yml, Dockerfiles, loadtest/", "", "Deployment and load test"],
      ],
    }],

    ["h2", "6.3 User Interface"],
    ["p", "The patient interface (Figure 6.1) is a chat window with a microphone button and example messages. For the demonstration, a side panel shows what the system understood for every message: intent and confidence, department, slots, the rules that fired, the dialogue manager's decisions and the dialogue state. A second tab shows the appointments table, with new bookings highlighted. Figure 6.2 shows a spoken turn and Figure 6.3 the staff schedule."],
    ["fig", { file: "results/demo_screens/chat.png", caption: "Patient chat: a booking completed and a cancellation started, with the NLU and dialogue state panel", width: 6.0 }],
    ["fig", { file: "results/demo_screens/voice.png", caption: "A spoken Urdu turn: the Whisper transcript, timing and the reply", width: 6.0 }],
    ["fig", { file: "results/demo_screens/admin.png", caption: "Staff schedule page: each doctor's 20-minute slots, bookings made by the chatbot and cancel buttons", width: 6.0 }],

    ["h2", "6.4 Deployment"],
    ["p", "`docker compose up --build` starts five services (Table 6.3). The backend creates the tables and seeds 16 doctors and six demo bookings on first start. Build options select whether XLM-R and voice are included, so the same files produce a small baseline image or a full image."],
    ["table", {
      caption: "Docker Compose services", widths: [1.2, 1.8, 3.4], left: true,
      header: ["Service", "Image", "Role"],
      rows: [["db", "postgres:16-alpine", "Clinic data in a persistent volume"], ["redis", "redis:7-alpine", "Conversation state"],
        ["backend", "backend/Dockerfile", "FastAPI, NLU, dialogue manager, optional voice"], ["reminders", "same image", "Reminder worker, every 5 minutes"],
        ["frontend", "frontend/Dockerfile", "Next.js server; forwards /api/* to the backend"]],
    }],
    ["p", "For a real clinic the stack should be placed behind HTTPS, only the frontend port published, the secrets changed and the database volume backed up; these steps are documented in `DEPLOY.md`."],

    ["h2", "6.5 Testing"],
    ["p", "The automated test suite (`backend/tests/`) covers date and time parsing, complete dialogues (booking, correction at confirmation, cancellation, rescheduling, Sunday and off-duty handling, emergencies mid-booking, out-of-scope requests), routing regressions such as the Tuesday/swallow bug, voice transcript cleanup, and the deployment layer (database API, reminders, staff routes and token, session stores, and a 30-thread race for one slot). On the final code the suite gives **102 passed and 1 skipped** (the skipped test needs the XLM-R weights, which were not loaded on the test machine). Seven deployment tests also run against PostgreSQL and one against Redis when those servers are available."],

    // =====================================================================================================
    ["h1", "Evaluation and Results"],
    ["p", "This chapter reports every evaluation, from single messages to whole dialogues, voice and load. Unless stated otherwise the numbers are for dataset v2 and come from the result files named in each table."],

    ["h2", "7.1 NLU: Baseline versus XLM-R"],
    ["table", {
      caption: "NLU results on dataset v2", widths: [2.6, 1, 1, 1, 1],
      header: ["Model and test set", "Intent acc", "Intent macro-F1", "Dept acc", "Slot F1"],
      rows: [
        ["Baseline, unseen-template test (1,453)", "0.69", "0.67", "0.94", "0.92"],
        ["**XLM-R, unseen-template test (1,453)**", "**0.96**", "**0.95**", "**1.00**", "**0.95**"],
        ["Baseline, free-form (145)", "0.67", "0.66", "0.93", "0.69"],
        ["**XLM-R, free-form (145)**", "**0.83**", "**0.80**", "0.91", "0.69"],
      ],
      note: "XLM-R is the v2 main run (trained on train, epochs chosen on validation). Department accuracy on unseen templates is 0.995. Sources: results/baseline_v2/scores.json, results/xlmr_v2_main/scores.json.",
    }],
    ["fig", { file: F + "fig_baseline_vs_xlmr.png", caption: "Baseline and XLM-R on the two test sets", width: 6.2 }],
    ["p", "XLM-R improves intent accuracy by 27 points on unseen templates and by 16 points on free-form text. The baseline's character n-grams capture vocabulary but not phrasing, so it confuses intents that share words (booking versus availability versus symptom). On free-form text the two models are level on department and slots: the baseline department classifier benefits from strong keywords, and slot F1 is limited by span-boundary conventions (\"aaj hi\" versus \"aaj\") and by naturally written symptom phrases being longer than template ones."],
    ["fig", { file: F + "fig_by_style.png", caption: "Free-form intent accuracy by writing style", width: 5.6 }],
    ["p", "By writing style (Figure 7.2), Urdu script is the hardest free-form slice for both models (XLM-R 0.79 intent accuracy, 0.65 slot F1), because the templates under-cover natural Urdu-script phrasing. On unseen templates XLM-R stays at or above 0.94 intent accuracy in every style."],
    ["fig", { file: F + "fig_training.png", caption: "Validation scores of XLM-R after each epoch (v2 main run)", width: 5.6 }],
    ["p", "Validation scores were still improving at epoch 5 (Figure 7.3), so both v2 runs use five epochs. The department head learns slowest (0.53 after one epoch) because it is trained only on the routed subset."],

    ["h3", "Ablations and model variants"],
    ["table", {
      caption: "XLM-R variants on the free-form set", widths: [3.4, 0.9, 0.9, 0.9, 0.9],
      header: ["Variant", "Intent acc", "Macro-F1", "Dept acc", "Slot F1"],
      rows: [
        ["v1: department head on all rows, 4 epochs", "0.84", "0.81", "0.86", "0.70"],
        ["v1: department head on routed rows, 5 epochs", "0.82", "0.81", "0.91", "0.72"],
        ["v1: final, trained on train + val, 4 epochs", "0.85", "0.85", "0.86", "0.67"],
        ["**v2: main, train only, 5 epochs (headline)**", "**0.83**", "**0.80**", "**0.91**", "**0.69**"],
        ["v2: final, trained on train + val, 5 epochs", "0.80", "0.77", "0.88", "0.69"],
      ],
      note: "Sources: results/xlmr_v1_dept_all_rows, xlmr_v1, xlmr_final, xlmr_v2_main, xlmr_v2. Differences under about 3 points (4 messages) are within noise.",
    }],
    ["p", "Training the department head only on routed rows raises free-form department accuracy from 0.86 to 0.91. The v1 and v2 models agree within noise on free-form text, as expected, because the free-form labels never had the age slips that v2 fixes; the fix shows on the rows it targets (Section 4.4). We report the v2 main run as the headline, since its epoch count was chosen on held-out validation data."],

    ["h3", "Error analysis"],
    ["ul", [
      "The largest confusion is describe_symptom versus emergency, where some labels are debatable (\"severe but not life-threatening\").",
      "Many describe_symptom versus book_appointment errors come from the labelling convention: \"bukhar hai, doctor dekh le\" is a booking request in our schema, though it reads like a symptom.",
      "Naturally phrased symptoms that no template resembles (\"kandha upar nahi uthta\", *the shoulder will not lift*) are the main source of free-form intent errors.",
    ]],

    ["h2", "7.2 Department Routing with the Keyword Backstop"],
    ["table", {
      caption: "XLM-R department accuracy, model alone and with the keyword and age backstop", widths: [3.2, 1.3, 1.5],
      header: ["Set", "Model only", "Model + keywords"],
      rows: [
        ["Free-form, all (56 routed messages)", "91.1%", "**98.2%**"], ["Free-form, Urdu script (19)", "84.2%", "**94.7%**"],
        ["Free-form, Roman Urdu (25)", "92.0%", "**100%**"], ["Free-form, mixed (12)", "100%", "100%"],
        ["Test templates, clean labels (394)", "99.5%", "**100%**"], ["Validation templates (360)", "100%", "100%"],
      ],
      note: "Source: backend/route_eval.py, DEMO.md. Some free-form failures were seen before the keyword lists were written, so the free-form gain is optimistic; the real-message test (Section 7.8) is the fair check.",
    }],
    ["p", "On free-form messages the keywords changed 4 answers and all 4 were fixes. With the baseline NLU they changed 6, with 5 fixes and 1 new error. The backstop is most useful for Urdu script, the model's weakest style."],

    ["h2", "7.3 Fine-Tuned XLM-R versus Prompted LLMs"],
    ["p", "We tested whether a general instruction-tuned LLM could replace the fine-tuned model. Qwen2.5-3B-Instruct and Qwen2.5-7B-Instruct (4-bit GGUF, run locally with llama.cpp) received the intent definitions, one line of typical complaints per department, the clinic's doctor directory, the slot rules and, in the few-shot setting, 33 labelled training examples. Output was JSON constrained by a grammar at temperature 0 (no invalid replies). Every model parsed exactly the same messages and was scored by the same code on the same 4-core CPU."],
    ["table", {
      caption: "Fine-tuned models versus prompted LLMs on the free-form set (145 messages)", widths: [2.4, 0.9, 0.9, 0.9, 0.9, 1.1],
      header: ["Model", "Intent acc", "Macro-F1", "Dept acc", "Slot F1 (exact)", "Median latency"],
      rows: [
        ["Baseline (TF-IDF + LR, CRF)", "0.66", "0.66", "**0.91**", "**0.69**", "1 ms"],
        ["**XLM-R fine-tuned**", "**0.85**", "**0.85**", "0.86", "0.67", "28 ms"],
        ["Qwen2.5-3B zero-shot", "0.48", "0.55", "0.68", "0.31", "6.5 s"],
        ["Qwen2.5-3B few-shot", "0.66", "0.71", "0.66", "0.46", "5.8 s"],
        ["Qwen2.5-7B few-shot", "0.74", "0.79", "0.80", "0.53", "10.6 s"],
      ],
      note: "XLM-R here is the v1 final model, the weights available on the machine that ran the comparison; on free-form text it is within noise of the v2 models (Table 7.2). Source: results/llm_compare/.",
    }],
    ["table", {
      caption: "Same comparison on a stratified 300-message sample of the unseen-template test", widths: [2.4, 1, 1, 1, 1],
      header: ["Model", "Intent acc", "Macro-F1", "Dept acc", "Slot F1 (exact)"],
      rows: [["Baseline", "0.71", "0.70", "1.00", "0.93"], ["**XLM-R fine-tuned**", "**0.99**", "**0.99**", "**1.00**", "0.90"],
        ["Qwen2.5-3B zero-shot", "0.54", "0.54", "0.57", "0.42"], ["Qwen2.5-3B few-shot", "0.74", "0.71", "0.59", "0.64"], ["Qwen2.5-7B few-shot", "0.77", "0.79", "0.71", "0.77"]],
    }],
    ["fig", { file: F + "fig_llm_compare.png", caption: "Free-form intent accuracy and median latency per message for each model", width: 6.2 }],
    ["p", "**Fine-tuning wins clearly.** The 270M-parameter XLM-R beats the 7B LLM by 11 points of free-form intent accuracy and 22 points on unseen templates, and runs about 400 times faster on the same hardware. On the free-form set 28 messages are right only for XLM-R and 12 only for the LLM; McNemar's test gives p ≈ 0.02, so the difference is significant. Scale and examples matter a great deal for the LLM (0.48 to 0.66 to 0.74 from 3B zero-shot to 3B few-shot to 7B few-shot). Its exact slot F1 is low mainly because it trims or rewrites spans (\"9 baje\" for \"saade 9 baje\", or transliterating a Roman name into Urdu script), and its routing is weakest for Urdu script (0.58 department accuracy on free-form)."],
    ["p", "**Where the LLM wins.** The two models make different mistakes. The LLM gets describe_symptom right 95% of the time on free-form text against 67% for XLM-R, because it understands naturally phrased symptoms no template resembles (\"subah uthte hi chakkar aata hai\", \"کندھا اوپر نہیں اٹھتا\"), and it caught \"my father is having a heart attack please help\", which XLM-R missed. This suggests two cheaper uses of an LLM than putting it in the chat loop: paraphrasing training data to make it more natural, and a fallback called only when XLM-R's confidence is low (Section 8.3)."],
    ["p", "**Cost.** The local runs cost nothing but are far too slow for a chat without a GPU. A projected API cost with the same few-shot prompt, at November 2026 list prices and with prompt caching, is about $0.06 per 1,000 messages for Claude Haiku 5.5 and $1.20 for Claude Sonnet 5.5; these are estimates from Qwen's token counts, not measurements."],

    ["h2", "7.4 Whole Dialogues with Simulated Users"],
    ["p", "`backend/simulate.py` plays a cooperative user with a goal (book 70%, cancel 15%, reschedule 15%) and judges success in the database, not in the bot's words. Each line uses 300 dialogues with seed 7, and both NLU engines use the same dialogue manager. \"Before\" is the dialogue manager without the keyword backstop; \"after\" is the final version."],
    ["table", {
      caption: "Task success in simulated dialogues", widths: [1.7, 0.9, 1, 1, 1, 1, 1],
      header: ["Openers", "NLU", "Success before", "Success after", "Booking before", "Booking after", "Invented booking numbers"],
      rows: [
        ["Free-form", "Baseline", "85.0%", "97.3%", "80.1%", "96.4%", "0"],
        ["Free-form", "**XLM-R**", "94.0%", "**99.7%**", "91.5%", "**99.5%**", "0"],
        ["Test templates", "Baseline", "99.3%", "100%", "99.1%", "100%", "0"],
        ["Test templates", "XLM-R", "98.7%", "100%", "98.0%", "100%", "0"],
      ],
      note: "Template lines leave out the 18 to 21 openers per 300 affected by the v1 adult-pediatrics label bug. Source: results/dialogue_sim/, DEMO.md.",
    }],
    ["p", "The simulated user answers in template language and always cooperates, and free-form openers are drawn with repetition from 145 messages, so these are upper bounds that show the components work together, not a measure of real-patient success. Importantly, in no dialogue did the bot invent a booking number."],

    ["h2", "7.5 Safety: Emergency Detection"],
    ["table", {
      caption: "Emergency detection on held-out messages", widths: [2.2, 1.6, 1.6, 1.6],
      header: ["NLU", "Template emergencies caught", "Free-form emergencies caught", "False alarms (free-form)"],
      rows: [["**XLM-R + rules**", "**37 / 37**", "**8 / 8**", "3.6%"], ["Baseline + rules", "37 / 37", "7 / 8", "0.7%"]],
      note: "False alarms on the 1,414 non-emergency template messages: 0% with XLM-R. Source: backend/emergency_check.py, results/dialogue_sim/emergency_*.json.",
    }],
    ["p", "Every held-out emergency message receives the Rescue 1122 advice with XLM-R. Its false alarms (for example \"khana hazam nahi hota\", *I cannot digest food*) are not dead ends, because a model-only emergency still offers a booking after the advice (Section 5.5). For a clinic agent, a false alarm costs a sentence, while a missed emergency could cost a life, so this trade-off is deliberate."],

    ["h2", "7.6 Voice"],
    ["p", "Speech recognition was evaluated on two sets: **FLEURS** (100 clips of real people reading Urdu news-style sentences, test split) and **synthetic clinic speech** (150 held-out Urdu-script messages from the dataset, covering every intent, spoken by the MMS voice, clean and with room noise at 10 dB SNR). Because the clinic clips are labelled, we also measured whether the NLU, exactly as the dialogue manager uses it, still recovers the intent and department from the transcript. Typed, the same 150 messages score 94.7% intent and 97.9% department accuracy."],
    ["table", {
      caption: "Whisper model sizes (int8, 4-core CPU), clean audio", widths: [2, 1, 0.8, 1, 1, 1, 1, 0.9],
      header: ["Whisper", "FLEURS WER", "FLEURS CER", "Clinic WER", "Intent from voice", "Dept from voice", "Emergencies", "Sec / msg"],
      rows: [
        ["tiny", "65.5%", "30.0%", "61.5%", "61.3%", "40.4%", "11/12", "1.0"],
        ["base", "50.3%", "21.6%", "52.7%", "65.3%", "51.1%", "11/12", "1.2"],
        ["small", "37.2%", "14.7%", "38.4%", "72.7%", "51.1%", "11/12", "3.8"],
        ["medium", "28.2%", "11.1%", "26.7%", "78.0%", "63.8%", "12/12", "5.8"],
        ["**large-v3-turbo**", "**21.4%**", "**7.9%**", "29.4%", "78.0%", "70.2%", "**12/12**", "5.1"],
        ["large-v3-turbo + names (as deployed)", "", "", "29.8%", "**78.7%**", "**76.6%**", "**12/12**", "5.5"],
      ],
      size: 18, note: "Source: results/voice_eval/fleurs.json and synthetic.json.",
    }],
    ["table", {
      caption: "Same clinic clips with room noise at 10 dB SNR", widths: [2.4, 1.2, 1.2, 1.2, 1.2],
      header: ["Whisper", "Clinic WER", "Intent from voice", "Dept from voice", "Emergencies"],
      rows: [["tiny", "86.0%", "32.0%", "21.3%", "9/12"], ["base", "68.0%", "44.7%", "38.3%", "10/12"], ["small", "50.5%", "71.3%", "44.7%", "11/12"], ["large-v3-turbo, as deployed", "41.2%", "74.7%", "59.6%", "12/12"]],
    }],
    ["fig", { file: F + "fig_voice.png", caption: "Word error rate and NLU accuracy from transcripts for each Whisper size (clean audio)", width: 6.2 }],
    ["ul", [
      "**large-v3-turbo is the right default.** On real speech it makes 42% fewer word errors than small and 24% fewer than medium, at about the speed of medium. Tiny and base are not usable for Urdu.",
      "**Emergencies survive voice.** Every spoken emergency triggered the 1122 advice with large-v3-turbo, clean and noisy, because emergency keywords are short, common words Whisper gets right.",
      "**Department routing suffers most** (97.9% typed, 76.6% spoken), usually from one misheard symptom word (پیٹ heard as پیپ). The system stays safe: a weak department goes to the General Physician, and the user sees the transcript and can correct it.",
      "**Prompt and name snapping help.** The clinic prompt lowers small's WER from 41.0% to 38.4%; doctor names and snapping raise department accuracy for large-v3-turbo from 70.2% to 76.6%.",
      "**Synthetic speech is not proof.** The MMS voice is robotic and joins words, so large-v3-turbo does better on real FLEURS voices (21% WER) than on synthetic clips (30%). Real patients will also mix English words into speech, which neither set covers. Recordings from real speakers (Section 7.9) are the honest test.",
    ]],

    ["h2", "7.7 Deployment, Load and Concurrency"],
    ["p", "The Docker stack (one uvicorn worker, PostgreSQL 16, Redis 7) was load-tested with Locust on a 4-CPU cloud machine. Each simulated patient opens a session and plays a whole conversation (booking in Roman Urdu or Urdu script, a symptom, doctor timings, check or cancel by booking number, or an emergency), waiting 1 to 3 seconds between messages. A turn fails on any HTTP error, empty reply, or an emergency without the 1122 advice. After each run the test reads every appointment and fails if any slot is booked twice."],
    ["table", {
      caption: "Load test results (baseline NLU, one worker)", widths: [0.9, 0.9, 0.9, 0.9, 0.9, 0.8, 0.8, 0.8, 0.9, 0.9],
      header: ["Run", "Patients", "Requests", "Failures", "Req/s", "Median", "p95", "p99", "Bookings", "Double-booked"],
      rows: [
        ["u50", "50", "2,948", "0", "25", "7 ms", "18 ms", "50 ms", "132", "0"],
        ["u100", "100", "5,898", "0", "49", "7 ms", "22 ms", "93 ms", "214", "0"],
        ["**u200**", "**200**", "11,807", "**0**", "98", "8 ms", "**39 ms**", "190 ms", "320", "**0**"],
        ["stress*", "200", "15,091", "0", "167", "730 ms", "1.8 s", "2.1 s", "414", "0"],
      ],
      size: 17, note: "*Stress run: 0.1 to 0.5 s between messages, 5 to 10 times faster than people type. Source: loadtest/results/, DEPLOY.md.",
    }],
    ["fig", { file: F + "fig_loadtest.png", caption: "Response time percentiles at 50, 100 and 200 concurrent simulated patients", width: 5.8 }],
    ["p", "Two hundred patients chatting at once are served in under 40 ms for 95% of messages, with no errors; a small clinic receives a few dozen conversations an hour. The stress run finds the limit of one worker at about 170 requests per second, set by Python CPU in the single process, not by the database (PostgreSQL stayed under 15% CPU). Across all four runs 1,080 bookings were made, many racing for the same early slots, and none was double-booked. Separately, the 30-thread race test lets exactly one of 30 simultaneous bookings for one slot succeed, on both SQLite and PostgreSQL."],
    ["p", "The Docker image used for the load test was built without PyTorch, because the test environment blocked the PyTorch download, so these numbers are for the baseline NLU. XLM-R takes about 28 ms per message on CPU against about 5 ms for the baseline, so one worker should serve roughly 25 to 30 messages a second, about 60 to 80 patients at the same pace. This estimate is to be replaced with a measurement (Section 7.10)."],

    ["h2", "7.8 Real Typed Messages"],
    ["p", "The free-form set was not written by patients, so the fairest test of the NLU is messages from real people. `real_test/` contains a collection sheet, a labelling guide and a scoring script. Participants (classmates, friends and family) are asked for 5 to 10 messages each, written \"the way you would actually WhatsApp a clinic\", covering bookings for themselves, a child and an elderly parent, a named doctor, cancel, reschedule, check, clinic information, one emergency, greetings and one off-topic question, with fake names and numbers."],
    ["todo", [
      "Collect 100 to 200 real messages from at least 15 people, label them with `real_test/LABELLING_GUIDE.md`, then run `python real_test/score_real.py real_messages.csv --e2e`.",
      "Fill Table 7.11 from `results/real_v1/`, and replace this box with two or three sentences comparing the result with the free-form numbers in Table 7.1.",
    ]],
    ["table", {
      caption: "Results on real typed messages (to be filled)", widths: [2.6, 1, 1, 1, 1],
      header: ["Model", "Intent acc", "Macro-F1", "Dept acc (model + keywords)", "Slot F1"],
      rows: [["Baseline", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]"], ["XLM-R (v2)", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]"],
        ["XLM-R, Roman Urdu only", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]"], ["XLM-R, Urdu script only", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]"],
        ["XLM-R, mixed only", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]"], ["Simulated chats opened by real messages: task success", "[[ ]]", "", "", ""]],
      note: "Number of messages: [[n]]; number of participants: [[n]].",
    }],

    ["h2", "7.9 Real Voice Recordings"],
    ["p", "`data/voice_recordings/refs.tsv` lists 30 clinic sentences with their intent and department labels, covering every intent, numbers, booking numbers and doctor names. Recordings of these sentences by real speakers on ordinary phones replace the synthetic voice as the honest test of the voice channel."],
    ["todo", [
      "Record the 30 sentences from 5 to 10 people (phone recordings, any format), name the files as in `refs.tsv`, and run `python backend/voice_eval.py --set recordings --dir data/voice_recordings --models large-v3-turbo small`.",
      "Fill Table 7.12 and replace this box with a short comparison against the FLEURS and synthetic results in Table 7.8.",
    ]],
    ["table", {
      caption: "Results on real voice recordings (to be filled)", widths: [2.2, 1, 1, 1, 1, 1],
      header: ["Whisper", "WER", "CER", "Intent from voice", "Dept from voice", "Emergencies"],
      rows: [["large-v3-turbo + names", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]"], ["small + names", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]", "[[ ]]"]],
      note: "Speakers: [[n]]; recordings: [[n]]; devices: [[phones used]].",
    }],

    ["h2", "7.10 Outstanding Measurements"],
    ["todo", [
      "**v2 model weights.** The v2 final weights (`joint_xlmr.pt`, 1.1 GB) were trained but never copied out of the training environment (Colab). Export them, split them with `scripts/split_weights.sh results/xlmr_v2/model/joint_xlmr.pt` and commit the parts, so the deployed system uses v2 instead of the v1 final model.",
      "**LLM comparison with v2.** Once the v2 weights are available, run `python models/local_eval.py --out results/llm_compare` and update the XLM-R row of Tables 7.4 and 7.5 (currently the v1 final model).",
      "**Load test with XLM-R.** Build the image with `WITH_XLMR=1` and rerun the u200 load test (Section 7.7); add the row to Table 7.10 and replace the estimate in the text.",
    ]],

    ["h2", "7.11 Requirements Traceability"],
    ["table", {
      caption: "Summary of results against the requirements", widths: [2.4, 4], left: true,
      header: ["Requirement", "Evidence"],
      rows: [
        ["Understand code-switched input (FR1, FR2)", "0.96 / 0.83 intent accuracy on unseen templates / free-form; at least 0.94 in every style on unseen templates"],
        ["Department routing with fallback (FR3)", "1.00 on unseen templates; 98.2% on free-form with the backstop; GP below 0.40 confidence"],
        ["Multi-turn dialogue and booking (FR4 to FR6)", "99.7% simulated task success with free-form openers; 0 invented booking numbers"],
        ["Reminders (FR7)", "Two SMS per booking, sent exactly once; tested in test_deploy.py"],
        ["Emergencies (FR8)", "45 / 45 held-out emergency messages caught with XLM-R; 12 / 12 spoken"],
        ["Voice (FR9)", "21.4% WER on real Urdu speech; 78.7% intent from synthetic speech"],
        ["No double booking", "0 of 1,080 load-test bookings; 1 of 30 racing threads succeeds"],
        ["Performance and scalability", "p95 39 ms at 200 concurrent patients (baseline NLU); XLM-R 28 ms per message"],
      ],
    }],

    // =====================================================================================================
    ["h1", "Conclusion and Future Work"],
    ["h2", "8.1 Conclusion"],
    ["p", "MedBook shows that a clinic booking agent can understand patients in the way they actually write, in Urdu script, Roman Urdu, English or a mix, and complete a real, verified booking. Building a labelled dataset from templates, with test splits that hold out whole templates and a separate free-form set, made it possible to train a joint XLM-R model with no real patient data, and gave an honest picture of where it generalises: 0.96 intent accuracy on unseen templates and 0.83 on free-form text, against 0.67 for a strong classical baseline. A careful label audit found and fixed errors that would otherwise have taught the model to send adults to pediatrics."],
    ["p", "A key finding is that, for a narrow task with a defined label set, a fine-tuned 270M-parameter encoder is both more accurate and about 400 times faster than a prompted 7B LLM on the same hardware. The LLM's strength, understanding natural symptom descriptions, is better used offline to enrich training data than in the chat loop."],
    ["p", "The design choice to combine a learned model with explicit rules was essential. Rules make emergency handling reliable, make routing transparent and correctable, and guarantee the properties a clinic cares about most: no invented slots or booking numbers, nothing written without the patient's confirmation, and no double bookings even under heavy concurrent load. The system is deployable with one command and adds a working Urdu voice channel that was beyond the original scope."],

    ["h2", "8.2 Limitations"],
    ["ul", [
      "**Training data is synthetic.** Templates under-cover natural phrasing, especially in Urdu script, and the free-form test set was written with AI assistance, not by patients. Results on real messages (Section 7.8) are the true measure.",
      "**Voice was evaluated on read and synthetic speech.** Real patients speak spontaneously, with English words and background noise.",
      "**Symptom-to-department mappings have not been reviewed by a doctor.** They are a scheduling aid, not medical triage.",
      "**One clinic, fixed shifts.** Multi-branch clinics, variable slot lengths and doctor leave are not modelled.",
      "**Shared staff token.** The staff page uses one shared password rather than per-user accounts.",
      "**Simulated users are cooperative.** Task success from simulation is an upper bound.",
    ]],

    ["h2", "8.3 Future Work"],
    ["ul", [
      "**WhatsApp channel** through the WhatsApp Business API or Twilio, reusing the same dialogue manager; reminders can use the same provider interface.",
      "**LLM paraphrase augmentation:** use an LLM to reword training rows into natural phrasing (`data_gen/paraphrase.py` is ready) and retrain XLM-R, keeping its 28 ms runtime.",
      "**LLM fallback** called only when XLM-R's intent confidence is low, to combine the encoder's speed with the LLM's understanding of unusual phrasing.",
      "**Pre-training on MASSIVE Urdu** before MedBook fine-tuning, and training on the real messages once enough are collected (with a fresh held-out set).",
      "**Roman-Urdu speech:** a TTS voice for Roman-Urdu replies, and fine-tuning Whisper on recorded clinic speech.",
      "**Clinical review** of the symptom lexicon by a doctor, and a pilot with a real clinic's reception staff.",
      "**Production hardening:** HTTPS, per-user staff accounts, audit logs and backups.",
    ]],

    // =====================================================================================================
    ["h1u", "References"],
    ["ref", [
      "A. Conneau, K. Khandelwal, N. Goyal, V. Chaudhary, G. Wenzek, F. Guzmán, E. Grave, M. Ott, L. Zettlemoyer and V. Stoyanov, \"Unsupervised cross-lingual representation learning at scale,\" in *Proc. 58th Annual Meeting of the ACL*, 2020, pp. 8440-8451.",
      "J. Devlin, M.-W. Chang, K. Lee and K. Toutanova, \"BERT: Pre-training of deep bidirectional transformers for language understanding,\" in *Proc. NAACL-HLT*, 2019, pp. 4171-4186.",
      "A. Radford, J. W. Kim, T. Xu, G. Brockman, C. McLeavey and I. Sutskever, \"Robust speech recognition via large-scale weak supervision,\" in *Proc. 40th Int. Conf. on Machine Learning (ICML)*, 2023.",
      "V. Pratap et al., \"Scaling speech technology to 1,000+ languages,\" *Journal of Machine Learning Research*, vol. 25, 2024.",
      "A. Conneau, M. Ma, S. Khanuja, Y. Zhang, V. Axelrod, S. Dalmia, J. Riesa, C. Rivera and A. Bapna, \"FLEURS: Few-shot learning evaluation of universal representations of speech,\" in *Proc. IEEE Spoken Language Technology Workshop (SLT)*, 2022.",
      "J. FitzGerald et al., \"MASSIVE: A 1M-example multilingual natural language understanding dataset with 51 typologically-diverse languages,\" in *Proc. 61st Annual Meeting of the ACL*, 2023.",
      "Q. Chen, Z. Zhuo and W. Wang, \"BERT for joint intent classification and slot filling,\" arXiv:1902.10909, 2019.",
      "B. Liu and I. Lane, \"Attention-based recurrent neural network models for joint intent detection and slot filling,\" in *Proc. Interspeech*, 2016.",
      "C.-W. Goo, G. Gao, Y.-K. Hsu, C.-L. Huo, T.-C. Chen, K.-W. Hsu and Y.-N. Chen, \"Slot-gated modeling for joint slot filling and intent prediction,\" in *Proc. NAACL-HLT*, 2018.",
      "C. T. Hemphill, J. J. Godfrey and G. R. Doddington, \"The ATIS spoken language systems pilot corpus,\" in *Proc. DARPA Speech and Natural Language Workshop*, 1990.",
      "A. Coucke et al., \"Snips Voice Platform: An embedded spoken language understanding system for private-by-design voice interfaces,\" arXiv:1805.10190, 2018.",
      "S. Larson et al., \"An evaluation dataset for intent classification and out-of-scope prediction,\" in *Proc. EMNLP-IJCNLP*, 2019.",
      "P. Budzianowski, T.-H. Wen, B.-H. Tseng, I. Casanueva, S. Ultes, O. Ramadan and M. Gašić, \"MultiWOZ: A large-scale multi-domain Wizard-of-Oz dataset for task-oriented dialogue modelling,\" in *Proc. EMNLP*, 2018.",
      "S. Young, M. Gašić, B. Thomson and J. D. Williams, \"POMDP-based statistical spoken dialog systems: A review,\" *Proceedings of the IEEE*, vol. 101, no. 5, pp. 1160-1179, 2013.",
      "J. D. Williams, A. Raux and M. Henderson, \"The dialog state tracking challenge series: A review,\" *Dialogue & Discourse*, vol. 7, no. 3, pp. 4-33, 2016.",
      "T. Bocklisch, J. Faulkner, N. Pawlowski and A. Nichol, \"Rasa: Open source language understanding and dialogue management,\" arXiv:1712.05181, 2017.",
      "S. Khanuja, S. Dandapat, A. Srinivasan, S. Sitaram and M. Choudhury, \"GLUECoS: An evaluation benchmark for code-switched NLP,\" in *Proc. 58th Annual Meeting of the ACL*, 2020.",
      "G. Aguilar, S. Kar and T. Solorio, \"LinCE: A centralized benchmark for linguistic code-switching evaluation,\" in *Proc. LREC*, 2020.",
      "S. Sitaram, K. R. Chandu, S. K. Rallabandi and A. W. Black, \"A survey of code-switched speech and language processing,\" arXiv:1904.00784, 2019.",
      "A. Daud, W. Khan and D. Che, \"Urdu language processing: A survey,\" *Artificial Intelligence Review*, vol. 47, no. 3, pp. 279-311, 2017.",
      "J. Lafferty, A. McCallum and F. Pereira, \"Conditional random fields: Probabilistic models for segmenting and labeling sequence data,\" in *Proc. 18th ICML*, 2001.",
      "L. A. Ramshaw and M. P. Marcus, \"Text chunking using transformation-based learning,\" in *Proc. 3rd Workshop on Very Large Corpora*, 1995.",
      "Q. McNemar, \"Note on the sampling error of the difference between correlated proportions or percentages,\" *Psychometrika*, vol. 12, no. 2, pp. 153-157, 1947.",
      "Qwen Team, \"Qwen2.5 technical report,\" arXiv:2412.15115, 2024.",
      "T. Brown et al., \"Language models are few-shot learners,\" in *Advances in Neural Information Processing Systems 33*, 2020.",
      "A. Vaswani, N. Shazeer, N. Parmar, J. Uszkoreit, L. Jones, A. N. Gomez, Ł. Kaiser and I. Polosukhin, \"Attention is all you need,\" in *Advances in Neural Information Processing Systems 30*, 2017.",
      "L. Laranjo et al., \"Conversational agents in healthcare: A systematic review,\" *Journal of the American Medical Informatics Association*, vol. 25, no. 9, pp. 1248-1258, 2018.",
      "T. Wolf et al., \"Transformers: State-of-the-art natural language processing,\" in *Proc. EMNLP: System Demonstrations*, 2020.",
      "A. Paszke et al., \"PyTorch: An imperative style, high-performance deep learning library,\" in *Advances in Neural Information Processing Systems 32*, 2019.",
      "F. Pedregosa et al., \"Scikit-learn: Machine learning in Python,\" *Journal of Machine Learning Research*, vol. 12, pp. 2825-2830, 2011.",
      "I. Loshchilov and F. Hutter, \"Decoupled weight decay regularization,\" in *Proc. ICLR*, 2019.",
      "T. Kudo and J. Richardson, \"SentencePiece: A simple and language independent subword tokenizer and detokenizer for neural text processing,\" in *Proc. EMNLP: System Demonstrations*, 2018.",
      "G. Gerganov et al., \"llama.cpp: LLM inference in C/C++,\" GitHub repository, https://github.com/ggml-org/llama.cpp.",
    ]],

    // =====================================================================================================
    ["h1u", "Appendix A: Example Dialogues"],
    ["p", "**A.1 Generated training dialogue (from dataset v2).** Labels in brackets are the user's intent or the system action."],
    ["code", "user:   salam, koi hai?                                  [greet]\nsystem: Walaikum salam! Main MedBook hoon, kaise madad karun?\nuser:   mujhe 1 tareekh 4 baje ke baad Dr. Shazia Kanwal se\n        appointment chahiye                              [book_appointment]\nsystem: Patient ka naam bata dein.                       [ask PATIENT_NAME]\nuser:   Zainab                                           [inform]\nsystem: Apna mobile number bata dein.                    [ask PHONE]\nuser:   mera number 0333 7654321                         [inform]\nsystem: (summary: doctor, date, time, name, phone)\n        Confirm kar doon?\nuser:   g                                                [confirm]\nsystem: Ho gaya! Aapka booking number MB-8941 hai.       [done]"],
    ["p", "**A.2 Demonstration script** used at the mid evaluation (run against the live system):"],
    ["ol", [
      "`salam, mujhe kal skin specialist ko dikhana hai` then `subah`, `2`, `Ali Raza`, `0300-1234567`, `ji haan`: the booking appears in the appointments tab with its MB number.",
      "`mere bete ko 3 din se bukhar hai`: routed to pediatrics from the symptom and the word \"bete\".",
      "An Urdu-script booking with a correction at the confirmation step (\"نہیں، پرسوں کر دیں\", *no, make it the day after tomorrow*).",
      "`MB-1042 cancel karni hai`, then rescheduling MB-7781 to next Monday morning.",
      "`Dr Kamran kab baithte hain?`: answered from the duty table with the next free slot.",
      "`abbu behosh ho gaye hain` in the middle of a booking: the task is dropped and the user is sent to Rescue 1122.",
      "A request for a Sunday: the bot says the clinic is closed and offers real alternatives.",
    ]],

    ["h1u", "Appendix B: Reproducing the Results"],
    ["p", "All code, data and result files are in the project repository (github.com/bilalafzal6349/medbook). The main commands are:"],
    ["code", "# dataset and audit\ncd data_gen && python build_dataset.py --out ../data/dataset_v2 && python audit_labels.py ../data/dataset_v2\n# baseline and XLM-R\ncd ../models && python baseline.py --data ../data/dataset_v2 --out ../results/baseline_v2\npython train_xlmr.py --data ../data/dataset_v2 --out ../results/xlmr_v2_main --epochs 5 --no_save\npython train_xlmr.py --data ../data/dataset_v2 --out ../results/xlmr_v2 --epochs 5 --train_on_val\n# system tests and evaluations\ncd ../backend && python -m pytest -q\npython simulate.py --n 300 --freeform && python route_eval.py && python emergency_check.py\npython voice_eval.py --set synthetic --models large-v3-turbo small --doctors\n# full stack and load test\ncd .. && docker compose up --build -d\ncd loadtest && locust -f locustfile.py --host http://localhost:8000 --headless -u 200 -r 20 -t 2m\n# report figures and this document\npython docs/report_figures/make_figures.py && node docs/report_src/build_report.js"],

    ["h1u", "Appendix C: Labelling Guide Summary for Real Messages"],
    ["p", "When a message does two things, the intent is the first rule that fits: emergency, then cancel / reschedule / check, then book, then doctor_availability, then describe_symptom, then clinic_info, then the rest. Any sign of danger (unconscious, cannot breathe, heavy bleeding, severe or sudden chest pain, stroke signs, poisoning, seizure, accident, self-harm) is labelled emergency; when in doubt, emergency. Slots are marked in a copy of the text as `[value](SLOT)`, and the scoring script checks that the labelled text equals the original text plus brackets, so a typo while labelling cannot silently change a test message. Real messages are used only for testing, never for training. The full guide is `real_test/LABELLING_GUIDE.md`."],
  ],
};
