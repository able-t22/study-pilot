/* StudyPilot front-end (vanilla JS). Talks to the FastAPI backend under /api. */
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (p, o = {}) => {
  const fd = o.body instanceof FormData;
  const r = await fetch("/api" + p, { ...o, headers: o.body && !fd ? { "Content-Type": "application/json" } : {}, body: o.body && !fd ? JSON.stringify(o.body) : o.body });
  if (!r.ok) { let d = r.statusText; try { d = (await r.json()).detail || d; if(Array.isArray(d)) d=d.map(x=>x.msg || String(x)).join("; "); else if(typeof d === "object")d=JSON.stringify(d); } catch (e) {} throw new Error(d); }
  const j = await r.json();
  if (j && j.job && j.state) JOBCACHE[j.job] = j.state;  // serverless: the finished job state comes back with the POST itself
  return j;
};
const JOBCACHE = {}, jobGet = jid => JOBCACHE[jid] ? Promise.resolve(JOBCACHE[jid]) : api("/jobs/" + jid);
let SID = null, GRAPH = null, charts = {}, CITES = {}, HIST = [], RUN = null, CFG = {}, TIMER = null, MODE = "adaptive", SOURCES = [];

/* ---------- icons ---------- */
const P = {
  folder: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z", map: "M6 5a2 2 0 1 0 0 .01M18 5a2 2 0 1 0 0 .01M12 19a2 2 0 1 0 0 .01M7.5 6.7l3.5 10.5M16.5 6.7L13 17.2M8 5h8",
  chat: "M21 12a8 8 0 0 1-11.8 7L4 20l1.2-4.6A8 8 0 1 1 21 12z", target: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12h.01", chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  flask: "M9 3h6M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2.2h12.4A1.5 1.5 0 0 0 19.5 19L14 9V3M7.5 15h9", upload: "M12 16V4m0 0l-4 4m4-4l4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3",
  play: "M6 4l14 8-14 8z", refresh: "M20 11a8 8 0 0 0-14.9-3M4 5v4h4M4 13a8 8 0 0 0 14.9 3M20 19v-4h-4", mic: "M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3zM5 11a7 7 0 0 0 14 0M12 18v3",
  x: "M6 6l12 12M18 6L6 18", file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5", video: "M3 7a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM16 10l5-3v10l-5-3",
  slide: "M3 4h18v12H3zM12 16v4M8 20h8", book: "M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 19V5", sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z", bolt: "M13 2L4 14h7l-1 8 9-12h-7z", layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5", clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
  check: "M5 13l4 4L19 7", audio: "M11 5L6 9H3v6h3l5 4zM15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13", print: "M6 9V3h12v6M6 18H4a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-2M7 14h10v7H7z",
  hex: "M12 3l8 4.5v9L12 21l-8-4.5v-9z", send: "M5 12l14-8-4 16-3-6z", img: "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M9 9h.01", spark: "M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z", note: "M5 3h11l3 3v15H5zM8 9h8M8 13h8M8 17h5", dl: "M12 4v12m0 0l-4-4m4 4l4-4M4 20h16"
};
const ic = (n, s = 18) => `<svg viewBox="0 0 24 24" width="${s}" height="${s}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${P[n] || ""}"/></svg>`;
const kindIcon = { pdf: "book", pptx: "slide", video: "video", audio: "audio", transcript: "file", text: "file" };
const kindName = { pdf: "Textbook / PDF", pptx: "Slides", video: "Lecture video", audio: "Lecture audio", transcript: "Transcript", text: "Notes" };

/* ---------- ui helpers ---------- */
function toast(msg, type = "") { const t = document.createElement("div"); t.className = "toast " + type; t.textContent = msg; $("#toasts").append(t); setTimeout(() => t.remove(), 4200); }
const chart = (id, cfg) => { if (typeof Chart === "undefined") return; charts[id]?.destroy(); const el = $("#" + id); if (!el) return; cfg.options = Object.assign({ responsive: true, maintainAspectRatio: false }, cfg.options || {}); charts[id] = new Chart(el, cfg); };
function themeChart() { if (typeof Chart === "undefined") return; const l = document.documentElement.dataset.theme === "light"; Chart.defaults.color = l ? "#5c6684" : "#8e98b4"; Chart.defaults.borderColor = l ? "rgba(20,25,60,.08)" : "rgba(255,255,255,.07)"; Chart.defaults.font.family = "Inter, system-ui, sans-serif"; }
function toggleTheme() { const d = document.documentElement, n = d.dataset.theme === "light" ? "dark" : "light"; d.dataset.theme = n; try { localStorage.setItem("sp-theme", n); } catch (e) {} paintTheme(); themeChart(); const t = $("#tabs .on")?.dataset.k; if (t) show(t); }
function paintTheme() { const l = document.documentElement.dataset.theme === "light"; $("#themeBtn").innerHTML = ic(l ? "moon" : "sun", 16) + (l ? " Dark mode" : " Light mode"); }
function countUp(el, to, suf = "", dec = 0) { const t0 = performance.now(); const f = n => { const k = Math.min(1, (n - t0) / 700), e = 1 - Math.pow(1 - k, 3); el.textContent = (to * e).toFixed(dec) + suf; if (k < 1) requestAnimationFrame(f); }; requestAnimationFrame(f); }
const kpi = (v, label, cls = "", suf = "", dec = 0) => `<div class="kpi ${cls}"><i></i><b data-to="${v}" data-suf="${suf}" data-dec="${dec}">0${suf}</b><span>${label}</span></div>`;
const animateKpis = root => $$(root + " [data-to]").forEach(e => countUp(e, +e.dataset.to, e.dataset.suf, +e.dataset.dec));
function ring(p, size = "", color) { const r = 52, c = 2 * Math.PI * r, col = color || (p >= .7 ? "var(--good)" : p >= .4 ? "var(--warn)" : "var(--bad)");
  return `<div class="ring ${size}"><svg viewBox="0 0 120 120" width="100%" height="100%"><circle cx="60" cy="60" r="${r}" fill="none" stroke="var(--surface2)" stroke-width="11"/><circle cx="60" cy="60" r="${r}" fill="none" stroke="${col}" stroke-width="11" stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - Math.max(0, Math.min(1, p)))}" style="transition:stroke-dashoffset .9s"/></svg><b>${Math.round(p * 100)}%</b></div>`; }
const skeleton = (n = 3) => Array.from({ length: n }, () => '<div class="skel"></div>').join("");
const needStudent = () => { if (SID) return false; toast("Create a learner profile first (top right).", "err"); openIntake(); return true; };
function openModal(html, narrow) { $("#mbody").innerHTML = html; $("#mbox").classList.toggle("narrow", !!narrow); $("#modal").classList.remove("hidden"); }
function closeModal() { $("#modal").classList.add("hidden"); $("#mbody").innerHTML = ""; }

/* ---------- languages ---------- */
let LANGS = {}, ANSWER_LANG = "auto"; try { ANSWER_LANG = localStorage.getItem("sp-lang") || "auto"; } catch (e) {}
const speechCode = l => (LANGS[l] || {}).speech || "en-IN";
function fillLangSelects() { const opts = (auto) => (auto ? `<option value="auto">Auto · answer in my language</option>` : "") + Object.entries(LANGS).map(([k, v]) => `<option value="${k}">${v.native}${v.name !== v.native ? " · " + v.name : ""}</option>`).join("");
  $("#lang").innerHTML = opts(true); $("#lang").value = ANSWER_LANG; $("#n_lang").innerHTML = opts(false); $("#n_lang").value = ANSWER_LANG === "auto" ? "en" : ANSWER_LANG; }
function setLang(v) { ANSWER_LANG = v; try { localStorage.setItem("sp-lang", v); } catch (e) {} if (v !== "auto") $("#n_lang").value = v; }
function voiceFor(l) { const vs = speechSynthesis.getVoices(); return vs.find(v => v.lang.replace("_", "-").toLowerCase() === speechCode(l).toLowerCase()) || vs.find(v => v.lang.toLowerCase().startsWith(l)); }
function speakText(t, l) { if (!window.speechSynthesis) return toast("Speech output is not supported in this browser", "err"); const u = new SpeechSynthesisUtterance(t.replace(/\[S\d+\]/g, "").replace(/\*\*/g, "")); u.lang = speechCode(l); const v = voiceFor(l);
  if (v) u.voice = v; else if (l !== "en") toast(`No ${LANGS[l]?.name || l} voice is installed on this device. Add it in your OS speech settings (Chrome/Edge on Windows: Settings → Time & language → Speech).`, "err"); speechSynthesis.cancel(); speechSynthesis.speak(u); }
if (window.speechSynthesis) speechSynthesis.getVoices();

/* ---------- navigation ---------- */
const TABS = [["cockpit", "Study cockpit", "bolt", "Your daily actions, evidence of progress and mistake notebook"], ["library", "Library", "folder", "Add sources & see the knowledge base"], ["notes", "Notes", "note", "Turn any lecture or document into notes written the way you want"], ["map", "Course map", "map", "Topics, concepts and prerequisites"], ["tutor", "Tutor", "chat", "Source-cited answers, flagged when off-material"],
  ["revise", "Revise", "spark", "Flashcards, slides and audio briefs for your weak topics"], ["practice", "Practice", "target", "Verified quizzes and mock exams with cited feedback"], ["dash", "Dashboard", "chart", "Mastery, retention, schedule and revision"], ["eval", "Evaluation", "flask", "Answer quality and simulated-student results"]];
