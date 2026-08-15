"""Dashboard web local pour suivre les uploads FreeFox."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from freefox.config import CollectorConfig
from freefox.queue import QueueEntry, UploadQueue


HTML = r"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FreeFox - Tableau de bord</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700;800&family=Barlow+Condensed:wght@600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --fox-orange: #FF6B00;
      --fox-red:    #E63200;
      --fox-amber:  #FFAA33;
      --fox-cream:  #F5F0E8;
      --fox-dark:   #1A0A00;

      --bg:      #0D0804;
      --bg2:     #140C06;
      --panel:   #1C1109;
      --panel2:  #231508;
      --line:    #2E1C0E;
      --line2:   #3D2510;

      --text:    #F0E8DF;
      --muted:   #8A7060;
      --faint:   #4A3020;

      --green:       #4ADE80;
      --green-bg:    #052E16;
      --blue:        #60A5FA;
      --blue-bg:     #0C1A3A;
      --purple:      #C084FC;
      --purple-bg:   #2E1065;
      --red:         #F87171;
      --red-bg:      #450A0A;
      --amber:       #FCD34D;
      --amber-bg:    #451A03;

      --font-d: 'Barlow Condensed', sans-serif;
      --font-b: 'Barlow', sans-serif;
      --font-m: 'JetBrains Mono', monospace;
      --r: 6px; --rl: 10px;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: var(--font-b);
      font-size: 14px;
      color: var(--text);
      background: var(--bg);
      background-image:
        radial-gradient(ellipse 60% 40% at 10% 0%, rgba(255,107,0,.13) 0%, transparent 60%),
        radial-gradient(ellipse 30% 30% at 90% 100%, rgba(230,50,0,.07) 0%, transparent 50%);
      min-height: 100vh;
    }

    /* En-tete */
    header {
      position: sticky; top: 0; z-index: 100;
      display: flex; align-items: center; justify-content: space-between; gap: 20px;
      padding: 0 24px; height: 68px;
      background: rgba(13,8,4,.94);
      backdrop-filter: blur(14px);
      border-bottom: 1px solid var(--line2);
      box-shadow: 0 1px 0 rgba(255,107,0,.1), 0 4px 32px rgba(0,0,0,.6);
    }
    .brand { display: flex; align-items: center; gap: 14px; flex-shrink: 0; }
    .brand-logo {
      height: 50px; width: auto; display: block;
      filter: drop-shadow(0 0 10px rgba(255,107,0,.4));
      transition: filter .3s;
    }
    .brand-logo:hover { filter: drop-shadow(0 0 18px rgba(255,107,0,.7)); }
    .brand-name {
      font-family: var(--font-d); font-weight: 800; font-size: 28px;
      letter-spacing: .04em; text-transform: uppercase;
      background: linear-gradient(130deg, var(--fox-orange), var(--fox-amber) 55%, var(--fox-cream));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    }
    .brand-sub {
      font-size: 10px; font-weight: 700; letter-spacing: .14em;
      text-transform: uppercase; color: var(--muted); margin-top: 3px;
    }
    .header-meta { display: flex; align-items: center; gap: 12px; flex: 1; justify-content: center; }
    .meta-pill {
      display: flex; align-items: center; gap: 7px;
      padding: 5px 13px;
      background: var(--panel); border: 1px solid var(--line2); border-radius: 999px;
      font-size: 12px; font-family: var(--font-m); color: var(--muted);
      white-space: nowrap; max-width: 240px; overflow: hidden; text-overflow: ellipsis;
    }
    .meta-pill b { color: var(--fox-amber); font-weight: 500; }
    .live-dot {
      width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
      background: var(--fox-orange); box-shadow: 0 0 6px var(--fox-orange);
      animation: blink 2s ease-in-out infinite;
    }
    .live-dot.off { background: var(--muted); box-shadow: none; animation: none; }
    @keyframes blink { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.4;transform:scale(.7)} }
    .toolbar { display: flex; gap: 8px; flex-shrink: 0; }
    .btn {
      display: inline-flex; align-items: center; gap: 6px;
      height: 34px; padding: 0 14px; border-radius: var(--r);
      font-family: var(--font-b); font-size: 13px; font-weight: 700;
      cursor: pointer; transition: all .15s; border: 1px solid transparent;
    }
    .btn-ghost { background: transparent; border-color: var(--line2); color: var(--text); }
    .btn-ghost:hover { border-color: var(--fox-orange); color: var(--fox-orange); background: rgba(255,107,0,.07); }
    .btn-primary {
      background: linear-gradient(135deg, var(--fox-orange), var(--fox-red));
      color: #fff; font-weight: 800;
      box-shadow: 0 2px 14px rgba(255,107,0,.35);
    }
    .btn-primary:hover { box-shadow: 0 4px 22px rgba(255,107,0,.55); transform: translateY(-1px); }
    .btn-primary:active { transform: none; }

    /* Contenu principal */
    main { width: min(1560px,100%); margin: 0 auto; padding: 22px 22px 60px; }

    /* Statistiques */
    .stats { display: grid; grid-template-columns: repeat(6,1fr); gap: 10px; margin-bottom: 20px; }
    .stat {
      background: var(--panel); border: 1px solid var(--line2); border-radius: var(--rl);
      padding: 16px 18px; position: relative; overflow: hidden; transition: border-color .2s;
    }
    .stat::after {
      content: ""; position: absolute; inset: 0;
      background: linear-gradient(135deg, rgba(255,107,0,.07) 0%, transparent 55%);
      pointer-events: none;
    }
    .stat:hover { border-color: rgba(255,107,0,.35); }
    .stat-label {
      font-size: 10px; font-weight: 800; letter-spacing: .1em;
      text-transform: uppercase; color: var(--muted); margin-bottom: 10px;
    }
    .stat-val {
      font-family: var(--font-d); font-size: 36px; font-weight: 800; line-height: 1;
    }
    .c-orange { color: var(--fox-orange); }
    .c-green  { color: var(--green); }
    .c-red    { color: var(--red); }
    .c-amber  { color: var(--amber); }
    .c-blue   { color: var(--blue); }

    /* Mise en page */
    .layout { display: grid; grid-template-columns: minmax(0,2.2fr) 370px; gap: 16px; align-items: start; }

    /* Panneaux */
    .panel { background: var(--panel); border: 1px solid var(--line2); border-radius: var(--rl); overflow: hidden; margin-bottom: 16px; }
    .panel-hd {
      display: flex; align-items: center; justify-content: space-between;
      padding: 12px 16px; border-bottom: 1px solid var(--line); background: var(--panel2);
    }
    .panel-title {
      font-family: var(--font-d); font-size: 13px; font-weight: 700;
      letter-spacing: .08em; text-transform: uppercase; color: var(--fox-amber);
    }
    .pill {
      font-family: var(--font-m); font-size: 11px; color: var(--muted);
      background: var(--bg2); border: 1px solid var(--line); border-radius: 999px; padding: 2px 9px;
    }

    /* Tableaux */
    .tbl-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    th {
      padding: 9px 12px; text-align: left;
      font-size: 10px; font-weight: 800; letter-spacing: .09em; text-transform: uppercase;
      color: var(--muted); background: rgba(0,0,0,.3); border-bottom: 1px solid var(--line);
    }
    td { padding: 10px 12px; border-bottom: 1px solid rgba(46,28,14,.5); font-size: 13px; vertical-align: middle; }
    tr:last-child td { border-bottom: 0; }
    tr:hover td { background: rgba(255,107,0,.04); }
    .mono { font-family: var(--font-m); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .dim { color: var(--muted); }
    .err-row td { color: var(--red); font-family: var(--font-m); font-size: 11px; }

    /* Badges */
    .badge {
      display: inline-flex; align-items: center; gap: 5px;
      height: 22px; padding: 0 9px; border-radius: 999px;
      font-size: 11px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; white-space: nowrap;
    }
    .badge::before { content:""; width:5px; height:5px; border-radius:50%; background:currentColor; opacity:.7; }
    .badge.queued    { color:#93C5FD; background:var(--blue-bg);   border:1px solid #1E3A5F; }
    .badge.uploading { color:#C4B5FD; background:var(--purple-bg); border:1px solid #3B1F6A; animation:blink 1.4s ease-in-out infinite; }
    .badge.done      { color:#86EFAC; background:var(--green-bg);  border:1px solid #14532D; }
    .badge.failed    { color:#FCA5A5; background:var(--red-bg);    border:1px solid #7F1D1D; }
    .badge.pending   { color:#FDE68A; background:var(--amber-bg);  border:1px solid #78350F; }
    .badge.writing   { color:#C4B5FD; background:var(--purple-bg); border:1px solid #3B1F6A; }
    .badge.stable    { color:#86EFAC; background:var(--green-bg);  border:1px solid #14532D; }
    .badge.not-queued { color:#FCA5A5; background:var(--red-bg);   border:1px solid #7F1D1D; }
    .badge.integrity-ok { color:#86EFAC; background:var(--green-bg); border:1px solid #14532D; }
    .badge.integrity-no { color:#FCA5A5; background:var(--red-bg); border:1px solid #7F1D1D; }
    .badge.integrity-pending { color:#FDE68A; background:var(--amber-bg); border:1px solid #78350F; }
    .badge.integrity-off { color:#94A3B8; background:rgba(148,163,184,.12); border:1px solid rgba(148,163,184,.24); }

    /* Progression */
    .prog { display: grid; grid-template-columns: 1fr 44px; gap: 8px; align-items: center; }
    .bar { height: 6px; border-radius: 999px; background: var(--line2); overflow: hidden; }
    .bar-fill {
      height: 100%; width: 0; border-radius: 999px;
      background: linear-gradient(90deg, var(--fox-orange), var(--fox-amber));
      box-shadow: 0 0 6px rgba(255,107,0,.5); transition: width .4s ease;
    }
    .pct { font-family: var(--font-m); font-size: 11px; color: var(--muted); text-align: right; }

    /* Incidents */
    .incident {
      display: flex; gap: 12px; align-items: flex-start;
      padding: 13px 16px; border-bottom: 1px solid var(--line);
      background: rgba(255,107,0,.03);
    }
    .incident:last-child { border-bottom: 0; }
    .incident-icon { font-size: 15px; flex-shrink: 0; margin-top: 1px; }
    .incident-kind { font-size: 11px; font-weight: 800; letter-spacing: .07em; text-transform: uppercase; color: var(--fox-orange); margin-bottom: 3px; }
    .incident-msg  { font-size: 12px; color: var(--muted); line-height: 1.45; }

    /* Configuration */
    .cfg-row {
      display: grid; grid-template-columns: 110px 1fr; gap: 12px;
      padding: 9px 16px; border-bottom: 1px solid rgba(46,28,14,.5); align-items: center;
    }
    .cfg-row:last-child { border-bottom: 0; }
    .cfg-key { font-size: 11px; font-weight: 800; letter-spacing: .07em; text-transform: uppercase; color: var(--muted); }
    .cfg-val { font-family: var(--font-m); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

    .empty { padding: 32px 20px; text-align: center; color: var(--faint); font-size: 13px; font-style: italic; }

    @media(max-width:1100px){.stats{grid-template-columns:repeat(3,1fr)}.layout{grid-template-columns:1fr}}
    @media(max-width:640px){.stats{grid-template-columns:repeat(2,1fr)}.header-meta{display:none}}
  </style>
</head>
<body>
<header>
  <div class="brand">
    <img class="brand-logo" src="/brand/freefox.png" alt="FreeFox">
    <div>
      <div class="brand-name">FreeFox</div>
      <div class="brand-sub">ROS 2 · Collecteur de bags</div>
    </div>
  </div>
  <div class="header-meta">
    <div class="meta-pill"><span class="live-dot" id="dot"></span>robot: <b id="m-robot">—</b></div>
    <div class="meta-pill">dossier: <b id="m-watch">—</b></div>
    <div class="meta-pill">maj: <b id="m-updated">—</b></div>
  </div>
  <div class="toolbar">
    <button class="btn btn-ghost" id="btn-refresh">↺ Actualiser</button>
    <button class="btn btn-primary" id="btn-toggle">⏸ Pause</button>
  </div>
</header>

<main>
  <section class="stats" id="stats"></section>
  <section class="layout">
    <div>
      <div class="panel">
        <div class="panel-hd"><span class="panel-title">Transferts</span><span class="pill" id="c-tr">0</span></div>
        <div class="tbl-wrap" id="transfers"></div>
      </div>
      <div class="panel">
        <div class="panel-hd"><span class="panel-title">Fichiers surveilles</span><span class="pill" id="c-fi">0</span></div>
        <div class="tbl-wrap" id="files"></div>
      </div>
    </div>
    <aside>
      <div class="panel">
        <div class="panel-hd"><span class="panel-title">Incidents</span><span class="pill" id="c-in">0</span></div>
        <div id="incidents"></div>
      </div>
      <div class="panel">
        <div class="panel-hd"><span class="panel-title">Configuration</span></div>
        <div id="config"></div>
      </div>
    </aside>
  </section>
</main>

<script>
const $ = id => document.getElementById(id);
const esc = v => String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
const fmtB = v => { if(!v) return "0 B"; const u=["B","KiB","MiB","GiB","TiB"]; let n=v,i=0; while(n>=1024&&i<u.length-1){n/=1024;i++;} return `${n.toFixed(n>=10||i===0?0:1)} ${u[i]}`; };
const fmtT = v => v ? new Date(v*1000).toLocaleString() : "—";
const fmtD = s => { if(!s||s<0)return"—"; s=Math.round(s); const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),r=s%60; return h?`${h}h ${m}m`:m?`${m}m ${r}s`:`${r}s`; };
const fmtR = b => (!b||b<0)?"—":`${(b/1024/1024).toFixed(2)} MiB/s · ${((b*8)/1000/1000).toFixed(2)} Mbps`;
const fmtNext = e => {
  if(e.status !== "queued") return "—";
  if(!e.retry_after_seconds || e.retry_after_seconds <= 0) return "pret";
  return `dans ${fmtD(e.retry_after_seconds)}`;
};
const statut = s => ({
  queued: "en file",
  uploading: "upload",
  done: "termine",
  failed: "echec",
  pending: "attente",
  writing: "ecriture",
  stable: "stable",
  "not-queued": "non ajoute",
  "integrity-ok": "OK",
  "integrity-no": "NO",
  "integrity-pending": "attente",
  "integrity-off": "—"
}[s] || s);

function renderStats(st, mt, q) {
  const cards = [
    {l:"En file",   v:st.queued||0,    c:""},
    {l:"Prets",     v:(q&&q.ready)||0, c:"c-blue"},
    {l:"Retry",     v:(q&&q.waiting)||0, c:"c-amber"},
    {l:"En upload", v:st.uploading||0, c:"c-orange"},
    {l:"Termines",  v:st.done||0,      c:"c-green"},
    {l:"Echecs",    v:st.failed||0,    c:"c-red"},
    {l:"Trafic",    v:fmtB(mt.bytes_sent_estimate||0), c:"c-blue"},
    {l:"Debit",     v:fmtR(mt.active_bytes_per_second||0), c:"c-amber"},
  ];
  $("stats").innerHTML = cards.map(c=>`<article class="stat"><div class="stat-label">${c.l}</div><div class="stat-val ${c.c}">${esc(String(c.v))}</div></article>`).join("");
}

function renderTransfers(es) {
  $("c-tr").textContent = es.length;
  if(!es.length){ $("transfers").innerHTML=`<div class="empty">Aucun transfert dans la file</div>`; return; }
  $("transfers").innerHTML = `<table><thead><tr>
    <th style="width:48px">ID</th><th style="width:110px">Statut</th>
    <th style="width:170px">Progression</th><th>Chemin distant</th>
    <th style="width:88px">Taille</th><th style="width:88px">Duree</th>
    <th style="width:180px">Debit</th><th style="width:76px">Reste</th>
    <th style="width:92px">Prochain</th><th style="width:86px">Integrite</th>
    <th style="width:96px">BLAKE3</th><th style="width:60px">Essais</th>
  </tr></thead><tbody>${es.map(e=>{
    const pct = Math.max(0,Math.min(100,e.progress_percent||0));
    return `<tr>
      <td class="mono dim">#${e.id}</td>
      <td><span class="badge ${esc(e.status)}">${esc(statut(e.status))}</span></td>
      <td><div class="prog"><div class="bar"><div class="bar-fill" style="width:${pct}%"></div></div><span class="pct">${pct.toFixed(1)}%</span></div></td>
      <td class="mono" title="${esc(e.remote_path)}">${esc(e.remote_path)}</td>
      <td class="dim">${fmtB(e.size_bytes)}</td>
      <td class="dim">${fmtD(e.duration_seconds)}</td>
      <td class="dim">${fmtR(e.bytes_per_second)}</td>
      <td class="dim">${fmtD(e.eta_seconds)}</td>
      <td class="dim">${esc(fmtNext(e))}</td>
      <td><span class="badge ${esc(e.integrity_status_class)}">${esc(e.integrity_status)}</span></td>
      <td class="mono dim" title="${esc(e.blake3_digest||'')}">${esc((e.blake3_digest||'').slice(0,12)||"—")}</td>
      <td class="dim">${e.retries}</td>
    </tr>${e.error_summary?`<tr class="err-row"><td></td><td colspan="11">⚠ ${esc(e.error_summary)}</td></tr>`:""}`;
  }).join("")}</tbody></table>`;
}

function renderFiles(fs) {
  $("c-fi").textContent = fs.length;
  if(!fs.length){ $("files").innerHTML=`<div class="empty">Aucun bag dans le dossier surveille</div>`; return; }
  $("files").innerHTML = `<table><thead><tr>
    <th>Nom</th><th style="width:100px">Taille</th>
    <th style="width:170px">Modifie</th><th style="width:110px">Etat</th><th style="width:90px">Pret dans</th>
  </tr></thead><tbody>${fs.map(f=>`<tr>
    <td class="mono" title="${esc(f.path)}">${esc(f.name)}</td>
    <td class="dim">${fmtB(f.size_bytes)}</td>
    <td class="dim">${fmtT(f.modified_at)}</td>
    <td><span class="badge ${esc(f.state_class)}">${esc(statut(f.state_class))}</span></td>
    <td class="dim">${esc(f.ready_in)}</td>
  </tr>`).join("")}</tbody></table>`;
}

function renderIncidents(is) {
  $("c-in").textContent = is.length;
  $("incidents").innerHTML = is.length
    ? is.map(i=>`<div class="incident"><div class="incident-icon">⚠</div><div><div class="incident-kind">${esc(i.kind)}</div><div class="incident-msg">${esc(i.message)}</div></div></div>`).join("")
    : `<div class="empty">Aucun incident</div>`;
}

function renderConfig(cfg) {
  const destination = cfg.storage_backend === "rsync"
    ? cfg.rsync_destination
    : (cfg.drive_folder_id||"racine");
  const rows = [
    ["Robot",      cfg.robot_id],
    ["Backend",    cfg.storage_backend],
    ["Dossier",    cfg.watch_directory],
    ["Base SQLite", cfg.queue_db],
    ["Destination", destination],
    ["Extensions", (cfg.extensions||[]).join(", ")],
    ["Stabilite",  `${cfg.stable_seconds}s`],
  ];
  $("config").innerHTML = rows.map(([k,v])=>`<div class="cfg-row"><span class="cfg-key">${esc(k)}</span><span class="cfg-val" title="${esc(v)}">${esc(v)}</span></div>`).join("");
}

async function refresh() {
  try {
    const d = await fetch("/api/status").then(r=>r.json());
    $("m-robot").textContent   = d.config.robot_id;
    $("m-watch").textContent   = d.config.watch_directory;
    $("m-updated").textContent = new Date().toLocaleTimeString();
    renderStats(d.stats, d.metrics, d.queued);
    renderTransfers(d.entries);
    renderFiles(d.files);
    renderIncidents(d.incidents);
    renderConfig(d.config);
  } catch(e) { console.warn(e); }
}

let running=true, timer=null;
function schedule(){ clearInterval(timer); if(running) timer=setInterval(refresh,2000); }

$("btn-refresh").addEventListener("click", refresh);
$("btn-toggle").addEventListener("click", ()=>{
  running=!running;
  $("btn-toggle").textContent = running ? "⏸ Pause" : "▶ Reprendre";
  $("btn-toggle").className   = running ? "btn btn-primary" : "btn btn-ghost";
  $("dot").className          = running ? "live-dot" : "live-dot off";
  schedule();
});

refresh(); schedule();
</script>
</body>
</html>
"""


