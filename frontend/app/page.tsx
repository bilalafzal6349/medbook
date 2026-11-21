"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";

type Slot = { label: string; value: string };
type NLU = {
  intent: string;
  intent_conf: number;
  department?: string;
  department_conf?: number;
  slots: Slot[];
  rules: Record<string, unknown>;
  engine: string;
  ms: number;
};
type ChatResponse = {
  session_id: string;
  reply: string;
  nlu: NLU;
  state: Record<string, unknown>;
  trace: string[];
  transcript?: string;
  asr?: { model: string; audio_s: number; asr_ms: number };
};
type Msg = { who: "user" | "bot"; text: string; meta?: string; emergency?: boolean; voice?: boolean };
type Appt = {
  ref: string; doctor: string; department: string; day: string; time: string;
  patient: string; phone: string; status: string; source: string;
};
type Health = { nlu_engine: string; voice: boolean; tts?: boolean; whisper_model?: string; now: string };

const MAX_REC_S = 30;

const EXAMPLES = [
  "salam, mujhe kal skin specialist ko dikhana hai",
  "mere bete ko 3 din se bukhar hai",
  "مجھے کل دل کے ڈاکٹر سے ملنا ہے",
  "Dr Kamran kab baithte hain?",
  "MB-1042 cancel karni hai",
  "MB-7781 ko agle somwar shift kar dein",
  "کلینک کی fee کتنی ہے؟",
  "abbu behosh ho gaye hain",
];

const isRtl = (t: string) => (t.match(/[؀-ۿ]/g) || []).length > (t.match(/[A-Za-z]/g) || []).length;

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
    let detail = `${r.status}`;
    try { detail = (await r.json()).detail || detail; } catch { /* not json */ }
    throw new Error(detail);
  }
  return r.json();
}