$("#tabs").innerHTML = TABS.map(([k, v, i]) => `<button data-k="${k}" onclick="show('${k}')">${ic(i)}<span>${v}</span></button>`).join("");
$("#logo").innerHTML = ic("hex", 22); $("#micBtn").innerHTML = ic("mic"); $("#mclose").innerHTML = ic("x", 16); $("#dropic").innerHTML = ic("upload", 24);
$("#notesBtn").innerHTML = ic("note", 16) + " Generate notes"; $("#uploadBtn").innerHTML = ic("upload", 16) + " Upload files"; $("#reBtn").innerHTML = ic("refresh", 16) + " Re-analyse";
function show(k) { const t = TABS.find(x => x[0] === k); $$(".tab").forEach(e => e.classList.toggle("hidden", e.id !== k)); $$("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.k === k));
  $("#ptitle").textContent = t[1]; $("#psub").textContent = t[3]; window.scrollTo({ top: 0 });
  ({ cockpit: loadCockpit, library: loadLibrary, notes: loadNotes, map: loadMap, tutor: loadTutor, practice: loadPractice, revise: loadRevise, dash: loadDash, eval: loadEval })[k](); }

/* ---------- students ---------- */
const setUser = id => { document.cookie = "sp_user=" + (id || 0) + ";path=/;max-age=31536000;SameSite=Lax"; };
async function loadStudents(sel) { if (sel) setUser(sel); else { const m = document.cookie.match(/sp_user=(\d+)/); if (m) sel = +m[1]; } const s = await api("/students"); if (sel && !s.find(x => x.id === sel)) sel = null; $("#student").innerHTML = s.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join("") || "<option value=''>No learner yet</option>";
  if (sel) $("#student").value = sel; SID = +$("#student").value || null; setUser(SID); if (!sel && SID) setUser(SID); const cur = s.find(x => x.id === SID); $("#avatar").textContent = cur ? cur.name.trim()[0].toUpperCase() : "?"; }
$("#student").onchange = () => { SID = +$("#student").value || null; setUser(SID); window._rev=null; POD=null; window._gl=[]; $("#n_view").classList.add("hidden"); $("#n_btn").disabled=false; $("#n_bar").classList.add("hidden"); GRAPH = null; RUN = null; HIST = []; $$("#msgs .m").forEach(e => e.remove()); loadStudents(SID); const t = $("#tabs .on")?.dataset.k; if (t) show(t); };
async function delLearner() { if (!SID) return; const n = $("#student").selectedOptions[0]?.textContent; if (!confirm(`Delete "${n}" and ALL of their uploaded material, notes and progress?`)) return; await api("/students/" + SID, { method: "DELETE" }); SID = null; setUser(0); await loadStudents(); toast("Learner deleted"); show("library"); if (!SID) openIntake(); }
function openIntake() { openModal(`<h2>Create a learner</h2><p class="muted">Every learner gets a private, empty workspace. Only the material you upload will appear — topics, quizzes, notes and progress are built from it.</p>
  <div class="form"><label>Your name<input id="in_name" placeholder="Your name" autofocus></label>
  <label>Current level<div class="seg"><label><input type="radio" name="lv" value="beginner" checked><b>Beginner</b><small>new to it</small></label><label><input type="radio" name="lv" value="intermediate"><b>Intermediate</b><small>some background</small></label><label><input type="radio" name="lv" value="advanced"><b>Advanced</b><small>revising</small></label></div></label>
  <label>Goal<input id="in_goal" placeholder="What do you want to achieve?"></label><label>Exam date (optional)<input id="in_exam" type="date"></label>
  <div class="row"><button onclick="saveIntake()">Create profile</button><button class="ghost" onclick="closeModal()">Later</button></div></div>`, true); setTimeout(() => $("#in_name")?.focus(), 50); }
async function saveIntake() { const name = $("#in_name").value.trim(); if (!name) return toast("Please enter a name", "err");
  const r = await api("/students", { method: "POST", body: { name, level: document.querySelector("input[name=lv]:checked").value, goal: $("#in_goal").value, exam_date: $("#in_exam").value } });
  closeModal(); GRAPH = null; RUN = null; HIST = []; $$("#msgs .m").forEach(e => e.remove()); await loadStudents(r.id); toast("Workspace created for " + name + " — upload your material to begin", "ok"); show("library"); }

/* ---------- library ---------- */
const drop = $("#drop"); ["dragover", "dragenter"].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", ev => upload(ev.dataTransfer.files)); drop.addEventListener("click", ev => { if (ev.target.tagName !== "A") $("#files").click(); }); $("#files").onchange = e => upload(e.target.files);
function sendUpload(fd) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest(); xhr.open("POST", "/api/upload");
    xhr.upload.onprogress = e => {
      if (!e.lengthComputable) return;
      const pct = Math.round(e.loaded / e.total * 100);
      $("#jobfill").style.width = pct + "%"; $("#jobpct").textContent = pct + "%";
      $("#jobmsg").textContent = "Sending " + (e.loaded / 1048576).toFixed(1) + " / " + (e.total / 1048576).toFixed(1) + " MB";
    };
    xhr.onerror = () => reject(new Error("Upload connection failed. Please try again."));
    xhr.onload = () => {
      let j; try { j = JSON.parse(xhr.responseText); } catch(e) { reject(new Error("Invalid upload response")); return; }
      if (xhr.status < 200 || xhr.status >= 300) { reject(new Error(j.detail || "Upload failed")); return; }
      if (j.job && j.state) JOBCACHE[j.job] = j.state;
      resolve(j);
    };
    xhr.send(fd);
  });
}
async function upload(fl) { if (!fl.length) return; if (needStudent()) return; const fd = new FormData(); fd.append("fast", $("#fastUpload").checked); [...fl].forEach(f => fd.append("files", f)); $("#uploadBtn").disabled = true; $("#jobbar").classList.remove("hidden"); $("#jobtitle").textContent = "Sending files…"; $("#jobfill").style.width = "0%"; $("#jobpct").textContent = "0%"; $("#jobmsg").textContent = "Uploading files to your workspace"; try { const r = await sendUpload(fd); toast(`Uploading ${fl.length} file(s)…`); track(r.job, async () => { await loadLibrary(); if ([...fl].some(f => /\.(mp4|mkv|mov|webm|mp3|wav|m4a|vtt|srt)$/i.test(f.name))) toast("Lecture ready — open the Notes tab to generate notes from it", "ok"); }, "Ingesting & analysing"); } catch (e) { toast(e.message, "err"); $("#jobbar").classList.add("hidden"); } finally { $("#uploadBtn").disabled = false; $("#files").value = ""; } }
async function reanalyze() { if (!confirm("Re-analysing resets quiz history and mastery. Continue?")) return; const r = await api("/analyze", { method: "POST" }); track(r.job, loadLibrary, "Re-analysing structure"); }
function track(jid, done, title = "Processing") { $("#jobbar").classList.remove("hidden"); $("#jobtitle").textContent = title; window.scrollTo({ top: 0, behavior: "smooth" });
  const uid = SID; const t = setInterval(async () => { if (SID !== uid) { clearInterval(t); $("#jobbar").classList.add("hidden"); return; } try { const j = await jobGet(jid); $("#jobfill").style.width = (j.pct * 100) + "%"; $("#jobpct").textContent = Math.round(j.pct * 100) + "%"; $("#jobmsg").textContent = j.msg;
    if (j.status !== "running") { clearInterval(t); if (j.status === "error") { $("#jobmsg").textContent = "❌ " + j.msg; toast(j.msg, "err"); } else { setTimeout(() => $("#jobbar").classList.add("hidden"), 900); done && done(j); } } } catch (e) { clearInterval(t); $("#jobmsg").textContent = "Could not read job status: " + e.message; toast(e.message, "err"); } }, 700); }
const ART = `<svg viewBox="0 0 320 260" fill="none"><defs><linearGradient id="g1" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7c83ff"/><stop offset="1" stop-color="#c084fc"/></linearGradient></defs>
 <g stroke="url(#g1)" stroke-width="2" opacity=".7"><path d="M160 130L70 60M160 130L260 70M160 130L80 200M160 130L255 195M70 60L35 135M260 70L290 140"/></g>
 <g fill="var(--bg2)" stroke="url(#g1)" stroke-width="2.5"><circle cx="160" cy="130" r="34"/><circle cx="70" cy="60" r="22"/><circle cx="260" cy="70" r="22"/><circle cx="80" cy="200" r="22"/><circle cx="255" cy="195" r="22"/><circle cx="35" cy="135" r="13"/><circle cx="290" cy="140" r="13"/></g>
 <path d="M160 112l15 9v18l-15 9-15-9v-18z" fill="url(#g1)"/></svg>`;
async function loadLibrary() { $("#heroart").innerHTML = ART; $("#sources").innerHTML = skeleton(); let s = [], o = {};
  try { [s, o] = await Promise.all([api("/sources"), api("/overview")]); } catch (e) { toast(e.message, "err"); } SOURCES = s;
  const fig = o.units?.figure || 0, tr = o.units?.transcript || 0, tot = Object.values(o.units || {}).reduce((a, b) => a + b, 0);
  $("#kpis").innerHTML = kpi(s.length, "Sources ingested") + kpi(tot, "Knowledge units") + kpi(o.topics || 0, "Topics") + kpi(o.concepts || 0, "Key concepts") + kpi(fig, "Figures understood") + kpi(tr, "Transcript segments") + kpi(o.verified || 0, "Verified questions", "good"); animateKpis("#kpis");
  const steps = [["Ingest", "PDF · slides · video · audio", s.length > 0], ["Structure", `${o.topics || 0} topics · ${o.concepts || 0} concepts · ${o.prereqs || 0} prerequisite links`, (o.topics || 0) > 0],
    ["Ground", `${o.tagged || 0} units tagged with page / slide / timestamp`, (o.tagged || 0) > 0], ["Assess", `${o.questions || 0} questions generated, ${o.verified || 0} verified`, (o.questions || 0) > 0], ["Personalise", `${o.students || 0} learner profile(s) tracked`, (o.students || 0) > 0]];
  $("#pipeline").innerHTML = steps.map(([a, b, d], i) => `<div class="step ${d ? "done" : ""}"><span class="n">${d ? ic("check", 14) : i + 1}</span><div><b>${a}</b><small>${b}</small></div></div>`).join("");
  $("#sources").innerHTML = s.length ? `<table><tr><th>Source</th><th>Type</th><th>Units</th><th></th></tr>${s.map(x => `<tr><td><b>${esc(x.name)}</b></td><td><span class="kind">${ic(kindIcon[x.kind] || "file", 13)} ${kindName[x.kind] || x.kind}</span></td><td>${x.units}</td><td style="text-align:right"><button class="ghost sm" onclick="notesFor(${x.id})">Notes</button> <button class="ghost sm" onclick="delSource(${x.id})">Remove</button></td></tr>`).join("")}</table>`
    : `<div class="empty"><p>Nothing here yet. Upload a lecture video, PDF, slides or a transcript — everything (topics, quizzes, notes, tutor) is built only from your files.</p><button onclick="$('#files').click()">${ic("upload", 16)} Upload files</button></div>`; }
async function delSource(id) { if (confirm("Remove this source? Topics will need re-analysis.")) { await api("/sources/" + id, { method: "DELETE" }); toast("Removed. Click Re-analyse to rebuild topics."); loadLibrary(); } }

/* ---------- source viewer ---------- */
async function openSource(c) { const info = await api(`/source/${c.source_id}/info`); const L = c.loc || {}; let h = `<h3 style="padding-right:40px">${esc(c.source_name || info.name)} · ${esc(c.label)}</h3>`;
  if ("t0" in L && info.has_video) h += `<video id="vid" controls src="/api/source/${c.source_id}/media"></video><p class="muted small">Jumped to ${esc(c.label)}</p>`;
  else if (info.kind === "pdf" && L.page) h += `<img alt="PDF page" src="/api/source/${c.source_id}/page/${L.page}.png?q=${encodeURIComponent((c.snippet || "").slice(0, 50))}">`;
  else if (L.slide && info.has_pdf) h += `<img alt="Slide" src="/api/source/${c.source_id}/page/${L.slide}.png">`;
  else if (L.slide) { const s = await api(`/source/${c.source_id}/slide/${L.slide}`); h += s.units.map(u => `<div class="flag acc">${esc(u.snippet)}</div>`).join("") + s.images.map(i => `<img src="/api/media/${i}">`).join(""); }
  h += `<div class="flag acc"><b>Cited excerpt</b><br>${esc(c.snippet || "")}</div>`; openModal(h);
  const v = $("#vid"); if (v) v.addEventListener("loadedmetadata", () => { v.currentTime = L.t0; v.play().catch(() => 0); }); }
const regCite = c => { const k = "c" + c.unit_id; CITES[k] = c; return k; };
const citeIcon = c => ("t0" in (c.loc || {})) ? "video" : c.loc?.slide ? "slide" : c.unit_kind === "figure" ? "img" : "book";
const citeBtn = (id, c) => `<span class="cite" onclick='openSource(CITES["${regCite(c)}"])' title="${esc(c.source_name)} · ${esc(c.label)}">${ic(citeIcon(c), 12)}${id ? id + " · " : ""}${esc(c.label)}</span>`;


