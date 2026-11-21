# Dataset v1 samples

| split | text | intent | department | script | slots |
|---|---|---|---|---|---|
| train | hello، MB-0930 کا time دوپہر دو بجے کر دیں please | reschedule_appointment | none | mixed | APPOINTMENT_ID=MB-0930; TIME=دوپہر دو بجے |
| train | غلام رسول، age چھ مہینے | inform | none | mixed | PATIENT_NAME=غلام رسول; AGE=چھ مہینے |
| train | patient ka naam Sadia hai aur umar 35 years | inform | none | roman | PATIENT_NAME=Sadia; AGE=35 years |
| train | مجھے چکر ہے، please appointment دے دیں | book_appointment | general_physician | mixed | SYMPTOM=چکر |
| train | which days does Farhan Butt sahab sit? | doctor_availability | gastroenterology | roman | DOCTOR=Farhan Butt sahab |
| train | tomorrow کو please | inform | none | mixed | DATE=tomorrow |
| train | پچھلے مہینے سے ٹانسلز کا مسئلہ ہے | describe_symptom | ent | urdu | SYMPTOM=ٹانسلز |
| train | السلام علیکم، ہاں جی | confirm | none | urdu | - |
| train | تھکاوٹ ہے | inform | none | urdu | SYMPTOM=تھکاوٹ |
| train | slot book karna hai teen din baad, number 03004445566 | book_appointment | none | roman | DATE=teen din baad; PHONE=03004445566 |
| train | patient کا نام Muhammad Usman ہے | inform | none | mixed | PATIENT_NAME=Muhammad Usman |
| train | mere bete ko saans mein khar khar hai, itwaar appointment mil sakti hai? | book_appointment | pediatrics | roman | SYMPTOM=saans mein khar khar; DATE=itwaar |
| train | ایڑی میں درد کے لیے کس ماہر کے پاس جاؤں؟ | describe_symptom | orthopedics | urdu | SYMPTOM=ایڑی میں درد |
| train | hum nai aa sakenge Monday cancel kr dein | cancel_appointment | none | roman | DATE=Monday |
| train | subah 10 baje ke baad koi bhi time | inform | none | roman | TIME=subah 10 baje |
| test | میری اگلے مہینے والی اپائنٹمنٹ منسوخ کر دیں مہربانی | cancel_appointment | none | urdu | DATE=اگلے مہینے |
| test | MB-1042 cancel karni hai | cancel_appointment | none | roman | APPOINTMENT_ID=MB-1042 |
| test | hassan raza, umar 3 saal | inform | none | roman | PATIENT_NAME=hassan raza; AGE=3 saal |
| test | done kar dein | confirm | none | roman | - |
| test | جی بالکل | confirm | none | urdu | - |
| test | Dr. Farhan Butt | inform | none | roman | DOCTOR=Dr. Farhan Butt |
| test | مجھے بخار ہے، کس ڈاکٹر کو دکھاؤں؟ | describe_symptom | general_physician | urdu | SYMPTOM=بخار |
| test | AoA lady doctor ki checkup fee kitni hai? | clinic_info | none | roman | DEPARTMENT=lady doctor |
| test | meri booking ka time badal dein, last slot better hai | reschedule_appointment | none | roman | TIME=last slot |
| test | سر میری سوموار والی اپائنٹمنٹ منسوخ کر دیں مہربانی | cancel_appointment | none | urdu | DATE=سوموار |
| test | pediatrician ki checkup fee kitni he? | clinic_info | none | roman | DEPARTMENT=pediatrician |
| test | meri booking ka time badal dein, morning better hai | reschedule_appointment | none | roman | TIME=morning |
| test | booking number MB-0087 ہے | inform | none | mixed | APPOINTMENT_ID=MB-0087 |
| test | ammi ko knee pain rehta hai | describe_symptom | orthopedics | roman | SYMPTOM=knee pain |
| test | book an appt for usman tariq with dr ahmed raza jaldi bata dein | book_appointment | cardiology | roman | PATIENT_NAME=usman tariq; DOCTOR=dr ahmed raza |

## Example dialogue

- **user:** salam, koi hai? `[greet]`
- **system:** Walaikum salam! Main MedBook hoon, kaise madad karun? `[greet]`
- **user:** mujhe 1 tareekh 4 baje ke baad Dr. Shazia Kanwal se appointment chahiye `[book_appointment]`
- **system:** Patient ka naam bata dein. `[ask_PATIENT_NAME]`
- **user:** Zainab `[inform]`
- **system:** Apna mobile number bata dein. `[ask_PHONE]`
- **user:** mera number 0333 7654321 `[inform]`
- **system:** DATE: 1 tareekh, TIME: 4 baje ke baad, DOCTOR: Dr. Shazia Kanwal, DEPARTMENT: cardiology, PATIENT_NAME: Zainab, PHONE: 0333 7654321. Confirm kar doon? `[confirm]`
- **user:** g `[confirm]`
- **system:** Ho gaya! Aapka booking number MB-8941 hai. `[done]`