export default function Home() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [sid, setSid] = useState<string | null>(null);
  const [last, setLast] = useState<ChatResponse | null>(null);
  const [tab, setTab] = useState<"nlu" | "appts">("nlu");
  const [appts, setAppts] = useState<Appt[]>([]);
  const [seen, setSeen] = useState<Set<string>>(new Set());
  const [health, setHealth] = useState<Health | null>(null);
  const [rec, setRec] = useState<MediaRecorder | null>(null);
  const [recS, setRecS] = useState(0);
  const [speakReplies, setSpeakReplies] = useState(true);
  const [playing, setPlaying] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const box = useRef<HTMLDivElement>(null);

  const stopAudio = () => { audioRef.current?.pause(); audioRef.current = null; setPlaying(null); };

  // Speak an Urdu-script bot message with the backend's MMS-TTS voice.
  const speak = useCallback(async (t: string, idx: number) => {
    stopAudio();
    try {
      const r = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: t }) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${r.status}`);
      const url = URL.createObjectURL(await r.blob());
      const a = new Audio(url);
      audioRef.current = a;
      setPlaying(idx);
      a.onended = () => { URL.revokeObjectURL(url); setPlaying((p) => (p === idx ? null : p)); };
      await a.play();
    } catch (e) {
      setPlaying(null);
      setErr(`Speech: ${(e as Error).message}`);
    }
  }, []);

  const loadAppts = useCallback(async () => {
    try { setAppts(await api<Appt[]>("/api/appointments")); } catch { /* backend down: shown elsewhere */ }
  }, []);

  useEffect(() => {
    // keep trying until the backend is up (it may still be loading the model)
    let timer: ReturnType<typeof setTimeout>;
    const ping = () => api<Health>("/api/health")
      .then((h) => { setHealth(h); setErr(""); loadAppts(); })
      .catch(() => { setErr("Backend not reachable on /api yet. Start it with: uvicorn main:app --port 8000"); timer = setTimeout(ping, 3000); });
    ping();
    api<Appt[]>("/api/appointments").then((a) => { setAppts(a); setSeen(new Set(a.map((x) => x.ref))); }).catch(() => {});
    return () => clearTimeout(timer);
  }, [loadAppts]);

  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight, behavior: "smooth" }); }, [msgs]);

  const handle = (r: ChatResponse, voice = false) => {
    setSid(r.session_id);
    setLast(r);
    const n = r.nlu;
    let botIdx = 0;
    setMsgs((m) => {
      const out = [...m];
      if (voice && r.transcript) {
        const a = r.asr;
        out.push({ who: "user", text: r.transcript, voice: true,
          meta: a ? `voice · Whisper ${a.model} · ${a.audio_s.toFixed(1)} s audio, ${(a.asr_ms / 1000).toFixed(1)} s to transcribe` : "voice" });
      }
      out.push({
        who: "bot", text: r.reply, emergency: n.intent === "emergency",
        meta: `${n.intent} ${Math.round(n.intent_conf * 100)}%` + (n.department ? ` · ${n.department}` : ""),
      });
      botIdx = out.length - 1;
      return out;
    });
    // A spoken question gets a spoken answer (only Urdu-script replies can be spoken).
    if (voice && speakReplies && health?.tts && isRtl(r.reply)) setTimeout(() => speak(r.reply, botIdx), 0);
    loadAppts();
  };

  const send = async (t: string) => {
    const msg = t.trim();
    if (!msg || busy) return;
    setText("");
    setErr("");
    setMsgs((m) => [...m, { who: "user", text: msg }]);
    setBusy(true);
    try {
      handle(await api<ChatResponse>("/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: msg, session_id: sid }),
      }));
    } catch (e) {
      setErr(`Error: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (sid) await api("/api/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sid }) }).catch(() => {});
    stopAudio();
    setMsgs([]); setLast(null); setSid(null); setErr("");
  };

  // Recording timer, with an automatic stop so a forgotten mic does not upload minutes of audio.
  useEffect(() => {
    if (!rec) return;
    const t0 = Date.now();
    setRecS(0);
    const id = setInterval(() => {
      const s = Math.floor((Date.now() - t0) / 1000);
      setRecS(s);
      if (s >= MAX_REC_S && rec.state === "recording") rec.stop();
    }, 250);
    return () => clearInterval(id);
  }, [rec]);

  const toggleRec = async () => {
    if (rec) { rec.stop(); return; }
    stopAudio();
    setErr("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const mr = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      const started = Date.now();
      mr.ondataavailable = (e) => chunks.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRec(null);
        if (Date.now() - started < 600) { setErr("Hold on a little longer: press Mic, speak, then press Stop."); return; }
        const fd = new FormData();
        const ext = mr.mimeType.includes("mp4") ? "m4a" : mr.mimeType.includes("ogg") ? "ogg" : "webm";
        fd.append("audio", new Blob(chunks, { type: mr.mimeType }), `voice.${ext}`);
        if (sid) fd.append("session_id", sid);
        setBusy(true);
        try { handle(await api<ChatResponse>("/api/voice", { method: "POST", body: fd }), true); }
        catch (e) { setErr(`Voice: ${(e as Error).message}`); }
        finally { setBusy(false); }
      };
      mr.start();
      setRec(mr);
    } catch {
      setErr("Microphone not available in this browser.");
    }
  };

  const n = last?.nlu;
  const st = last?.state as Record<string, unknown> | undefined;

  return (
    <main className="app">
      <section className="card">
        <div className="head">
          <div>
            <h1>MedBook</h1>
            <small>Clinic appointments in Urdu, Roman Urdu and English</small>
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            {health && <span className="badge">NLU: {health.nlu_engine}</span>}
            {health && <span className={`badge ${health.voice ? "" : "off"}`}
              title={health.voice ? `Whisper ${health.whisper_model}` : "pip install faster-whisper on the backend"}>
              voice {health.voice ? "on" : "off"}</span>}
            {health?.tts && (
              <label className="badge toggle" title="Read Urdu replies aloud after a voice message">
                <input type="checkbox" checked={speakReplies} onChange={(e) => { setSpeakReplies(e.target.checked); if (!e.target.checked) stopAudio(); }} />
                speak replies
              </label>
            )}
            <button className="ghost" onClick={reset}>New chat</button>
          </div>
        </div>

        <div className="msgs" ref={box}>
          {msgs.length === 0 && (
            <div className="empty">Type a message, or pick an example below. Try writing in any script{health?.voice ? ", or press Mic and speak in Urdu" : ""}.</div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={`msg ${m.who}${m.emergency ? " emergency" : ""}`} dir={isRtl(m.text) ? "rtl" : "ltr"}>
              {m.text}
              {m.meta && <span className="meta" dir="ltr">{m.meta}</span>}
              {m.who === "bot" && health?.tts && isRtl(m.text) && (
                <button type="button" className="speak" title={playing === i ? "Stop" : "Listen"} aria-label={playing === i ? "Stop" : "Listen"}
                  onClick={() => (playing === i ? stopAudio() : speak(m.text, i))}>{playing === i ? "■" : "🔊"}</button>
              )}
            </div>
          ))}
          {rec && <div className="msg user recording" dir="ltr"><i className="dot" /> Listening… {recS}s / {MAX_REC_S}s</div>}
          {busy && <div className="msg bot">…</div>}
        </div>
        {err && <div className="err">{err}</div>}
        <div className="chips">
          {EXAMPLES.map((e) => (
            <button key={e} className="chip" dir="auto" onClick={() => send(e)} disabled={busy}>{e}</button>
          ))}
        </div>
        <form className="composer" onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <input value={text} onChange={(e) => setText(e.target.value)} dir={isRtl(text) ? "rtl" : "ltr"}
            placeholder="Likhein… / یہاں لکھیں…" autoFocus />
          <button type="button" className={`ghost ${rec ? "rec" : ""}`} onClick={toggleRec}
            disabled={!health?.voice || (busy && !rec)}
            title={health?.voice ? "Record a voice message" : "Voice is off on the backend (pip install faster-whisper)"}>
            {rec ? `Stop ${recS}s` : "Mic"}
          </button>
          <button className="primary" disabled={busy || !text.trim()}>Send</button>
        </form>
      </section>

      <aside className="card">
        <div className="tabs">
          <button className={tab === "nlu" ? "on" : ""} onClick={() => setTab("nlu")}>Under the hood</button>
          <button className={tab === "appts" ? "on" : ""} onClick={() => { setTab("appts"); loadAppts(); }}>
            Appointments ({appts.filter((a) => a.status === "booked").length})
          </button>
        </div>
        {tab === "nlu" ? (
          <div className="side">
            {!n ? <p className="empty">Send a message to see what the model understood and what the dialogue manager decided.</p> : (
              <>
                <h3>NLU ({n.engine}, {n.ms} ms)</h3>
                <div className="kv">
                  <span>intent</span>
                  <span>{n.intent}<div className="bar"><i style={{ width: `${n.intent_conf * 100}%` }} /></div></span>
                  {n.department && (<>
                    <span>department</span>
                    <span>{n.department}<div className="bar"><i style={{ width: `${(n.department_conf || 0) * 100}%` }} /></div></span>
                  </>)}
                  <span>slots</span>
                  <span>{n.slots.length === 0 ? "none" : n.slots.map((s, i) => (
                    <span key={i} className="slot" dir="auto"><b>{s.label}</b>{s.value}</span>
                  ))}</span>
                  {Object.keys(n.rules).length > 0 && (<><span>rules</span><span>{JSON.stringify(n.rules)}</span></>)}
                </div>
                <h3>Dialogue manager</h3>
                {last.trace.length ? <ol className="trace">{last.trace.map((t, i) => <li key={i} dir="auto">{t}</li>)}</ol>
                  : <p className="empty">No decisions this turn.</p>}
                <h3>Dialogue state</h3>
                <div className="kv">
                  {st && Object.entries(st).filter(([, v]) => v !== null && v !== "" && !(typeof v === "object" && Object.keys(v as object).length === 0) && v !== 0)
                    .map(([k, v]) => (
                      <Fragment key={k}><span>{k}</span><span dir="auto">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span></Fragment>
                    ))}
                </div>
              </>
            )}
          </div>
        ) : (
          <div className="side">
            <table>
              <thead><tr><th>Ref</th><th>When</th><th>Doctor</th><th>Patient</th></tr></thead>
              <tbody>
                {appts.map((a) => (
                  <tr key={a.ref} className={`${a.status}${seen.has(a.ref) ? "" : " new"}`}>
                    <td>{a.ref}</td><td>{a.day}<br />{a.time}</td><td>{a.doctor}</td><td dir="auto">{a.patient}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="empty">Green = booked in this demo. Struck through = cancelled.</p>
          </div>
        )}
      </aside>
    </main>
  );
}