/* ---------- notes ---------- */
const NSTYLE_ICON = { key_points: "bolt", summary: "file", detailed: "book", study_guide: "target", qa: "chat", outline: "layers", cheatsheet: "spark" };
let NOPT = null, N_STYLE = "key_points", N_LEN = "standard";
function notesFor(id) { show("notes"); setTimeout(() => { $("#n_src").value = id; }, 300); }
const mdNotes = text => preserveMath(text, t => { let h = esc(t).replace(/^### (.+)$/gm, "<h4>$1</h4>").replace(/^## (.+)$/gm, "<h3>$1</h3>").replace(/^# (.+)$/gm, "<h2>$1</h2>").replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\*(.+?)\*/g, "<i>$1</i>")
  .replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>").replace(/^---$/gm, "<hr>");
  h = h.replace(/^(\s*)[-*] (.+)$/gm, (m, sp, x) => `<li style="margin-left:${Math.min(sp.length, 8) * 8}px">${x}</li>`).replace(/^(\s*)\d+\. (.+)$/gm, (m, sp, x) => `<li class="ol" style="margin-left:${Math.min(sp.length, 8) * 8}px">${x}</li>`);
  return h.split(/\n{2,}/).map(b => /^\s*<(h\d|li|hr|block)/.test(b) ? b.replace(/((?:<li[^>]*>.*<\/li>\s*)+)/g, "<ul>$1</ul>") : `<p>${b.replace(/\n/g, "<br>")}</p>`).join(""); });
function selectNoteStyle(k) { N_STYLE = k; if (k === "detailed") N_LEN = "detailed"; renderNoteOptions(); }
function renderNoteOptions() {
  $("#n_styles").innerHTML = Object.entries(NOPT.styles).map(([k,v]) => `<button type="button" class="mode ${k === N_STYLE ? "on" : ""}" aria-pressed="${k === N_STYLE}" onclick="selectNoteStyle('${k}')">${ic(NSTYLE_ICON[k] || "file",22)}<b>${esc(v.name)}</b><p>${esc(v.desc)}</p></button>`).join("");
  $("#n_len").innerHTML = Object.entries(NOPT.lengths).map(([k,v]) => `<label><input type="radio" name="nlen" value="${k}" ${k === N_LEN ? "checked" : ""} onchange="N_LEN='${k}'"><b>${esc(v)}</b></label>`).join("");
}
async function loadNotes() {
  if (!NOPT) NOPT = await api("/notes/options");
  const src = await api("/sources"); SOURCES = src;
  const prefer = src.slice().reverse().find(x => x.kind === "video" || x.kind === "audio") || src[src.length - 1], cur = $("#n_src").value;
  $("#n_src").innerHTML = src.length ? src.map(x => `<option value="${x.id}">${esc(x.name)} · ${kindName[x.kind] || x.kind}</option>`).join("") + (src.length > 1 ? '<option value="all">All sources combined</option>' : "") : "<option value=''>Upload a source first</option>";
  $("#n_src").value = (cur === "all" && src.length > 1 || src.some(x => String(x.id) === cur)) ? cur : (prefer ? prefer.id : "");
  renderNoteOptions();
  const list = await api("/notes");
  $("#n_list").innerHTML = list.map(n => `<div class="rec"><div style="cursor:pointer" onclick="openNote(${n.id})"><b>${esc(n.title)}</b><span class="muted small">${new Date(n.created * 1000).toLocaleString()} · ${esc(JSON.parse(n.options).style.replace("_", " "))} · ${esc(JSON.parse(n.options).length)}</span></div><button class="ghost sm" onclick="delNote(${n.id})">${ic("x", 12)}</button></div>`).join("") || '<div class="empty"><p>No notes yet.</p></div>'; }
async function genNotes() {
 if(needStudent())return;
 const v=$('#n_src').value,uid=SID;
 if(!v)return toast('Upload course material first','err');
 $('#n_btn').disabled=true;$('#n_bar').classList.remove('hidden');
 try {
  const pending=await api('/notes/generate',{method:'POST',body:{source_id:v==='all'?null:+v,style:N_STYLE,length:N_LEN,language:$('#n_lang').value,level:$('#n_level').value,focus:$('#n_focus').value,timestamps:$('#n_ts').checked,visuals:$('#n_vis').checked}});
  const started=Date.now();
  while(SID===uid) {
   const j=await jobGet(pending.job);
   $('#n_msg').textContent=j.msg;$('#n_fill').style.width=(j.pct*100)+'%';
   if(j.status==='error')throw new Error(j.msg);
   if(j.status!=='running'){await loadNotes();if(SID===uid)await openNote(j.result.note_id);break;}
   if(Date.now()-started>600000)throw new Error('Notes are still processing. Reopen Notes later to see the result.');
   await new Promise(resolve=>setTimeout(resolve,700));
  }
 }catch(e){if(SID===uid)toast(e.message,'err');}
 finally{if(SID===uid){$('#n_btn').disabled=false;$('#n_bar').classList.add('hidden');$('#n_msg').textContent='';}refreshConnection();}
}
async function openNote(id) { const n = await api("/notes/" + id); const box = $("#n_view"); box.classList.remove("hidden");
  const html = mdNotes(n.body).replace(/\[\[U(\d+)\]\]/g, (m, u) => { const c = n.cites[u]; return c ? " " + citeBtn("", c) : ""; });
  box.innerHTML = `<div class="card-h"><h3>${esc(n.title)}</h3><div class="row tight"><button class="ghost sm" onclick="copyNote(${id})">Copy</button><a href="/api/notes/${id}/download"><button class="ghost sm">${ic("dl", 14)} Download .md</button></a><button class="ghost sm" onclick="window.print()">${ic("print", 14)} Print</button></div></div><div class="notebody">${html}</div>`; box.scrollIntoView({ behavior: "smooth" }); }
async function copyNote(id) { const t = await (await fetch(`/api/notes/${id}/download`)).text(); try { await navigator.clipboard.writeText(t); toast("Notes copied", "ok"); } catch (e) { toast("Copy failed", "err"); } }
async function delNote(id) { await api("/notes/" + id, { method: "DELETE" }); $("#n_view").classList.add("hidden"); loadNotes(); }

/* ---------- course map ---------- */
async function loadMap() { try { GRAPH = await api("/graph" + (SID ? "?student_id=" + SID : "")); } catch (e) { return toast(e.message, "err"); } const T = GRAPH.topics.filter(t => !t.parent_id);
  if (!T.length) { $("#net").innerHTML = `<div class="empty"><p>Ingest material to generate the course flow map.</p><button onclick="show('library')">Go to Library</button></div>`; return; }
  const pre = {}; GRAPH.prereqs.forEach(p => (pre[p.topic_id] = pre[p.topic_id] || []).push(p.prereq_id));
  const nm = id => GRAPH.topics.find(x => x.id === id)?.name, lvl = p => p == null ? "na" : p >= .7 ? "strong" : p >= .4 ? "dev" : "weak";
  $("#net").innerHTML = `<div class="flow">${T.slice().sort((x, y) => x.order_idx - y.order_idx).map((t, i) => { const p = t.p_eff, ps = (pre[t.id] || []).map(nm).filter(Boolean);
    return `<div class="fnode ${lvl(p)}" id="fn${t.id}" onclick="topicPanel(${t.id})"><span class="fstep">${i + 1}</span><b>${esc(t.name)}</b><div class="fbar"><i style="width:${Math.round((p || 0) * 100)}%"></i></div>
      <span class="small muted">${p == null ? "Not assessed yet" : Math.round(p * 100) + "% mastery"} · ${t.units} source unit${t.units === 1 ? "" : "s"}</span>${ps.length ? `<span class="tiny muted">Learn first: ${esc(ps.join(", "))}</span>` : ""}</div>`; }).join("")}</div>`; }
async function topicPanel(id) { $$(".fnode").forEach(n => n.classList.toggle("sel", n.id === "fn" + id)); const t = GRAPH.topics.find(x => x.id === id), subs = GRAPH.topics.filter(x => x.parent_id === id), cons = GRAPH.concepts.filter(c => c.topic_id === id); $("#topicpanel").innerHTML = skeleton(5);
  const us = await api("/units?topic_id=" + id), pre = GRAPH.prereqs.filter(p => p.topic_id === id).map(p => GRAPH.topics.find(x => x.id === p.prereq_id)?.name).filter(Boolean);
  $("#topicpanel").innerHTML = `<h3>${esc(t.name)}</h3><p class="muted small">${esc(t.summary)}</p><div class="tags"><span class="tag">${t.units} source units</span>${t.p_eff != null ? `<span class="tag ${t.p_eff >= .7 ? "ok" : ""}">mastery ${Math.round(t.p_eff * 100)}%</span>` : ""}</div>
   ${pre.length ? `<b class="small">Prerequisites</b><div class="tags">${pre.map(x => `<span class="tag acc">${esc(x)}</span>`).join("")}</div>` : ""}
   <b class="small">Subtopics</b><div class="tags">${subs.map(s => `<span class="tag">${esc(s.name)}</span>`).join("") || "—"}</div><b class="small">Key concepts</b><div class="tags">${cons.map(c => `<span class="tag">${esc(c.name)}</span>`).join("") || "—"}</div>
   <b class="small">Cited source units</b><div>${us.slice(0, 10).map(u => `<div style="margin:8px 0">${citeBtn("", u)}<div class="muted small">${esc(u.snippet.slice(0, 110))}…</div></div>`).join("")}</div><button style="margin-top:12px" onclick="practiceTopic(${id})">${ic("target", 16)} Practise this topic</button>`; }
function practiceTopic(id) { MODE = "quiz"; show("practice"); setTimeout(() => $$("#scope input").forEach(i => i.checked = +i.value === id), 250); }

/* ---------- tutor ---------- */
const md = text => preserveMath(text, t => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/^[-•] /gm, "• ").replace(/\n/g, "<br>"));
function say(t, l) { if ($("#speak").checked) speakText(t, l || "en"); }
function mic() { const R = window.SpeechRecognition || window.webkitSpeechRecognition; if (!R) return toast("Speech recognition needs Chrome or Edge", "err"); const l = ANSWER_LANG === "auto" ? "en" : ANSWER_LANG, r = new R(); r.lang = speechCode(l);
  r.onresult = e => { $("#q").value = e.results[0][0].transcript; ask(); }; r.onerror = e => toast("Voice input failed: " + e.error, "err"); toast(`Listening in ${LANGS[l]?.name || "English"}… (in Auto mode, pick a language to speak in it)`); r.start(); }
async function loadTutor() { if ($("#msgs .m")) return; let g = { topics: [] }; try { g = await api("/graph"); } catch (e) {} const T = g.topics.filter(t => !t.parent_id).slice(0, 3);
  const sug = T.length ? T.map(t => `Explain ${t.name.split(" · ")[0]}`) : [];
  $("#welcome").innerHTML = `<div class="logo" style="margin:0 auto 14px;width:54px;height:54px;border-radius:16px">${ic("spark", 26)}</div><h2>Ask your course anything</h2><p class="muted">Answers are built only from your uploaded material and cite the exact page, slide or video timestamp. Questions the material doesn't cover are flagged, never invented.</p>
   <div class="sugg">${(sug.length ? sug : []).map(s => `<button onclick='ask(${JSON.stringify(s).replace(/'/g, "&#39;")})'>${esc(s)}</button>`).join("")}</div>`; }
async function ask(text, forceOutside) { const q = (typeof text === "string" ? text : $("#q").value).trim(); if (!q) return; $("#q").value = ""; $("#welcome")?.remove(); const box = $("#msgs");
  box.insertAdjacentHTML("beforeend", `<div class="m u">${esc(q)}</div>`); const wait = document.createElement("div"); wait.className = "m a"; wait.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>'; box.append(wait); box.scrollTop = 1e9;
  try { const r = await api("/chat", { method: "POST", body: { student_id: SID, message: q, lang: $("#lang").value, style: $("#tstyle").value, allow_outside: !!forceOutside || $("#outside").checked, history: HIST.slice(-6) } });
    let h = `<span class="badge ${r.covered ? "ok" : "no"}">${ic(r.covered ? "check" : "x", 12)} ${r.covered ? (r.mode === "source_excerpts" ? "Source excerpts · AI unavailable" : "AI explanation · cited") : "Not in your material"} · coverage ${Math.round(r.coverage * 100)}%</span> <span class="badge">${esc(LANGS[r.lang]?.native || "")}</span>${r.query_en ? ` <span class="muted tiny">searched as: “${esc(r.query_en)}”</span>` : ""}<br>`;
    h += md(r.answer).replace(/\[S(\d+)\]/g, (m, n) => { const c = r.citations.find(c => c.id === "S" + n); return c ? citeBtn("S" + n, c) : ""; });
    if (r.covered && r.citations.length) h += `<div class="muted small" style="margin-top:10px">Sources: ${r.citations.map(c => citeBtn(c.id, c)).join("")}</div>`;
    if (!r.covered) h += `<div class="flag">${r.outside_answer ? `<b>${r.outside_web ? "Outside knowledge · from the web" : "Outside knowledge"} — not from your material</b><br>${md(r.outside_answer)}${(r.outside_sources || []).length ? `<div class="tiny muted" style="margin-top:8px">Web sources: ${r.outside_sources.map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || new URL(s.url).hostname)}</a>`).join(" · ")}</div>` : ""}`
      : r.outside_error ? `${esc(r.outside_error)} <a href="#" onclick='ask(${JSON.stringify(q).replace(/'/g, "&#39;")}, true);return false'>Try again →</a>`
      : `This isn't in your uploaded material. <a href="#" onclick='ask(${JSON.stringify(q).replace(/'/g, "&#39;")}, true);return false'><b>Answer with outside knowledge (web) →</b></a>`}</div>`;
    if (r.check_question) h += `<div class="flag teal"><b>Quick check</b> · ${esc(r.check_question)} <a href="#" onclick='ask(${JSON.stringify(r.check_question).replace(/'/g, "&#39;")});return false'>discuss →</a></div>`;
    if (r.signal) h += `<div class="muted tiny" style="margin-top:8px">Learner model updated · ${esc(r.signal)}</div>`;
    h += `<div style="margin-top:8px"><button class="ghost sm" onclick="speakText(this.closest('.m').dataset.t, '${r.lang}')">${ic("audio", 14)} Listen</button></div>`;
    wait.className = "m a" + (r.covered ? "" : " refuse"); wait.dataset.t = r.outside_answer || r.answer; wait.innerHTML = h; HIST.push({ role: "user", content: q }, { role: "assistant", content: r.outside_answer || r.answer }); say(r.outside_answer || r.answer, r.lang);
  } catch (e) { wait.textContent = "Error: " + e.message; } refreshConnection(); box.scrollTop = 1e9; }

/* ---------- practice ---------- */
const MODES = [["adaptive", "Adaptive quiz", "Targets your weakest and fading topics, difficulty follows mastery.", "bolt"], ["quiz", "Custom-scope quiz", "Choose exactly which topics to practise.", "target"],
  ["exam", "Mock exam", "Mixed difficulty, feedback deferred to the report. Timed.", "clock"], ["diagnostic", "Diagnostic", "Short placement quiz for new students.", "spark"]];
async function loadPractice() {
  $("#modes").innerHTML = MODES.map(([k, a, b, i]) => `<div class="mode ${k === MODE ? "on" : ""}" onclick="MODE='${k}';loadPractice()">${ic(i, 24)}<b>${a}</b><p>${b}</p></div>`).join("");
  const keep = $$("#scope input:checked").map(i => i.value); let g = { topics: [] }; try { g = await api("/graph"); } catch (e) {}
  $("#scope").innerHTML = g.topics.filter(t => !t.parent_id).map(t => `<label class="pill"><input type="checkbox" value="${t.id}" ${keep.includes(String(t.id)) ? "checked" : ""}><span>${esc(t.name)}</span></label>`).join("") || "<span class='muted'>Ingest material first.</span>"; }