def _human_error(error: str | None) -> str:
    if not error:
        return ""
    lowered = error.lower()
    if (
        "quota google drive depasse" in lowered
        or "storagequotaexceeded" in lowered
        or "storage quota" in lowered
    ):
        return "L'espace Google Drive du compte est plein."
    if (
        "erreur reseau temporaire" in lowered
        or "temporary failure in name resolution" in lowered
        or "nameresolutionerror" in lowered
        or "failed to resolve" in lowered
        or "read timed out" in lowered
        or "connection timed out" in lowered
        or "max retries exceeded" in lowered
    ):
        return "Connexion instable vers Google Drive. FreeFox reessaiera automatiquement."
    if "local file missing" in lowered or "file not found" in lowered:
        return "Le fichier local est introuvable ou a ete deplace."
    if "resumable upload session expired" in lowered:
        return "La session d'upload Google Drive a expire. FreeFox va recreer une session."
    if "integrity metadata mismatch" in lowered or "local file size changed" in lowered:
        return "Controle d'integrite echoue. Le fichier est considere comme incoherent."
    if "permission" in lowered or "403" in lowered:
        return "Google Drive refuse l'operation. Verifiez les droits du compte ou du dossier."
    return "Erreur d'upload. Consultez les logs FreeFox pour le detail technique."


