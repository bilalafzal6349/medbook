# MedBook: deployment

Everything the proposal lists for deployment: PostgreSQL storage, Redis session state, Docker, automated
appointment reminders, a staff view of the schedule, and a load test. SQLite and in-memory sessions are still the
default when no server is configured, so the tests and the laptop demo in [`DEMO.md`](DEMO.md) work as before.

```
                       ┌──────────────┐  /api/*   ┌────────────────────────────┐
 patient browser ────▶ │  frontend    │ ────────▶ │ backend (FastAPI, uvicorn) │──▶ NLU: XLM-R or baseline
 staff browser  ─/admin│  Next.js     │           │ dialogue manager           │
                       └──────────────┘           └───────┬─────────────┬──────┘
                                                          │             │
                                       sessions (pickled, │             │ departments, doctors, duty,
                                       30 min idle TTL)   ▼             ▼ appointments, reminders
                                                   ┌────────┐     ┌────────────┐
                                                   │ Redis  │     │ PostgreSQL │◀── reminders worker
                                                   └────────┘     └────────────┘    (every 5 min, SMS)
```

## 1. Run the whole stack with Docker

```bash
cd medbook
cp .env.example .env          # change POSTGRES_PASSWORD and MEDBOOK_ADMIN_TOKEN
docker compose up --build -d
docker compose ps             # db, redis, backend, reminders, frontend all "healthy" / "running"
```

| URL | What |
| --- | --- |
| http://localhost:3000 | Patient chat (same UI as the demo) |
| http://localhost:3000/admin | Staff schedule: every doctor's slots for a day, patient details, cancel, reminder log. Enter `MEDBOOK_ADMIN_TOKEN` in the token box |
| http://localhost:8000/docs | API (Swagger) |
| http://localhost:8000/api/health | Shows the NLU engine, `"db": "postgresql://db:5432/medbook"` and `"sessions": "redis://redis:6379/0"` |

Services in `docker-compose.yml`:

| Service | Image | Notes |
| --- | --- | --- |
| `db` | postgres:16-alpine | Data in the `pgdata` volume. The backend creates the tables and seeds 16 doctors and 6 demo bookings on first start |
| `redis` | redis:7-alpine | Conversation state. A backend restart no longer loses a half-finished booking |
| `backend` | `backend/Dockerfile` | Built from `medbook/` because it needs `data_gen/`, `models/`, `data/dataset_v1/` and `results/*/model` |
| `reminders` | same image | `python reminders.py --loop`, every `MEDBOOK_REMINDER_EVERY` seconds |
| `frontend` | `frontend/Dockerfile` | Next.js standalone server. Forwards `/api/*` to `http://backend:8000` |

**Build options** (in `.env`):
- `WITH_XLMR=1` (default) installs CPU-only torch and transformers, so the trained XLM-R model in
  `results/xlmr_final/model` is used. The first start downloads the `xlm-roberta-base` config from Hugging Face into the
  `hfcache` volume (needs internet once). `WITH_XLMR=0` with `MEDBOOK_NLU=baseline` gives a smaller image with the
  TF-IDF/CRF baseline.
- `WITH_VOICE=1` adds faster-whisper and soundfile for `/api/voice` and spoken replies (`/api/tts`, which also needs `WITH_XLMR=1` for torch). Whisper and TTS weights are cached in the same `hfcache` volume; `MEDBOOK_VOICE_PRELOAD=1` loads them at start-up. The default Whisper model is `large-v3-turbo` (best on real Urdu speech, about 1.6 GB download and 1.5 GB RAM); set `MEDBOOK_WHISPER=small` on small machines.
- `WEB_CONCURRENCY` sets the number of uvicorn workers. Sessions live in Redis, so 2 or more workers are safe, but each one
  loads its own copy of the model (about 1 GB RAM with XLM-R).

Useful commands:

```bash
docker compose logs -f backend reminders
docker compose exec backend python clinic_db.py --reset          # rebuild demo data in PostgreSQL
docker compose exec db psql -U medbook -c "select ref, day, start_min, patient_name, status from appointments"
docker compose down            # keep data;  docker compose down -v  also deletes the database volume
```

## 2. Run without Docker (PostgreSQL and Redis installed locally)

```bash
cd medbook/backend
pip install -r requirements.txt
export DATABASE_URL=postgresql://medbook:medbook@localhost:5432/medbook   # unset = SQLite file data/clinic.db
export REDIS_URL=redis://localhost:6379/0                                # unset = sessions in memory
export MEDBOOK_ADMIN_TOKEN=some-secret                                   # unset = staff routes open (laptop demo)
uvicorn main:app --port 8000
python reminders.py --loop        # in a second terminal
```

On Windows use `set NAME=value` instead of `export`.

## 3. What changed in the code