async function startAssess() { if (needStudent()) return; $("#genmsg").textContent = "Generating, verifying and de-duplicating questions…"; $("#genBtn").disabled = true;
  const types = $$("#types input:checked").map(i => i.value), topics = $$("#scope input:checked").map(i => +i.value);
  const uid = SID;
  try { const pending = await api("/assess/start-job", { method: "POST", body: { student_id: uid, topic_ids: topics, n: +$("#nq").value, types, kind: MODE } });
    const result = await awaitAssessment(pending.job, uid); if (SID !== uid || !result) return; RUN = result; if (RUN.notice) toast(RUN.notice); RUN.i = 0; RUN.log = []; RUN.t0 = Date.now(); $("#setup").classList.add("hidden"); $("#runner").classList.remove("hidden"); startTimer(); renderQ(); }
  catch (e) { toast(e.message, "err"); } finally { $("#genmsg").textContent = ""; $("#genBtn").disabled = false; } }
async function awaitAssessment(jid, uid) {
  while (SID === uid) {
    const j = await jobGet(jid);
    if (j.status === "error") throw new Error(j.msg);
    if (j.status === "done") return j.result;
    $("#genmsg").textContent = j.msg + " · " + Math.round(j.pct * 100) + "%";
    await new Promise(resolve => setTimeout(resolve, 700));
  }
  return null;
}
const fmtT = s => String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
const elapsed = () => RUN ? Math.max(0, Math.floor(((RUN.pausedAt || Date.now()) - RUN.t0 - (RUN.pausedTotal || 0)) / 1000)) : 0;
function tick() { const el = $("#timer"); if (el && RUN) el.innerHTML = ic("clock", 13) + " " + (RUN.pausedAt ? "Paused · " : "Time ") + fmtT(elapsed()); }
function startTimer() { clearInterval(TIMER); RUN.pausedAt = 0; RUN.pausedTotal = 0; TIMER = setInterval(tick, 1000); tick(); }
function pauseA() { if (!RUN) return; if (RUN.pausedAt) { RUN.pausedTotal += Date.now() - RUN.pausedAt; RUN.pausedAt = 0; } else RUN.pausedAt = Date.now();
  $("#qbody")?.classList.toggle("paused", !!RUN.pausedAt); $("#pauseBtn").innerHTML = RUN.pausedAt ? ic("bolt", 14) + " Resume" : ic("clock", 14) + " Pause"; tick(); }
async function retakeA() { if (!RUN || !confirm("Retake this quiz from question 1? You get the same questions in a new order, as a fresh attempt.")) return;
  const aid = RUN.assessment_id; clearInterval(TIMER); $("#runner").innerHTML = '<div class="empty"><p>Preparing your retake…</p></div>';
  try { RUN = await api("/assess/retake/" + aid, { method: "POST" }); RUN.i = 0; RUN.log = []; RUN.t0 = Date.now(); startTimer(); renderQ(); }
  catch (e) { toast(e.message, "err"); RUN = null; $("#runner").classList.add("hidden"); $("#setup").classList.remove("hidden"); } }
function endA() { if (!RUN) return; const n = RUN.log.filter(Boolean).length; if (!RUN.pausedAt) pauseA();
  openModal(`<h2>End this quiz?</h2><p class="muted">You have answered ${n} of ${RUN.questions.length} questions.</p><div class="row">${n ? `<button onclick="closeModal();finishA()">End &amp; see report</button>` : ""}<button class="ghost" onclick="closeModal();discardA()">Discard quiz</button><button class="ghost" onclick="closeModal();pauseA()">Keep going</button></div>`, true); }
function discardA() { clearInterval(TIMER); RUN = null; $("#runner").classList.add("hidden"); $("#setup").classList.remove("hidden"); toast("Quiz discarded"); }
function renderQ() { const q = RUN.questions[RUN.i], n = RUN.questions.length; RUN.answered = false;
  $("#runner").innerHTML = `<div class="qhead"><b>Question ${RUN.i + 1} <span class="muted">of ${n}</span></b><div class="tags" style="margin:0"><span class="tag">${q.qtype}</span><span class="tag">${q.difficulty}</span><span class="tag acc">${esc(q.topic)}</span>${q.source ? `<a class="tag link" href="#" title="Open the exact place in your material where this topic is taught" onclick="openSource(RUN.questions[${RUN.i}].source);return false">▶ ${esc(q.source.source_name || "")} · ${esc(q.source.label)}</a>` : ""}${q.verified ? `<span class="tag ok" title="${esc(q.verify_note || "")}">✔ verified</span>` : ""}<span class="tag" id="timer"></span></div></div>
   <div class="qtools"><button class="ghost sm" id="pauseBtn" onclick="pauseA()">${ic("clock", 14)} Pause</button><button class="ghost sm" onclick="retakeA()">${ic("bolt", 14)} Retake</button><button class="ghost sm danger" onclick="endA()">${ic("x", 14)} End quiz</button></div>
   <div id="qbody"><div class="pausecover"><b>Quiz paused</b><span class="muted">The timer is stopped and the question is hidden.</span><button onclick="pauseA()">Resume</button></div>
   <div class="segs">${RUN.questions.map((_, i) => `<i class="${i < RUN.i ? (RUN.log[i]?.fb.correct ? "done" : "bad") : i === RUN.i ? "cur" : ""}"></i>`).join("")}</div><div class="q-stem">${esc(q.stem)}</div>
   ${q.options ? q.options.map((o, i) => `<button class="opt" onclick="submitA(this.dataset.v)" data-v="${esc(o)}"><kbd>${i + 1}</kbd>${esc(o)}</button>`).join("") : `<div class="row"><input id="ans" style="flex:1" placeholder="${q.qtype === "numerical" ? "Enter a number" : "Type your answer"}" onkeydown="if(event.key==='Enter')submitA($('#ans').value)"><button onclick="submitA($('#ans').value)">Submit</button></div>`}<div id="fb"></div></div>`; $("#ans")?.focus(); tick(); }
document.addEventListener("keydown", e => { if ($("#practice").classList.contains("hidden") || !RUN || $("#runner").classList.contains("hidden") || /INPUT|TEXTAREA/.test(e.target.tagName)) return;
  if (RUN.pausedAt) return; if (!RUN.answered && /^[1-9]$/.test(e.key)) $$(".opt")[+e.key - 1]?.click(); else if (RUN.answered && e.key === "Enter") $("#nextBtn")?.click(); });
async function submitA(v) { if (!String(v).trim() || RUN.answered || RUN.pausedAt) return; RUN.answered = true; const q = RUN.questions[RUN.i]; $$(".opt").forEach(b => b.disabled = true);
  const fb = await api("/assess/answer", { method: "POST", body: { assessment_id: RUN.assessment_id, question_id: q.id, response: String(v) } }); RUN.log[RUN.i] = { q, fb };
  $$(".opt").forEach(b => { if (b.dataset.v === fb.correct_answer && RUN.kind !== "exam") b.classList.add("ok"); else if (b.dataset.v === v) b.classList.add(RUN.kind === "exam" ? "ok" : "no"); });
  const deferred = RUN.kind === "exam", last = RUN.i === RUN.questions.length - 1;
  $("#fb").innerHTML = (deferred ? `<div class="fb" style="border-color:var(--line);background:var(--surface)">Answer recorded. Feedback is shown in the final report.</div>` : `<div class="fb ${fb.correct ? "" : "bad"}"><b>${fb.correct ? "Correct" : "Not quite"}</b>${fb.correct ? "" : ` — answer: <b>${esc(fb.correct_answer)}</b>`}<p style="margin:8px 0">${esc(fb.explanation)}</p>${fb.misconception ? `<p class="muted small"><i>Likely misconception: ${esc(fb.misconception)}</i></p>` : ""}${fb.feedback ? `<p class="small">${esc(fb.feedback)}</p>` : ""}<div class="small">Review in your material: ${citeBtn("", fb.citation)}</div></div>`)
    + `<div class="row"><button id="nextBtn" onclick="${last ? "finishA()" : "RUN.i++;renderQ()"}">${last ? "Finish & see report" : "Next question →"}</button></div>`; }
async function finishA() { clearInterval(TIMER); const r = await api("/assess/finish/" + RUN.assessment_id, { method: "POST" }); const aid = RUN.assessment_id, kind = RUN.kind, log = RUN.log;
  $("#runner").innerHTML = `<div class="rep-top">${ring(r.total ? r.score / r.total : 0)}<div style="flex:1;min-width:240px"><h2>Assessment report</h2><p class="muted">${r.score} of ${r.total} correct · ${kind}</p>${r.narrative ? `<p>${esc(r.narrative)}</p>` : ""}</div></div>
   <div class="grid2"><div><h3>Accuracy by topic</h3><div class="chartbox short" style="height:230px"><canvas id="rc"></canvas></div></div><div><h3>Mastery change</h3>${(r.mastery || []).map(m => { const a = m.before ?? 0, b = m.after; return `<div class="delta"><span class="nm">${esc(m.topic)}</span><div class="tr"><i style="width:${a * 100}%;background:var(--surface2);filter:brightness(1.8)"></i><i style="width:${b * 100}%;background:${b >= a ? "var(--good)" : "var(--bad)"};opacity:.85"></i></div><b>${Math.round(a * 100)}→${Math.round(b * 100)}%</b></div>`; }).join("") || "<p class='muted'>—</p>"}
   <h3 style="margin-top:16px">Weak topics</h3><div class="tags">${r.weak_topics.map(w => `<span class="tag" style="color:var(--bad)">${esc(w.topic)} · ${w.correct}/${w.total}</span>`).join("") || '<span class="tag ok">None 🎉</span>'}</div></div></div>
   <h3>Likely misconceptions</h3>${r.misconceptions.map(m => `<div class="fb bad"><b>${esc(m.topic)}</b> — ${esc(m.likely_misconception)}<br><span class="muted small">Q: ${esc(m.question)} · you said “${esc(m.your_answer)}”, correct “${esc(m.correct)}”</span></div>`).join("") || "<p class='muted'>None detected.</p>"}
   <h3 style="margin-top:18px">Review in your material</h3><div>${r.review_sources.map(c => citeBtn("", c)).join("") || "—"}</div><h3 style="margin-top:18px">Recommended next</h3>${r.recommendations.map(x => `<div class="rec"><div><b>${esc(x.name)}</b><span class="muted small">${esc(x.reason)}</span></div></div>`).join("")}
   ${kind === "exam" ? "<h3>Answer review</h3>" + log.map(x => `<div class="fb ${x.fb.correct ? "" : "bad"}"><b>${x.fb.correct ? "Correct" : "Incorrect"}</b> · ${esc(x.q.stem.slice(0, 140))}${x.fb.correct ? "" : `<br>Correct: <b>${esc(x.fb.correct_answer)}</b> — ${esc(x.fb.explanation || "")} ${x.fb.citation ? citeBtn("", x.fb.citation) : ""}`}</div>`).join("") : ""}
   <div class="row"><button onclick="RUN=null;$('#runner').classList.add('hidden');$('#setup').classList.remove('hidden')">New assessment</button><button class="ghost" onclick="show('dash')">${ic("chart", 16)} Dashboard</button><button class="ghost" onclick="window.open('/api/report/${aid}','_blank')">${ic("print", 16)} Printable report</button></div>`;
  chart("rc", { type: "bar", data: { labels: r.per_topic.map(t => t.topic), datasets: [{ label: "Accuracy %", data: r.per_topic.map(t => t.accuracy * 100), backgroundColor: r.per_topic.map(t => t.accuracy >= .7 ? "#34d399" : t.accuracy >= .4 ? "#fbbf24" : "#fb7185"), borderRadius: 8 }] }, options: { scales: { y: { max: 100, min: 0 } }, plugins: { legend: { display: false } } } }); }