def _integrity_status(entry: QueueEntry) -> tuple[str, str]:
    error = (entry.error or "").lower()
    if "integrity metadata mismatch" in error or "local file size changed" in error:
        return "NO", "integrity-no"
    if entry.status.value == "done" and entry.blake3_digest:
        return "OK", "integrity-ok"
    if entry.blake3_digest:
        return "attente", "integrity-pending"
    return "—", "integrity-off"


def _entry_to_dict(entry: QueueEntry) -> dict:
    now = time.time()
    progress = max(0.0, min(100.0, entry.progress_percent or 0.0))
    started_at = entry.upload_started_at or 0.0
    finished_at = entry.upload_finished_at or 0.0
    bytes_sent = getattr(entry, "uploaded_bytes", None) or (
        int(entry.size_bytes * (progress / 100.0)) if started_at else 0
    )
    end_time = finished_at or (now if started_at else 0.0)
    duration = max(0.0, end_time - started_at) if started_at else 0.0
    bps = (entry.size_bytes / duration if entry.status.value == "done" else bytes_sent / duration) if started_at and duration > 0 else 0.0
    remaining = max(0, entry.size_bytes - bytes_sent)
    eta = remaining / bps if entry.status.value == "uploading" and bps > 0 else 0.0
    retry_after = max(0.0, entry.next_retry_at - now) if entry.status.value == "queued" else 0.0
    integrity_status, integrity_status_class = _integrity_status(entry)
    return {
        "id": entry.id, "local_path": entry.local_path, "remote_path": entry.remote_path,
        "status": entry.status.value, "retries": entry.retries,
        "next_retry_at": entry.next_retry_at, "retry_after_seconds": retry_after,
        "created_at": entry.created_at, "updated_at": getattr(entry, "updated_at", entry.created_at),
        "upload_started_at": entry.upload_started_at, "upload_finished_at": entry.upload_finished_at,
        "size_bytes": entry.size_bytes, "progress_percent": progress,
        "bytes_sent_estimate": bytes_sent, "bytes_per_second": bps,
        "duration_seconds": duration, "eta_seconds": eta,
        "blake3_digest": entry.blake3_digest,
        "integrity_status": integrity_status,
        "integrity_status_class": integrity_status_class,
        "error": entry.error,
        "error_summary": _human_error(entry.error),
    }