| File | What it does |
| --- | --- |
| `backend/db.py` | One database layer for both engines. SQL is written once with `?`, rows come back as dicts. PostgreSQL uses a connection pool (`MEDBOOK_DB_POOL`, default 10); SQLite uses one connection behind a lock |
| `backend/clinic_db.py` | Same API as before, now on `db.py`. Proper `DATE` / `TIMESTAMP` columns in PostgreSQL, indexes on day and phone, a `lang` column (so reminders go out in the patient's script) and the `reminders` table. `Clinic.reset()` and `Clinic.day_schedule()` are new |
| `backend/sessions.py` | `MemoryStore` (default) or `RedisStore` when `REDIS_URL` is set. Each turn loads the State, runs, saves it with a 30-minute idle timeout (`MEDBOOK_SESSION_TTL`) |
| `backend/reminders.py` | The reminder job and its providers |
| `backend/main.py` | Staff routes under `/api/admin/*`, token check, phone masking, health shows db / sessions / reminder provider |
| `frontend/app/admin/` | Staff schedule page |
| `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `.env.example`, `.dockerignore` | Containers |
| `loadtest/locustfile.py` | Load test |
| `backend/tests/test_deploy.py` | 13 new tests: 7 also run against PostgreSQL and 1 needs Redis, when those are available (20 in total then) (the 71 original tests are unchanged and pass) |

### No double booking under concurrent access

The proposal's reliability requirement is "zero double-bookings under concurrent access, enforced through transactional,
row-level database locking". `Clinic.book` and `Clinic.reschedule` now do the availability check and the insert in one
transaction, after `SELECT ... FROM doctors WHERE id = ? FOR UPDATE`. Two patients confirming slots with the same doctor
queue on that row lock, and the second one sees the first booking when it re-checks. The partial unique index on
(doctor, day, time) for booked rows stays as a second guard. In SQLite (`BEGIN IMMEDIATE`) the whole database is the lock.

`test_no_double_booking_under_concurrency` starts 30 threads that book the same slot at the same instant (released by a
barrier). Exactly one succeeds, on SQLite and on PostgreSQL. The load test below checks the same thing over HTTP.

### Staff view and privacy

`/admin` shows every doctor on duty for the chosen day with each 20-minute slot (free, booked with patient name, phone,
booking number and reason, or past), a cancel button, cancelled bookings, and the reminder log with a "send due
reminders now" button. It refreshes every 30 seconds.

When `MEDBOOK_ADMIN_TOKEN` is set, every `/api/admin/*` route needs the `X-Admin-Token` header (401 otherwise), and the
public `/api/appointments` list used by the demo side panel masks phone numbers (`0300*****67`). Without the token
(laptop demo) everything is open, as before.

| Route | |
| --- | --- |
| `GET /api/admin/schedule?day=2026-11-24` | Doctors on duty, slots with state and appointment, totals |
| `POST /api/admin/appointments/MB-1042/cancel` | Cancel as staff |
| `GET /api/admin/reminders` | Provider, reminders due now, last 50 sent |
| `POST /api/admin/reminders/run` | Send due reminders immediately |
| `POST /api/admin/reset-db` | Rebuild demo data (works on PostgreSQL too) |

### Reminders

Two SMS per booking, in Urdu script or Roman Urdu depending on how the patient chatted:

- `day_before` when the appointment is 3 to 24 hours away,
- `same_day` when it is less than 3 hours away.

> MedBook yaad-dihani: Ali Raza, aap ki appointment Dr. Ahmed Raza ke saath Monday, 23 November ko 11:00 AM baje hai
> (booking MB-1042). Cancel ya change karne ke liye MedBook chat par booking number bata dein.

Before sending, the worker inserts a `(ref, kind)` row into `reminders` (primary key), so each reminder goes out once even
with several workers or a restart. A reschedule deletes the booking's reminder rows so the new time gets fresh ones,
cancelled bookings get none, and a failed send is stored with the error and shown on the staff page.

| `MEDBOOK_REMINDER_PROVIDER` | Settings | Sends |
| --- | --- | --- |
| `log` (default) | none | Prints the SMS in the worker log and stores it (good for the demo and the viva) |
| `webhook` | `MEDBOOK_SMS_WEBHOOK` | POST `{"to": "+923001234567", "message", "ref", "kind"}` as JSON, for a local SMS gateway (for example a Jazz/Telenor bulk-SMS API behind a small adapter, or an Android SMS-gateway app) |
| `twilio` | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` | Twilio Programmable SMS |

Adding another channel (email, WhatsApp) is one class with a `send(to, message, **meta)` method in `reminders.py`.

To show reminders in a demo without waiting a day, fake the clock for one run:
`docker compose exec -e MEDBOOK_NOW=2026-11-22T12:00 reminders python reminders.py --once`.

## 4. Tests

```bash
cd medbook/backend
python -m pytest -q        # everything on SQLite + in-memory sessions (no servers needed)

# The same deployment tests also against PostgreSQL and Redis:
docker compose up -d db redis     # or local servers
MEDBOOK_TEST_PG_URL=postgresql://medbook:medbook@localhost:5432/medbook \
MEDBOOK_TEST_REDIS_URL=redis://localhost:6379/15 python -m pytest -q tests/test_deploy.py
```

The PostgreSQL tests call `Clinic.reset()`, so point `MEDBOOK_TEST_PG_URL` at a test database, not at real data.

## 5. Load test

`loadtest/locustfile.py` simulates patients with [Locust](https://locust.io). Each one opens a new session and plays a
whole conversation: booking in Roman Urdu (7 turns) or Urdu script (6 turns), a symptom, doctor timings or fees, check or
cancel by booking number, or an emergency message. A patient waits 1 to 3 seconds between messages. A turn fails on any
HTTP error, an empty reply, or an emergency message without the 1122 advice. When the run ends, the test reads every
appointment and fails if any doctor has two booked appointments in one slot.

```bash
cd medbook/loadtest
pip install locust
MEDBOOK_ADMIN_TOKEN=... locust -f locustfile.py --host http://localhost:8000 --headless -u 100 -r 20 -t 2m \
       --csv results/u100 --html results/u100.html
```

**Results** (Docker stack from section 1: one uvicorn worker, PostgreSQL 16, Redis 7; 4-CPU cloud VM with Locust on the
same machine; database reset before each run; 21 Nov 2026). The image was built with `WITH_XLMR=0`, so this is the
**baseline NLU**. The sandbox used for the run blocks the PyTorch download site, so XLM-R could not be measured in Docker.

| Run | Patients | Wait between messages | Requests | Failures | Throughput | Median | p95 | p99 | Bookings made | Double-booked slots |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| u50 | 50 | 1 to 3 s | 2,948 | 0 | 25 req/s | 7 ms | 18 ms | 50 ms | 132 | 0 |
| u100 | 100 | 1 to 3 s | 5,898 | 0 | 49 req/s | 7 ms | 22 ms | 93 ms | 214 | 0 |
| u200 | 200 | 1 to 3 s | 11,807 | 0 | 98 req/s | 8 ms | 39 ms | 190 ms | 320 | 0 |
| stress | 200 | 0.1 to 0.5 s | 15,091 | 0 | 167 req/s | 730 ms | 1.8 s | 2.1 s | 414 | 0 |

Backend CPU in the middle of each run was 13%, 17%, 68% and 125% (PostgreSQL stayed under 15%, Redis under 7%). Memory
was flat at about 130 MB for the backend.

What this shows:
- **200 patients chatting at the same time are served in under 40 ms for 95% of messages**, with no errors. A small
  clinic gets a few dozen conversations an hour, so one worker is far more than enough.
- The stress run, with patients typing 5 to 10 times faster than people do, finds the limit of one worker: about 170
  requests a second. Past that, messages queue (median 0.7 s) but none fail. The limit is Python CPU in the single process,
  not the database. More `WEB_CONCURRENCY` workers raise it, now that sessions are in Redis.
- **No double booking.** 1,080 bookings were made across the four runs, many of them racing for the same early
  morning slots, and the end-of-run check found 0 slots held twice.
- Lookups by booking number and the first message of a conversation have the slowest tail (p99 190 to 270 ms at 200
  users), because they read more rows (appointment joins, duty tables). Still well under a second.

**XLM-R estimate (not measured here).** The XLM-R model takes about 30 ms per message on CPU (section 1 of `DEMO.md`)
against about 5 ms for the baseline, so one worker would serve roughly 25 to 30 messages a second, which is about
60 to 80 patients chatting at the 1 to 3 second pace above. Run the same command on your machine with `WITH_XLMR=1` and
report those numbers next to these.

Raw results: `loadtest/results/` (`*_stats.csv` per turn type, `*_stats_history.csv` over time, `*.html` Locust
reports with charts, `*_stats_mid.txt` container CPU and memory).

## 6. Before a real clinic uses it

- Put the stack behind HTTPS (for example Caddy or nginx in front of port 3000) and do not publish ports 8000, 5432 or 6379.
- Change both secrets in `.env`, and back up the `pgdata` volume (`docker compose exec db pg_dump -U medbook medbook > backup.sql`).
- The staff token is a shared password. Per-user staff logins would be the next step if more than one clinic uses it.
- Replace the demo address, phone and fees in `replies.py` / `clinic_db.py`, and the demo doctors in `data_gen/lexicons.py`.
- Seed bookings (MB-1042 and so on) are created on first start for the demo. Run `Clinic.reset()` only on a demo database.