/* ---------- dashboard ---------- */
async function loadDash() { if (!SID) { $("#dkpis").innerHTML = `<div class="card grow empty"><p>Create a learner profile to see mastery and recommendations.</p><button onclick="openIntake()">Create profile</button></div>`; return; } let d;
  try { d = await api("/dashboard/" + SID); } catch (e) { return toast(e.message, "err"); } const M = d.mastery;
  $("#dbanner").innerHTML = d.attempts.n === 0 && M.length ? `<div class="bnr"><div><b>${d.intake?.done ? "Next: take the diagnostic" : "New here? Start with a 1-minute intake chat"}</b><span class="muted small">${d.intake?.done ? "One question per topic replaces your self-ratings with evidence, so every recommendation fits you." : "It sets your starting point; a short diagnostic quiz then measures what you really know."}</span></div><div class="row">${d.intake?.done ? "" : `<button onclick="startOnboarding()">Start intake</button>`}<button class="${d.intake?.done ? "" : "ghost"}" onclick="obDiagnostic()">Take diagnostic quiz</button></div></div>` : "";
  if (d.reviews?.due_now) $("#dbanner").innerHTML += `<div class="bnr"><div><b>${d.reviews.due_now} flashcard${d.reviews.due_now > 1 ? "s" : ""} due for review</b><span class="muted small">A few minutes now keeps them from fading.</span></div><button onclick="RV_TAB='review';show('revise')">Review now</button></div>`;
  if (d.intake?.data?.minutes_per_day) $("#smin").value = Math.max(30, Math.round(d.intake.data.minutes_per_day / 30) * 30);
  if (!M.length) { $("#dkpis").innerHTML = `<div class="card grow empty"><p>Ingest material first.</p><button onclick="show('library')">Go to Library</button></div>`; return; }
  const avg = a => a.reduce((x, y) => x + y, 0) / (a.length || 1), cnt = l => M.filter(m => m.level === l).length;
  $("#dkpis").innerHTML = kpi(Math.round(avg(M.map(m => m.p_eff)) * 100), "Overall mastery", "", "%") + kpi(Math.round(avg(M.map(m => m.retrievability)) * 100), "Memory retention", "", "%") + kpi(d.attempts.n, "Questions answered") + kpi(d.attempts.n ? Math.round(d.attempts.c / d.attempts.n * 100) : 0, "Overall accuracy", "", "%") + kpi(cnt("strong"), "Strong topics", "good") + kpi(cnt("developing"), "Developing", "warn") + kpi(cnt("weak"), "Weak topics", "bad"); animateKpis("#dkpis");
  const colr = l => l === "strong" ? "#34d399" : l === "developing" ? "#fbbf24" : "#fb7185", short = s => s.length > 22 ? s.slice(0, 21) + "…" : s;
  chart("radar", { type: "radar", data: { labels: M.map(m => short(m.name)), datasets: [{ label: "Effective mastery", data: M.map(m => m.p_eff * 100), backgroundColor: "rgba(124,131,255,.25)", borderColor: "#7c83ff", pointBackgroundColor: "#7c83ff" }, { label: "Retrievability", data: M.map(m => m.retrievability * 100), backgroundColor: "rgba(56,225,198,.12)", borderColor: "#38e1c6", pointBackgroundColor: "#38e1c6" }] }, options: { scales: { r: { min: 0, max: 100, ticks: { display: false }, pointLabels: { font: { size: 11 } } } } } });
  $("#mbars").innerHTML = M.map(m => `<div class="mrow"><span class="nm" title="${esc(m.name)}">${esc(m.name)}</span><div class="tr"><i style="width:${m.p_eff * 100}%;background:${colr(m.level)}"></i></div><b>${Math.round(m.p_eff * 100)}%</b></div>`).join("") + `<p class="tiny muted">Bars show effective mastery = P(know) × forgetting-curve retention. ${M.filter(m => m.n_obs).length}/${M.length} topics have evidence so far.</p>`;
  $("#recs").innerHTML = d.recommend.map(r => `<div class="rec"><div><b>${esc(r.name)}</b><span class="muted small">${esc(r.reason)}</span><span class="tiny muted">${r.n_obs ? r.n_obs + " question" + (r.n_obs > 1 ? "s" : "") + " answered" : "no questions answered yet"}</span></div><div class="pr">${ring(r.p_eff, "sm")}</div></div>`).join("") + (d.recommend.length ? `<div class="row"><button onclick="MODE='adaptive';show('practice')">${ic("bolt", 16)} Start adaptive quiz</button></div>` : "<p>🎉 Everything looks solid.</p>");
  const T = d.trajectory || []; chart("traj", { type: "line", data: { labels: T.map((t, i) => i === 0 ? "start" : "#" + i), datasets: [{ label: "Mean mastery %", data: T.map(t => t.mean * 100), borderColor: "#7c83ff", backgroundColor: "rgba(124,131,255,.18)", fill: true, tension: .35, pointRadius: T.length > 40 ? 0 : 3, pointBackgroundColor: T.map(t => t.src === "chat" ? "#38e1c6" : "#7c83ff") }] }, options: { scales: { y: { min: 0, max: 100 } }, plugins: { legend: { display: false } } } });
  chart("hchart", { type: "line", data: { labels: d.history.map((h, i) => "#" + (i + 1) + " " + h.kind), datasets: [{ label: "Score %", data: d.history.map(h => h.score / h.total * 100), borderColor: "#38e1c6", backgroundColor: "rgba(56,225,198,.15)", fill: true, tension: .3 }] }, options: { scales: { y: { max: 100, min: 0 } }, plugins: { legend: { display: false } } } });
  if (d.student?.exam_date) { const dd = Math.ceil((new Date(d.student.exam_date) - Date.now()) / 864e5); if (dd > 0 && dd <= 60) $("#sdays").value = dd; } }
async function loadSchedule() { if (needStudent()) return; $("#sched").innerHTML = skeleton(); const d = await api(`/schedule/${SID}?days=${$("#sdays").value}&minutes=${$("#smin").value}`);
  $("#sched").innerHTML = d.map(x => `<div class="day"><b>DAY ${x.day}</b>${x.items.map(i => `<div class="slot ${i.activity.split(" ")[0]}">${esc(i.topic)}<span>${esc(i.activity)} · ${i.minutes} min${i.start_at ? " · " + esc(i.start_at) : ""}</span></div>`).join("")}</div>`).join(""); }
/* ---------- onboarding: intake conversation -> diagnostic ---------- */
let OB = null;
const obSay = (who, html) => { const c = $("#obchat"); if (!c) return; c.insertAdjacentHTML("beforeend", `<div class="ob ${who}">${html}</div>`); c.scrollTop = 1e9; };
const obChips = (key, items) => `<div class="chips">${items.map(([v, l]) => `<button class="ghost sm" onclick="obChoose('${key}', ${JSON.stringify(v).replace(/"/g, "&quot;")}, '${l.replace(/'/g, "")}')">${l}</button>`).join("")}</div>`;
const OB_STEPS = [
  { q: "Hi! What is your main goal with this course?", ui: () => `<input id="ob_v" placeholder="e.g. pass the end-semester exam" onkeydown="if(event.key==='Enter')obAnswer()"><div class="chips">${["Pass an exam", "Learn from scratch", "Revise quickly", "Go deeper"].map(x => `<button class="ghost sm" onclick="$('#ob_v').value='${x}';obAnswer()">${x}</button>`).join("")}</div><div class="row"><button onclick="obAnswer()">Next</button></div>`,
    read: () => ({ data: { goal: $("#ob_v").value.trim() }, say: $("#ob_v").value.trim() || "No specific goal" }) },
  { q: "How would you describe your current level?", ui: () => obChips("level", [["beginner", "Beginner · new to it"], ["intermediate", "Intermediate · some background"], ["advanced", "Advanced · revising"]]) },
  { q: "How much time can you study per day?", ui: () => obChips("minutes_per_day", [[20, "20 min"], [45, "45 min"], [90, "90 min"], [120, "2 hours"]]) },
  { q: "Do you have an exam date?", ui: () => `<input id="ob_v" type="date"><div class="row"><button onclick="obAnswer()">Next</button><button class="ghost" onclick="obChoose('exam_date','','No exam date')">No exam</button></div>`,
    read: () => ({ data: { exam_date: $("#ob_v").value }, say: $("#ob_v").value || "No exam date" }) },
  { q: "How comfortable are you with each topic right now? (rough guess is fine, a quiz will check it)", skip: () => !OB.topics.length,
    ui: () => `<div class="rlist">${OB.topics.map(t => `<div class="rrow"><span>${esc(t.name)}</span><span class="rmini">${[["new", "New"], ["some", "Some"], ["good", "Good"]].map(([v, l]) => `<label><input type="radio" name="r${t.id}" value="${v}"><span>${l}</span></label>`).join("")}</span></div>`).join("")}</div><div class="row"><button onclick="obAnswer()">Next</button></div>`,
    read: () => { const r = {}; OB.topics.forEach(t => { const x = document.querySelector(`input[name=r${t.id}]:checked`); if (x) r[t.id] = x.value; }); return { data: { self_rating: r }, say: Object.keys(r).length ? `Rated ${Object.keys(r).length} topics` : "Skipped" }; } },
  { q: "Anything else I should know? e.g. “I struggle with joins but I'm fine with basics”.", ui: () => `<textarea id="ob_v" rows="2" placeholder="Optional"></textarea><div class="row"><button onclick="obAnswer()">Finish</button></div>`,
    read: () => ({ data: { notes: $("#ob_v").value.trim() }, say: $("#ob_v").value.trim() || "Nothing to add" }) },
];
async function startOnboarding() { if (needStudent()) return; let t = { topics: [] }; try { t = await api("/intake/" + SID); } catch (e) {}
  OB = { topics: t.topics || [], a: { self_rating: {}, minutes_per_day: 45 }, i: 0 };
  openModal(`<h2>Let's get to know you</h2><p class="muted small">About a minute. It sets your starting point; a short diagnostic quiz then replaces guesses with evidence.</p><div id="obchat" class="obchat"></div><div id="obin" class="obin"></div>`, true); obNext(); }
function obNext() { while (OB.i < OB_STEPS.length && OB_STEPS[OB.i].skip?.()) OB.i++; if (OB.i >= OB_STEPS.length) return obFinish(); const st = OB_STEPS[OB.i]; obSay("bot", st.q); $("#obin").innerHTML = st.ui(); $("#obin input,#obin textarea")?.focus(); }
function obChoose(key, val, label) { OB.a[key] = val; obSay("me", esc(label)); OB.i++; obNext(); }
function obAnswer() { const r = OB_STEPS[OB.i].read(); Object.assign(OB.a, r.data); obSay("me", esc(r.say)); OB.i++; obNext(); }
async function obFinish() { $("#obin").innerHTML = skeleton(1);
  try { await api("/intake/" + SID, { method: "POST", body: OB.a }); } catch (e) { $("#obin").innerHTML = ""; return toast(e.message, "err"); }
  const n = OB.topics.length; obSay("bot", n ? `Thanks! I've set your starting point. Next, a short diagnostic: about one question per topic (${n}), so I can measure what you really know instead of guessing.` : "Thanks! I've saved your profile. Upload your material in the Library, then take the diagnostic from the Practice tab and I'll personalise everything.");
  $("#obin").innerHTML = n ? `<div class="row"><button onclick="obDiagnostic()">Start diagnostic</button><button class="ghost" onclick="closeModal();show('dash')">Later</button></div>` : `<div class="row"><button onclick="closeModal();show('library')">Go to Library</button></div>`; }
function obDiagnostic() { closeModal(); MODE = "diagnostic"; show("practice"); setTimeout(() => { const nq = $("#nq"); if (nq) { nq.value = Math.min(Math.max((GRAPH?.topics || []).filter(t => !t.parent_id).length, 6), 12); $("#nqv").textContent = nq.value; } startAssess(); }, 500); }

/* ---------- revise: flashcards, slides, audio briefs ---------- */
let RV_TAB = "pack";
const RV_TABS = [["pack", "Revision pack"], ["review", "Spaced review"], ["audio", "Audio overview"], ["teach", "Teach-back"], ["glossary", "Glossary"]];
async function loadRevise() { if (needStudent()) return; rvTab(RV_TAB); }
function rvTab(k) { RV_TAB = k; window.speechSynthesis?.cancel(); $("#rv_tabs").innerHTML = RV_TABS.map(([id, l]) => `<label class="${id === k ? "on" : ""}" onclick="rvTab('${id}')"><span>${l}</span></label>`).join("");
  ({ pack: panelPack, review: panelReview, audio: panelAudio, teach: panelTeach, glossary: panelGlossary })[k](); }
function panelPack() { $("#rv_body").innerHTML = `<div class="card"><div class="card-h"><h3>Revision pack for your weak topics</h3><span class="chip">flashcards · slides · audio brief</span></div>
  <p class="muted">Built only from your uploaded material. Cards and slides use passages from your material with source links. Your weakest topics appear first.</p>
  <div class="row"><label class="inl">Topics<select id="rev_n"><option>1</option><option selected>3</option><option>5</option></select></label><button onclick="buildRevision()">Build revision pack</button><button id="rev_dl" class="ghost hidden">Download slides (.pptx)</button></div></div><div id="revout"></div>`;
  buildRevision(); }
const fmtIv = d => d < 1 / 24 ? Math.max(1, Math.round(d * 1440)) + "m" : d < 1 ? Math.round(d * 24) + "h" : d < 30 ? (Math.round(d * 10) / 10) + "d" : Math.round(d / 30) + "mo";