def _metrics(entries):
    ds = [_entry_to_dict(e) for e in entries]
    return {
        "bytes_sent_estimate": float(sum(d["bytes_sent_estimate"] for d in ds)),
        "active_bytes_per_second": float(sum(d["bytes_per_second"] for d in ds if d["status"] == "uploading")),
    }


def _list_watch_files(config, entries):
    directory = config.watch.directory
    queued = {e.local_path for e in entries}
    now = time.time()
    if not directory.exists(): return []
    files = []
    exts = {x.lower() for x in config.watch.extensions}
    for path in directory.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in exts: continue
        try: stat = path.stat()
        except OSError: continue
        is_q = str(path) in queued
        age = max(0.0, now - stat.st_mtime)
        if is_q:            state, sc, ri = "queued",     "queued",     "—"
        elif age < config.watch.stable_seconds: state, sc, ri = "writing", "writing", f"{config.watch.stable_seconds-age:.1f}s"
        else:               state, sc, ri = "not queued", "not-queued", "now"
        files.append({"name": path.name, "path": str(path), "size_bytes": stat.st_size,
                      "modified_at": stat.st_mtime, "state": state, "state_class": sc, "ready_in": ri})
    files.sort(key=lambda r: r["modified_at"], reverse=True)
    return files[:100]


