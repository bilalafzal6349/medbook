"use client";

import { useCallback, useEffect, useState } from "react";
import "./admin.css";

type Appt = {
  ref: string; doctor: string; doctor_id: number; department: string; day: string; start_min: number;
  time: string; patient: string; phone: string; age?: string | null; reason?: string | null;
  status: string; lang?: string | null; source: string;
};
type SlotRow = { start_min: number; time: string; state: "free" | "booked" | "past"; appointment: Appt | null };
type DoctorCol = {
  doctor: { id: number; name_roman: string; name_urdu: string; department: string };
  department: string; shifts: string[]; slots: SlotRow[]; cancelled: Appt[];
};
type Schedule = { day: string; weekday: string; doctors: DoctorCol[]; totals: { booked: number; free: number; doctors_on_duty: number } };
type Reminder = { ref: string; kind: string; channel: string; status: string; detail: string | null; message: string; created_at: string };
type Reminders = { provider: string; due_now: { ref: string; kind: string }[]; log: Reminder[] };

const TOKEN_KEY = "medbook-admin-token";

function readToken() {
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
}

function shift(day: string, n: number) {
  const d = new Date(day + "T12:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export default function Admin() {
  const [day, setDay] = useState<string>("");
  const [token, setToken] = useState("");
  const [sched, setSched] = useState<Schedule | null>(null);
  const [rem, setRem] = useState<Reminders | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [onlyBooked, setOnlyBooked] = useState(false);

  const call = useCallback(async <T,>(path: string, init?: RequestInit): Promise<T> => {
    const r = await fetch(path, { ...init, headers: { ...(init?.headers || {}), "X-Admin-Token": token } });
    if (!r.ok) {
      let detail = `${r.status}`;
      try { detail = (await r.json()).detail || detail; } catch { /* not json */ }
      throw new Error(detail);
    }
    return r.json();
  }, [token]);

  const load = useCallback(async () => {
    try {
      const s = await call<Schedule>(`/api/admin/schedule${day ? `?day=${day}` : ""}`);
      setSched(s);
      if (!day) setDay(s.day);
      setRem(await call<Reminders>("/api/admin/reminders?limit=30"));
      setErr("");
    } catch (e) {
      setErr(String((e as Error).message));
    }
  }, [call, day]);

  useEffect(() => { setToken(readToken()); }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const saveToken = (v: string) => {
    setToken(v);
    try { localStorage.setItem(TOKEN_KEY, v); } catch { /* private window */ }
  };

  const cancel = async (a: Appt) => {
    if (!confirm(`Cancel ${a.ref} for ${a.patient} at ${a.time}?`)) return;
    setBusy(true);
    try { await call(`/api/admin/appointments/${a.ref}/cancel`, { method: "POST" }); await load(); }
    catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(false); }
  };

  const sendReminders = async () => {
    setBusy(true);
    try {
      const r = await call<{ sent: unknown[] }>("/api/admin/reminders/run", { method: "POST" });
      await load();
      setErr(r.sent.length ? "" : "No reminders were due.");
    } catch (e) { setErr(String((e as Error).message)); }
    finally { setBusy(false); }
  };

  return (
    <main className="adm">
      <header className="adm-top">
        <div>
          <h1>MedBook staff schedule</h1>
          <small>Bookings made by the chatbot appear here. Refreshes every 30 seconds.</small>
        </div>
        <nav className="adm-tools">
          <a href="/" className="chip">Patient chat</a>
          <input type="password" placeholder="Staff token" value={token} onChange={(e) => saveToken(e.target.value)}
                 aria-label="Staff token" />
        </nav>
      </header>

      <section className="adm-bar">
        <button className="chip" onClick={() => setDay(shift(day, -1))} disabled={!day}>Previous day</button>
        <input type="date" value={day} onChange={(e) => setDay(e.target.value)} aria-label="Day" />
        <button className="chip" onClick={() => setDay(shift(day, 1))} disabled={!day}>Next day</button>
        {sched && (
          <span className="adm-totals">
            {sched.weekday}: <b>{sched.totals.booked}</b> booked, <b>{sched.totals.free}</b> free,{" "}
            <b>{sched.totals.doctors_on_duty}</b> doctors on duty
          </span>
        )}
        <label className="adm-check">
          <input type="checkbox" checked={onlyBooked} onChange={(e) => setOnlyBooked(e.target.checked)} /> Booked slots only
        </label>
      </section>

      {err && <p className="adm-err">{err}</p>}

      {sched && sched.doctors.length === 0 && <p className="adm-empty">No doctor is on duty on this day.</p>}

      <section className="adm-grid">
        {sched?.doctors.map((c) => (
          <article key={c.doctor.id} className="card adm-col">
            <div className="adm-colhead">
              <b>{c.doctor.name_roman}</b>
              <span>{c.department} · {c.shifts.join(", ")}</span>
            </div>
            <ul>
              {c.slots.filter((s) => !onlyBooked || s.state === "booked").map((s) => (
                <li key={s.start_min} className={`adm-slot ${s.state}`}>
                  <span className="adm-time">{s.time}</span>
                  {s.appointment ? (
                    <span className="adm-who">
                      <b dir="auto">{s.appointment.patient}</b>
                      <span className="adm-phone">{s.appointment.phone}</span>
                      <small>
                        {s.appointment.ref}
                        {s.appointment.reason ? ` · ${s.appointment.reason}` : ""}
                        {s.appointment.source === "seed" ? " · demo" : ""}
                      </small>
                    </span>
                  ) : (
                    <span className="adm-who muted">{s.state === "past" ? "past" : "free"}</span>
                  )}
                  {s.appointment && s.state === "booked" && (
                    <button className="adm-x" disabled={busy} onClick={() => cancel(s.appointment!)}>Cancel</button>
                  )}
                </li>
              ))}
            </ul>
            {c.cancelled.length > 0 && (
              <p className="adm-cancelled">Cancelled: {c.cancelled.map((a) => `${a.time} ${a.patient}`).join(", ")}</p>
            )}
          </article>
        ))}
      </section>

      <section className="card adm-rem">
        <div className="adm-colhead adm-remhead">
          <b>Reminders</b>
          <span>Provider: {rem?.provider ?? "?"} · due now: {rem?.due_now.length ?? 0}</span>
          <button className="chip" onClick={sendReminders} disabled={busy}>Send due reminders now</button>
        </div>
        {rem && rem.log.length === 0 && <p className="adm-empty">No reminders sent yet.</p>}
        {rem && rem.log.length > 0 && (
          <div className="adm-tablewrap">
            <table>
              <thead><tr><th>When</th><th>Booking</th><th>Kind</th><th>Status</th><th>Message</th></tr></thead>
              <tbody>
                {rem.log.map((r) => (
                  <tr key={r.ref + r.kind}>
                    <td>{r.created_at.replace("T", " ").slice(0, 16)}</td>
                    <td>{r.ref}</td>
                    <td>{r.kind === "day_before" ? "day before" : "same day"}</td>
                    <td className={r.status}>{r.status}{r.detail && r.status === "failed" ? `: ${r.detail}` : ""}</td>
                    <td dir="auto">{r.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