/* ----- spaced review ----- */
let RVW = { cards: [], i: 0, shown: false, stats: {} };
async function panelReview() { $("#rv_body").innerHTML = skeleton(); await rvwLoad(); }
async function rvwLoad() { let d; try { d = await api(`/review/${SID}/due`); } catch (e) { $("#rv_body").innerHTML=`<div class="card"><p>${esc(e.message)}</p><button onclick="rvwLoad()">Try again</button></div>`; return; } RVW = { cards: d.cards, i: 0, shown: false, stats: d }; rvwRender(); }
function rvwStats() { const t = RVW.stats; return `<div class="kpis">${kpi(t.due_now || 0, "Due now", t.due_now ? "warn" : "good")}${kpi(t.new || 0, "New cards")}${kpi(t.total || 0, "In your deck")}${kpi(t.mature || 0, "Mature (21d+)", "good")}${kpi(t.reviewed_today || 0, "Reviewed today")}</div>`; }
function rvwRender() { const c = RVW.cards[RVW.i], t = RVW.stats;
  const top = `<div class="card"><div class="card-h"><h3>Spaced review</h3><div class="row"><button class="ghost sm" onclick="rvwBuild()">+ Add cards from my weak topics</button><button class="ghost sm" onclick="location.href='/api/export/${SID}/anki.tsv'">Export to Anki</button></div></div>
    <p class="muted small">Cards come back just before you would forget them (SM-2 scheduling). Each answer also updates your mastery, so quizzes and recommendations adapt to what you actually remember.</p>${rvwStats()}</div>`;
  if (!t.total) { $("#rv_body").innerHTML = top + `<div class="card empty"><p>Your deck is empty. Add cards from your weakest topics to start.</p></div>`; return; }
  if (!c) { $("#rv_body").innerHTML = top + `<div class="card empty"><h3>All caught up 🎉</h3><p class="muted">Nothing is due right now. Come back later, or add cards from more topics.</p></div>`; return; }
  $("#rv_body").innerHTML = top + `<div class="card rvcard"><div class="small muted">Card ${RVW.i + 1} of ${RVW.cards.length} ${c.new ? "· new" : "· review"}</div><div class="rvfront">${esc(c.front)}</div>
    ${RVW.shown ? `<div class="rvback">${esc(c.back)}</div><div class="fsrc">${c.source ? `<a class="tag link" href="#" onclick="openSource(RVW.cards[RVW.i].source);return false">▶ ${esc(c.source.source_name || "")} · ${esc(c.source.label)}</a>` : ""}</div>
      <div class="row rvgrades">${[["again", "Again"], ["hard", "Hard"], ["good", "Good"], ["easy", "Easy"]].map(([g, l]) => `<button class="${g === "again" ? "ghost danger" : g === "easy" ? "" : "ghost"}" onclick="rvwGrade('${g}')">${l}<span>${fmtIv(c.preview[g])}</span></button>`).join("")}</div>`
      : `<div class="row"><button onclick="RVW.shown=true;rvwRender()">Show answer</button></div>`}</div>`; }
async function rvwGrade(g) { const c = RVW.cards[RVW.i]; try { RVW.stats = { ...RVW.stats, ...(await api(`/review/${SID}/grade`, { method: "POST", body: { id: c.id, grade: g } })) }; } catch (e) { return toast(e.message, "err"); }
  if (g === "again") RVW.cards.push({ ...c, new: false }); RVW.i++; RVW.shown = false; rvwRender(); }
async function rvwBuild() { toast("Building cards from your weak topics…"); try { const r = await api(`/review/${SID}/build`, { method: "POST", body: { per_topic: 8, lang: ANSWER_LANG === "auto" ? "en" : ANSWER_LANG } }); toast(`Added ${r.added} new cards`, "ok"); await rvwLoad(); } catch (e) { toast(e.message, "err"); } }

/* ----- two-host audio overview ----- */
let POD = null, PODI = 0, PODPLAY = false, PODRATE = 1;
async function panelAudio() { const d = await api("/dashboard/" + SID).catch(() => ({ mastery: [] })), ms = (d.mastery || []).slice().sort((a, b) => a.p_eff - b.p_eff);
  $("#rv_body").innerHTML = `<div class="card"><div class="card-h"><h3>Audio overview</h3><span class="chip">two hosts · built from your weakest topics</span></div>
    <p class="muted">Like a podcast about <i>your</i> material, but personalised: it focuses on what you know least, every factual line has its source, and anything the material does not support is dropped. Press “Ask a question” any time to interrupt.</p>
    <div class="chips">${ms.slice(0, 8).map(m => `<label class="pill"><input type="checkbox" class="podt" value="${m.topic_id}"><span>${esc(m.name)} · ${Math.round(m.p_eff * 100)}%</span></label>`).join("")}</div>
    <div class="row"><button onclick="podBuild()">Create overview</button><span class="muted small">(none selected = your 3 weakest topics)</span></div></div><div id="podout"></div>`; if (POD) podRender(); }
async function podBuild() { $("#podout").innerHTML = skeleton(); const topics = $$(".podt:checked").map(x => +x.value);
  try { POD = await api(`/podcast/${SID}`, { method: "POST", body: { topics, lang: ANSWER_LANG === "auto" ? "en" : ANSWER_LANG } }); } catch (e) { $("#podout").innerHTML = ""; return toast(e.message, "err"); } PODI = 0; PODPLAY = false; podRender(); }
function podRender() { const g = POD.grounding;
  $("#podout").innerHTML = `<div class="card"><div class="card-h"><h3>${esc(POD.title)}</h3><span class="chip ${g.dropped ? "warn" : "ok"}">${g.dropped ? g.dropped + " unsupported line(s) removed" : "✔ every factual line traced to your material"}</span></div>
    <div class="row"><button id="podplay" onclick="podToggle()">${ic("audio", 15)} Play</button><button class="ghost sm" onclick="podStep(-1)">‹ Prev</button><button class="ghost sm" onclick="podStep(1)">Next ›</button>
    <label class="inl">Speed<select onchange="PODRATE=+this.value"><option value="0.85">0.85×</option><option value="1" selected>1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option></select></label>
    <button class="ghost sm" onclick="podScript()">Download transcript</button></div>
    <div class="row"><input id="podq" placeholder="Interrupt: ask a question about this topic…" onkeydown="if(event.key==='Enter')podAsk()" style="flex:1"><button class="ghost" onclick="podAsk()">Ask</button></div><div id="podans"></div>
    <div class="pod">${POD.turns.map((t, i) => `<div class="pt ${t.speaker === "Alex" ? "a" : "s"}" id="pt${i}" onclick="podJump(${i})"><b>${t.speaker}</b><span>${esc(t.text)}</span>${t.source ? `<a class="tag link" href="#" onclick="event.stopPropagation();openSource(POD.turns[${i}].source);return false">▶ ${esc(t.source.label)}</a>` : ""}</div>`).join("")}</div></div>`; podMark(); }
function podMark() { $$(".pt").forEach((e, i) => e.classList.toggle("now", i === PODI)); $("#pt" + PODI)?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
function podVoice(host) { const vs = (speechSynthesis.getVoices() || []).filter(v => v.lang.toLowerCase().startsWith(speechCode(POD.lang).slice(0, 2).toLowerCase())); if (vs.length > 1) return vs[host === "Alex" ? 0 : 1]; return vs[0] || null; }
function podSay(i) { if (!window.speechSynthesis) return toast("Speech output is not supported in this browser", "err"); speechSynthesis.cancel(); if (i >= POD.turns.length) { PODPLAY = false; $("#podplay").innerHTML = ic("audio", 15) + " Play"; return; } PODI = i; podMark();
  const t = POD.turns[i], u = new SpeechSynthesisUtterance(t.text); u.lang = speechCode(POD.lang); u.rate = PODRATE; u.pitch = t.speaker === "Alex" ? 0.9 : 1.2; const v = podVoice(t.speaker); if (v) u.voice = v;
  u.onend = () => { if (PODPLAY) podSay(i + 1); }; speechSynthesis.speak(u); }
function podToggle() { PODPLAY = !PODPLAY; $("#podplay").innerHTML = ic("audio", 15) + (PODPLAY ? " Pause" : " Play"); if (PODPLAY) podSay(PODI); else speechSynthesis.cancel(); }
function podStep(d) { PODI = Math.min(Math.max(PODI + d, 0), POD.turns.length - 1); podMark(); if (PODPLAY) podSay(PODI); }
function podJump(i) { PODI = i; podMark(); PODPLAY = true; $("#podplay").innerHTML = ic("audio", 15) + " Pause"; podSay(i); }
function podScript() { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([POD.title + "\n\n" + POD.turns.map(t => `${t.speaker}: ${t.text}${t.source ? `  [${t.source.source_name} · ${t.source.label}]` : ""}`).join("\n\n")], { type: "text/plain" })); a.download = "audio-overview.txt"; a.click(); }
async function podAsk() { const q = $("#podq").value.trim(); if (!q) return; PODPLAY = false; speechSynthesis.cancel(); $("#podplay").innerHTML = ic("audio", 15) + " Play"; $("#podans").innerHTML = skeleton(1);
  try { const r = await api("/chat", { method: "POST", body: { student_id: SID, message: q, history: [], lang: ANSWER_LANG, allow_outside: false, style: "standard" } });
    $("#podans").innerHTML = `<div class="flag ${r.covered ? "ok" : ""}"><b>${r.covered ? "From your material" : "Not in your material"}</b><br>${md(r.answer)}</div>`; speakText(r.answer, r.lang || "en"); $("#podq").value = ""; } catch (e) { $("#podans").innerHTML = ""; toast(e.message, "err"); } }

/* ----- teach-back ----- */
async function panelTeach() { const t = await api("/intake/" + SID).catch(() => ({ topics: [] })), h = await api(`/teachback/${SID}/history`).catch(() => []);
  $("#rv_body").innerHTML = `<div class="card"><div class="card-h"><h3>Teach-back</h3><span class="chip">explain it in your own words</span></div>
    <p class="muted">The best test of understanding: explain a topic as if teaching a friend. StudyPilot checks your explanation against your material: which key ideas you covered, which you missed (with where to find them), and which sentences your material does <b>not</b> support — possible misconceptions.</p>
    <div class="row"><label class="inl">Topic<select id="tb_topic">${t.topics.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join("")}</select></label></div>
    <textarea id="tb_text" rows="6" placeholder="Explain it in your own words…" style="width:100%"></textarea><div class="row"><button onclick="tbCheck()">Check my explanation</button>${h.length ? `<span class="muted small">${h.length} previous teach-back${h.length > 1 ? "s" : ""} · last score ${Math.round(h[0].score * 100)}%</span>` : ""}</div></div><div id="tbout"></div>`; }
async function tbCheck() { const text = $("#tb_text").value.trim(); $("#tbout").innerHTML = skeleton();
  let r; try { r = await api(`/teachback/${SID}`, { method: "POST", body: { topic_id: +$("#tb_topic").value, text, lang: ANSWER_LANG === "auto" ? "en" : ANSWER_LANG } }); } catch (e) { $("#tbout").innerHTML = ""; return toast(e.message, "err"); }
  window._tb = r; $("#tbout").innerHTML = `<div class="card"><div class="card-h"><h3>${esc(r.topic)}</h3><div class="row">${ring(r.score, "sm")}<span class="chip">coverage ${Math.round(r.coverage * 100)}% · accuracy ${Math.round(r.accuracy * 100)}%</span></div></div><p>${esc(r.feedback)}</p>
    ${r.covered.length ? `<h4>You explained</h4><div class="chips">${r.covered.map(c => `<span class="chip ok">✔ ${esc(c)}</span>`).join("")}</div>` : ""}
    ${r.missing.length ? `<h4>Still missing</h4><ul>${r.missing.map((m, i) => `<li><b>${esc(m.concept)}</b>${m.hint ? ` — ${esc(m.hint)}` : ""} ${m.source ? `<a class="tag link" href="#" onclick="openSource(_tb.missing[${i}].source);return false">▶ ${esc(m.source.source_name || "")} · ${esc(m.source.label)}</a>` : ""}</li>`).join("")}</ul>` : ""}
    ${r.flagged.length ? `<h4>Not supported by your material <span class="muted small">· possible misconceptions, check the sources</span></h4><ul>${r.flagged.map(f => `<li class="flagged">${esc(f)}</li>`).join("")}</ul>` : ""}</div>`; }

/* ----- glossary ----- */
async function panelGlossary() { $("#rv_body").innerHTML = skeleton(); let g; try { g = await api("/glossary"); } catch (e) { $("#rv_body").innerHTML=`<div class="card"><p>${esc(e.message)}</p><button onclick="panelGlossary()">Try again</button></div>`; return; } window._gl = g;
  $("#rv_body").innerHTML = `<div class="card"><div class="card-h"><h3>Glossary</h3><span class="chip">${g.length} terms · each defined by a sentence from your material</span></div><input id="gl_q" placeholder="Search terms…" oninput="glFilter()" style="width:100%"><div id="gl_list"></div></div>`; glFilter(); }