def _incidents(config, entries):
    out = []
    if not config.watch.directory.exists():
        out.append({"kind": "dossier surveille", "message": f"N'existe pas: {config.watch.directory}"})
    if not config.drive.credentials_file.exists():
        out.append({"kind": "identifiants", "message": f"Fichier manquant: {config.drive.credentials_file}"})
    for e in entries:
        error = e.error or ""
        if e.status.value != "done" and (
            "Quota Google Drive depasse" in error
            or "storageQuotaExceeded" in error
            or "storage quota" in error.lower()
        ):
            out.append({
                "kind": "quota Google Drive",
                "message": (
                    "L'espace Drive du compte est plein. "
                    "FreeFox reessaiera automatiquement quand de l'espace sera disponible."
                ),
            })
            continue
        if e.status.value != "done" and (
            "Erreur reseau temporaire" in error
            or "temporary failure in name resolution" in error.lower()
            or "read timed out" in error.lower()
            or "connection timed out" in error.lower()
            or "failed to resolve" in error.lower()
        ):
            out.append({
                "kind": "reseau temporaire",
                "message": (
                    "La connexion vers Google Drive est instable. "
                    "FreeFox reessaiera automatiquement."
                ),
            })
            continue
        if e.status.value == "failed":
            out.append({"kind": f"transfert en echec #{e.id}", "message": _human_error(e.error) or e.remote_path})
    unq = [f for f in _list_watch_files(config, entries) if f["state"] == "not queued"]
    if unq:
        out.append({"kind": "surveillance", "message": f"{len(unq)} bag(s) stable(s) non ajoute(s) a la file. Le service tourne-t-il ?"})
    return out[:20]


