# Dataset v2 samples

| split | text | intent | department | script | slots |
|---|---|---|---|---|---|
| train | MB-1206 کا time شام پانچ بجے کر دیں please plz | reschedule_appointment | none | mixed | APPOINTMENT_ID=MB-1206; TIME=شام پانچ بجے |
| train | ثنا خان، age پانچ سال | inform | none | mixed | PATIENT_NAME=ثنا خان; AGE=پانچ سال |
| train | patient ka naam Kashif Ali hai aur umar 15 saal | inform | none | roman | PATIENT_NAME=Kashif Ali; AGE=15 saal |
| train | مجھے سینے پر بوجھ ہے، please appointment دے دیں | book_appointment | cardiology | mixed | SYMPTOM=سینے پر بوجھ |
| train | which days does Dr. Adeel Qureshi sit? | doctor_availability | orthopedics | roman | DOCTOR=Dr. Adeel Qureshi |
| train | آج کو please | inform | none | mixed | DATE=آج |
| train | جی پچھلے مہینے سے معدے میں جلن کا مسئلہ ہے | describe_symptom | gastroenterology | urdu | SYMPTOM=معدے میں جلن |
| train | ok ٹھیک ہے | confirm | none | mixed | - |
| train | قبض ہے | inform | none | urdu | SYMPTOM=قبض |
| train | slot book karna hai day after tomorrow, number 0312-5556677 | book_appointment | none | roman | DATE=day after tomorrow; PHONE=0312-5556677 |
| train | patient کا نام اسد محمود ہے | inform | none | mixed | PATIENT_NAME=اسد محمود |
| train | mere bete ko saans mein khar khar hai, itwaar appointment mil sakti hai? | book_appointment | pediatrics | roman | SYMPTOM=saans mein khar khar; DATE=itwaar |
| train | سر جلد پر دانے کے لیے کس ماہر کے پاس جاؤں؟ | describe_symptom | dermatology | urdu | SYMPTOM=جلد پر دانے |
| train | hum nahi aa sakenge Wednesday, cancel kar dein | cancel_appointment | none | roman | DATE=Wednesday |
| train | shaam 6 se 7 ke beech ke baad koi bhi time | inform | none | roman | TIME=shaam 6 se 7 ke beech |
| test | میری جمعرات والی اپائنٹمنٹ منسوخ کر دیں | cancel_appointment | none | urdu | DATE=جمعرات |
| test | mb-0930 cancel karni he | cancel_appointment | none | roman | APPOINTMENT_ID=mb-0930 |
| test | mehwish umar 60 saal | inform | none | roman | PATIENT_NAME=mehwish; AGE=60 saal |
| test | done kar dein jaldi bata dein | confirm | none | roman | - |
| test | جی بالکل | confirm | none | urdu | - |
| test | Dr Tariq | inform | none | roman | DOCTOR=Dr Tariq |
| test | مجھے جلد پر دھبے ہے، کس ڈاکٹر کو دکھاؤں؟ | describe_symptom | dermatology | urdu | SYMPTOM=جلد پر دھبے |
| test | excuse me, gastro ki checkup fee kitni hai? | clinic_info | none | roman | DEPARTMENT=gastro |
| test | meri booking ka time badal dain dopahar 2 bjy btter h please | reschedule_appointment | none | roman | TIME=dopahar 2 bjy |
| test | میری اٹھائیس تاریخ والی اپائنٹمنٹ منسوخ کر دیں | cancel_appointment | none | urdu | DATE=اٹھائیس تاریخ |
| test | ji skin specialist ki checkup fee kitni hai? | clinic_info | none | roman | DEPARTMENT=skin specialist |
| test | meri booking ka time badal dein, last slot better hai | reschedule_appointment | none | roman | TIME=last slot |
| test | booking number MB 6610 ہے | inform | none | mixed | APPOINTMENT_ID=MB 6610 |
| test | AoA ammi ko dil ghabrata hai rehta hai | describe_symptom | cardiology | roman | SYMPTOM=dil ghabrata hai |
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