function glFilter() { const q = ($("#gl_q")?.value || "").toLowerCase(), g = window._gl.map((x, i) => [x, i]).filter(([x]) => !q || x.term.toLowerCase().includes(q) || x.definition.toLowerCase().includes(q));
  $("#gl_list").innerHTML = g.length ? g.map(([x, i]) => `<div class="gl"><b>${esc(x.term)}</b><span class="muted small"> · ${esc(x.topic)}</span><p>${esc(x.definition)}</p><a class="tag link" href="#" onclick="openSource(_gl[${i}].source);return false">▶ ${esc(x.source.source_name || "")} · ${esc(x.source.label)}</a></div>`).join("") : `<p class="muted">No matching terms.</p>`; }
const srcLink = (src, ti, kind, ci) => src ? `<a class="tag link" href="#" onclick="event.stopPropagation();openSource(_rev[${ti}].${kind}[${ci}].source);return false">▶ ${esc(src.source_name || "")} · ${esc(src.label)}</a>` : "";
let revisionRequest=0;
async function buildRevision() { if (needStudent()) return; const uid=SID,version=++revisionRequest; $("#revout").innerHTML = skeleton(); $("#rev_dl").classList.add("hidden");
  const rl = ANSWER_LANG === "auto" ? "en" : ANSWER_LANG; let d; try { d = await api(`/revision/${SID}?lang=${rl}&n=${$("#rev_n").value}`); } catch (e) { $("#revout").innerHTML = `<div class="card"><p>${esc(e.message)}</p><button onclick="buildRevision()">Try again</button></div>`; return; }
  if(SID!==uid || version!==revisionRequest || RV_TAB!=="pack" || !$("#revout"))return;
  window._rev = d; renderRevision(d, rl); }
function renderRevision(d, rl) { rl = rl || (ANSWER_LANG === "auto" ? "en" : ANSWER_LANG); window._sl = {}; window.speechSynthesis?.cancel();
  if (!d.length) { $("#revout").innerHTML = `<div class="card empty"><p>No readable material yet. Upload course material to build a revision pack.</p></div>`; return; }
  $("#rev_dl").classList.remove("hidden"); $("#rev_dl").onclick = () => { location.href = `/api/revision/${SID}/slides.pptx?topics=${d.map(t => t.topic_id).join(",")}&lang=${rl}`; };
  $("#revout").innerHTML = d.map((t, ti) => { const g = t.grounding, drop = g.cards_dropped + g.bullets_dropped;
    return `<div class="card revt"><div class="card-h"><h3>${esc(t.topic)}</h3><div class="row">${ring(t.p_eff, "sm")}<span class="chip ${drop ? "warn" : "ok"}" title="Every card, bullet and sentence is checked against your uploaded material.">${drop ? `${drop} unsupported item${drop > 1 ? "s" : ""} removed` : "✔ all items traced to your material"} · brief ${Math.round(g.brief_supported_pct * 100)}% supported</span></div></div>
    <h4>Flashcards <span class="muted small">· click to flip</span></h4>${t.flashcards.length ? `<div class="cards">${t.flashcards.map((f, ci) => `<div class="fc" onclick="this.classList.toggle('flip')"><div class="fi"><div class="ff">${esc(f.front)}</div><div class="fk">${esc(f.back)}</div></div></div><div class="fsrc">${srcLink(f.source, ti, "flashcards", ci)}</div>`).join("")}</div>` : `<p class="muted small">Not enough material in this topic for grounded flashcards.</p>`}
    <h4>Slides</h4><div id="sl_${ti}"></div>
    <h4>Audio brief</h4><p class="muted small">${esc(t.audio_brief)}</p><div class="row"><button class="ghost sm" onclick="revPlay(${ti})">${ic("audio", 15)} Play</button><button class="ghost sm" onclick="revPause()">Pause / resume</button><button class="ghost sm" onclick="speechSynthesis.cancel()">Stop</button><button class="ghost sm" onclick="revScript(${ti})">Download script</button></div>
    ${t.sources.length ? `<p class="tiny muted">Sources used: ${t.sources.map(esc).join(" · ")}</p>` : ""}</div>`; }).join(""); d.forEach((_, ti) => revSlide(ti, 0)); }
function revSlide(ti, dir) { const t = _rev[ti], n = t.slides.length, el = $("#sl_" + ti); if (!el) return; if (!n) { el.innerHTML = `<p class="muted small">Not enough material for slides.</p>`; return; }
  const i = _sl[ti] = (((_sl[ti] || 0) + dir) % n + n) % n, s = t.slides[i];
  el.innerHTML = `<div class="slide"><div class="stitle">${esc(s.title)}</div><ul>${s.bullets.map(b => `<li>${esc(b)}</li>`).join("")}</ul><div class="sfoot">${srcLink(s.source, ti, "slides", i)}<span class="muted small">${i + 1} / ${n}</span></div></div><div class="row"><button class="ghost sm" onclick="revSlide(${ti},-1)">‹ Prev</button><button class="ghost sm" onclick="revSlide(${ti},1)">Next ›</button></div>`; }
function revPlay(ti) { speakText(_rev[ti].audio_brief, _rev[ti].lang || "en"); }
function revPause() { if (!window.speechSynthesis) return; speechSynthesis.paused ? speechSynthesis.resume() : speechSynthesis.pause(); }
function revScript(ti) { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([_rev[ti].topic + "\n\n" + _rev[ti].audio_brief], { type: "text/plain" })); a.download = "audio-brief-" + _rev[ti].topic.replace(/\W+/g, "-").toLowerCase() + ".txt"; a.click(); }
/* ---------- evaluation ---------- */
const EVAL_URL = { rag: "/eval/rag?n=20", sim: "/eval/sim?students=30", fw: "/eval/framework?n=10" };
async function runEval(k) { try { if (k === "audit") { $("#evmsg").textContent = "Auditing…"; await api("/eval/audit", { method: "POST" }); $("#evmsg").textContent = ""; toast("Audit complete", "ok"); return loadEval(); }
  const r = await api(EVAL_URL[k], { method: "POST" }); $("#evbar").classList.remove("hidden");
  const t = setInterval(async () => { const j = await jobGet(r.job); $("#evmsg").textContent = j.msg; $("#evfill").style.width = j.pct * 100 + "%"; if (j.status !== "running") { clearInterval(t); $("#evbar").classList.add("hidden"); $("#evmsg").textContent = ""; if (j.status === "error") toast(j.msg, "err"); else toast("Evaluation complete", "ok"); loadEval(); } }, 800); } catch (e) { $("#evmsg").textContent = ""; toast(e.message, "err"); } }