class DashboardServer(ThreadingHTTPServer):
    def __init__(self, addr, config):
        super().__init__(addr, DashboardHandler)
        self.config_obj = config
        self.queue = UploadQueue(config.queue_db)
        self.started_at = time.time()


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer
    def log_message(self, *_): return

    def _send(self, code, ct, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            self._send(200, "text/html; charset=utf-8", HTML.encode()); return
        if p == "/brand/freefox.png":
            img = Path(__file__).resolve().parents[1] / "images" / "freefox.png"
            try: self._send(200, "image/png", img.read_bytes())
            except OSError: self._send(404, "text/plain", b"introuvable")
            return
        if p == "/api/status":
            qs  = parse_qs(urlparse(self.path).query)
            lim = int(qs.get("limit", ["100"])[0])
            entries = self.server.queue.recent(limit=lim)
            cfg = self.server.config_obj
            body = json.dumps({
                "config": {
                    "robot_id": cfg.robot_id, "watch_directory": str(cfg.watch.directory),
                    "storage_backend": cfg.storage.backend,
                    "queue_db": str(cfg.queue_db), "drive_folder_id": cfg.drive.target_folder_id,
                    "rsync_destination": cfg.rsync.destination,
                    "extensions": cfg.watch.extensions, "stable_seconds": cfg.watch.stable_seconds,
                },
                "stats": self.server.queue.stats(),
                "queued": self.server.queue.queued_breakdown(),
                "metrics": _metrics(entries),
                "entries": [_entry_to_dict(e) for e in entries],
                "files": _list_watch_files(cfg, entries),
                "incidents": _incidents(cfg, entries),
            }, indent=2).encode()
            self._send(200, "application/json", body); return
        self._send(404, "text/plain", b"introuvable")


def main():
    parser = argparse.ArgumentParser(description="Dashboard web local FreeFox")
    parser.add_argument("-c", "--config", default="/etc/freefox/config.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    config = CollectorConfig.from_yaml(args.config)
    server = DashboardServer((args.host, args.port), config)
    url = f"http://{args.host}:{args.port}"
    print(f"Dashboard FreeFox -> {url}")
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