const gauge = (l, v, hint) => `<div class="gauge">${v == null ? '<b class="muted">—</b>' : ring(v, "sm")}<b style="font:600 14px Sora">${l}</b><span>${hint}</span></div>`;
const pc = v => v == null ? "—" : Math.round(v * 100) + "%", caveats = a => (a || []).length ? `<ul class="tiny muted">${a.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
async function loadEval() { const e = await api("/eval/results"); let h = "";
  if (e.rag) { const R = e.rag, m = R.team_set || R.metrics, miss = R.rows.filter(r => r.in_scope && (r.declined || r.context_recall === 0)).slice(0, 6);
    h += `<div class="card"><div class="card-h"><h3>Answer quality ${R.team_set ? "· team test set" : ""}</h3><span class="chip">${esc(R.framework || "")} · ${esc(R.provider)} · ${m.n_in_scope} questions with known source + ${m.n_off_material} off-material</span></div>
      <div class="gauges">${gauge("Faithfulness", m.faithfulness, "claims supported by context")}${gauge("Answer relevancy", m.answer_relevancy, "answers the question asked")}${gauge("Context precision", m.context_precision, "relevant chunks ranked first")}${gauge("Context recall", m.context_recall, "right source retrieved")}</div>
      <div class="kpis">${kpi(Math.round((m.hit_at_1 || 0) * 100), "Top-1 retrieval hit", "", "%")}${kpi(+(m.mrr || 0).toFixed(2), "MRR", "", "", 2)}${kpi(Math.round((m.citation_accuracy || 0) * 100), "Citation accuracy", "", "%")}${kpi(Math.round((m.context_recall_ref || 0) * 100), "Reference recall", "", "%")}${kpi(Math.round((m.correct_refusal_rate_off_material || 0) * 100), "Off-material declined", "good", "%")}${R.adjacent_refusal_rate != null ? kpi(Math.round(R.adjacent_refusal_rate * 100), "Adjacent-topic declined", "warn", "%") : ""}</div>
      ${miss.length ? `<details><summary class="small">Where it failed (${miss.length})</summary><ul class="small">${miss.map(r => `<li>${esc(r.question)} — ${r.declined ? "declined" : "wrong source retrieved"}</li>`).join("")}</ul></details>` : ""}${caveats(R.caveats)}</div>`; }
  if (e.deepeval) { const D = e.deepeval, m = D.metrics;
    h += `<div class="card"><div class="card-h"><h3>DeepEval run</h3><span class="chip">${esc(D.framework)} · judge: ${esc(D.judge)} · ${D.n_answered}/${D.n_questions} answered${D.metric_errors ? " · " + D.metric_errors + " metric errors" : ""}</span></div>
      <div class="gauges">${gauge("Faithfulness", m.faithfulness, "FaithfulnessMetric")}${gauge("Answer relevancy", m.answer_relevancy, "AnswerRelevancyMetric")}${gauge("Context precision", m.context_precision, "ContextualPrecisionMetric")}${gauge("Context recall", m.context_recall, "ContextualRecallMetric")}</div>${caveats(D.caveats)}</div>`; }
  if (e.audit) { const K = e.audit.kb, Q = e.audit.questions, LM = Q.learner_model;
    h += `<div class="card"><div class="card-h"><h3>Knowledge-base integrity</h3><span class="chip ${K.pass ? "ok" : "warn"}">${K.pass ? "✔ every unit traced to its origin" : "needs attention"}</span></div>
      <div class="kpis">${kpi(Math.round(K.units_with_origin * 100), "Units with page / slide / timestamp", "good", "%")}${kpi(K.topics, "Topics")}${kpi(K.concepts, "Concepts")}${kpi(K.prereq_edges, "Prerequisite links")}${kpi(Math.round(K.topics_with_concepts * 100), "Topics with concepts", "", "%")}</div>
      <p class="small muted">Prerequisite graph ${K.prereq_graph_acyclic ? "is acyclic ✔" : "HAS A CYCLE ✖"} · ${Object.entries(K.by_source_kind).map(([k, v]) => `${k}: ${v.with_origin}/${v.units} traced`).join(" · ")}</p></div>
    <div class="card"><div class="card-h"><h3>Question &amp; tag quality</h3><span class="chip">${Q.questions} questions · ${Q.attempts || 0} real attempts</span></div>${Q.note ? `<p class="muted">${esc(Q.note)}</p>` : `
      <div class="kpis">${kpi(Math.round((Q.verified_rate || 0) * 100), "Passed verification", "good", "%")}${kpi(Math.round((Q.answer_key_supported || 0) * 100), "Answer key found in source", "", "%")}${kpi(Math.round((Q.mcq_well_formed || 0) * 100), "MCQs well-formed", "", "%")}${kpi(Math.round((Q.topic_tag_agreement_top3 || 0) * 100), "Topic tag agrees with retrieval", "", "%")}${LM ? kpi(+(LM.skill_score * 100).toFixed(1), "Learner-model skill vs base rate", LM.skill_score > 0 ? "good" : "bad", "%", 1) : ""}</div>
      ${Q.correct_rate_by_difficulty ? `<p class="small muted">Observed correct rate by difficulty tag: ${Object.entries(Q.correct_rate_by_difficulty).map(([k, v]) => `${k} ${pc(v.rate)} (n=${v.n})`).join(" · ")} ${Q.difficulty_tags_monotonic === true ? "— tags track real difficulty ✔" : Q.difficulty_tags_monotonic === false ? "— difficulty tags are NOT monotonic ✖" : ""}</p>` : ""}
      ${LM ? `<div class="grid2"><div class="chartbox"><canvas id="c4"></canvas></div><p class="small muted">Learner model replayed over every real answer, using only evidence available <i>before</i> each answer. Brier ${LM.brier} vs ${LM.brier_base_rate} for a constant guess; first half ${LM.brier_first_half} → second half ${LM.brier_second_half} (lower = better, so predictions should improve as data accumulates).</p></div>` : `<p class="small muted">Answer at least 20 quiz questions to see how well the learner model predicts your answers.</p>`}${caveats(Q.caveats)}`}</div>`; }
  if (e.sim) { const a = e.sim.adaptive, b = e.sim.random, ai = e.sim.adaptive_intake, c = e.sim.comparison, g = e.sim.data_growth, ia = e.sim.intake_ablation;
    h += `<div class="card"><div class="card-h"><h3>Simulated students</h3><span class="chip">${e.sim.config.students} synthetic students × ${e.sim.config.sessions} sessions</span></div><div class="kpis">${kpi((a.mean_gain * 100).toFixed(1), "Mastery gain, adaptive (pts)", "good", "", 1)}${ai ? kpi((ai.mean_gain * 100).toFixed(1), "…with intake chat (pts)", "good", "", 1) : ""}${kpi((b.mean_gain * 100).toFixed(1), "Mastery gain, random (pts)", "bad", "", 1)}${kpi((a.repetition_rate * 100).toFixed(1), "Question repetition, adaptive", "good", "%", 1)}${kpi((b.repetition_rate * 100).toFixed(1), "Question repetition, random", "bad", "%", 1)}</div>
      ${g ? `<p class="small"><b>Personalisation improves with data:</b> the learner model is ${pc(g.vs_prior_only_first)} → ${pc(g.vs_prior_only_last)} more accurate than a never-learning prior-only model; raw estimation error ${g.estimation_mae_first} → ${g.estimation_mae_last}; rank correlation with true mastery ${g.rank_corr_first} → ${g.rank_corr_last}; share of questions aimed at the truly weakest topics ${pc(g.targeting_first_session)} → ${pc(g.targeting_last_session)} (random baseline ${pc(g.targeting_random_baseline)}).</p>` : ""}
      ${ia ? `<p class="small"><b>Intake chat:</b> estimation error right after the diagnostic ${ia.mae_after_diagnostic_without_intake} without intake vs ${ia.mae_after_diagnostic_with_intake} with it (self-ratings simulated with noise sd ${ia.self_rating_noise_sd}).</p>` : ""}
      <div class="grid2"><div class="chartbox"><canvas id="c1"></canvas></div><div class="chartbox"><canvas id="c2"></canvas></div></div><div class="chartbox" style="margin-top:12px"><canvas id="c3"></canvas></div>${caveats(e.sim.assumptions)}</div>`; }
  $("#evout").innerHTML = h || `<div class="card empty"><p>No results yet — run an evaluation above. Results are saved here.</p></div>`; animateKpis("#evout");
  const line = (lab, ds, title, o = {}) => ({ type: "line", data: { labels: lab, datasets: ds }, options: { plugins: { title: { display: true, text: title } }, ...o } }), ln = (l, d, c) => ({ label: l, data: d, borderColor: c, tension: .3 });
  if (e.sim) { const a = e.sim.adaptive, b = e.sim.random, ai = e.sim.adaptive_intake, S = x => x.map((_, i) => i === 0 ? "diagnostic" : "s" + i);
    chart("c1", line(a.mastery_curve.map((_, i) => i === 0 ? "start" : i === 1 ? "diagnostic" : "session " + (i - 1)), [ln("Adaptive (ours)", a.mastery_curve, "#38e1c6"), ...(ai ? [ln("Adaptive + intake", ai.mastery_curve, "#7c83ff")] : []), ln("Random baseline", b.mastery_curve, "#fb7185")], "True mastery (simulated)"));
    chart("c2", line(S(a.estimation_mae_by_session), [ln("Adaptive", a.estimation_mae_by_session, "#38e1c6"), ...(ai ? [ln("Adaptive + intake", ai.estimation_mae_by_session, "#7c83ff")] : []), ln("Random", b.estimation_mae_by_session, "#fb7185")], "Learner-model error (MAE, lower = better)"));
    if (a.targeting_by_session) chart("c3", line(a.targeting_by_session.map((_, i) => "session " + (i + 1)), [ln("Adaptive", a.targeting_by_session, "#38e1c6"), ln("Random", b.targeting_by_session, "#fb7185")], "Share of questions aimed at the truly weakest third of topics", { scales: { y: { min: 0, max: 1 } } })); }
  const LM = e.audit?.questions?.learner_model; if (LM) chart("c4", { type: "bar", data: { labels: LM.calibration.map(c => c.bin), datasets: [{ label: "Predicted P(correct)", data: LM.calibration.map(c => c.predicted), backgroundColor: "#7c83ff" }, { label: "Observed", data: LM.calibration.map(c => c.observed), backgroundColor: "#38e1c6" }] }, options: { plugins: { title: { display: true, text: "Calibration: predicted vs observed" } }, scales: { y: { min: 0, max: 1 } } } }); }

/* ---------- boot ---------- */
(async () => { try { document.documentElement.dataset.theme = localStorage.getItem("sp-theme") || "dark"; } catch (e) {} paintTheme(); themeChart();
  try { paintConnection(await api("/config")); } catch(e) { $("#status").classList.remove("hidden"); $("#mode").textContent="Backend unavailable · start server"; $("#status").title=e.message; }
  try { LANGS=await api("/languages"); } catch(e) { LANGS={en:{native:"English",name:"English",speech:"en-IN"}}; }
  fillLangSelects();
  await loadStudents(); show("library"); if (!SID) openIntake(); })();

/* ---------- study cockpit ---------- */
async function loadCockpit() {
  const host = $("#cockpitBody"), uid = SID;
  if (!uid) { host.innerHTML = '<div class="card empty"><p>Create a learner and upload your course to build your study plan.</p><button onclick="openIntake()">Create learner</button></div>'; return; }
  host.innerHTML = skeleton();
  try {
    const d = await api('/cockpit/' + uid);
    if (SID !== uid) return;
    const days = d.student.exam_date ? Math.round((new Date(d.student.exam_date + 'T00:00:00') - new Date(new Date().toDateString())) / 86400000) : null;
    const dateLabel = days === null ? 'Set an exam date when creating a learner to track your countdown.' : days < 0 ? 'Exam date has passed.' : days + ' day(s) until your exam.';
    host.innerHTML = '<div class="card"><span class="eyebrow">Your goal</span><h3>' + esc(d.student.goal || 'Build confidence in your course') + '</h3><p class="muted">' + esc(dateLabel) + '</p></div>' +
      '<div class="kpis">' + kpi(d.practised, 'Topics practised / ' + d.topics) + kpi(d.strong, 'Practised topics above 70%', 'good') + kpi(d.reviews.due_now, 'Cards due now', 'warn') + kpi(d.mistakes.length, 'Mistakes to repair') + '</div>' +
      '<div class="grid2"><div class="card"><div class="card-h"><h3>Today’s study mission</h3><span class="chip">about 20 minutes</span></div>' +
      '<div class="mission"><b>1 · Recall · 5 min</b><p class="muted">' + (d.reviews.due_now ? d.reviews.due_now + ' cards are ready for spaced review.' : 'Build a review deck from your weak topics.') + '</p><button class="ghost sm" onclick="openCockpitReview()">Open spaced review</button></div>' +
      '<div class="mission"><b>2 · Repair · 5 min</b><p class="muted">' + (d.mistakes.length ? 'Revisit the source behind your mistakes, then retry them.' : 'No unresolved mistakes. Keep practising to find gaps.') + '</p><button class="ghost sm" onclick="retryMistakes()" ' + (!d.mistakes.length ? 'disabled' : '') + '>Retry mistakes</button></div>' +
      '<div class="mission"><b>3 · Apply · 10 min</b><p class="muted">Practise your weakest topics with adaptive questions.</p><button class="sm" onclick="openAdaptivePractice()">Start adaptive practice</button></div></div>' +
      '<div class="card"><div class="card-h"><h3>Evidence of progress</h3></div><p><b>' + (d.mastery === null ? 'No practice evidence yet' : Math.round(d.mastery * 100) + '% mean mastery on practised topics') + '</b></p><p class="muted small">' + d.practised + ' of ' + d.topics + ' topics have answer or conversation evidence. Untouched topics are excluded from this average. This is a learning estimate, not an exam-score prediction.</p>' +
      d.recommendations.slice(0, 4).map(r => '<div class="mission"><b>' + esc(r.name) + '</b><p class="muted small">' + esc(r.reason) + '</p></div>').join('') + '</div></div>' +
      '<div class="card"><div class="card-h"><h3>Mistake notebook</h3><button class="ghost sm" onclick="exportMistakes()" ' + (!d.mistakes.length ? 'disabled' : '') + '>Download notebook</button></div><p class="muted small">Your latest incorrect answers, linked to the source. A correct retry automatically clears a mistake.</p>' +
      (d.mistakes.length ? d.mistakes.map(m => '<details class="mistake"><summary>' + esc(m.topic) + ' · ' + esc(m.stem) + '</summary><p><b>Your answer:</b> ' + esc(m.response) + '</p><p><b>Correct answer:</b> ' + esc(m.answer) + '</p><p>' + esc(m.explanation) + '</p>' + citeBtn('', m.source) + '</details>').join('') : '<div class="empty"><p>No unresolved mistakes. Complete a quiz to start collecting useful feedback.</p></div>') + '</div>';
    window.COCKPIT = {uid, data: d}; animateKpis('#cockpitBody');
  } catch (e) { if (SID === uid) host.innerHTML = '<div class="card"><p>' + esc(e.message) + '</p><button onclick="loadCockpit()">Try again</button></div>'; }
}
function openCockpitReview() { RV_TAB = 'review'; show('revise'); }
function openAdaptivePractice() { MODE = 'adaptive'; show('practice'); }
async function retryMistakes() {
  if (needStudent()) return;
  const uid = SID;
  try {
    const run = await api('/assess/start', {method: 'POST', body: {student_id: uid, n: 10, kind: 'mistakes'}});
    if (SID !== uid) return;
    show('practice'); RUN = run; RUN.i = 0; RUN.log = []; RUN.t0 = Date.now();
    $('#setup').classList.add('hidden'); $('#runner').classList.remove('hidden'); startTimer(); renderQ();
    if (RUN.notice) toast(RUN.notice);
  } catch (e) { toast(e.message, 'err'); }
}
function exportMistakes() {
  const c = window.COCKPIT;
  if (!c || c.uid !== SID) return;
  const text = '# StudyPilot mistake notebook\n\n' + c.data.mistakes.map(m => '## ' + m.topic + '\n\n' + m.stem + '\n\nYour answer: ' + m.response + '\n\nCorrect answer: ' + m.answer + '\n\n' + m.explanation + '\n\nSource: ' + m.source.source_name + ' · ' + m.source.label).join('\n\n---\n\n');
  const url = URL.createObjectURL(new Blob([text], {type: 'text/markdown'}));
  const a = document.createElement('a'); a.href = url; a.download = 'studypilot-mistakes.md'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
let sourceSearchVersion = 0;
async function searchMaterial() {
  const q = $('#sourceQuery').value.trim(), uid = SID, version = ++sourceSearchVersion, host = $('#searchResults');
  if (!q) { host.innerHTML = ''; return; }
  host.innerHTML = skeleton(2);
  try {
    const d = await api('/search?q=' + encodeURIComponent(q));
    if (SID !== uid || version !== sourceSearchVersion) return;
    host.innerHTML = d.results.length ? d.results.map(c => '<div class="mission"><b>' + esc(c.source_name) + '</b><p class="source-excerpt">' + esc(c.snippet) + '</p>' + citeBtn('', c) + '</div>').join('') : '<p class="muted">No matching passages. Try a term from your course material.</p>';
  } catch(e) { if (SID === uid && version === sourceSearchVersion) host.innerHTML = '<p>' + esc(e.message) + '</p>'; }
}

/* Connection state is independent of optional language / chart loading. */
function paintConnection(d) {
 CFG=d;
 const a=d.ai||{},state=a.status||'untested';
 $('#status').classList.remove('hidden');
 $('#status .dot').classList.toggle('ok',state==='connected');
 $('#mode').textContent=!d.llm?'Local study · add OpenRouter key':state==='connected'?'OpenRouter connected':state==='error'?'OpenRouter needs attention':'OpenRouter configured · untested';
 $('#status').title=a.last_error||a.model||'Local study is available';
}
async function connectionDetails(probe=false) {
 openModal('<h2>OpenRouter connection</h2><div id="aiDetails">'+skeleton(1)+'</div>',true);
 try {
  const a=probe?await api('/ai/test',{method:'POST'}):(await api('/config')).ai;
  if(!$('#aiDetails'))return;
  $('#aiDetails').innerHTML='<p><b>'+esc(a.status)+'</b></p><p class="small">Model: '+esc(a.model)+'</p>'+
    (a.last_error?'<div class="flag">'+esc(a.last_error)+'</div>':'<p class="muted">'+(a.configured?'A configured key is tested only when a request is made.':'Add OPENROUTER_API_KEY to .env and restart the server.')+'</p>')+
    '<p class="muted small">Free models have provider quotas. Source-based practice and revision stay available during outages.</p><button onclick="connectionDetails(true)">Test connection</button>';
  paintConnection(await api('/config'));
 } catch(e) {if($('#aiDetails'))$('#aiDetails').textContent=e.message;}
}

function preserveMath(text, format) {
 const saved=[];
 const masked=String(text??'').replace(/\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|(?<!\\)\$[^$\n]+?\$/g,m=>{
   let i=saved.push(m.replace(/\n/g,' '))-1;return 'SPFORMULATOKEN'+i+'END';
 });
 return format(masked).replace(/SPFORMULATOKEN(\d+)END/g,(_,i)=>esc(saved[+i]));
}

async function refreshConnection(){try{paintConnection(await api("/config"));}catch(e){}}
