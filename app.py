import streamlit as st
import streamlit.components.v1 as components
import time

# =========================
# TOKEN QR / LINK SQUADRA
# =========================
TOKEN_TTL_HOURS = 24

def _safe_float(val, default=0.0):
    """Convert val to float safely (handles '', None, commas)."""
    try:
        if val is None:
            return float(default)
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip()
        if s == "":
            return float(default)
        s = s.replace(",", ".")
        return float(s)
    except Exception:
        return float(default)




def render_clock_in_sidebar(show_stopwatch: bool = True):
    """
    Orologio ultra-compatto in sidebar, aggiornamento ogni secondo via JS, tempo in UTC.
    Evita tagli: iframe height conservativo + layout elastico (no height fissa).
    """
    import streamlit as st
    import streamlit.components.v1 as components

    clock_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  html, body {{
    margin: 0;
    padding: 0;
    height: auto;
    overflow: visible !important;
    background: transparent;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  }}
  .clock-card {{
    width: 100%;
    background: #0e2a47;
    border-radius: 12px;
    padding: 6px 10px 8px 10px;
    box-sizing: border-box;
  }}
  .row {{
    display: flex;
    align-items: baseline;
    justify-content: center;
    gap: 6px;
  }}
  .time {{
    font-size: 1.45rem;
    font-weight: 800;
    letter-spacing: 1px;
    line-height: 1.2;
    color: #ffffff;
    text-align: center;
    white-space: nowrap;
  }}
  .sec {{
    font-size: 0.72rem;
    opacity: 0.78;
    font-weight: 700;
  }}
  .utc {{
    font-size: 0.70rem;
    opacity: 0.85;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 999px;
    background: rgba(255,255,255,0.12);
    color: #ffffff;
    line-height: 1;
  }}
  .sw {{
    margin-top: 2px;
    text-align: center;
    font-size: 0.70rem;
    opacity: 0.82;
    color: #ffffff;
    line-height: 1.1;
    white-space: nowrap;
  }}
</style>
</head>
<body>
  <div class="clock-card">
    <div class="row">
      <div class="time" id="t">--:--<span class="sec">:--</span></div>
      <div class="utc">UTC</div>
    </div>
    {"<div class='sw'>⏱ Cronometro pronto</div>" if show_stopwatch else ""}
  </div>

<script>
  function pad2(n) {{ return String(n).padStart(2, '0'); }}

  function tickUTC() {{
    const d = new Date();
    const hh = pad2(d.getUTCHours());
    const mm = pad2(d.getUTCMinutes());
    const ss = pad2(d.getUTCSeconds());
    const el = document.getElementById("t");
    el.innerHTML = `${{hh}}:${{mm}}<span class="sec">:${{ss}}</span>`;
  }}

  tickUTC();
  setInterval(tickUTC, 1000);
</script>
</body>
</html>
"""
    # Height conservativo per evitare tagli su zoom/DPI diversi
    components.html(clock_html, height=96)

import pandas as pd
from datetime import datetime, timedelta
import folium
from branca.element import Template, MacroElement
from streamlit_folium import st_folium
import os
import socket
import re
import base64
import json
import uuid
import urllib.parse
import urllib.request
import qrcode
from io import BytesIO
from typing import Optional, Tuple, Dict, Any, List
import hashlib
import io


# =========================
# REPORT CACHE (GLOBAL, SAFE)
# =========================
# =========================
# SQUADRE: COLORI E ICONE
# =========================
SQUAD_STYLE = [
    {"icon": "🔵", "color": "#1e88e5"},
    {"icon": "🟢", "color": "#43a047"},
    {"icon": "🟡", "color": "#fdd835"},
    {"icon": "🟠", "color": "#fb8c00"},
    {"icon": "🔴", "color": "#e53935"},
    {"icon": "🟣", "color": "#8e24aa"},
]

def squad_badge(idx: int, name: str) -> str:
    style = SQUAD_STYLE[idx % len(SQUAD_STYLE)]
    return f"<span style='color:{style['color']};font-weight:700'>{style['icon']} {name}</span>"
@st.cache_data(show_spinner=False)
def _cached_report_bytes(payload_json: str, meta_json: str) -> bytes:
    """Cache del report HTML. Usa JSON compatti per hashing veloce.
    Deve essere definita PRIMA di ogni utilizzo.
    """
    payload = json.loads(payload_json) if payload_json else {}
    meta = json.loads(meta_json) if meta_json else {}
    return make_html_report_bytes(
        squads=payload.get("squadre", {}),
        brogliaccio=payload.get("brogliaccio", []),
        center=payload.get("center", []),
        meta=meta,
    )


def team_style(team: str) -> dict:
    """Ritorna icona+colore stabile per squadra (in base all'ordine alfabetico)."""
    try:
        keys = sorted(list((st.session_state.get("squadre") or {}).keys()))
        idx = keys.index(team) if team in keys else 0
    except Exception:
        idx = 0
    return SQUAD_STYLE[idx % len(SQUAD_STYLE)]

def team_icon(team: str) -> str:
    return team_style(team).get("icon", "🔵")

def team_hex(team: str) -> str:
    """Colore squadra (override: mantiene compatibilità con vecchia funzione se già esiste)."""
    return team_style(team).get("color", "#1e88e5")

def _merge_template_text(user_text: str) -> str:
    tpl = st.session_state.get("field_last_template") or st.session_state.get("campo_template_text", "")
    if tpl and tpl not in (user_text or ""):
        if user_text:
            return f"{tpl}\n\n{user_text}"
        return tpl
    return user_text



def _b64_encode_bytes(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


# =========================
# CLOCK (SIDEBAR) – digitale + cronometro (JS, compatto)
# =========================
def render_clock_in_sidebar(show_stopwatch: bool = True) -> None:
    """
    Orologio digitale compatto + cronometro (tutto client-side).
    Non richiede rerun di Streamlit: si aggiorna via JS.
    """
    height = 156 if show_stopwatch else 86  # extra height to avoid iframe clipping
    html = f"""
    <style>
      .pc-clock-card {{
        background: rgba(17, 24, 39, 0.92);
        border: 1px solid rgba(148, 163, 184, 0.35);
        border-radius: 14px;
        padding: 10px 10px 12px 10px; /* + spazio sotto (evita taglio) */
        margin: -6px 0 6px 0; /* più compatto */
        color: #fff;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
        user-select: none;
        min-height: 68px;          /* evita clipping contenuto */
        overflow: visible !important;
      }}

      /* sidebar: non tagliare l'iframe del clock */
      section[data-testid="stSidebar"], 
      section[data-testid="stSidebar"] > div {{
        overflow: visible !important;
      }}

      .pc-clock-row {{
        display:flex; align-items:baseline; justify-content:space-between;
      }}
      .pc-time {{
        letter-spacing: 0.03em;
        font-weight: 900;
        font-size: 20px;
        line-height: 1;
      }}
      .pc-colon {{
        animation: pcBlink 1s steps(1) infinite;
        display:inline-block;
        width: 7px;
        text-align:center;
      }}
      @keyframes pcBlink {{ 50% {{ opacity: .18; }} }}
      .pc-sec {{
        font-weight: 800;
        font-size: 12px;
        opacity: .80;
        margin-left: 6px;
      }}
      .pc-date {{
        font-size: 11px;
        opacity: .70;
        margin-top: 4px;
      }}
      .pc-sw {{
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px dashed rgba(148,163,184,.35);
      }}
      .pc-sw-time {{
        font-weight: 900;
        font-size: 16px;
        letter-spacing: 0.02em;
        line-height: 1;
      }}
      .pc-sw-controls {{
        display:flex; gap:6px; margin-top: 6px;
      }}
      .pc-btn {{
        flex:1;
        border: 1px solid rgba(148,163,184,.35);
        background: rgba(255,255,255,.06);
        color: #fff;
        border-radius: 10px;
        padding: 6px 8px;
        font-size: 12px;
        font-weight: 800;
        cursor: pointer;
      }}
      .pc-btn:active {{
        transform: translateY(1px);
      }}
      .pc-btn.primary {{
        background: rgba(59,130,246,.22);
        border-color: rgba(59,130,246,.55);
      }}
      .pc-mini {{
        font-size: 10px;
        opacity: .65;
        margin-top: 4px;
      }}
    </style>

    <div class="pc-clock-card">
      <div class="pc-clock-row">
        <div class="pc-time">
          <span id="pc_hh">--</span><span class="pc-colon">:</span><span id="pc_mm">--</span>
          <span class="pc-sec" id="pc_ss">--</span>
        </div>
        <div style="font-size:11px;opacity:.75;font-weight:800">🕒</div>
      </div>
      <div class="pc-date" id="pc_date">--</div>

      {('<div class="pc-sw">'
         '<div class="pc-sw-time" id="pc_sw">00:00.0</div>'
         '<div class="pc-sw-controls">'
         '  <button class="pc-btn primary" id="pc_sw_toggle">▶︎</button>'
         '  <button class="pc-btn" id="pc_sw_reset">⟲</button>'
         '</div>'
         '<div class="pc-mini">Cronometro locale (non richiede refresh)</div>'
         '</div>') if show_stopwatch else ''}
    </div>

    <script>
      const pad2 = (n) => String(n).padStart(2,'0');

      // --- CLOCK ---
      function tickClock(){{
        const d = new Date();
        document.getElementById('pc_hh').textContent = pad2(d.getHours());
        document.getElementById('pc_mm').textContent = pad2(d.getMinutes());
        document.getElementById('pc_ss').textContent = pad2(d.getSeconds());
        const opts = {{ weekday:'short', year:'numeric', month:'2-digit', day:'2-digit' }};
        document.getElementById('pc_date').textContent = d.toLocaleDateString(undefined, opts);
      }}
      tickClock();
      setInterval(tickClock, 250);

      // --- STOPWATCH (persist in localStorage) ---
      const hasSW = {str(show_stopwatch).lower()};
      if (hasSW) {{
        const K_RUN = 'pc_sw_running_v1';
        const K_ELA = 'pc_sw_elapsed_v1'; // ms
        const K_T0  = 'pc_sw_t0_v1';      // ms epoch

        let running = (localStorage.getItem(K_RUN) === '1');
        let elapsed = parseFloat(localStorage.getItem(K_ELA) || '0');
        let t0 = parseFloat(localStorage.getItem(K_T0) || '0');

        const elSW = document.getElementById('pc_sw');
        const btnToggle = document.getElementById('pc_sw_toggle');
        const btnReset  = document.getElementById('pc_sw_reset');

        function format(ms){{
          const t = Math.max(0, ms);
          const totalSec = Math.floor(t/1000);
          const min = Math.floor(totalSec/60);
          const sec = totalSec % 60;
          const tenth = Math.floor((t % 1000) / 100);
          return `${{pad2(min)}}:${{pad2(sec)}}.${{tenth}}`;
        }}

        function save(){{
          localStorage.setItem(K_RUN, running ? '1' : '0');
          localStorage.setItem(K_ELA, String(elapsed));
          localStorage.setItem(K_T0, String(t0));
        }}

        function updateBtn(){{
          btnToggle.textContent = running ? '⏸' : '▶︎';
        }}

        function nowMs(){{ return (new Date()).getTime(); }}

        function render(){{
          let cur = elapsed;
          if (running) {{
            cur = elapsed + (nowMs() - t0);
          }}
          elSW.textContent = format(cur);
          requestAnimationFrame(render);
        }}

        btnToggle.addEventListener('click', () => {{
          if (!running) {{
            running = true;
            t0 = nowMs();
          }} else {{
            running = false;
            elapsed = elapsed + (nowMs() - t0);
          }}
          updateBtn();
          save();
        }});

        btnReset.addEventListener('click', () => {{
          running = false;
          elapsed = 0;
          t0 = 0;
          updateBtn();
          save();
          elSW.textContent = format(0);
        }});

        // init
        updateBtn();
        // if running but missing t0, fix
        if (running && (!t0 || isNaN(t0))) {{
          t0 = nowMs();
          save();
        }}
        requestAnimationFrame(render);
      }}
    </script>
    """
    components.html(html, height=height, scrolling=False)


def _b64_decode_bytes(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))



def _normalize_photo_obj(photo):
    """Ensure JSON-serializable photo object. Accepts None/bytes/dict."""
    if not photo:
        return None
    if isinstance(photo, (bytes, bytearray)):
        return {"name": "foto", "type": "image/jpeg", "b64": _b64_encode_bytes(bytes(photo))}
    if isinstance(photo, dict) and photo.get("b64"):
        return {"name": photo.get("name") or "foto", "type": photo.get("type") or "image/jpeg", "b64": str(photo.get("b64"))}
    return None

def _photo_to_bytes(photo) -> Optional[bytes]:
    """Accepts None, raw bytes, or dict {'b64':..., ...}. Returns bytes or None."""
    if not photo:
        return None
    if isinstance(photo, (bytes, bytearray)):
        return bytes(photo)
    if isinstance(photo, dict) and photo.get("b64"):
        try:
            return _b64_decode_bytes(photo["b64"])
        except Exception:
            return None
    return None


# =========================
# CONFIG
# =========================
st.set_page_config(page_title="RADIO MANAGER - PROTEZIONE CIVILE THIENE", layout="wide")
# =========================
# UI THEME – CONSISTENZA & COMPATTEZZA (v77)
# =========================
st.markdown(
    """
<style>
  :root{
    --pc-navy:#0e2a47;
    --pc-navy-2:#0b2138;
    --pc-blue:#1e88e5;
    --pc-bg:#f6f8fb;
    --pc-card:#ffffff;
    --pc-border: rgba(15,23,42,.14);
    --pc-text:#0f172a;
    --pc-muted: rgba(15,23,42,.72);
    --pc-radius:16px;
  }

  /* Sfondo app */
  .stApp{
    background: var(--pc-bg);
    color: var(--pc-text);
  }

  /* Card uniformi */
  .pc-card{
    background: var(--pc-card) !important;
    border: 1px solid var(--pc-border) !important;
    border-radius: var(--pc-radius) !important;
  }

  /* Card OPERATORE RADIO (colore diverso) */
  .pc-card-radio{
    background: rgba(30,136,229,.08) !important;
    border: 1px solid rgba(30,136,229,.28) !important;
  }

  /* Sidebar più compatta e leggibile */
  section[data-testid="stSidebar"]{
    background: var(--pc-navy) !important;
  }
  section[data-testid="stSidebar"] .block-container{
    padding-top: .7rem !important;
    padding-bottom: .7rem !important;
  }
  section[data-testid="stSidebar"] .stMarkdown{
    margin-bottom: .35rem !important;
  }
  section[data-testid="stSidebar"] .stButton{
    margin-top: .25rem !important;
    margin-bottom: .25rem !important;
  }

  /* Input: testo sempre ben leggibile su sfondi chiari */
  .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div{
    color: var(--pc-text) !important;
  }

  /* Bottoni: testo scuro quando lo sfondo è chiaro */
  button[kind="secondary"], button[kind="tertiary"]{
    color: var(--pc-text) !important;
    font-weight: 800 !important;
  }
  /* Primary: mantenere leggibilità */
  button[kind="primary"]{
    font-weight: 900 !important;
  }

  /* Riduci gli spazi verticali dei container Streamlit */
  div[data-testid="stVerticalBlock"] > div{
    gap: .55rem !important;
  }
</style>
    """,
    unsafe_allow_html=True,
)












# =========================
# QR MODE + SICUREZZA RUOLI
# =========================
try:
    qp = dict(st.query_params)  # Streamlit >= 1.30
except Exception:
    try:
        qp = st.experimental_get_query_params()
    except Exception:
        qp = {}

def _qp_first(key, default=""):
    v = qp.get(key, default)
    if isinstance(v, (list, tuple)):
        return (v[0] if v else default)
    return v

_q_mode = (_qp_first("mode", "") or _qp_first("ruolo", "") or _qp_first("role", "")).strip().lower()
LOCK_CAPO = _q_mode in {"capo", "caposquadra", "capo_squadra", "caposq", "c"}
LOCK_CAMPO = _q_mode in {"campo", "field", "modulo_campo", "modulo-campo", "camp"}
LOCK_FIELD = LOCK_CAPO or LOCK_CAMPO




if LOCK_FIELD:
    st.markdown("""
    <style>
      /* Nasconde completamente la sidebar */
      section[data-testid="stSidebar"] { display: none !important; }
      div[data-testid="stSidebar"] { display: none !important; }
      nav[data-testid="stSidebarNav"] { display: none !important; }

      /* Nasconde il controllo di riapertura */
      div[data-testid="collapsedControl"] { display: none !important; }
      button[data-testid="baseButton-headerNoPadding"] { display:none !important; }

      /* Toolbar */
      header [data-testid="stToolbar"] { visibility: hidden !important; height: 0 !important; }
      header { min-height: 0 !important; }

      /* Padding pagina mobile più stretto */
      .block-container { padding-top: .6rem !important; padding-left: .75rem !important; padding-right: .75rem !important; }
    </style>
    """, unsafe_allow_html=True)




# =========================
# TOP SPACING – TITOLO A FILO (v81)
# =========================
st.markdown(
    """
<style>
  /* Togli aria sopra la pagina (più aggressivo) */
  [data-testid="stAppViewContainer"]{
    padding-top: 0 !important;
  }
  [data-testid="stAppViewContainer"] .main{
    padding-top: 0 !important;
    margin-top: 0 !important;
  }

  /* Header Streamlit: elimina spazio residuo */
  header[data-testid="stHeader"],
  [data-testid="stHeader"]{
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
  }

  /* Container principale: a filo */
  [data-testid="stAppViewContainer"] .main .block-container,
  .main .block-container,
  section.main .block-container{
    padding-top: 0rem !important;
    margin-top: 0rem !important;
  }

  /* Titoli: niente margine sopra */
  .stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
  div[data-testid="stMarkdownContainer"] h1,
  div[data-testid="stMarkdownContainer"] h2,
  div[data-testid="stMarkdownContainer"] h3{
    margin-top: 0 !important;
    padding-top: 0 !important;
  }

  /* Primo blocco del main: “tira su” ancora un filo */
  [data-testid="stAppViewContainer"] .main .block-container > div:first-child{
    margin-top: -0.65rem !important;
  }
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# FIX TITOLI MODULO CAMPO (mobile)
# =========================
st.markdown("""
<style>
/* Titolo: compatto e non tagliato */
.campo-title,
.modulo-campo-title,
div[data-testid="stMarkdownContainer"] h1,
div[data-testid="stMarkdownContainer"] h2,
div[data-testid="stMarkdownContainer"] h3 {
  line-height: 1.22 !important;
}

/* Riduci spazio tra bordo superiore e titolo */
.main .block-container {
  padding-top: 0.45rem !important;
}

div[data-testid="stMarkdownContainer"] h1 {
  margin-top: 0.15rem !important;
  padding-top: 0 !important;
}

@media (max-width: 768px) {
  .main .block-container {
    padding-top: 0.28rem !important;
  }
  div[data-testid="stMarkdownContainer"] h1 {
    margin-top: 0.10rem !important;
  }
}
</style>
""", unsafe_allow_html=True)




st.session_state["AUTH_SALA_OK"] = True  # nessun secondo PIN: Sala sempre disponibile dopo accesso iniziale


def _sync_ruolo_from_sel():
    st.session_state["ruolo_ui"] = st.session_state.get("ruolo_sel", "MODULO CAPOSQUADRA")

def ensure_sala_auth():
    """Accesso Sala Operativa: nessun secondo PIN.
    La Sala Radio è disponibile dopo l'accesso iniziale dell'app.
    """
    st.session_state["AUTH_SALA_OK"] = True
    return True


# =========================
# GLOBAL CSS (readability fixes)
# =========================
st.markdown(
    """
<style>
/* QR link box inside Streamlit app */
.qr-linkbox{
  background:#0b1220 !important;
  border:1px solid rgba(255,255,255,.14) !important;
  padding:.55rem .65rem !important;
  border-radius:.75rem !important;
  color:#ffffff !important;
  word-break: break-all !important;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace !important;
  font-size:.9rem !important;
  margin-top:.35rem !important;
}
.qr-linkbox .qr-linklabel{
  display:block !important;
  margin-bottom:.25rem !important;
  font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif !important;
  font-size:.8rem !important;
  opacity:.9 !important;
}

/* Fix: sidebar text input readable even if bg becomes white */
[data-testid="stSidebar"] .stTextInput input{
  color:#111 !important;
}
[data-testid="stSidebar"] .stTextInput input::placeholder{
  color:#666 !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# NETWORK (OFFLINE / LAN / ONLINE)
# =========================
def _has_internet(timeout: float = 1.5) -> bool:
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=timeout).close()
        return True
    except OSError:
        return False

def _local_ip() -> str:
    # Best-effort local LAN IP (works even without Internet if LAN exists)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _guess_public_url() -> str:
    """
    Best-effort: ricava l'URL pubblico dall'host della richiesta (Streamlit Cloud / reverse proxy).
    Se non determinabile, ritorna stringa vuota.
    """
    # 1) variabile ambiente (se vuoi forzare)
    env = (os.getenv("PUBLIC_URL") or os.getenv("BASE_URL") or "").strip().rstrip("/")
    if env:
        return env

    # 2) headers della request (quando disponibili)
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx  # type: ignore
        ctx = get_script_run_ctx()
        req = getattr(ctx, "request", None)
        if req is not None:
            headers = getattr(req, "headers", {}) or {}
            host = headers.get("Host") or headers.get("host") or ""
            if host:
                proto = headers.get("X-Forwarded-Proto") or headers.get("x-forwarded-proto") or "https"
                # se è locale, usa IP del PC invece di localhost
                if "localhost" in host or host.startswith("127.0.0.1"):
                    port = int(st.session_state.get("NET_PORT") or 8501)
                    ip = _local_ip()
                    return f"http://{ip}:{port}".rstrip("/")
                return f"{proto}://{host}".rstrip("/")
    except Exception:
        pass

    return ""

def _public_ip(timeout: float = 2.0) -> str:
    """Ritorna l'IP pubblico (WAN) del router visto da Internet. Se non disponibile, stringa vuota."""
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=timeout) as r:
            ip = (r.read() or b"").decode("utf-8", errors="ignore").strip()
        # sanity
        if ip and re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", ip):
            return ip
    except Exception:
        pass
    return ""

def compute_net_state(force_offline: bool, port: int) -> dict:
    ip = _local_ip()
    internet = _has_internet()
    lan = ip not in ("127.0.0.1", "0.0.0.0", "", None)

    offline = bool(force_offline) or (not internet and not lan)
    online = (not offline) and internet
    lan_only = (not offline) and (not internet) and lan

    effective_url = ""
    source = ""
    public_ip = ""

    if lan_only:
        effective_url = f"http://{ip}:{port}"
        source = "lan"
    elif online:
        # 1) se impostato manualmente (secrets/env/sidebar), usa quello
        candidate = (st.session_state.get("PUBLIC_URL") or "").strip().rstrip("/")
        if candidate:
            effective_url = candidate
            source = "public_url"
        else:
            # 2) prova a ricavare l'host dalla request (Streamlit Cloud / reverse proxy)
            candidate = (_guess_public_url() or "").strip().rstrip("/")
            if candidate:
                effective_url = candidate
                source = "guess_request"
            else:
                # 3) fallback: IP pubblico WAN (richiede Internet)
                public_ip = _public_ip()
                if public_ip:
                    effective_url = f"http://{public_ip}:{port}"
                    source = "public_ip"
                elif lan:
                    # 4) ultimissimo: LAN (almeno funziona in sede)
                    effective_url = f"http://{ip}:{port}"
                    source = "lan_fallback"

    return {
        "ip": ip,
        "port": port,
        "internet": internet,
        "lan": lan,
        "offline": offline,
        "online": online,
        "lan_only": lan_only,
        "effective_url": effective_url,
        "public_ip": public_ip,
        "source": source,
    }



DATA_PATH = "data.json"
APP_PORT = 8501
LOGO_PATH = "logo.png"

# ⚠️ Per avere MAPPA CHE STAMPA SICURO nell'HTML:
# aggiungi in requirements.txt:
# staticmap==0.5.7
# pillow==10.4.0
# requests==2.32.3
#
# (Streamlit Cloud rilegge requirements e poi la mappa in stampa diventa un'IMMAGINE)

COLORI_STATI = {
    "In attesa al COC": {"color": "black", "hex": "#455a64"},
    "In uscita dal COC": {"color": "cadetblue", "hex": "#fff176"},
    "Arrivata sul luogo di intervento": {"color": "blue", "hex": "#2196f3"},
    "Intervento in corso": {"color": "red", "hex": "#e57373"},
    "Intervento concluso": {"color": "purple", "hex": "#9575cd"},
    "Rientro in corso": {"color": "orange", "hex": "#ffb74d"},
    "Rientrata al Coc": {"color": "green", "hex": "#81c784"},
}

# Colori fissi per SQUADRA (usati sia nei pallini in sidebar che nei marker in mappa)
# (cicla se le squadre sono più della palette)
COLORI_SQUADRE = [
    "#e53935",  # rosso
    "#1e88e5",  # blu
    "#43a047",  # verde
    "#fb8c00",  # arancio
    "#8e24aa",  # viola
    "#00897b",  # teal
    "#6d4c41",  # marrone
    "#546e7a",  # blu-grigio
    "#c0ca33",  # lime
    "#f4511e",  # arancio scuro
]

def _pick_next_team_color(used_hex: set) -> str:
    for hx in COLORI_SQUADRE:
        if hx not in used_hex:
            return hx
    return COLORI_SQUADRE[len(used_hex) % len(COLORI_SQUADRE)]

def ensure_team_colors() -> None:
    """Assicura che ogni squadra abbia un colore fisso ('mhex')."""
    used = set()
    for _name, info in st.session_state.squadre.items():
        hx = (info.get("mhex") or "").strip()
        if hx.startswith("#") and len(hx) == 7:
            used.add(hx)
    for name in sorted(st.session_state.squadre.keys()):
        info = st.session_state.squadre[name]
        hx = (info.get("mhex") or "").strip()
        if not (hx.startswith("#") and len(hx) == 7):
            info["mhex"] = _pick_next_team_color(used)
            used.add(info["mhex"])

def team_hex(team: str) -> str:
    info = st.session_state.squadre.get(team, {}) if hasattr(st.session_state, "squadre") else {}
    hx = (info.get("mhex") or "").strip()
    return hx if (hx.startswith("#") and len(hx) == 7) else "#1e88e5"


# =========================
# NATO – Spelling radio
# =========================
NATO = {
    "A":"Alfa","B":"Bravo","C":"Charlie","D":"Delta","E":"Echo","F":"Foxtrot",
    "G":"Golf","H":"Hotel","I":"India","J":"Juliett","K":"Kilo","L":"Lima",
    "M":"Mike","N":"November","O":"Oscar","P":"Papa","Q":"Quebec","R":"Romeo",
    "S":"Sierra","T":"Tango","U":"Uniform","V":"Victor","W":"Whiskey",
    "X":"X-ray","Y":"Yankee","Z":"Zulu"
}

# =========================
# QUERY PARAMS (ACCESSO CAMPO)
# =========================
try:
    qp = st.query_params
    qp_mode = (qp.get("mode") or "").strip()
    qp_team = (qp.get("team") or "").strip().upper()
    qp_token = (qp.get("token") or "").strip()
except Exception:
    qp_mode, qp_team, qp_token = "", "", ""

# Auto-refresh della pagina (solo Sala Operativa, non lato campo)



# =========================
# UTILS
# =========================
def img_to_base64(path: str) -> Optional[str]:
    if not path or not os.path.exists(path):
        return None
    ext = os.path.splitext(path)[1].lower().replace(".", "")
    if ext not in ("png", "jpg", "jpeg"):
        return None
    mime = "image/png" if ext == "png" else "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def bytes_to_data_uri_png(png_bytes: bytes) -> str:
    b64 = base64.b64encode(png_bytes).decode("utf-8")
    return f"data:image/png;base64,{b64}"

def text_color_for_bg(hex_color: str) -> str:
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return "#0b1220"
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    lum = (0.299 * r + 0.587 * g + 0.114 * b)
    return "#0b1220" if lum > 160 else "#ffffff"

def chip_stato(stato: str) -> str:
    bg = COLORI_STATI.get(stato, {}).get("hex", "#e2e8f0")
    fg = text_color_for_bg(bg)
    return (
        f"<span class='pc-chip' style='background:{bg};color:{fg};'>"
        f"<span class='pc-dot'></span>{stato}</span>"
    )

def _get_last_team_status(team: str) -> str:
    """Ritorna ultimo stato noto per la squadra: prima quello salvato in anagrafica, poi dal brogliaccio."""
    try:
        st0 = (st.session_state.squadre.get(team, {}) or {}).get("stato")
        if st0:
            return st0
    except Exception:
        pass
    # fallback: cerca nel brogliaccio l'ultimo evento con st valorizzato
    try:
        for ev in st.session_state.get("brogliaccio", []):
            if ev.get("sq") == team and ev.get("st"):
                return ev.get("st")
    except Exception:
        pass
    # default
    return list(COLORI_STATI.keys())[0]

def _sync_radio_status_to_team():
    """Quando cambia la squadra selezionata nel modulo radio, imposta lo stato al valore più recente di quella squadra."""
    team = st.session_state.get("radio_squadra_sel")
    if not team:
        return
    st_last = _get_last_team_status(team)
    # Imposta solo se diverso (evita loop) e se valido
    if st_last in COLORI_STATI and st.session_state.get("radio_stato_sel") != st_last:
        st.session_state["radio_stato_sel"] = st_last

def get_squadra_info(nome_sq: str) -> Dict[str, Any]:
    info = st.session_state.squadre.get(nome_sq, {})
    return {
        "capo": (info.get("capo") or "").strip(),
        "tel": (info.get("tel") or "").strip(),
        "stato": info.get("stato", "In attesa al COC"),
        "token": (info.get("token") or "").strip(),
        "token_created_at": (info.get("token_created_at") or "").strip(),
        "token_expires_at": (info.get("token_expires_at") or "").strip(),
        "token_last_access": (info.get("token_last_access") or "").strip(),
    }

def call_flow_from_row(row: dict) -> Tuple[str, str]:
    chi = (row.get("chi") or "").strip()
    sq = (row.get("sq") or "").strip()
    if chi.upper() == "SALA OPERATIVA":
        return "SALA OPERATIVA", (sq if sq else "—")
    return (sq if sq else "SQUADRA"), "SALA OPERATIVA"

def chip_call_flow(row: dict) -> str:
    a, b = call_flow_from_row(row)
    return f"<div class='pc-flow'>📞 <b>{a}</b> <span class='pc-arrow'>➜</span> 🎧 <b>{b}</b></div>"


def _folium_tiles_spec(choice: str | None = None) -> dict:
    """Restituisce specifiche tiles per Folium.

    choice:
      - "Topografica" (OpenTopoMap)
      - "Stradale" (OpenStreetMap)
      - "Satellite" (Esri World Imagery)
      - "Leggera" (CartoDB Positron)
    """
    c = (choice or "").strip().lower()

    if c in ("topografica", "topo", "opentopomap"):
        return {
            "name": "Topografica",
            "tiles": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
            "attr": "OpenTopoMap (CC-BY-SA)",
        }
    if c in ("satellite", "esri", "imagery"):
        return {
            "name": "Satellite",
            "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            "attr": "Tiles © Esri",
        }
    if c in ("leggera", "light", "positron", "cartodb"):
        # provider integrato Folium
        return {
            "name": "Leggera",
            "tiles": "CartoDB positron",
            "attr": "",
        }
    # default: stradale
    return {
        "name": "Stradale",
        "tiles": "OpenStreetMap",
        "attr": "",
    }


def _folium_base_choice() -> str:
    """Scelta base map per la mappa principale (app)."""
    return st.session_state.get("map_base_main", "Topografica")


def _folium_apply_base_layer(m: folium.Map, choice: str | None = None) -> folium.Map:
    """Applica il layer base selezionato alla mappa Folium (tiles + attr)."""
    spec = _folium_tiles_spec(choice or _folium_base_choice())
    tiles = spec["tiles"]
    attr = spec.get("attr", "")
    name = spec.get("name", "Base")

    # Usiamo tiles=None e aggiungiamo TileLayer per gestire sia provider "name" che URL custom.
    folium.TileLayer(tiles=tiles, attr=attr, name=name, control=False).add_to(m)
    return m


def build_folium_map_from_df(df: pd.DataFrame, center: list, zoom: int = 13, inbox: Optional[List[dict]] = None) -> folium.Map:
    m = folium.Map(location=center, zoom_start=zoom, tiles=None, prefer_canvas=True)
    _folium_apply_base_layer(m)
    ultime_pos = {}
    if not df.empty:
        for _, row in df.iterrows():
            pos = row.get("pos")
            sq = (row.get("sq") or "").strip()
            stt = (row.get("st") or "").strip()
            if isinstance(pos, list) and len(pos) == 2 and sq:
                ultime_pos[sq] = {"pos": pos, "st": stt}


    # Aggiunge anche le POSIZIONI PENDING (inbox) per visualizzarle subito in mappa
    if inbox:
        for mmsg in inbox:
            try:
                sqp = (mmsg.get("sq") or "").strip()
                posp = mmsg.get("pos")
                if isinstance(posp, list) and len(posp) == 2 and sqp:
                    # le pending NON sovrascrivono una posizione già valida da brogliaccio
                    ultime_pos.setdefault(sqp, {"pos": posp, "st": "📥 In attesa validazione"})
            except Exception:
                continue

    for sq, info in ultime_pos.items():
        stt = info["st"] or ""
        hx = team_hex(sq)
        folium.CircleMarker(
            location=info["pos"],
            radius=8,
            color=hx,
            weight=3,
            fill=True,
            fill_color=hx,
            fill_opacity=1.0,
            tooltip=f"{sq}: {stt}" if stt else sq,
        ).add_to(m)
    return m


def build_folium_map_from_events(events: List[dict], center: list, zoom: int = 13, inbox: Optional[List[dict]] = None) -> folium.Map:
    """Mappa più veloce: usa direttamente la lista eventi (brogliaccio) senza pandas.

    - prende l'ULTIMO punto per squadra (events è newest->oldest, quindi basta il primo punto visto per squadra)
    - aggiunge anche posizioni 'pending' (inbox) senza sovrascrivere quelle già valide
    """
    m = folium.Map(location=center, zoom_start=zoom, tiles=None, prefer_canvas=True)
    _folium_apply_base_layer(m)

    ultime_pos: Dict[str, Dict[str, Any]] = {}
    seen = set()

    if isinstance(events, list) and events:
        # newest -> oldest: il primo GPS per squadra è l'ultima posizione
        for row in events:
            sq = (row.get("sq") or "").strip()
            if not sq or sq in seen:
                continue
            pos = row.get("pos")
            if isinstance(pos, list) and len(pos) == 2:
                stt = (row.get("st") or "").strip()
                ultime_pos[sq] = {"pos": pos, "st": stt}
                seen.add(sq)
                # ottimizzazione: se abbiamo già tutte le squadre, possiamo fermarci
                if hasattr(st.session_state, "squadre") and len(seen) >= len(st.session_state.squadre):
                    break

    # posizioni pending inbox
    if inbox:
        for mmsg in inbox:
            try:
                sqp = (mmsg.get("sq") or "").strip()
                posp = mmsg.get("pos")
                if isinstance(posp, list) and len(posp) == 2 and sqp:
                    ultime_pos.setdefault(sqp, {"pos": posp, "st": "📥 In attesa validazione"})
            except Exception:
                continue

    for sq, info in ultime_pos.items():
        stt = info.get("st") or ""
        hx = team_hex(sq)
        folium.CircleMarker(
            location=info["pos"],
            radius=8,
            color=hx,
            weight=3,
            fill=True,
            fill_color=hx,
            fill_opacity=1.0,
            tooltip=f"{sq}: {stt}" if stt else sq,
        ).add_to(m)

    return m


def build_folium_map_from_latest_positions(
    ultime_pos: Dict[str, Dict[str, Any]],
    center: list,
    zoom: int = 13,
) -> folium.Map:
    """Costruisce una mappa Folium partendo già da posizioni 'deduplicate'."""
    m = folium.Map(location=center, zoom_start=zoom, tiles=None, prefer_canvas=True)
    _folium_apply_base_layer(m)
    for sq, info in (ultime_pos or {}).items():
        pos = info.get("pos")
        if not (isinstance(pos, list) and len(pos) == 2):
            continue
        stt = (info.get("st") or "").strip()
        hx = team_hex(sq)
        folium.CircleMarker(
            location=pos,
            radius=8,
            color=hx,
            weight=3,
            fill=True,
            fill_color=hx,
            fill_opacity=1.0,
            tooltip=f"{sq}: {stt}" if stt else sq,
        ).add_to(m)
    return m

def df_for_report(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    out["GPS"] = out["pos"].apply(
        lambda x: f"{x[0]:.4f}, {x[1]:.4f}" if isinstance(x, list) and len(x) == 2 else "OMISSIS"
    )

    def _caller_receiver(row):
        chi = (row.get("chi") or "").strip()
        sq = (row.get("sq") or "").strip()
        if chi.upper() == "SALA OPERATIVA":
            return "SALA OPERATIVA", sq if sq else "—"
        return sq if sq else "SQUADRA", "SALA OPERATIVA"

    cr = out.apply(_caller_receiver, axis=1, result_type="expand")
    out["CHI CHIAMA"] = cr[0]
    out["CHI RICEVE"] = cr[1]

    cols = ["ora", "CHI CHIAMA", "CHI RICEVE", "sq", "st", "mit", "ris", "GPS", "op"]
    for c in cols:
        if c not in out.columns:
            out[c] = ""

    out = out[cols].rename(
        columns={
            "ora": "ORA",
            "sq": "SQUADRA",
            "st": "STATO",
            "mit": "MESSAGGIO",
            "ris": "RISPOSTA",
            "op": "OPERATORE",
        }
    )
    return out


# =========================
# PERFORMANCE – CACHE
# =========================
def _hash_obj(o: Any) -> str:
    """Hash stabile e veloce (per cache) su piccoli oggetti JSON-compatibili."""
    try:
        s = json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        s = str(o)
    return hashlib.md5(s.encode("utf-8")).hexdigest()


@st.cache_data(show_spinner=False, ttl=60)
def _latest_positions_cached(events_slice: List[dict], inbox: List[dict], squad_names: List[str]) -> Dict[str, Dict[str, Any]]:
    """Estrae solo l'ULTIMA posizione per squadra (velocissimo) + inbox pending.

    La cache evita di rifare il lavoro a ogni rerun (che Streamlit fa spesso).
    """
    ultime_pos: Dict[str, Dict[str, Any]] = {}
    seen = set()

    if isinstance(events_slice, list) and events_slice:
        for row in events_slice:  # newest -> oldest
            sq = (row.get("sq") or "").strip()
            if not sq or sq in seen:
                continue
            pos = row.get("pos")
            if isinstance(pos, list) and len(pos) == 2:
                stt = (row.get("st") or "").strip()
                ultime_pos[sq] = {"pos": pos, "st": stt}
                seen.add(sq)
                if squad_names and len(seen) >= len(squad_names):
                    break

    # pending inbox (non sovrascrive)
    if inbox:
        for mmsg in inbox:
            try:
                sqp = (mmsg.get("sq") or "").strip()
                posp = mmsg.get("pos")
                if isinstance(posp, list) and len(posp) == 2 and sqp:
                    ultime_pos.setdefault(sqp, {"pos": posp, "st": "📥 In attesa validazione"})
            except Exception:
                continue

    return ultime_pos


@st.cache_data(show_spinner=False, ttl=60)
def _build_folium_from_latest_cached(latest: Dict[str, Dict[str, Any]], center: List[float], zoom: int) -> folium.Map:
    """Costruisce la mappa Folium partendo SOLO dalle ultime posizioni (pochi marker).

    La parte lenta è spesso il download delle tiles nel browser; qui riduciamo anche
    i marker e i JS ridondanti.
    """
    m = folium.Map(location=center, zoom_start=zoom, tiles=None, prefer_canvas=True)
    _folium_apply_base_layer(m)
    for sq, info in (latest or {}).items():
        stt = (info.get("st") or "").strip()
        hx = team_hex(sq)
        folium.CircleMarker(
            location=info.get("pos"),
            radius=8,
            color=hx,
            weight=3,
            fill=True,
            fill_color=hx,
            fill_opacity=1.0,
            tooltip=f"{sq}: {stt}" if stt else sq,
        ).add_to(m)
    return m

def qr_png_bytes(url: str) -> bytes:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# =========================
# STATIC MAP (PER STAMPA HTML AFFIDABILE)
# =========================
def _extract_points_latest_by_team(df: pd.DataFrame) -> List[Tuple[float, float, str]]:
    """
    Ritorna (lat, lon, label) con ultima posizione per squadra (dedup).
    """
    points = []
    if df.empty:
        return points

    # df è in ordine "brogliaccio" (noi inseriamo in testa), quindi per latest basta primo che ha pos per squadra
    seen = set()
    for _, row in df.iterrows():
        sq = (row.get("sq") or "").strip()
        pos = row.get("pos")
        if not sq or sq in seen:
            continue
        if isinstance(pos, list) and len(pos) == 2:
            try:
                lat, lon = float(pos[0]), float(pos[1])
            except Exception:
                continue
            stt = (row.get("st") or "").strip()
            label = f"{sq} · {stt}" if stt else sq
            points.append((lat, lon, label))
            seen.add(sq)
    return points

def _extract_points_all_events(df: pd.DataFrame) -> List[Tuple[float, float, str]]:
    """
    Ritorna (lat, lon, label) per tutti gli eventi con GPS (anche ripetuti).
    """
    points = []
    if df.empty:
        return points
    for _, row in df.iterrows():
        pos = row.get("pos")
        if isinstance(pos, list) and len(pos) == 2:
            try:
                lat, lon = float(pos[0]), float(pos[1])
            except Exception:
                continue
            sq = (row.get("sq") or "").strip()
            ora = (row.get("ora") or "").strip()
            stt = (row.get("st") or "").strip()
            label = " · ".join([x for x in [sq, ora, stt] if x])
            points.append((lat, lon, label if label else "Evento"))
    return points

def _extract_polyline_all_events(df: pd.DataFrame) -> List[Tuple[float, float]]:
    """
    Lista ordinata di punti (lat,lon) per disegnare una traccia.
    """
    line = []
    if df.empty:
        return line
    # qui metto cronologico: df è newest->oldest, quindi invertiamo
    for _, row in df.iloc[::-1].iterrows():
        pos = row.get("pos")
        if isinstance(pos, list) and len(pos) == 2:
            try:
                lat, lon = float(pos[0]), float(pos[1])
            except Exception:
                continue
            line.append((lat, lon))
    return line

def render_static_map_png(
    points: List[Tuple[float, float, str]],
    polyline: Optional[List[Tuple[float, float]]] = None,
    size: Tuple[int, int] = (1200, 700),
    zoom: int = 14,
) -> Optional[bytes]:
    """
    Ritorna PNG bytes di una mappa statica (stampabile).
    Richiede: staticmap + pillow + requests.
    """
    try:
        from staticmap import StaticMap, CircleMarker, Line  # type: ignore
    except Exception:
        return None

    try:
        smap = StaticMap(size[0], size[1], url_template="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png")
        # linea (percorso)
        if polyline and len(polyline) >= 2:
            smap.add_line(Line(polyline, "#111827", 3))  # colore scuro, spessore 3

        # marker
        for (lat, lon, _label) in points:
            # marker blu (staticmap non stampa label sul tile; ma almeno i punti ci sono)
            smap.add_marker(CircleMarker((lon, lat), "#2563eb", 10))

        image = smap.render(zoom=zoom)
        buf = BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=30)
def _static_map_png_cached(cache_key: str, points: List[Tuple[float, float, str]], zoom: int) -> Optional[bytes]:
    """PNG statico con cache breve.

    - serve per una "mappa rapida" (immagine) che si apre istantaneamente e non dipende dal caricamento tiles.
    - cache_key invalida quando cambiano i punti.
    """
    _ = cache_key
    return render_static_map_png(points=points, polyline=None, size=(1200, 650), zoom=zoom)

def make_html_report_bytes(
    squads: Dict[str, Any],
    brogliaccio: list,
    center: list,
    meta: dict,
) -> bytes:
    """
    Report HTML stampabile con:
    - Selettore squadra (TUTTE o singola)
    - Selettore mappa (Ultime posizioni / Tutti eventi / Percorso)
    - Mappa Folium integrata (iframe srcdoc) -> niente Pillow/staticmap.
    - Mappa "bloccata" (niente pan/zoom) per stampa pulita.
    - Legenda + scala.
    """
    import html as _html

    df_all = pd.DataFrame(brogliaccio or [])

    include_map = bool((meta or {}).get('include_map', True))
    include_map_js = 'true' if include_map else 'false'

    def _safe(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _df_to_html_table(df_view: pd.DataFrame) -> str:
        if df_view is None or df_view.empty:
            return "<div class='muted'>Nessun dato presente.</div>"

        dfv = df_view.copy()

        # Normalizza colonne principali
        if "ora" not in dfv.columns and "t" in dfv.columns:
            dfv["ora"] = dfv["t"]
        if "mit" not in dfv.columns:
            dfv["mit"] = ""
        if "ris" not in dfv.columns:
            dfv["ris"] = ""

        # Coord in formato leggibile
        if "pos" in dfv.columns and "coord" not in dfv.columns:
            def _fmt_pos(p):
                try:
                    if isinstance(p, (list, tuple)) and len(p) == 2:
                        return f"{float(p[0]):.6f}, {float(p[1]):.6f}"
                except Exception:
                    return ""
                return ""
            dfv["coord"] = dfv["pos"].apply(_fmt_pos)

        # Ordine + etichette per report
        col_order = ["ora", "sq", "chi", "st", "mit", "ris", "op", "coord"]
        col_labels = {
            "ora": "Ora",
            "sq": "Squadra",
            "chi": "Chiamante",
            "st": "Stato",
            "mit": "Messaggio",
            "ris": "Risposta",
            "op": "Operatore",
            "coord": "Coordinate",
        }
        keep = [c for c in col_order if c in dfv.columns]
        dfv = dfv[keep].rename(columns=col_labels)

        return dfv.to_html(index=False, classes="tbl", escape=True)


    # ---- meta
    ev_data = _safe(str(meta.get("ev_data", "")))
    ev_tipo = _safe(str(meta.get("ev_tipo", "")))
    ev_nome = _safe(str(meta.get("ev_nome", "")))
    ev_desc = _safe(str(meta.get("ev_desc", "")))
    op_name = _safe(str(meta.get("op_name", "")))
    map_style = str(meta.get("map_style", "Topografica"))

    # ---- tiles
    TILESETS = {
        "Stradale": {"tiles": "OpenStreetMap", "attr": "OpenStreetMap"},
        "Topografica": {"tiles": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", "attr": "OpenTopoMap"},
        "Satellite": {"tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                      "attr": "Esri World Imagery"},
    }
    if map_style not in TILESETS:
        map_style = "Topografica"
    tile = TILESETS[map_style]

    def _legend_macro() -> MacroElement:
        # legend inside map
        tmpl = Template("""
        {% macro html(this, kwargs) %}
        <div style="
            position: fixed;
            bottom: 18px;
            left: 18px;
            z-index: 9999;
            background: rgba(15, 23, 42, 0.85);
            color: #ffffff;
            padding: 10px 12px;
            border-radius: 12px;
            font-family: Arial, sans-serif;
            font-size: 13px;
            line-height: 1.25;
            box-shadow: 0 10px 24px rgba(0,0,0,.25);
            max-width: 260px;
        ">
          <div style="font-weight: 900; font-size: 12px; letter-spacing: .06em; opacity:.95; margin-bottom:6px;">
            LEGENDA
          </div>
          <div style="display:flex; gap:8px; align-items:center; margin:4px 0;">
            <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#e11d48;"></span>
            <span>Evento / posizione</span>
          </div>
          <div style="display:flex; gap:8px; align-items:center; margin:4px 0;">
            <span style="display:inline-block;width:14px;height:2px;background:#0ea5e9;"></span>
            <span>Percorso</span>
          </div>
          <div style="margin-top:6px; opacity:.85;">
            Base: {{this.map_style}}
          </div>
        </div>
        {% endmacro %}
        """)
        macro = MacroElement()
        macro._template = tmpl
        macro.map_style = map_style
        return macro

    def _normalize_points(points_raw):
        out = []
        for p in (points_raw or []):
            if isinstance(p, dict):
                lat = p.get("lat"); lon = p.get("lon")
                label = p.get("label", "")
            else:
                # tuple/list (lat, lon, label?)
                lat = p[0] if len(p) > 0 else None
                lon = p[1] if len(p) > 1 else None
                label = p[2] if len(p) > 2 else ""
            try:
                out.append((float(lat), float(lon), str(label)))
            except Exception:
                continue
        return out

    def _normalize_line(line_raw):
        out = []
        for p in (line_raw or []):
            if isinstance(p, dict):
                lat = p.get("lat"); lon = p.get("lon")
            else:
                lat = p[0] if len(p) > 0 else None
                lon = p[1] if len(p) > 1 else None
            try:
                out.append((float(lat), float(lon)))
            except Exception:
                continue
        return out

    def _folium_srcdoc(points_raw, line_raw=None, zoom=14) -> str:
        pts = _normalize_points(points_raw)
        line = _normalize_line(line_raw)

        # center fallback
        if pts:
            lat0, lon0, _ = pts[0]
        else:
            try:
                lat0 = float(center[0]); lon0 = float(center[1])
            except Exception:
                lat0, lon0 = 45.64, 11.48  # fallback Veneto

        # "bloccata" per stampa pulita
        m = folium.Map(
            location=[lat0, lon0],
            zoom_start=zoom,
            tiles=tile["tiles"],
            attr=tile["attr"],
            control_scale=True,
            zoom_control=False,
            dragging=False,
            scrollWheelZoom=False,
            doubleClickZoom=False,
            touchZoom=False,
        )

        # line
        if len(line) >= 2:
            folium.PolyLine(line, color="#0ea5e9", weight=4, opacity=0.9).add_to(m)

        # markers
        for (lat, lon, label) in pts:
            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                color="#ffffff",
                weight=2,
                fill=True,
                fill_color="#e11d48",
                fill_opacity=0.95,
                popup=_safe(label),
            ).add_to(m)

        m.add_child(_legend_macro())

        buf = io.BytesIO()
        m.save(buf, close_file=False)
        return buf.getvalue().decode("utf-8", errors="ignore")

    # helper: produce 3 map srcdocs for a df
    def _maps_for_df(df_x: pd.DataFrame) -> Dict[str, str]:
        # LATEST
        pts_latest = _extract_points_latest_by_team(df_x) if ("sq" in df_x.columns or "squadra" in df_x.columns) else _extract_points_all_events(df_x)
        src_latest = _folium_srcdoc(pts_latest, None, zoom=14)

        # ALL
        pts_all = _extract_points_all_events(df_x)
        src_all = _folium_srcdoc(pts_all, None, zoom=14)

        # TRACK
        line = _extract_polyline_all_events(df_x)
        src_track = _folium_srcdoc(pts_all, line if line else None, zoom=14)

        return {"LATEST": src_latest, "ALL": src_all, "TRACK": src_track}

    # build sections per squadra
    options_html = ["<option value='TUTTE'>TUTTE</option>"]
    sections_html = []

    # compute maps for totals
    maps_tot = _maps_for_df(df_all) if (include_map and df_all is not None and not df_all.empty) else {"LATEST": "", "ALL": "", "TRACK": ""}

    # per squadra
    for sq_name in sorted(list(squads.keys())):
        options_html.append(f"<option value='{_safe(sq_name)}'>{_safe(sq_name)}</option>")
        if df_all is None or df_all.empty:
            df_sq = pd.DataFrame()
        else:
            # colonne possibili: sq / squadra
            if "sq" in df_all.columns:
                df_sq = df_all[df_all["sq"] == sq_name].copy()
            elif "squadra" in df_all.columns:
                df_sq = df_all[df_all["squadra"] == sq_name].copy()
            else:
                df_sq = pd.DataFrame()

        maps_sq = _maps_for_df(df_sq) if (df_sq is not None and not df_sq.empty) else {"LATEST": "", "ALL": "", "TRACK": ""}
        tbl = _df_to_html_table(df_sq)

        map_html = ""
        if include_map:
            map_html = f"""
          <div class=\"mapwrap\">
            <iframe class=\"mapframe\" data-map=\"LATEST\" srcdoc=\"{_html.escape(maps_sq['LATEST'], quote=True)}\"></iframe>
            <iframe class=\"mapframe\" data-map=\"ALL\" srcdoc=\"{_html.escape(maps_sq['ALL'], quote=True)}\" style=\"display:none\"></iframe>
            <iframe class=\"mapframe\" data-map=\"TRACK\" srcdoc=\"{_html.escape(maps_sq['TRACK'], quote=True)}\" style=\"display:none\"></iframe>
          </div>
            """

        sections_html.append(f"""
        <section class="block" data-squad="{_safe(sq_name)}">
          <div class="block-title">Squadra: {_safe(sq_name)}</div>
          {map_html}
          <div class="tablewrap">{tbl}</div>
        </section>
        """)

    # total section
    tbl_tot = _df_to_html_table(df_all)

    map_html_tot = ""
    if include_map:
        map_html_tot = f"""
      <div class=\"mapwrap\">
        <iframe class=\"mapframe\" data-map=\"LATEST\" srcdoc=\"{_html.escape(maps_tot['LATEST'], quote=True)}\"></iframe>
        <iframe class=\"mapframe\" data-map=\"ALL\" srcdoc=\"{_html.escape(maps_tot['ALL'], quote=True)}\" style=\"display:none\"></iframe>
        <iframe class=\"mapframe\" data-map=\"TRACK\" srcdoc=\"{_html.escape(maps_tot['TRACK'], quote=True)}\" style=\"display:none\"></iframe>
      </div>
        """

    sections_html.insert(0, f"""
    <section class="block" data-squad="TUTTE">
      <div class="block-title">TUTTE LE SQUADRE</div>
          {map_html_tot}
          <div class="tablewrap">{tbl_tot}</div>
    </section>
    """)

    # -----------------------------
    # TEMPLATE HTML (NO f-string!)
    # -----------------------------
    template = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Report Sala Operativa</title>

<style>
  :root{
    --bg:#ffffff;
    --ink:#0f172a;
    --muted:#475569;
    --border:#e2e8f0;
    --accent:#0ea5e9;
  }
  *{ box-sizing:border-box; }
  body{
    margin:0;
    padding:24px;
    background:var(--bg);
    color:var(--ink);
    font-family: Arial, sans-serif;
  }

  /* Header */
  .head{
    border:2px solid var(--border);
    border-radius:16px;
    padding:16px 18px;
    margin-bottom:14px;
  }
  .h1{ font-weight:900; font-size:20px; margin:0 0 6px 0; }
  .meta{ color:var(--muted); font-size:13px; line-height:1.35; }
  .meta b{ color:var(--ink); }

  /* Controls */
  .controls{
    display:flex;
    gap:10px;
    flex-wrap:wrap;
    align-items:center;
    margin:14px 0 18px 0;
  }
  .controls label{ font-size:12px; color:var(--muted); font-weight:700; letter-spacing:.02em; }
  select{
    padding:10px 12px;
    border:1px solid #cbd5e1;
    border-radius:12px;
    font-weight:800;
    background:#fff;
  }
  .spacer{ flex:1 1 auto; }
  .hint{ font-size:12px; color:var(--muted); }

  button.printbtn{
    padding:10px 14px;
    border:1px solid var(--accent);
    background:var(--accent);
    color:#ffffff;
    border-radius:12px;
    font-weight:900;
    cursor:pointer;
  }
  button.printbtn:active{ transform: translateY(1px); }

  /* Blocks */
  .block{
    border:1px solid var(--border);
    border-radius:18px;
    padding:14px;
    margin:14px 0;
    break-inside: avoid;
  }
  .block-title{
    font-weight:900;
    margin:0 0 10px 0;
    font-size:15px;
  }

  /* Tables */
  .tablewrap{ overflow:auto; }
  table.tbl{
    width:100%;
    border-collapse: collapse;
    font-size:12px;
  }
  .tbl th, .tbl td{
    border:1px solid var(--border);
    padding:8px 10px;
    vertical-align: top;
  }
  .tbl th{
    background:#f8fafc;
    font-weight:900;
  }
  .muted{ color:var(--muted); }

  /* Map iframes */
  .mapwrap{
    margin: 8px 0 12px 0;
    border: 1px solid var(--border);
    border-radius: 14px;
    overflow: hidden;
  }
  .mapframe{
    width:100%;
    height:520px;
    border:0;
    display:block;
  }

  /* Print */
  @media print{
    body{ padding: 10mm; }
    .controls{ display:none !important; }
    a[href]::after{ content:""; }
    .mapframe{ height:170mm; }
  }

  /* QR link box: leggibile anche su sfondi chiari */
  .qr-linkbox{
    background:#0b1220 !important;
    border:1px solid rgba(255,255,255,.14) !important;
    padding:.55rem .65rem !important;
    border-radius:.75rem !important;
    color:#ffffff !important;
    word-break: break-all !important;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace !important;
    font-size:.9rem !important;
  }
  .qr-linkbox .qr-linklabel{
    display:block !important;
    margin-bottom:.25rem !important;
    font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif !important;
    font-weight:700 !important;
    color:#ffffff !important;
  }
</style>
</head>

<body>
  <div class="head">
    <div class="h1">Report Sala Operativa – %%EV_NOME%%</div>
    <div class="meta">
      <div><b>Data:</b> %%EV_DATA%% &nbsp; <b>Tipo:</b> %%EV_TIPO%%</div>
      <div><b>Operatore:</b> %%OP_NAME%%</div>
      <div>%%EV_DESC%%</div>
    </div>
  </div>

  <div class="controls">
    <div>
      <label>Squadra</label><br/>
      <select id="selSquad">
        %%OPTIONS%%
      </select>
    </div>

    <div id="mapControls">
      <label>Mappa</label><br/>
      <select id="selMap">
        <option value="LATEST">Ultime posizioni</option>
        <option value="ALL">Tutti eventi</option>
        <option value="TRACK">Percorso</option>
      </select>
    </div>

    <div class="spacer"></div>

    <button class="printbtn" onclick="window.print()">🖨️ Stampa PDF</button>
    <div class="hint">Suggerito: Chrome/Edge → “Salva come PDF”</div>
  </div>

  <div id="sections">
    %%SECTIONS%%
  </div>

<script>
  const includeMap = %%INCLUDE_MAP%%;

  function showSection(sq){
    document.querySelectorAll("section.block").forEach(sec=>{
      const ok = (sec.getAttribute("data-squad") === sq);
      sec.style.display = ok ? "block" : "none";
    });
  }

  function switchMap(which){
    document.querySelectorAll("section.block").forEach(sec=>{
      sec.querySelectorAll("iframe.mapframe").forEach(fr=>{
        const m = fr.getAttribute("data-map");
        fr.style.display = (m === which) ? "block" : "none";
      });
    });
  }

  function onInit(){
    const sel = document.getElementById("selSquad");
    const selMap = document.getElementById("selMap");
    const mapControls = document.getElementById("mapControls");

    if(!includeMap){
      if(mapControls) mapControls.style.display = "none";
      // Nasconde eventuali mappe presenti (difensivo)
      document.querySelectorAll("iframe.mapframe").forEach(fr=>{ fr.style.display = "none"; });
    }

    showSection(sel.value);
    if(includeMap){ switchMap(selMap.value); }

    sel.addEventListener("change", ()=>{
      showSection(sel.value);
      if(includeMap){ switchMap(selMap.value); }
    });

    if(selMap){
      selMap.addEventListener("change", ()=>{
        if(includeMap){ switchMap(selMap.value); }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", onInit);
</script>

</body>
</html>
"""

    html_doc = (
        template
        .replace("%%EV_NOME%%", ev_nome)
        .replace("%%EV_DATA%%", ev_data)
        .replace("%%EV_TIPO%%", ev_tipo)
        .replace("%%EV_DESC%%", ev_desc)
        .replace("%%OP_NAME%%", op_name)
        .replace("%%OPTIONS%%", "".join(options_html))
        .replace("%%SECTIONS%%", "".join(sections_html))
        .replace("%%INCLUDE_MAP%%", include_map_js)
    )

    return html_doc.encode("utf-8")
    return html_doc.encode("utf-8")
def default_state_payload():
    return {
        "brogliaccio": [],
        "inbox": [],
        "squadre": {"SQUADRA 1": {"stato": "In attesa al COC", "capo": "", "tel": "", "token": uuid.uuid4().hex}},
        "pos_mappa": [45.7075, 11.4772],
        "op_name": "",
        "ev_data": datetime.now().date().isoformat(),
        "ev_tipo": "Emergenza",
        "ev_nome": "",
        "ev_desc": "",
        "BASE_URL": "",
        "cnt_conclusi": 0,
    }


# =========================
# OUTBOX (invii in attesa di salvataggio su disco)
# =========================
OUTBOX_PENDING_FILE = "outbox_pending.json"

def _load_outbox_pending() -> list:
    try:
        if os.path.exists(OUTBOX_PENDING_FILE):
            with open(OUTBOX_PENDING_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception:
        pass
    return []

def _save_outbox_pending(items: list) -> None:
    try:
        with open(OUTBOX_PENDING_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _outbox_init():
    if "outbox_pending" not in st.session_state:
        st.session_state.outbox_pending = _load_outbox_pending()

def _outbox_add(item: dict):
    _outbox_init()
    st.session_state.outbox_pending.append(item)
    _save_outbox_pending(st.session_state.outbox_pending)

def _outbox_clear():
    st.session_state.outbox_pending = []
    _save_outbox_pending([])

def _outbox_retry_save() -> bool:
    try:
        ok = save_data_to_disk(force=True)
        if ok:
            _outbox_clear()
        return bool(ok)
    except Exception:
        return False


def _photo_sig(photo_obj: dict) -> dict:
    """Firma leggera foto: evita confronto base64 completo."""
    if not photo_obj or not isinstance(photo_obj, dict):
        return {}
    b64 = photo_obj.get("b64") or ""
    return {"name": photo_obj.get("name",""), "type": photo_obj.get("type",""), "len": len(b64)}

def _entry_sig(e: dict) -> dict:
    if not isinstance(e, dict):
        return {}
    d = dict(e)
    if "foto" in d:
        d["foto"] = _photo_sig(d.get("foto"))
    return d

def save_data_to_disk(force: bool = False) -> bool:
    """Salvataggio veloce + atomico."""
    payload = {
        "brogliaccio": [dict(x, foto=_normalize_photo_obj(x.get("foto"))) for x in st.session_state.brogliaccio],
        "inbox": [dict(x, foto=_normalize_photo_obj(x.get("foto"))) for x in st.session_state.inbox],
        "squadre": st.session_state.squadre,
        "pos_mappa": st.session_state.pos_mappa,
        "op_name": st.session_state.op_name,
        "ev_data": str(st.session_state.ev_data),
        "ev_tipo": st.session_state.ev_tipo,
        "ev_nome": st.session_state.ev_nome,
        "ev_desc": st.session_state.ev_desc,
        "BASE_URL": st.session_state.get("BASE_URL", ""),
        "cnt_conclusi": st.session_state.get("cnt_conclusi", 0),
    }

    sig = None
    try:
        sig_obj = {
            "brogliaccio": [_entry_sig(x) for x in (payload.get("brogliaccio") or [])],
            "inbox": [_entry_sig(x) for x in (payload.get("inbox") or [])],
            "squadre": payload.get("squadre") or {},
            "pos_mappa": payload.get("pos_mappa") or [],
            "op_name": payload.get("op_name") or "",
            "ev_data": payload.get("ev_data") or "",
            "ev_tipo": payload.get("ev_tipo") or "",
            "ev_nome": payload.get("ev_nome") or "",
            "ev_desc": payload.get("ev_desc") or "",
            "BASE_URL": payload.get("BASE_URL") or "",
            "cnt_conclusi": payload.get("cnt_conclusi") or 0,
        }
        sig = hashlib.sha1(json.dumps(sig_obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    except Exception:
        sig = None

    if not force and sig is not None and st.session_state.get("_last_saved_sig") == sig:
        return False

    try:
        tmp_path = DATA_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp_path, DATA_PATH)
        if sig is not None:
            st.session_state["_last_saved_sig"] = sig
        return True
    except Exception:
        return False

def load_data_from_disk():
    if not os.path.exists(DATA_PATH):
        return False
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return False

    st.session_state.brogliaccio = payload.get("brogliaccio", [])
    st.session_state.inbox = payload.get("inbox", [])
    st.session_state.squadre = payload.get("squadre", default_state_payload()["squadre"])
    st.session_state.pos_mappa = payload.get("pos_mappa", [45.7075, 11.4772])
    st.session_state.op_name = payload.get("op_name", "")
    st.session_state.ev_data = datetime.fromisoformat(payload.get("ev_data", datetime.now().date().isoformat())).date()
    st.session_state.ev_tipo = payload.get("ev_tipo", "Emergenza")
    st.session_state.ev_nome = payload.get("ev_nome", "")
    st.session_state.ev_desc = payload.get("ev_desc", "")
    st.session_state.BASE_URL = payload.get("BASE_URL", "") or ""
    st.session_state.cnt_conclusi = int(payload.get("cnt_conclusi", 0) or 0)
    ensure_inbox_ids()
    return True


# =========================
# AUTO-REFRESH smart (solo nuovi eventi + pausa durante scrittura)
# =========================
def _disk_events_signature() -> str:
    """Firma leggera degli eventi (inbox+brogliaccio) letta da disco.
    Serve per capire se sono arrivati nuovi eventi senza rifare render pesanti.
    """
    try:
        if not os.path.exists(DATA_PATH):
            return "no-data"
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
        inbox = payload.get("inbox", []) or []
        brog = payload.get("brogliaccio", []) or []
        last_in = (inbox[-1].get("id") if inbox else "") or ""
        last_br = (brog[-1].get("id") if brog else "") or ""
        # include anche le lunghezze per robustezza
        return f"i{len(inbox)}:{last_in}|b{len(brog)}:{last_br}"
    except Exception:
        return "sig-err"

def _mark_typing(ttl_seconds: int = 20) -> None:
    """Segna che l'utente sta scrivendo: sospende l'auto-refresh per un po'."""
    try:
        st.session_state["_typing_until"] = time.time() + int(ttl_seconds)
    except Exception:
        pass

def _is_user_typing() -> bool:
    try:
        return time.time() < float(st.session_state.get("_typing_until", 0) or 0)
    except Exception:
        return False

def _fmt_last_update(ts: float | None) -> str:
    try:
        if not ts:
            return "—"
        dt = datetime.fromtimestamp(float(ts))
        return dt.strftime("%H:%M:%S")
    except Exception:
        return "—"

def load_data_from_uploaded_json(file_bytes: bytes):
    payload = json.loads(file_bytes.decode("utf-8"))
    st.session_state.brogliaccio = payload.get("brogliaccio", [])
    st.session_state.inbox = payload.get("inbox", [])
    st.session_state.squadre = payload.get("squadre", default_state_payload()["squadre"])
    st.session_state.pos_mappa = payload.get("pos_mappa", [45.7075, 11.4772])
    st.session_state.op_name = payload.get("op_name", "")
    st.session_state.ev_data = datetime.fromisoformat(payload.get("ev_data", datetime.now().date().isoformat())).date()
    st.session_state.ev_tipo = payload.get("ev_tipo", "Emergenza")
    st.session_state.ev_nome = payload.get("ev_nome", "")
    st.session_state.ev_desc = payload.get("ev_desc", "")
    st.session_state.BASE_URL = payload.get("BASE_URL", "") or ""
    st.session_state.cnt_conclusi = int(payload.get("cnt_conclusi", 0) or 0)
    save_data_to_disk()
    ensure_inbox_ids()



def ensure_inbox_ids() -> None:
    """Assicura che ogni messaggio in inbox abbia un id stabile (evita bug widget/rerun)."""
    inbox = st.session_state.get("inbox", [])
    changed = False
    if isinstance(inbox, list):
        for m in inbox:
            if isinstance(m, dict):
                if not m.get("id"):
                    m["id"] = uuid.uuid4().hex
                    changed = True
    if changed:
        # non forziamo save qui sempre: lo farà chi chiama, ma teniamo consistenza
        pass
# =========================
# INIT STATE
# =========================
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.open_map_event = None
    st.session_state.team_edit_open = None
    st.session_state.team_qr_open = None

    ok = load_data_from_disk()
    ensure_inbox_ids()
    # inizializza contatore conclusi se mancante (deriva dal brogliaccio)
    if "cnt_conclusi" not in st.session_state or st.session_state.cnt_conclusi is None:
        st.session_state.cnt_conclusi = sum(1 for r in st.session_state.get("brogliaccio", []) if r.get("st") == "Intervento concluso")
    if not ok:
        d = default_state_payload()
        st.session_state.brogliaccio = d["brogliaccio"]
        st.session_state.inbox = d["inbox"]
        ensure_inbox_ids()
        st.session_state.squadre = d["squadre"]
        st.session_state.pos_mappa = d["pos_mappa"]
        st.session_state.op_name = d["op_name"]
        st.session_state.ev_data = datetime.fromisoformat(d["ev_data"]).date()
        st.session_state.ev_tipo = d["ev_tipo"]
        st.session_state.ev_nome = d["ev_nome"]
        st.session_state.ev_desc = d["ev_desc"]
        st.session_state.cnt_conclusi = 0
        st.session_state.BASE_URL = d["BASE_URL"]
        save_data_to_disk()

# assicura token a tutte le squadre
for _, info in st.session_state.squadre.items():
    if "token" not in info or not info["token"]:
        info["token"] = uuid.uuid4().hex


# =========================
# SYNC MULTI-SESSION (Caposquadra -> Console)
# =========================
# Se un caposquadra invia dal proprio link QR, scrive su DATA_PATH.
# La console vede i nuovi dati al prossimo rerun: qui forziamo un reload quando il file cambia.
if not st.session_state.get("field_ok"):
    try:
        _mtime = os.path.getmtime(DATA_PATH) if os.path.exists(DATA_PATH) else None
        if _mtime and st.session_state.get("_data_mtime") != _mtime:
            load_data_from_disk()
            st.session_state._data_mtime = _mtime
    except Exception:
        pass

# =========================
# AUTO BASE URL (opzionale: streamlit-js-eval)
# =========================
try:
    from streamlit_js_eval import get_page_location  # type: ignore
    loc = get_page_location()
    if isinstance(loc, dict):
        origin = (loc.get("origin") or "").strip().rstrip("/")
        if origin and (not st.session_state.get("BASE_URL")):
            st.session_state.BASE_URL = origin
except Exception:
    pass



# =========================
# GEOLOCATION (CAPOSQUADRA)
# =========================
def _extract_latlon(geo: Any) -> Optional[List[float]]:
    """Accetta vari formati (streamlit-js-eval) e ritorna [lat, lon] oppure None."""
    if not isinstance(geo, dict):
        return None

    # Formato A: {"latitude": .., "longitude": ..}
    lat = geo.get("latitude")
    lon = geo.get("longitude")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return [float(lat), float(lon)]

    # Formato B: {"coords": {"latitude":.., "longitude":..}}
    coords = geo.get("coords")
    if isinstance(coords, dict):
        lat = coords.get("latitude")
        lon = coords.get("longitude")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return [float(lat), float(lon)]

    # Formato C: {"lat":.., "lng":..} / {"lon":..}
    lat = geo.get("lat")
    lon = geo.get("lng") if "lng" in geo else geo.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return [float(lat), float(lon)]

    return None

def get_phone_gps_once() -> Optional[List[float]]:
    """Prova a leggere il GPS dal browser (telefono).
    Usa `streamlit-js-eval` se disponibile; altrimenti ritorna None.
    """
    try:
        from streamlit_js_eval import get_geolocation  # type: ignore
        geo = get_geolocation()
        return _extract_latlon(geo)
    except Exception:
        st.session_state["_gps_dep_missing"] = True
        return None

# =========================
# TEAM OPS
# =========================
def update_team(old_name: str, new_name: str, capo: str, tel: str) -> Tuple[bool, str]:
    old_name = (old_name or "").strip().upper()
    new_name = (new_name or "").strip().upper()
    capo = (capo or "").strip()
    tel = (tel or "").strip()

    if not old_name or old_name not in st.session_state.squadre:
        return False, "Seleziona una squadra valida."
    if not new_name:
        return False, "Il nuovo nome non può essere vuoto."
    if new_name != old_name and new_name in st.session_state.squadre:
        return False, "Esiste già una squadra con questo nome."

    if new_name != old_name:
        st.session_state.squadre[new_name] = st.session_state.squadre.pop(old_name)

        for msg in st.session_state.inbox:
            if (msg.get("sq") or "").strip().upper() == old_name:
                msg["sq"] = new_name

        for b in st.session_state.brogliaccio:
            if (b.get("sq") or "").strip().upper() == old_name:
                b["sq"] = new_name
            if (b.get("chi") or "").strip().upper() == old_name:
                b["chi"] = new_name

        if st.session_state.team_edit_open == old_name:
            st.session_state.team_edit_open = new_name
        if st.session_state.team_qr_open == old_name:
            st.session_state.team_qr_open = new_name

    st.session_state.squadre[new_name]["capo"] = capo
    st.session_state.squadre[new_name]["tel"] = tel
    if "token" not in st.session_state.squadre[new_name] or not st.session_state.squadre[new_name]["token"]:
        st.session_state.squadre[new_name]["token"] = uuid.uuid4().hex

    save_data_to_disk()
    return True, f"Aggiornata: {old_name} → {new_name}"

def regenerate_team_token(team: str) -> None:
    team = (team or "").strip().upper()
    if team in st.session_state.squadre:
        st.session_state.squadre[team]["token"] = uuid.uuid4().hex
        st.session_state.squadre[team]["token_created_at"] = datetime.now().isoformat(timespec="seconds")
        st.session_state.squadre[team]["token_expires_at"] = (datetime.now() + timedelta(hours=TOKEN_TTL_HOURS)).isoformat(timespec="seconds")
        st.session_state.squadre[team]["token_last_access"] = ""
        save_data_to_disk()

def delete_team(team: str) -> Tuple[bool, str]:
    team = (team or "").strip().upper()
    if team not in st.session_state.squadre:
        return False, "Squadra non trovata."
    if len(st.session_state.squadre) <= 1:
        return False, "Deve rimanere almeno 1 squadra."
    del st.session_state.squadre[team]
    st.session_state.inbox = [m for m in st.session_state.inbox if (m.get("sq") or "").strip().upper() != team]
    if st.session_state.team_edit_open == team:
        st.session_state.team_edit_open = None
    if st.session_state.team_qr_open == team:
        st.session_state.team_qr_open = None
    save_data_to_disk()
    return True, f"Squadra eliminata: {team}"

# =========================
# ACCESSO PROTETTO
# =========================

def require_login():
    # Se OFFLINE totale: niente accesso caposquadra via link
    if st.session_state.get("NET_OFFLINE"):
        st.session_state.auth_ok = True
        st.session_state.field_ok = False
        return

    # Accesso diretto caposquadra via link QR
    if (
        qp_mode.lower() == "campo"
        and qp_team in st.session_state.get("squadre", {})
        and qp_token
        and qp_token == st.session_state.squadre[qp_team].get("token")
    ):
        # Verifica scadenza token (se presente)
        exp = (st.session_state.squadre[qp_team].get("token_expires_at") or "").strip()
        if exp:
            try:
                exp_dt = datetime.fromisoformat(exp)
                if datetime.now() > exp_dt:
                    st.session_state.auth_ok = False
                    st.session_state.field_ok = False
                    st.session_state.field_team = None
                    st.warning("Token caposquadra scaduto. Rigenera il QR dalla Sala Operativa.")
                    return
            except Exception:
                pass

        # Log ultimo accesso
        st.session_state.squadre[qp_team]["token_last_access"] = datetime.now().isoformat(timespec="seconds")
        save_data_to_disk()

        st.session_state.auth_ok = False
        st.session_state.field_ok = True
        st.session_state.field_team = qp_team
        return

    # Login Sala Operativa (password opzionale)
    pw = None
    try:
        pw = st.secrets.get("APP_PASSWORD", None)
    except Exception:
        pw = None

    # Se la password non è impostata: permetti accesso locale (utile in emergenza)
    if not pw:
        st.session_state.auth_ok = True
        st.session_state.field_ok = False
        return

    # Se già autenticato
    if st.session_state.get("auth_ok"):
        st.session_state.field_ok = False
        return

    st.sidebar.warning("🔐 Accesso Sala Operativa")
    entered = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Accedi"):
        if entered == pw:
            st.session_state.auth_ok = True
            st.session_state.field_ok = False
            st.rerun()
        else:
            st.sidebar.error("Password errata.")
# =========================
# NET STATE (pre-sidebar) + LOGIN
# =========================
if "force_offline" not in st.session_state:
    st.session_state.force_offline = False

# Calcolo stato rete prima della sidebar (serve per decidere accesso/ruolo)
_net = compute_net_state(bool(st.session_state.get("force_offline", False)), APP_PORT)
st.session_state.EFFECTIVE_URL = _net.get("effective_url", "")
st.session_state.NET_OFFLINE = bool(_net.get("offline", False))
st.session_state.NET_LAN_ONLY = bool(_net.get("lan_only", False))
st.session_state.NET_ONLINE = bool(_net.get("online", False))
st.session_state.NET_IP = _net.get("ip", "")
st.session_state.NET_PORT = int(_net.get("port", APP_PORT) or APP_PORT)

# Per compatibilità: BASE_URL usato in parti vecchie
if st.session_state.NET_ONLINE:
    st.session_state.BASE_URL = (st.session_state.get("PUBLIC_URL") or "").strip().rstrip("/")

# Login / accesso (mostra form in sidebar se serve)
require_login()
if (not st.session_state.get("auth_ok")) and (not st.session_state.get("field_ok")):
    st.stop()


# =========================
# AUTO-REFRESH (solo Sala Operativa DOPO login)
# =========================
# Auto aggiornamento (SOFT): evita reload pagina (non perde login)
if st.session_state.get("auth_ok") and (not st.session_state.get("field_ok")) and st.session_state.get("AUTO_REFRESH", True):
    # 🧭 indicatore ultimo aggiornamento (ogni run)
    st.session_state["_last_update_ts"] = time.time()

    # 🔕 pausa automatica refresh quando scrivi (evita reset/scroll mentre compili messaggi)
    if not _is_user_typing():
        sec = int(st.session_state.get("AUTO_REFRESH_SEC") or 20)

        # 📡 refresh solo su nuovi eventi:
        # - se firma eventi è cambiata → usa intervallo selezionato
        # - se non cambia → rallenta a 60s per ridurre reload inutili
        cur_sig = _disk_events_signature()
        last_sig = st.session_state.get("_last_events_sig")
        new_events = (last_sig is None) or (cur_sig != last_sig)
        st.session_state["_last_events_sig"] = cur_sig

        interval_ms = (sec * 1000) if new_events else 60000  # 60s quando non arrivano novità

        try:
            from streamlit_autorefresh import st_autorefresh  # pip install streamlit-autorefresh (se serve)
            st_autorefresh(interval=interval_ms, key=f"sala_autorefresh_{sec}_{'new' if new_events else 'idle'}")
        except Exception:
            # Nessun auto refresh disponibile: usa il pulsante "Aggiorna" o disattiva Auto aggiorna.
            pass



# =========================
# CSS (UI)
# =========================
st.markdown("""
<style>
header[data-testid="stHeader"] { background: transparent; border:none; }
.stApp { background: linear-gradient(180deg,#e9eef3 0%, #dfe7ee 100%); color:#0b1220; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }

.pc-hero{
  background: radial-gradient(1200px 300px at 50% 0%, rgba(255,255,255,.18), rgba(255,255,255,0)),
              linear-gradient(135deg, #0d47a1 0%, #0b1f3a 80%);
  color:white; border: 1px solid rgba(255,255,255,.18);
  border-radius: 18px; padding: 18px 22px;
  margin-top: -60px; margin-bottom: 18px;
  box-shadow: 0 10px 30px rgba(2,6,23,.12);
  display:flex; align-items:center; justify-content:space-between; gap:16px;
}
.pc-hero-left{ display:flex; align-items:center; gap:14px; }
.pc-hero .title{ font-size: 2.05rem; font-weight: 900; text-transform: uppercase; margin:0; letter-spacing: 1px; }
.pc-hero .subtitle{ margin: 2px 0 0 0; opacity:.85; font-size: 1rem; }
.pc-logo{ width: 64px; height: 64px; border-radius: 16px; background: rgba(255,255,255,.12);
  border: 1px solid rgba(255,255,255,.22); padding: 6px; object-fit: contain; }
.pc-badge{ background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.22);
  padding: 10px 14px; border-radius: 999px; font-weight: 800; white-space: nowrap; }
.pc-card{ background: #fff; border: 1px solid rgba(15,23,42,.15);
  border-radius: 16px; padding: 18px; box-shadow: 0 8px 22px rgba(2,6,23,.08); margin-bottom: 14px; }
.pc-chip{ display:inline-flex; align-items:center; gap:8px; padding:6px 10px; border-radius:999px;
  font-weight:900; font-size:.85rem; border:1px solid rgba(15,23,42,.12); line-height:1; }
.pc-dot{ width:10px; height:10px; border-radius:999px; background: rgba(255,255,255,.85); border:1px solid rgba(15,23,42,.15); }
.pc-flow{
  background: linear-gradient(90deg, #fff7cc 0%, #dbeafe 100%);
  border: 1px solid rgba(15,23,42,.12);
  border-radius: 14px;
  padding: 10px 12px;
  font-size: 1.05rem;
  font-weight: 900;
  display: inline-block;
  margin: 6px 0 10px 0;
  box-shadow: 0 8px 18px rgba(2,6,23,.08);
}
.pc-arrow{ margin: 0 10px; opacity: .9; }
.pc-metric-color{ border-radius: 16px; padding: 14px; border: 1px solid rgba(15,23,42,.12); box-shadow: 0 8px 22px rgba(2,6,23,.10); }
.pc-metric-color .k{ font-size:.85rem; font-weight: 900; text-transform: uppercase; letter-spacing: .8px; opacity: .95; }
.pc-metric-color .v{ font-size: 2.1rem; font-weight: 950; margin-top: 2px; }
.pc-alert{ background: linear-gradient(135deg, #ff4d4d 0%, #ff7a59 100%);
  color:white; padding: 14px 16px; border-radius: 14px; font-weight: 900; text-align:center;
  box-shadow: 0 12px 28px rgba(255,77,77,.22); border: 1px solid rgba(255,255,255,.22); margin-bottom: 10px; }

section[data-testid="stSidebar"]{
  background: linear-gradient(180deg, #123356 0%, #0b2542 100%) !important;
  border-right: 1px solid rgba(255,255,255,.10) !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3{
  color: #f8fafc !important;
  font-weight: 900 !important;
}
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{
  color: rgba(248,250,252,.95) !important;
  font-weight: 800 !important;
}
section[data-testid="stSidebar"] hr{ border-color: rgba(255,255,255,.14) !important; }
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] textarea{
  background: #ffffff !important;
  color: #0b1220 !important;
  border: 1px solid rgba(15,23,42,.22) !important;
  border-radius: 12px !important;
  font-weight: 800 !important;
}

/* Fix visibilità testo nei campi input (Streamlit BaseWeb) */
section[data-testid="stSidebar"] div[data-baseweb="input"] input,
section[data-testid="stSidebar"] div[data-baseweb="textarea"] textarea{
  color: #0b1220 !important;
  background: #ffffff !important;
}
section[data-testid="stSidebar"] div[data-baseweb="input"] input::placeholder{
  color: rgba(71,85,105,.85) !important;
}

/* File uploader (sidebar): nasconde la scheda "Drag and drop..." e rende il box compatto */
section[data-testid="stSidebar"] div[data-testid="stFileUploaderDropzoneInstructions"],
section[data-testid="stSidebar"] div[data-testid="stFileUploaderDropzoneInstructions"] *{
  display: none !important;
}
section[data-testid="stSidebar"] div[data-testid="stFileUploaderDropzone"]{
  padding: .35rem .45rem !important;
  min-height: 48px !important;
  border-radius: 12px !important;
  background: rgba(255,255,255,.10) !important;
  border: 1px solid rgba(255,255,255,.22) !important;
}
section[data-testid="stSidebar"] div[data-testid="stFileUploaderDropzone"]:hover{
  border-color: rgba(255,255,255,.35) !important;
}
section[data-testid="stSidebar"] div[data-testid="stFileUploaderDropzone"] button{
  padding: .35rem .6rem !important;
  border-radius: 10px !important;
  font-weight: 950 !important;
}

/* Bottone del file-uploader: solo icona (contraria al download) */
section[data-testid="stSidebar"] div[data-testid="stFileUploaderDropzone"] button span{ display:none !important; }
section[data-testid="stSidebar"] div[data-testid="stFileUploaderDropzone"] button::before{
  content: "📦⬆️";
  font-size: 1.15rem;
  line-height: 1;
}
section[data-testid="stSidebar"] div[data-baseweb="select"] > div{
  background: #ffffff !important;
  border: 1px solid rgba(15,23,42,.22) !important;
  border-radius: 12px !important;
}
section[data-testid="stSidebar"] div[data-baseweb="select"] span{
  color: #0b1220 !important;
  font-weight: 900 !important;
}
section[data-testid="stSidebar"] .stButton > button,
section[data-testid="stSidebar"] div[data-testid="stFormSubmitButton"] > button{
  width: 100% !important;
  background: linear-gradient(180deg, #334155 0%, #1f2937 100%) !important;
  color: #ffffff !important;
  border: 1px solid rgba(255,255,255,.18) !important;
  border-radius: 12px !important;
  font-weight: 950 !important;
}
section[data-testid="stSidebar"] .stDownloadButton > button{
  width: 100% !important;
  background: linear-gradient(180deg, #fde68a 0%, #fbbf24 100%) !important;
  color: #0b1220 !important;
  border: 1px solid rgba(15,23,42,.18) !important;
  border-radius: 12px !important;
  font-weight: 950 !important;
}

/* Sidebar — lista squadre compatta */
.pc-sqdot{
  width: 12px; height: 12px;
  border-radius: 999px;
  margin-top: 10px;
  border: 1px solid rgba(255,255,255,.35);
  box-shadow: 0 6px 14px rgba(2,6,23,.18);
}
.pc-sqrow{ line-height: 1.1; padding: 2px 0; }
.pc-sqname{ font-weight: 950; color: #f8fafc; font-size: .95rem; }
.pc-sqsub{ font-weight: 800; color: rgba(248,250,252,.92); font-size: .74rem; margin-top: 2px; }

/* NATO mini (solo sala radio) */
.nato-title{margin-top:10px;font-weight:950;color:#0d47a1;font-size:.9rem;}
.nato-mini{display:grid;grid-template-columns:repeat(auto-fill,minmax(74px,1fr));gap:6px;margin-top:10px;}
.nato-chip{background:#f1f5f9;border:1px solid rgba(15,23,42,.15);border-radius:10px;padding:6px;text-align:center;line-height:1.05;}
.nato-letter{font-size:.92rem;font-weight:950;color:#0d47a1;}
.nato-word{font-size:.70rem;font-weight:850;color:#334155;}
@media print{.nato-title,.nato-mini,.nato-spell{display:none!important;}}


/* Expander: sostituisce la freccia con + / - e nasconde la freccia originale (anche se cambia DOM) */
div[data-testid="stExpander"] [data-testid="stExpanderToggleIcon"],
div[data-testid="stExpander"] summary svg,
div[data-testid="stExpander"] summary [data-testid="stExpanderToggleIcon"],
div[data-testid="stExpander"] summary span[aria-hidden="true"]{
  display: none !important;   /* nasconde la freccia originale */
}

/* Header expander in sidebar: NON deve diventare bianco quando aperto */
section[data-testid="stSidebar"] div[data-testid="stExpander"] summary{
  background: linear-gradient(180deg, rgba(30,41,59,.55), rgba(15,23,42,.35)) !important;
  border: 1px solid rgba(255,255,255,.10) !important;
  border-radius: 16px !important;
}
section[data-testid="stSidebar"] div[data-testid="stExpander"][open] summary{
  background: linear-gradient(180deg, rgba(30,41,59,.60), rgba(15,23,42,.40)) !important;
  border-color: rgba(255,255,255,.14) !important;
}

div[data-testid="stExpander"] summary{
  position: relative !important;
  padding-left: 2.1rem !important; /* spazio per + / - */
}
div[data-testid="stExpander"] summary::before{
  content: "+" !important;
  position: absolute !important;
  left: .55rem !important;
  top: 50% !important;
  transform: translateY(-50%) !important;
  color: #ffb300 !important;
  font-weight: 950 !important;
  font-size: 1.35rem !important;
  line-height: 1 !important;
}
div[data-testid="stExpander"][open] summary::before{
  content: "−" !important;
}

/* Download QR: bottone più largo/alto e solo icone */
section[data-testid="stSidebar"] div[data-testid="stDownloadButton"] button{
  width: 2.75rem !important;
  height: 2.75rem !important;
  padding: 0 !important;
  border-radius: 14px !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
}
section[data-testid="stSidebar"] div[data-testid="stDownloadButton"] button span{
  font-size: 1.15rem !important;
  line-height: 1 !important;
}

/* Sidebar: bottoni azione solo icone (stessa dimensione) */
section[data-testid="stSidebar"] div[data-testid="stExpander"] button[kind="secondary"]{
  width: 2.35rem !important;
  height: 2.35rem !important;
  padding: 0 !important;
  border-radius: 12px !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
}
section[data-testid="stSidebar"] div[data-testid="stExpander"] button[kind="secondary"] span{
  font-size: 1.05rem !important;
  line-height: 1 !important;
}


/* ====== MOBILE: Modulo da campo leggibile anche in dark mode ====== */
@media (max-width: 768px){

  :root { color-scheme: light; }

  /* sfondo generale chiaro */
  .stApp{
    background: #f5f7fa !important;
    color: #0b1220 !important;
  }

  /* card e contenitori */
  .pc-card{
    background: #ffffff !important;
    border: 1px solid rgba(15,23,42,.14) !important;
  }

  /* input / textarea: sempre chiari */
  input, textarea{
    background-color: #ffffff !important;
    color: #0b1220 !important;
    border: 1px solid rgba(15,23,42,.20) !important;
    border-radius: 12px !important;
    padding: 0.70rem 0.85rem !important;
    font-size: 1.02rem !important;
    font-weight: 800 !important;
  }
  textarea{ min-height: 120px !important; }

  input::placeholder, textarea::placeholder{
    color: rgba(71,85,105,.85) !important;
  }

  /* label più leggibili */
  label, .stMarkdown, .stCaption, p, span{
    -webkit-text-size-adjust: 100%;
  }

  /* Bottoni: touch-friendly */
  .stButton>button, button{
    border-radius: 14px !important;
    padding: 0.75rem 1.0rem !important;
    font-size: 1.05rem !important;
    font-weight: 900 !important;
    min-height: 46px !important;
  }

  /* Submit button nei form (es. Rapporto completo): grande, full-width, sempre leggibile */
  div[data-testid="stFormSubmitButton"] > button,
  div[data-testid="stFormSubmitButton"] button{
    width: 100% !important;
    min-height: 56px !important;
    font-size: 1.12rem !important;
    letter-spacing: .2px !important;
  }

  /* Barra "sticky" solo nel modulo da campo: il bottone invio resta sempre a portata */
  .pc-card div[data-testid="stFormSubmitButton"]{
    position: sticky !important;
    bottom: 10px !important;
    z-index: 50 !important;
    padding: 0.35rem 0 !important;
    background: linear-gradient(180deg, rgba(245,247,250,0) 0%, rgba(245,247,250,0.92) 35%, rgba(245,247,250,1) 100%) !important;
  }

  /* Pulsanti dell'uploader foto / file: miglior contrasto */
  div[data-testid="stFileUploader"] section{
    background: #ffffff !important;
    border: 1px solid rgba(15,23,42,.14) !important;
    border-radius: 14px !important;
  }

  /* Primari ben visibili */
  button[kind="primary"], .stButton>button[kind="primary"]{
    background: linear-gradient(135deg, #1976d2 0%, #0d47a1 100%) !important;
    color: #ffffff !important;
    border: 1px solid rgba(255,255,255,.20) !important;
    box-shadow: 0 10px 22px rgba(13,71,161,.22) !important;
  }

  /* Nel modulo da campo: bottone invio ancora più evidente (verde) */
  .pc-card button[kind="primary"], .pc-card .stButton>button[kind="primary"]{
    background: linear-gradient(135deg, #2e7d32 0%, #1b5e20 100%) !important;
    box-shadow: 0 12px 26px rgba(27,94,32,.22) !important;
  }

  /* Secondari chiari */
  button[kind="secondary"], .stButton>button[kind="secondary"]{
    background: #e3f2fd !important;
    color: #0d47a1 !important;
    border: 1px solid rgba(13,71,161,.18) !important;
  }

  /* Download button in campo: più largo e leggibile */
  div[data-testid="stDownloadButton"] > button{
    width: 100% !important;
  }

}

</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* === CENTRO DI CONTROLLO (TOP) === */
.ctrl-card{
  width:100%;
  background:#ffe9a8;
  border:1px solid rgba(0,0,0,.12);
  border-radius:12px;
  padding:10px 10px 10px 10px;
  margin-bottom:6px;
  box-sizing:border-box;
}
.ctrl-title{
  text-align:center;
  font-size:0.78rem;
  font-weight:950;
  letter-spacing:.7px;
  text-transform:uppercase;
  color:#0f172a;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* === SIDEBAR KPI CARD === */
.sidebar-kpi-card{
  width:100%;
  background:#0e2a47;
  border-radius:12px;
  padding:8px 10px 8px 10px;
  box-sizing:border-box;
  margin-top:4px;
  margin-bottom:2px;
}
.sidebar-kpi-grid{
  display:grid;
  grid-template-columns: 1fr 1fr;
  gap:8px;
}
.sidebar-kpi-item{
  background: rgba(255,255,255,0.10);
  border-radius:10px;
  padding:8px 8px;
  text-align:center;
}
.sidebar-kpi-num{
  font-size:1.25rem;
  font-weight:800;
  line-height:1.1;
  color:#fff;
}
.sidebar-kpi-lab{
  margin-top:2px;
  font-size:0.72rem;
  font-weight:700;
  opacity:0.9;
  color:#fff;
  line-height:1.1;
}
</style>
""", unsafe_allow_html=True)

# =========================
# SIDEBAR
# =========================
with st.sidebar:

    # 🧭 Centro di Controllo – Selezione ruolo (TOP)
    st.markdown("""<div class='ctrl-card'><div class='ctrl-title'>CENTRO DI CONTROLLO</div></div>""", unsafe_allow_html=True)
    
    # 🧭 Selettore ruolo (safe): lock da QR e richiesta PIN per Sala
    if "ruolo_ui" not in st.session_state:
        st.session_state["ruolo_ui"] = "SALA OPERATIVA"

    if LOCK_FIELD:
        st.session_state["ruolo_ui"] = "MODULO CAPOSQUADRA"
        st.session_state["ruolo_sel"] = "MODULO CAPOSQUADRA"
        opzioni_ruolo = ["MODULO CAPOSQUADRA"]
    else:
        can_sala = bool(st.session_state.get("AUTH_SALA_OK", False))
        if not can_sala:
            # senza PIN: si può usare solo Caposquadra (Sala non selezionabile)
            st.session_state["ruolo_ui"] = "MODULO CAPOSQUADRA"
            st.session_state["ruolo_sel"] = "MODULO CAPOSQUADRA"
            opzioni_ruolo = ["MODULO CAPOSQUADRA"]
        else:
            opzioni_ruolo = ["SALA OPERATIVA", "MODULO CAPOSQUADRA"]
            if "ruolo_sel" not in st.session_state:
                st.session_state["ruolo_sel"] = st.session_state.get("ruolo_ui", "SALA OPERATIVA")

    st.radio(
        "Ruolo operativo",
        opzioni_ruolo,
        horizontal=True,
        label_visibility="collapsed",
        key="ruolo_sel",
        on_change=_sync_ruolo_from_sel,
        disabled=LOCK_FIELD
    )
    _sync_ruolo_from_sel()

    if LOCK_FIELD:
        st.caption("🔒 Accesso da QR/Link Modulo Campo: Sala Operativa bloccata.")
    elif not st.session_state.get("AUTH_SALA_OK", False):
        st.caption("🔐 Sala Operativa protetta: inserisci PIN per sbloccare.")
        ensure_sala_auth()
# --- STATO CONNESSIONE (OFFLINE / LAN / ONLINE) ---
    st.markdown(
        """
        <style>
        /* Expander as dark card + white text */
        section[data-testid="stSidebar"] div[data-testid="stExpander"] details {
            background: rgba(17, 24, 39, 0.92);
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 14px;
            padding: 6px 10px 10px 10px;
        }
        section[data-testid="stSidebar"] div[data-testid="stExpander"] summary {
            color: #ffffff !important;
            font-weight: 800;
        }
        section[data-testid="stSidebar"] div[data-testid="stExpander"] * {
            color: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("🛜 STATO CONNESSIONE", expanded=False):
        force_offline = st.toggle(
            "Forza",
            value=bool(st.session_state.get("force_offline", False)),
            key="force_offline",
        )

        # Auto aggiornamento (per ricevere subito avvisi dal modulo campo)
        if "AUTO_REFRESH" not in st.session_state:
            st.session_state["AUTO_REFRESH"] = True
        if "AUTO_REFRESH_SEC" not in st.session_state:
            st.session_state["AUTO_REFRESH_SEC"] = 20

        st.toggle("Auto aggiorna", key="AUTO_REFRESH")
        # Intervallo auto-refresh (secondi)
        _opts = [10, 20, 30, 60]
        _cur = int(st.session_state.get("AUTO_REFRESH_SEC") or 20)
        if _cur not in _opts:
            # se arriva da versioni precedenti (2/3/5/15), riallinea ad un valore valido
            _cur = min(_opts, key=lambda x: abs(x - _cur))
            st.session_state["AUTO_REFRESH_SEC"] = _cur
        st.session_state["AUTO_REFRESH_SEC"] = st.select_slider(
            "Intervallo (s)",
            options=_opts,
            value=_cur,
        )
        if st.button("🔄", help="Aggiorna ora"):
            st.rerun()

        st.caption(f"🧭 Ultimo aggiornamento: {_fmt_last_update(st.session_state.get('_last_update_ts'))}")

        ip = _local_ip()
        internet = _has_internet()
        lan = ip not in ("127.0.0.1", "0.0.0.0", "", None)

        offline = bool(force_offline) or (not internet and not lan)
        lan_only = (not offline) and (not internet) and lan
        online = (not offline) and internet

        if offline:
            st.markdown("🔌 **OFFLINE TOTALE**")
            st.markdown("Solo Sala Operativa.")
            effective_url = ""
        elif lan_only:
            effective_url = f"http://{ip}:{APP_PORT}"
            st.markdown("📡 **LAN LOCALE**")
            st.markdown("Modulo campo attivo in rete locale.")
            st.code(effective_url)
        else:
            st.markdown("🌍 **ONLINE**")
            # Auto-compila (se possibile) l'URL pubblico quando ONLINE e il campo è vuoto
            if not (st.session_state.get("PUBLIC_URL") or "").strip():
                _auto = _guess_public_url()
                if _auto:
                    st.session_state["PUBLIC_URL"] = _auto
            # Fallback: se ancora vuoto (es. ctx.request non disponibile), usa IP locale invece di localhost
            if not (st.session_state.get("PUBLIC_URL") or "").strip():
                try:
                    _ip = _local_ip()
                    _port = int(st.session_state.get("NET_PORT") or 8501)
                    if _ip and _ip not in ("127.0.0.1", "0.0.0.0"):
                        st.session_state["PUBLIC_URL"] = f"http://{_ip}:{_port}"
                except Exception:
                    pass

            public_url = (
                st.text_input(
                    "URL pubblico (https://…)",
                    key="PUBLIC_URL",
                )
                .strip()
                .rstrip("/")
            )
            st.session_state.BASE_URL = public_url  # compatibilità

            if st.button('🧪 ', key='btn_net_test'):
                ip_now = _local_ip()
                internet_now = _has_internet()
                st.write(f"IP: {ip_now}")
                st.write(f"Internet: {'OK' if internet_now else 'NO'}")
                # test tiles (1 richiesta veloce)
                try:
                    sample = 'https://{s}.tile.opentopomap.org/0/0/0.png'.replace('{s}','a')
                    r = requests.get(sample, timeout=2)
                    st.write(f"Tiles topo: {'OK' if r.status_code==200 else r.status_code}")
                except Exception:
                    st.write('Tiles topo: NO')
# compatibilità con codice esistente
            effective_url = public_url
        st.session_state.EFFECTIVE_URL = effective_url
        st.session_state.NET_OFFLINE = offline
        st.session_state.NET_LAN_ONLY = lan_only
        st.session_state.NET_ONLINE = online

    # ⏱️ Orologio (UTC) sotto Stato Connessione
    render_clock_in_sidebar(show_stopwatch=True)
    # 📊 KPI Sidebar (subito sotto orologio)
    _squads = st.session_state.get("squadre", None)
    try:
        squadre_registrate = len(_squads) if _squads is not None else 0
    except Exception:
        squadre_registrate = 0

    _brog = st.session_state.get("brogliaccio", st.session_state.get("registro", [])) or []
    _inbox = st.session_state.get("inbox", st.session_state.get("avvisi_inbox", st.session_state.get("inbox_avvisi", []))) or []
    try:
        comunicazioni_effettuate = int(len(_brog)) + int(len(_inbox))
    except Exception:
        comunicazioni_effettuate = 0

    st.markdown(
        f"""
        <div class='sidebar-kpi-card'>
          <div class='sidebar-kpi-grid'>
            <div class='sidebar-kpi-item'>
              <div class='sidebar-kpi-num'>👥 {squadre_registrate}</div>
              <div class='sidebar-kpi-lab'>Squadre registrate</div>
            </div>
            <div class='sidebar-kpi-item'>
              <div class='sidebar-kpi-num'>📡 {comunicazioni_effettuate}</div>
              <div class='sidebar-kpi-lab'>Comunicazioni</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.divider()

    ruolo = st.session_state.get("ruolo_ui", "SALA OPERATIVA")

    # (Navigazione rimossa: ruolo gestito in alto)

    if ruolo == "SALA OPERATIVA":
        st.markdown("## ➕ SQUADRE ATTIVE")
        st.caption(f"Totale: **{len(st.session_state.squadre)}**")

        squadre_sorted = sorted(list(st.session_state.squadre.keys()))

        # pulizia selezioni se una squadra viene rinominata/eliminata
        if st.session_state.get("team_open") and st.session_state.team_open not in st.session_state.squadre:
            st.session_state.team_open = None
        if st.session_state.get("team_edit_open") and st.session_state.team_edit_open not in st.session_state.squadre:
            st.session_state.team_edit_open = None
        if st.session_state.get("team_qr_open") and st.session_state.team_qr_open not in st.session_state.squadre:
            st.session_state.team_qr_open = None

        for team in squadre_sorted:
            inf = get_squadra_info(team)
            hx = team_hex(team)
            capo_txt = inf["capo"] if inf["capo"] else "—"
            tel_txt = inf["tel"] if inf["tel"] else "—"

            exp_open = (st.session_state.get("team_open") == team)
            with st.expander(f"{team_icon(team)}  {team}", expanded=exp_open):
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:10px;'>"
                    f"<div class='pc-sqdot' style='background:{hx};margin-top:0;'></div>"
                    f"<div style='flex:1;'>"
                    f"<div class='pc-sqname' style='font-size:1.02rem'>{team_icon(team)} {team}</div>"
                    f"<div class='pc-sqsub'>👤 {capo_txt} · 📞 {tel_txt}</div>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

                
                # Riga comandi (chip a sinistra + icone a destra)
                r1, r2, r3, r4, r5 = st.columns([6, 1, 1, 1, 1])

                with r1:
                    st.markdown(chip_stato(inf["stato"]), unsafe_allow_html=True)

                # ✏️ Modifica (apre form sotto il nome)
                if r2.button("✏️", key=f"open_edit_{team}", help="Modifica squadra", type="secondary"):
                    st.session_state.team_open = team
                    st.session_state.team_edit_open = team
                    st.session_state.team_qr_open = None
                    st.session_state["_del_arm"] = None
                    st.rerun()

                # 📱 QR
                if r3.button("📱", key=f"open_qr_{team}", help="Mostra QR", type="secondary"):
                    st.session_state.team_open = team
                    st.session_state.team_qr_open = team
                    st.session_state.team_edit_open = None
                    st.session_state["_del_arm"] = None
                    st.rerun()

                # ♻️ Token
                if r4.button("♻️", key=f"regen_tok_{team}", help="Rigenera token", type="secondary"):
                    regenerate_team_token(team)
                    st.session_state.team_open = team
                    st.session_state.team_qr_open = team
                    st.session_state.team_edit_open = None
                    st.success("Token rigenerato ✅")
                    st.rerun()

                # 🗑️ Elimina (arm)
                if r5.button("🗑️", key=f"del_{team}", help="Elimina squadra", type="secondary"):
                    st.session_state.team_open = team
                    st.session_state["_del_arm"] = team
                    st.session_state.team_edit_open = None
                    st.session_state.team_qr_open = None
                    st.rerun()
                # --- Modifica sotto il nome (solo se aperta) ---
                if st.session_state.get("team_edit_open") == team:
                    st.divider()
                    st.markdown("### ✏️ Modifica squadra")

                    with st.form(f"form_edit_{team}"):
                        new_name = st.text_input("Nome squadra", value=team, help="Il nome viene salvato in MAIUSCOLO")
                        new_capo = st.text_input("Caposquadra", value=inf["capo"], placeholder="Es. Rossi Mario")
                        new_tel = st.text_input("Telefono", value=inf["tel"], placeholder="Es. 3331234567")
                        cA, cB = st.columns(2)
                        save = cA.form_submit_button("💾 Salva")
                        close = cB.form_submit_button("✅ Chiudi")

                    if save:
                        ok, msg = update_team(team, new_name, new_capo, new_tel)
                        (st.success if ok else st.warning)(msg)
                        if ok:
                            new_t = (new_name or "").strip().upper()
                            st.session_state.team_open = new_t
                            st.session_state.team_edit_open = None
                            st.session_state.team_qr_open = None
                            st.rerun()

                    if close:
                        st.session_state.team_edit_open = None
                        st.rerun()

                # --- QR sotto il nome (solo se aperto) ---
                if st.session_state.get("team_qr_open") == team:
                    st.divider()
                    st.markdown("### 📱 QR accesso caposquadra")

                    base_url = (st.session_state.get("EFFECTIVE_URL") or "").strip().rstrip("/")
                    if not base_url:
                        st.info("QR disattivato: OFFLINE totale oppure (ONLINE) URL pubblico non impostato.")
                    else:
                        token = st.session_state.squadre[team].get("token", "")
                        if not base_url.startswith("http"):
                            st.warning("Imposta un URL pubblico valido (https://...) quando sei ONLINE.")
                        else:
                            team_q = urllib.parse.quote(team)
                            link = f"{base_url}/?mode=campo&team={team_q}&token={token}"
                            png = qr_png_bytes(link)
                            st.image(png, width=230)
                            st.download_button(
                                "⬇️📱",
                                data=png,
                                file_name=f"QR_{team.replace(' ', '_')}.png",
                                mime="image/png",
                                key=f"dlqr_{team}",
                            )
                            st.markdown(f"<div class='qr-linkbox'><span class='qr-linklabel'>🔗 Link QR</span>{link}</div>", unsafe_allow_html=True)
                            exp = (st.session_state.squadre.get(team, {}).get('token_expires_at') or '').strip()
                            last = (st.session_state.squadre.get(team, {}).get('token_last_access') or '').strip()
                            meta_bits = []
                            if exp:
                                meta_bits.append(f"Scade: {exp}")
                            if last:
                                meta_bits.append(f"Ultimo accesso: {last}")
                            if meta_bits:
                                st.caption(" · ".join(meta_bits))
                    if st.session_state.get("_del_arm") == team:
                        st.divider()
                        st.warning("Conferma eliminazione: questa azione è irreversibile.")
                        conf = st.checkbox("Confermo eliminazione squadra", key=f"confdel_{team}")
                        cD, cE = st.columns(2)
                        if cD.button("✅ Conferma elimina", disabled=not conf, key=f"confirm_del_{team}"):
                            ok, msg = delete_team(team)
                            (st.success if ok else st.warning)(msg)
                            st.session_state["_del_arm"] = None
                            st.session_state.team_open = None
                            st.rerun()
                        if cE.button("❌ Annulla", key=f"cancel_del_{team}"):
                            st.session_state["_del_arm"] = None
                            st.rerun()

        st.divider()
        st.markdown("## ➕ CREA SQUADRA")
        with st.form("form_add_team", clear_on_submit=True):
            n_sq = st.text_input("Nome squadra", placeholder="Es. SQUADRA 2 / ALFA / DELTA…")
            capo = st.text_input("Nome caposquadra", placeholder="Es. Rossi Mario")
            tel = st.text_input("Telefono caposquadra", placeholder="Es. 3331234567")
            submitted = st.form_submit_button("➕ AGGIUNGI SQUADRA")
        if submitted:
            nome = (n_sq or "").strip().upper()
            if not nome:
                st.warning("Inserisci il nome squadra.")
            elif nome in st.session_state.squadre:
                st.warning("Esiste già una squadra con questo nome.")
            else:
                token = uuid.uuid4().hex
                used = {(inf.get("mhex") or "").strip() for inf in st.session_state.squadre.values()}
                used = {hx for hx in used if hx.startswith("#") and len(hx) == 7}
                colore = _pick_next_team_color(set(used))

                st.session_state.squadre[nome] = {
                    "stato": "In attesa al COC",
                    "capo": (capo or "").strip(),
                    "tel": (tel or "").strip(),
                    "token": token,
                    "token_created_at": datetime.now().isoformat(timespec="seconds"),
                    "token_expires_at": (datetime.now() + timedelta(hours=TOKEN_TTL_HOURS)).isoformat(timespec="seconds"),
                    "token_last_access": "",
                    "mhex": colore,
                }
                save_data_to_disk()
                # apri subito la scheda e mostra QR
                st.session_state.team_open = nome
                st.session_state.team_qr_open = nome
                st.session_state.team_edit_open = None
                st.success("✅ Squadra creata! QR visibile sotto.")
                st.rerun()
# BACKUP in fondo
    st.divider()
    st.markdown("## 💾 Backup / Ripristino")

    payload_now = {
        "brogliaccio": st.session_state.brogliaccio,
        "inbox": st.session_state.inbox,
        "squadre": st.session_state.squadre,
        "pos_mappa": st.session_state.pos_mappa,
        "op_name": st.session_state.op_name,
        "ev_data": str(st.session_state.ev_data),
        "ev_tipo": st.session_state.ev_tipo,
        "ev_nome": st.session_state.ev_nome,
        "ev_desc": st.session_state.ev_desc,
        "BASE_URL": st.session_state.get("BASE_URL", ""),
        "cnt_conclusi": st.session_state.get("cnt_conclusi", 0),
    }

    # 📦⬇️ Scarica
    st.download_button(
        "📦⬇️",
        data=json.dumps(payload_now, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="backup_radio_manager.json",
        mime="application/json",
        help="Scarica un backup completo (JSON) di brogliaccio, inbox, squadre e impostazioni.",
        use_container_width=True,
    )

    # 📦⬆️ Ripristina (carica JSON: ripristino automatico)
    st.markdown("**📦⬆️ Carica backup**")
    up = st.file_uploader(
        "" ,
        type=["json"],
        key="restore_backup_json",
        label_visibility="collapsed",
        help="Carica un backup JSON esportato dal sistema: il ripristino parte automaticamente.",
    )

    if up is not None:
        try:
            load_data_from_uploaded_json(up.getvalue())
            st.success("✅ Ripristino completato.")
            st.rerun()
        except Exception:
            st.error("❌ Backup non valido o file corrotto.")

# =========================
# HEADER
# =========================
logo_data_uri = img_to_base64(LOGO_PATH)
logo_html = f"<img class='pc-logo' src='{logo_data_uri}' />" if logo_data_uri else ""
# Mostra il badge ruolo solo in console (non nel Modulo da Campo)
is_field_ui = bool(st.session_state.get("field_ok")) or bool(LOCK_FIELD)
badge_ruolo = ruolo
badge_html = f'<div class="pc-badge">📡 {badge_ruolo}</div>' if not is_field_ui else ""

st.markdown(
    f"""
<div class="pc-hero">
  <div class="pc-hero-left">
    {logo_html}
    <div>
      <div class="title">Protezione Civile Thiene</div>
      <div class="subtitle">Radio Manager Pro · Console Operativa Sala Radio</div>
    </div>
  </div>
  {badge_html}
</div>
""",
    unsafe_allow_html=True,
)

# =========================
# MODULO CAPOSQUADRA
# =========================
if badge_ruolo == "MODULO CAPOSQUADRA":
    st.markdown("<div class='pc-card pc-card-radio'>", unsafe_allow_html=True)
    st.subheader("📱 Modulo da campo")
    # FIELD_UI_V3
    # Header comandi (mobile friendly)
    if LOCK_FIELD:
        sun_mode = st.toggle("☀️ Modalità Sole", value=False, help="Contrasto alto per uso in esterno", key="sun_mode_mobile")
        st.caption("Suggerimento: usa IP in LAN (http://IP:8501) per GPS più affidabile rispetto a localhost.")
    else:
        c_ui1, c_ui2 = st.columns([2, 3])
        with c_ui1:
            sun_mode = st.toggle("☀️ Modalità Sole", value=False, help="Contrasto alto per uso in esterno")
        with c_ui2:
            st.caption("Suggerimento: usa IP in LAN (http://IP:8501) per GPS più affidabile rispetto a localhost.")


    _net_ok = bool(st.session_state.get("NET_ONLINE") or st.session_state.get("NET_LAN_ONLY"))
    _net_label = "🟢 Online" if st.session_state.get("NET_ONLINE") else ("🟡 LAN" if st.session_state.get("NET_LAN_ONLY") else "🔴 Offline")
    _gps_ok = isinstance(st.session_state.get("field_gps"), list) and len(st.session_state.get("field_gps")) == 2

    st.markdown(
        f"""
<style>
/* ==== MODULO CAMPO UI ==== */
.field-hud {{
  position: sticky; top: 0; z-index: 999;
  padding: .6rem .75rem; margin: .25rem 0 .75rem 0;
  border-radius: 14px;
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255,255,255,.12);
}}
.field-hud .row {{
  display:flex; gap:.5rem; flex-wrap:wrap; align-items:center; justify-content:space-between;
}}
.field-pill {{
  display:inline-flex; gap:.35rem; align-items:center;
  padding:.35rem .6rem; border-radius: 999px;
  font-weight:700; font-size:.9rem;
  border:1px solid rgba(255,255,255,.14);
}}
.field-muted {{opacity:.85; font-weight:600}}
/* chips template */
div[data-testid="stButton"] > button[kind="secondary"] {{
  border-radius: 999px !important;
  padding: .55rem .8rem !important;
  font-weight: 700 !important;
  border: 1px solid rgba(255,255,255,.18) !important;
}}
/* invio primary: più alto e leggibile */
div[data-testid="stButton"] > button[kind="primary"] {{
  padding: .75rem 1rem !important;
  font-weight: 800 !important;
  font-size: 1.05rem !important;
  border-radius: 16px !important;
}}
/* inputs più compatti */
div[data-testid="stTextInput"] input, textarea {{
  border-radius: 14px !important;
}}
/* riduci spazio tra elementi */
section.main .block-container {{padding-top: 1rem;}}
</style>
""",
        unsafe_allow_html=True,
    )

    # HUD (sempre visibile in alto mentre scorri)
    hud_bg = "rgba(245,245,255,.92)" if sun_mode else "rgba(15,15,22,.92)"
    hud_fg = "#0b0b0f" if sun_mode else "#ffffff"
    pill_bg = "rgba(0,0,0,.06)" if sun_mode else "rgba(255,255,255,.08)"

    st.markdown(
        f"""
<div class="field-hud" style="background:{hud_bg}; color:{hud_fg};">
  <div class="row">
    <div style="display:flex; gap:.45rem; flex-wrap:wrap;">
      <span class="field-pill" style="background:{pill_bg}; color:{hud_fg};">📡 Rete: <span class="field-muted">{_net_label}</span></span>
      <span class="field-pill" style="background:{pill_bg}; color:{hud_fg};">📍 GPS: <span class="field-muted">{'🟢 OK' if _gps_ok else '🔴 NO'}</span></span>
    </div>
    <div style="display:flex; gap:.45rem; flex-wrap:wrap; align-items:center;">
      <span class="field-pill" style="background:{pill_bg}; color:{hud_fg};">🧑‍🚒 {st.session_state.get("field_team") or "Seleziona squadra"}</span>
      <span class="field-pill" style="background:{pill_bg}; color:{hud_fg};">🌐 {st.session_state.get("NET_IP","") or "—"}:{st.session_state.get("NET_PORT","") or ""}</span>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


    # --- Stato invii (persistenza su disco) ---
    _outbox_init()
    if st.session_state.get("outbox_pending"):
        st.warning(f"🛰️ Invii in attesa di salvataggio su disco: **{len(st.session_state.outbox_pending)}**")
        c_retry, c_info = st.columns([2, 3])
        with c_retry:
            if st.button("🔁 Riprova salvataggio", use_container_width=True, key="outbox_retry_btn", type="primary"):
                if _outbox_retry_save():
                    st.success("✅ Salvato su disco.")
                    st.rerun()
                else:
                    st.error("❌ Ancora non riesco a salvare su disco.")
        with c_info:
            st.caption("Se rete/disco sono instabili, l'app conserva gli invii e ritenta quando premi Riprova.")

    # --- Ultimo invio (log rapido) ---
    if "field_last_sent" not in st.session_state:
        st.session_state.field_last_sent = None
    if st.session_state.field_last_sent:
        ls = st.session_state.field_last_sent
        with st.expander("🧾 Ultimo invio", expanded=False):
            st.markdown(f"**⏱️ Ora:** {ls.get('ora','—')}")
            st.markdown(f"**🧑‍🚒 Squadra:** {ls.get('sq','—')}")
            st.markdown(f"**✉️ Messaggio:** {ls.get('msg','')[:400]}")
            if ls.get("pos"):
                st.markdown(f"**📍 Posizione:** {ls.get('pos')}")
            st.markdown(f"**💾 Stato:** {ls.get('status','—')}")


    if st.session_state.get("field_ok"):
        sq_c = st.session_state.get("field_team")
        st.info(f"🔒 Accesso campo abilitato per: **{sq_c}**")
    else:
        sq_c = st.selectbox("TUA SQUADRA:", list(st.session_state.squadre.keys()))

    info_sq = get_squadra_info(sq_c)
    st.markdown(f"**👤 Caposquadra:** {info_sq['capo'] or '—'} &nbsp;&nbsp; | &nbsp;&nbsp; **📞 Tel:** {info_sq['tel'] or '—'}")

    share_gps = st.checkbox("📍 Includi posizione GPS (Privacy)", value=True)

    # Helper: posizione da inviare (GPS se disponibile, altrimenti manuale)
    def get_field_pos_to_send(_share: bool):
        if not _share:
            return None
        p = st.session_state.get("field_gps")
        if isinstance(p, list) and len(p) == 2:
            return p
        mp = st.session_state.get("field_manual_pos")
        if (
            isinstance(mp, list)
            and len(mp) == 2
            and mp[0] is not None
            and mp[1] is not None
        ):
            return mp
        return None



    # GPS dal telefono (richiede permesso posizione nel browser)
    if "field_gps" not in st.session_state:
        st.session_state.field_gps = None

    gps_c1, gps_c2 = st.columns([2, 5])
    with gps_c1:
        # Pulsante più "touch" su smartphone
        if st.button("📍 GPS", help="Aggiorna GPS dal telefono", use_container_width=True):
            st.session_state.field_gps = get_phone_gps_once()

    with gps_c2:
        if share_gps:
            _p = st.session_state.get("field_gps")
            if isinstance(_p, list) and len(_p) == 2:
                st.caption(f"GPS attuale: **{_p[0]:.6f}, {_p[1]:.6f}**")
            else:
                st.caption("GPS: **non disponibile**. Consenti la posizione sul telefono e premi 📍.")
        else:
            st.caption("GPS disattivato (Privacy).")


    if st.session_state.get("_gps_dep_missing"):
        st.info("ℹ️ GPS automatico: installa `streamlit-js-eval` (pip install streamlit-js-eval). Su smartphone, consenti la posizione nel browser. In HTTP, alcuni browser bloccano il GPS: in LAN usa l'IP (http://IP:8501) oppure HTTPS in Cloud.")

    # Fallback manuale (se il GPS non viene letto dal browser)
    if "field_manual_pos" not in st.session_state:
        st.session_state.field_manual_pos = [None, None]

    if share_gps:
        _p = st.session_state.get("field_gps")
        if not (isinstance(_p, list) and len(_p) == 2):
            st.caption("✍️ Se il GPS non viene letto, inserisci manualmente le coordinate (da Google Maps).")
            with st.expander("✍️ Coordinate manuali", expanded=False):
                mc1, mc2 = st.columns(2)
                # default: centro mappa corrente (solo come comodità)
                try:
                    _dlat = float(st.session_state.pos_mappa[0])
                    _dlon = float(st.session_state.pos_mappa[1])
                except Exception:
                    _dlat, _dlon = 45.0, 11.0
                lat_man = mc1.number_input("LAT (manuale)", value=_dlat, format="%.6f", key="field_lat_manual")
                lon_man = mc2.number_input("LON (manuale)", value=_dlon, format="%.6f", key="field_lon_manual")
                
                st.session_state.field_manual_pos = [float(lat_man), float(lon_man)]
    else:
        st.session_state.field_manual_pos = [None, None]

    st.subheader("📍 Invio rapido")

    # --- Applica template "pending" prima di instanziare il widget (evita errori Streamlit) ---
    if "pending_field_msg_rapido" in st.session_state:
        st.session_state["field_msg_rapido"] = st.session_state.pop("pending_field_msg_rapido")

    msg_rapido = st.text_input(
        "Nota breve:",
        placeholder="In movimento, arrivati...",
        key="field_msg_rapido",
    )

    st.markdown("**⚡ Template rapidi**")
    tpl_cols = st.columns(3)
    tpl_defs = [
        ("🌊 Allagamento", "🌊 Allagamento in corso. Richiesta valutazione e intervento."),
        ("🚧 Strada bloccata", "🚧 Strada bloccata/ostruita. Necessaria gestione viabilità."),
        ("🌳 Albero caduto", "🌳 Albero/rami caduti. Verifica e messa in sicurezza area."),
        ("⚡ Blackout", "⚡ Interruzione elettrica. Verifica criticità e supporto alla popolazione."),
        ("🔥 Fumo/Incendio", "🔥 Presenza di fumo/incendio. Allertare competenti e delimitare area."),
        ("🧍 Persona in difficoltà", "🧍 Persona in difficoltà. Richiesta supporto e valutazione sanitaria."),
    ]
    for i, (lbl, txt) in enumerate(tpl_defs):
        with tpl_cols[i % 3]:
            if st.button(lbl, use_container_width=True, key=f"tpl_rap_{i}", type="secondary"):
                st.session_state["field_last_template"] = txt
                st.session_state["pending_field_msg_rapido"] = txt
                st.rerun()

    if st.button("🚀 INVIA RAPIDO", use_container_width=True, type="primary"):
        pos_da_inviare = get_field_pos_to_send(share_gps)
        base = st.session_state.get("field_msg_rapido") or msg_rapido or ""
        msg_finale = _merge_template_text(base) or "Aggiornamento posizione"
        st.session_state.inbox.append(
            {
                "id": uuid.uuid4().hex,
                "ora": datetime.now().strftime("%H:%M"),
                "sq": sq_c,
                "msg": msg_finale,
                "foto": None,
                "pos": pos_da_inviare,
            }
        )
        try:
            try:
                save_data_to_disk()
                st.session_state.field_last_sent = {
                    "ora": datetime.now().strftime("%H:%M"),
                    "sq": sq_c,
                    "msg": _merge_template_text(st.session_state.get("field_msg_completo") or ""),
                    "pos": pos_da_inviare,
                    "status": "✅ Salvato su disco",
                }
                st.toast("✅ Inviato", icon="✅")
                st.success("✅ Inviato!")
            except Exception as e:
                st.error(f"Errore salvataggio: {e}")
                st.info("Messaggio inserito in memoria, ma non salvato su disco.")
                _outbox_add({"t": datetime.now().isoformat(timespec="seconds"), "sq": sq_c, "msg": _merge_template_text(st.session_state.get("field_msg_completo") or ""), "pos": pos_da_inviare})
                st.session_state.field_last_sent = {
                    "ora": datetime.now().strftime("%H:%M"),
                    "sq": sq_c,
                    "msg": _merge_template_text(st.session_state.get("field_msg_completo") or ""),
                    "pos": pos_da_inviare,
                    "status": "🛰️ In attesa di salvataggio",
                }
            finally:
                st.session_state["field_last_template"] = ""
                st.session_state["campo_template_text"] = ""
                st.session_state["field_msg_completo"] = ""
        except Exception as e:
            st.error(f"Errore salvataggio: {e}")
            st.info("Messaggio inserito in memoria, ma non salvato su disco.")
            _outbox_add({"t": datetime.now().isoformat(timespec="seconds"), "sq": sq_c, "msg": msg_finale, "pos": pos_da_inviare})
            st.session_state.field_last_sent = {
                "ora": datetime.now().strftime("%H:%M"),
                "sq": sq_c,
                "msg": msg_finale,
                "pos": pos_da_inviare,
                "status": "🛰️ In attesa di salvataggio",
            }
        finally:
            st.session_state["field_last_template"] = ""
            st.session_state["campo_template_text"] = ""
            st.session_state["pending_field_msg_rapido"] = ""  # clear input safely next rerun
    st.divider()
    st.markdown("**⚡ Template rapidi (per rapporto completo)**")
    tplc_cols = st.columns(3)
    for i, (lbl, txt) in enumerate(tpl_defs):
        with tplc_cols[i % 3]:
            if st.button(lbl, use_container_width=True, key=f"tpl_com_{i}", type="secondary"):
                st.session_state["field_last_template"] = txt
                st.session_state["pending_field_msg_completo"] = txt
                st.rerun()

    with st.form("form_c"):
        st.subheader("📸 Rapporto completo")
        # --- Applica template pending prima di instanziare la textarea ---
        if "pending_field_msg_completo" in st.session_state:
            st.session_state["field_msg_completo"] = st.session_state.pop("pending_field_msg_completo")

        msg_c = st.text_area("DESCRIZIONE:", key="field_msg_completo")


        foto = st.file_uploader("FOTO:", type=["jpg", "jpeg", "png"])
        if foto is not None:
            st.image(foto, caption="Anteprima foto", use_container_width=True)

        if st.form_submit_button("🚀 INVIA RAPPORTO COMPLETO", type="primary", use_container_width=True):
            pos_da_inviare = get_field_pos_to_send(share_gps)
            st.session_state.inbox.append(
                {
                    "id": uuid.uuid4().hex,
                    "ora": datetime.now().strftime("%H:%M"),
                    "sq": sq_c,
                    "msg": _merge_template_text(st.session_state.get("field_msg_completo") or ""),
                    "foto": (
                        {
                            "name": getattr(foto, "name", "foto"),
                            "type": getattr(foto, "type", "image/jpeg"),
                            "b64": _b64_encode_bytes(foto.read()),
                        }
                        if foto
                        else None
                    ),
                    "pos": pos_da_inviare,
                }
            )
            save_data_to_disk()
            st.session_state.field_last_sent = {
                "ora": datetime.now().strftime("%H:%M"),
                "sq": sq_c,
                "msg": msg_finale,
                "pos": pos_da_inviare,
                "status": "✅ Salvato su disco",
            }
            st.success("✅ Inviato!")

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# =========================
# SALA OPERATIVA
# =========================
st.markdown("<h1 style='text-align:center;color:#0d47a1;margin-top:-10px;'>📡 CONSOLE SALA RADIO</h1>", unsafe_allow_html=True)

st_lista = [info.get("stato", "In attesa al COC") for info in st.session_state.squadre.values()]
c1, c2, c3, c4, c5 = st.columns(5)

def metric_box(col, icon, label, value):
    fg = text_color_for_bg(col)
    return f"""
    <div class='pc-metric-color' style='background:{col};color:{fg};'>
      <div class='k'>{icon} {label}</div>
      <div class='v'>{value}</div>
    </div>
    """

c1.markdown(metric_box(COLORI_STATI["In uscita dal COC"]["hex"], "🚪", "Uscita", st_lista.count("In uscita dal COC")), unsafe_allow_html=True)
c2.markdown(metric_box(COLORI_STATI["Intervento in corso"]["hex"], "🔥", "In corso", st_lista.count("Intervento in corso")), unsafe_allow_html=True)
c3.markdown(metric_box(COLORI_STATI["Intervento concluso"]["hex"], "✅", "Conclusi", st.session_state.get("cnt_conclusi", 0)), unsafe_allow_html=True)
with c3:
    if st.button("↺ Reset conclusi", help="Azzera il contatore cumulativo degli interventi conclusi", key="reset_cnt_conclusi", use_container_width=True):
        st.session_state.cnt_conclusi = 0
        save_data_to_disk()
        st.rerun()
c4.markdown(metric_box(COLORI_STATI["Rientrata al Coc"]["hex"], "↩️", "Rientro", st_lista.count("Rientrata al Coc")), unsafe_allow_html=True)
c5.markdown(metric_box(COLORI_STATI["In attesa al COC"]["hex"], "🏠", "Al COC", st_lista.count("In attesa al COC")), unsafe_allow_html=True)


# =========================
# INBOX APPROVAZIONE
# (renderizzato sopra la MAPPA)
# =========================
def render_inbox_approval():
    if not st.session_state.get('inbox'):
        return
    for data in list(st.session_state.inbox):
        msg_id = data.get("id") or uuid.uuid4().hex
        data["id"] = msg_id
        sq_in = data["sq"]
        inf_in = get_squadra_info(sq_in)

        with st.expander(f"📥 APPROVAZIONE: {sq_in} ({data['ora']})", expanded=False):
            st.markdown(f"<div class='pc-flow'>📞 <b>{sq_in}</b> <span class='pc-arrow'>➜</span> 🎧 <b>SALA OPERATIVA</b></div>", unsafe_allow_html=True)
            st.markdown(f"**👤 Caposquadra:** {inf_in['capo'] or '—'} &nbsp;&nbsp; | &nbsp;&nbsp; **📞 Tel:** {inf_in['tel'] or '—'}")

            st.write(f"**MSG:** {data['msg']}")
            if data["pos"]:
                st.info(f"📍 GPS acquisito: {data['pos']}")
            if data["foto"]:
                st.image(_photo_to_bytes(data["foto"]), width=220)

            st_v = st.selectbox("Nuovo Stato:", list(COLORI_STATI.keys()), key=f"sv_inbox_{msg_id}")
            st.markdown(chip_stato(st_v), unsafe_allow_html=True)

            cb1, cb2 = st.columns(2)
            if cb1.button("✅ APPROVA", key=f"ap_{msg_id}"):
                pref = "[AUTO]" if data["pos"] else "[AUTO-PRIVACY]"
                st.session_state.brogliaccio.insert(
                    0,
                    {"ora": data["ora"], "chi": sq_in, "sq": sq_in, "st": st_v,
                     "mit": f"{pref} {data['msg']}", "ris": "VALIDATO", "op": st.session_state.op_name,
                     "pos": data["pos"], "foto": data["foto"]}
                )
                prev_st = st.session_state.squadre.get(sq_in, {}).get("stato")
                st.session_state.squadre[sq_in]["stato"] = st_v
                if st_v == "Intervento concluso" and prev_st != "Intervento concluso":
                    st.session_state.cnt_conclusi = int(st.session_state.get("cnt_conclusi", 0) or 0) + 1
                st.session_state.inbox = [m for m in st.session_state.inbox if (m.get("id") != msg_id)]
                save_data_to_disk()
                st.rerun()

            if cb2.button("🗑️ SCARTA", key=f"sc_{msg_id}"):
                st.session_state.inbox = [m for m in st.session_state.inbox if (m.get("id") != msg_id)]
                save_data_to_disk()
                st.rerun()

# =========================
# DATI EVENTO
# =========================
st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
st.subheader("📋 Dati Intervento ed Evento")
cd1, cd2, cd3, cd4 = st.columns([1, 1, 1, 2])

st.session_state.ev_data = cd1.date_input("DATA", value=st.session_state.ev_data)

tipi = ["Emergenza", "Esercitazione", "Monitoraggio", "Altro"]
idx_tipo = tipi.index(st.session_state.ev_tipo) if st.session_state.ev_tipo in tipi else 0
st.session_state.ev_tipo = cd2.selectbox("TIPO INTERVENTO", tipi, index=idx_tipo)

st.session_state.ev_nome = cd3.text_input("NOME EVENTO", value=st.session_state.ev_nome)
st.session_state.ev_desc = cd4.text_input("DESCRIZIONE DETTAGLIATA", value=st.session_state.ev_desc)

st.markdown("</div>", unsafe_allow_html=True)

# =========================
# TABS
# =========================
t_rad, t_rep = st.tabs(["🖥️ SALA RADIO", "📊 REPORT"])

with t_rad:
    l, r = st.columns([1, 1.2])

    with l:
        st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
        # ---- Inserimento comunicazione (UI reattiva: toggle coordinate immediato) ----
        st.session_state.op_name = st.text_input("OPERATORE RADIO", value=st.session_state.op_name, key="radio_operatore")
        chi = st.radio("CHI CHIAMA?", ["SALA OPERATIVA", "SQUADRA ESTERNA"], key="radio_chi_chiama")

        sq = st.selectbox("SQUADRA", list(st.session_state.squadre.keys()), key="radio_squadra_sel", on_change=_sync_radio_status_to_team)
        inf = get_squadra_info(sq)
        st.caption(f"👤 Caposquadra: {inf['capo'] or '—'} · 📞 {inf['tel'] or '—'}")

        _stati = list(COLORI_STATI.keys())
        _cur = st.session_state.get("radio_stato_sel")
        _idx = _stati.index(_cur) if _cur in _stati else (_stati.index(_get_last_team_status(sq)) if sq in st.session_state.squadre else 0)
        st_s = st.selectbox("STATO", _stati, index=_idx, key="radio_stato_sel")

        # --- reset campi form radio (DEVE avvenire prima dei widget) ---
        if st.session_state.pop("_clear_radio_form", False):
            st.session_state["radio_messaggio"] = ""
            st.session_state["radio_risposta"] = ""
            st.session_state["radio_lat"] = ""
            st.session_state["radio_lon"] = ""
            st.session_state["radio_save_coords"] = False
        mit = st.text_area("MESSAGGIO", key="radio_messaggio", on_change=_mark_typing)
        ris = st.text_area("RISPOSTA", key="radio_risposta", on_change=_mark_typing)
        st.markdown(chip_stato(st_s), unsafe_allow_html=True)

        save_coords = st.toggle(
            "📍 Salva coordinate (solo se comunicate)",
            value=bool(st.session_state.get("radio_save_coords", False)),
            key="radio_save_coords",
            help="Se OFF l'evento viene salvato senza coordinate (più leggero; report senza mappa)."
        )

        lat = lon = None
        if save_coords:
            c_g1, c_g2 = st.columns(2)
            # Normalizza valori in session_state (evita ValueError quando sono stringhe vuote)
            st.session_state["radio_lat"] = _safe_float(st.session_state.get("radio_lat"), st.session_state.pos_mappa[0])
            st.session_state["radio_lon"] = _safe_float(st.session_state.get("radio_lon"), st.session_state.pos_mappa[1])

            lat = c_g1.number_input("LAT", value=float(st.session_state["radio_lat"]), format="%.6f", key="radio_lat")
            lon = c_g2.number_input("LON", value=float(st.session_state["radio_lon"]), format="%.6f", key="radio_lon")

        b1, b2 = st.columns(2)

        # Metti in attesa: salva SOLO testo (senza cambiare stato)
        if b1.button("⏳ METTI IN ATTESA", use_container_width=True, key="btn_mettti_in_attesa"):
            # Salva in coda + nel brogliaccio, ma SENZA cambiare lo stato della squadra
            if "reply_queue" not in st.session_state:
                st.session_state.reply_queue = []

            _eid = uuid.uuid4().hex
            _pos = ([float(lat), float(lon)] if (save_coords and lat is not None and lon is not None) else None)

            st.session_state.reply_queue.insert(0, {
                "id": _eid,
                "ora": datetime.now().strftime("%H:%M"),
                "chi": chi,
                "sq": sq,
                # Chi chiama / chi deve rispondere (la squadra è quella selezionata al momento della messa in attesa)
                "caller_label": ("SALA OPERATIVA" if str(chi).strip().upper().startswith("SALA") else f"SQUADRA {sq}"),
                "answerer_label": (f"SQUADRA {sq}" if str(chi).strip().upper().startswith("SALA") else "SALA OPERATIVA"),
                # Manteniamo anche il campo storico per compatibilità (SALA/SQUADRA)
                "attesa_da": ("SQUADRA" if str(chi).strip().upper().startswith("SALA") else "SALA"),
                "mit": mit,
                "op": st.session_state.op_name,
                "pos": _pos,
                "reply": "",
            })

            # Brogliaccio: annota il messaggio (risposta verrà compilata quando chiudi la coda)
            try:
                st.session_state.brogliaccio.insert(
                    0,
                    {"id": _eid,
                     "ora": datetime.now().strftime("%H:%M"),
                     "chi": chi,
                     "sq": sq,
                     "caller_label": ("SALA OPERATIVA" if str(chi).strip().upper().startswith("SALA") else f"SQUADRA {sq}"),
                     "answerer_label": (f"SQUADRA {sq}" if str(chi).strip().upper().startswith("SALA") else "SALA OPERATIVA"),
                     "attesa_da": ("SQUADRA" if str(chi).strip().upper().startswith("SALA") else "SALA"),
                     "st": None,
                     "mit": mit,
                     "ris": "",
                     "op": st.session_state.op_name,
                     "pos": _pos,
                     "foto": None,
                     "pending": True}
                )
            except Exception:
                pass
            save_data_to_disk()
            st.session_state["_clear_radio_form"] = True
            st.rerun()

        if b2.button("✅ REGISTRA COMUNICAZIONE", use_container_width=True, key="btn_registra_comunicazione"):
            pos = [float(lat), float(lon)] if (save_coords and lat is not None and lon is not None) else None
            st.session_state.brogliaccio.insert(
                0,
                {"ora": datetime.now().strftime("%H:%M"), "chi": chi, "sq": sq, "st": st_s,
                 "mit": mit, "ris": ris, "op": st.session_state.op_name, "pos": pos, "foto": None}
            )
            prev_st = st.session_state.squadre.get(sq, {}).get("stato")
            st.session_state.squadre[sq]["stato"] = st_s
            if st_s == "Intervento concluso" and prev_st != "Intervento concluso":
                st.session_state.cnt_conclusi = int(st.session_state.get("cnt_conclusi", 0) or 0) + 1
            if pos:
                st.session_state.pos_mappa = pos
            save_data_to_disk()
            st.session_state["_clear_radio_form"] = True
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    with r:
        # Avvisi e approvazioni: subito sopra la mappa
        if st.session_state.get('inbox'):
            cA, cB = st.columns([1, 0.25])
            with cA:
                st.markdown(f"<div class='pc-alert'>⚠️ RICEVUTI {len(st.session_state.inbox)} AGGIORNAMENTI DA VALIDARE</div>", unsafe_allow_html=True)
            with cB:
                if st.button('🔄', key='refresh_console', help='Aggiorna dati dalla memoria condivisa'):
                    load_data_from_disk()
                    st.rerun()
            try:
                render_inbox_approval()
            except Exception as _e:
                st.error("Errore visualizzazione inbox (non blocca la mappa). Premi 🔄")

            st.divider()

        st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
        # =========================
        # MAPPA (ottimizzata)
        # =========================
        show_map = st.toggle("🗺️ Mostra mappa", value=True, key="show_main_map")
        fast_img = st.toggle("⚡ Mappa rapida (immagine)", value=False, key="fast_map_img")
        st.caption("Suggerimento: se la mappa interattiva impiega molto (tiles), usa 'Mappa rapida (immagine)'.")

        if show_map:
            # per la dedup basta una slice dei primi eventi (newest->oldest)
            events_slice = st.session_state.brogliaccio[:2000]
            inbox_now = st.session_state.get('inbox') or []
            squad_names = sorted(list(st.session_state.squadre.keys()))

            ultime_pos = _latest_positions_cached(events_slice, inbox_now, squad_names)
            # =========================
            # ⏳ Comunicazioni in attesa (coda risposte) – sopra la mappa
            # =========================
            queue = st.session_state.get("reply_queue", []) or []
            if queue:
                st.markdown(
                    f"""<div style="background:#fff3bf;border:1px solid #ffd43b;border-radius:14px;padding:10px 12px;margin:6px 0 10px 0;">
                    <div style="font-weight:900;color:#000;font-size:1.05rem;">⏳ Comunicazioni in attesa <span style="opacity:.75;">({len(queue)})</span></div>
                    <div style="color:#000;opacity:.75;font-size:.85rem;line-height:1.2;margin-top:2px;">Da gestire prima/dopo consulto. Qui puoi annotare e chiudere.</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

                for _i, it in enumerate(queue):
                    _id = it.get("id", f"q{_i}")
                    caller_lbl = it.get("caller_label") or it.get("chi","")
                    answer_lbl = it.get("answerer_label") or (("SQUADRA " + str(it.get("sq","")).strip()) if str(it.get("chi","")).strip().upper().startswith("SALA") else "SALA OPERATIVA")
                    titolo = f"{it.get('ora','')} · {caller_lbl} → {answer_lbl}"

                    with st.expander(f"➕ 🟡 {titolo}", expanded=False):
                        st.markdown(f"**Messaggio:** {it.get('mit','')}")
                        st.caption(f"⏳ In attesa di risposta da: {answer_lbl}")
                        if it.get("pos"):
                            try:
                                st.caption(f"📍 Coordinate salvate: {it['pos'][0]:.6f}, {it['pos'][1]:.6f}")
                            except Exception:
                                st.caption("📍 Coordinate salvate")

                        k_reply = f"reply_text_{_id}"
                        if k_reply not in st.session_state:
                            st.session_state[k_reply] = it.get("reply", "")

                        _att = (it.get("attesa_da") or ("SQUADRA" if str(it.get("chi","")).strip().upper().startswith("SALA") else "SALA")).strip().upper()
                        _label = f"Risposta ({answer_lbl})"
                        _ph = ("Annota qui la risposta ricevuta dalla squadra…" if _att == "SQUADRA" else "Scrivi qui la risposta della SALA da dare al caposquadra…")

                        st.text_area(_label, key=k_reply, height=80, placeholder=_ph)

                        c1, c2 = st.columns([1, 1])
                        if c1.button("✅ Segna come risposto", key=f"btn_reply_done_{_id}", use_container_width=True):
                            # sposta su brogliaccio come nota risposta (senza cambiare stato squadra)
                            try:
                                it["reply"] = st.session_state.get(k_reply, "")
                            except Exception:
                                pass
                            # aggiorna brogliaccio: salva la risposta SULLA STESSA comunicazione (senza cambiare stato squadra)
                            try:
                                _reply_txt = (it.get("reply","") or "").strip()
                                for _ev in st.session_state.brogliaccio:
                                    if _ev.get("id") == _id:
                                        _ev["ris"] = _reply_txt
                                        _ev["pending"] = False
                                        _ev["ris_ora"] = datetime.now().strftime("%H:%M")
                                        _ev["ris_da"] = (it.get("answerer_label") or (it.get("attesa_da") or "SALA")).upper()
                                        break
                            except Exception:
                                pass

# rimuovi dalla coda
                            st.session_state.reply_queue = [x for x in st.session_state.reply_queue if x.get("id") != _id]
                            save_data_to_disk()
                            st.rerun()

                        if c2.button("🗑️ Rimuovi dalla coda", key=f"btn_reply_rm_{_id}", use_container_width=True):
                            st.session_state.reply_queue = [x for x in st.session_state.reply_queue if x.get("id") != _id]
                            save_data_to_disk()
                            st.rerun()


            if fast_img:
                pts = []
                for sq, info in (ultime_pos or {}).items():
                    pos = info.get("pos")
                    if isinstance(pos, list) and len(pos) == 2:
                        try:
                            pts.append((float(pos[0]), float(pos[1]), f"{sq} · {info.get('st','')}"))
                        except Exception:
                            pass
                ck = _hash_obj({"p": pts, "z": 14})
                png = _static_map_png_cached(ck, pts, zoom=14)
                if png:
                    st.image(png, use_container_width=True)
                else:
                    st.info("Per la mappa rapida serve 'staticmap' in requirements.txt. In alternativa usa la mappa interattiva.")
            else:
                # interattiva (Folium)
                st.selectbox(
                    "Tipo mappa",
                    ["Topografica", "Stradale", "Satellite", "Leggera"],
                    index=["Topografica", "Stradale", "Satellite", "Leggera"].index(st.session_state.get("map_base_main", "Topografica")),
                    key="map_base_main",
                )
                m = build_folium_map_from_latest_positions(
                    ultime_pos,
                    center=st.session_state.pos_mappa,
                    zoom=14,
                )
                st_folium(m, width=1100, height=450, returned_objects=[], key="map_main")
        else:
            st.info("Mappa nascosta (velocizza i rerun).")
        # =========================
        # NATO – Convertitore (solo sala radio)
        # =========================
        st.markdown("<div class='nato-title'>📻 Alfabeto NATO – convertitore</div>", unsafe_allow_html=True)

        mode = st.radio(
            "Modalità:",
            ["Testo → NATO", "NATO → Frase"],
            horizontal=False,
            key="nato_mode",
        )

        NATO_REV = {v.upper().replace("-", "").replace(" ", ""): k for k, v in NATO.items()}

        def _clean_token(s: str) -> str:
            return (
                (s or "")
                .strip()
                .upper()
                .replace(".", "")
                .replace(",", "")
                .replace(";", "")
                .replace(":", "")
                .replace("|", " ")
                .replace("/", " ")
            )

        def render_nato_grid_from_text(txt: str) -> str:
            out = []
            for ch in (txt or ""):
                if ch == " ":
                    out.append("<span style='opacity:.35;margin:0 6px;'>•</span>")
                    continue
                c = ch.upper()
                if c in NATO:
                    out.append(
                        f"<div class='nato-chip nato-spell'>"
                        f"<div class='nato-letter'>{c}</div>"
                        f"<div class='nato-word'>{NATO[c]}</div>"
                        f"</div>"
                    )
                elif c.isdigit():
                    out.append(
                        f"<div class='nato-chip nato-spell'>"
                        f"<div class='nato-letter'>{c}</div>"
                        f"<div class='nato-word'>Numero</div>"
                        f"</div>"
                    )
            return "<div class='nato-mini'>" + "".join(out) + "</div>"

        def nato_phrase_to_text(nato_phrase: str) -> str:
            s = _clean_token(nato_phrase)
            tokens = [t for t in s.split() if t]
            out_chars = []
            for t in tokens:
                key = t.replace("-", "").replace(" ", "")
                if key.isdigit():
                    out_chars.append(key)
                    continue
                letter = NATO_REV.get(key)
                if letter:
                    out_chars.append(letter)
                else:
                    out_chars.append(key[:1])
            return "".join(out_chars)

        if mode == "Testo → NATO":
            testo_nato = st.text_input(
                "Scrivi testo / nominativo / codice",
                placeholder="Es. DAVIDE 21 / SQUADRA ALFA",
                key="nato_input_text",
            )

            if testo_nato.strip():
                st.markdown(render_nato_grid_from_text(testo_nato), unsafe_allow_html=True)
            else:
                st.markdown("""<div class="nato-mini">
          <div class="nato-chip"><div class="nato-letter">A</div><div class="nato-word">Alfa</div></div>
          <div class="nato-chip"><div class="nato-letter">B</div><div class="nato-word">Bravo</div></div>
          <div class="nato-chip"><div class="nato-letter">C</div><div class="nato-word">Charlie</div></div>
          <div class="nato-chip"><div class="nato-letter">D</div><div class="nato-word">Delta</div></div>
          <div class="nato-chip"><div class="nato-letter">E</div><div class="nato-word">Echo</div></div>
          <div class="nato-chip"><div class="nato-letter">F</div><div class="nato-word">Foxtrot</div></div>
          <div class="nato-chip"><div class="nato-letter">G</div><div class="nato-word">Golf</div></div>
          <div class="nato-chip"><div class="nato-letter">H</div><div class="nato-word">Hotel</div></div>
          <div class="nato-chip"><div class="nato-letter">I</div><div class="nato-word">India</div></div>
          <div class="nato-chip"><div class="nato-letter">J</div><div class="nato-word">Juliett</div></div>
          <div class="nato-chip"><div class="nato-letter">K</div><div class="nato-word">Kilo</div></div>
          <div class="nato-chip"><div class="nato-letter">L</div><div class="nato-word">Lima</div></div>
          <div class="nato-chip"><div class="nato-letter">M</div><div class="nato-word">Mike</div></div>
          <div class="nato-chip"><div class="nato-letter">N</div><div class="nato-word">November</div></div>
          <div class="nato-chip"><div class="nato-letter">O</div><div class="nato-word">Oscar</div></div>
          <div class="nato-chip"><div class="nato-letter">P</div><div class="nato-word">Papa</div></div>
          <div class="nato-chip"><div class="nato-letter">Q</div><div class="nato-word">Quebec</div></div>
          <div class="nato-chip"><div class="nato-letter">R</div><div class="nato-word">Romeo</div></div>
          <div class="nato-chip"><div class="nato-letter">S</div><div class="nato-word">Sierra</div></div>
          <div class="nato-chip"><div class="nato-letter">T</div><div class="nato-word">Tango</div></div>
          <div class="nato-chip"><div class="nato-letter">U</div><div class="nato-word">Uniform</div></div>
          <div class="nato-chip"><div class="nato-letter">V</div><div class="nato-word">Victor</div></div>
          <div class="nato-chip"><div class="nato-letter">W</div><div class="nato-word">Whiskey</div></div>
          <div class="nato-chip"><div class="nato-letter">X</div><div class="nato-word">X-ray</div></div>
          <div class="nato-chip"><div class="nato-letter">Y</div><div class="nato-word">Yankee</div></div>
          <div class="nato-chip"><div class="nato-letter">Z</div><div class="nato-word">Zulu</div></div>
        </div>""", unsafe_allow_html=True)

        else:
            nato_in = st.text_input(
                "Scrivi le parole NATO",
                placeholder="Es. Delta Alfa Victor India Delta Echo",
                key="nato_input_nato",
            )
            if nato_in.strip():
                out = nato_phrase_to_text(nato_in)
                st.success(f"✅ Frase: **{out}**")
                st.caption("Puoi separare con spazi, | oppure / (es. Delta|Alfa|Victor).")
            else:
                st.caption("Scrivi una sequenza NATO per convertirla in testo.")
        st.markdown("</div>", unsafe_allow_html=True)

with t_rep:
    st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
    st.subheader("📊 Report per Squadra")

    df = pd.DataFrame(st.session_state.brogliaccio)
    filtro = st.selectbox("Seleziona squadra:", ["TUTTE"] + list(st.session_state.squadre.keys()), index=0)

    st.markdown("#### 📞 Rubrica Squadre (Caposquadra / Telefono)")
    rubrica = []
    for sq_name, inf in st.session_state.squadre.items():
        rubrica.append({
            "SQUADRA": sq_name,
            "CAPOSQUADRA": (inf.get("capo") or "").strip() or "—",
            "TELEFONO": (inf.get("tel") or "").strip() or "—",
            "STATO": inf.get("stato", "In attesa al COC")
        })
    st.dataframe(pd.DataFrame(rubrica), use_container_width=True, height=220)

    st.divider()
    if df.empty:
        st.info("Nessun dato nel brogliaccio.")
        df_f = pd.DataFrame()
        df_view = pd.DataFrame()
    else:
        df_f = df[df["sq"] == filtro].copy() if filtro != "TUTTE" else df.copy()
        df_view = df_for_report(df_f)
        st.dataframe(df_view, use_container_width=True, height=360)

        st.divider()
        csv = df_f.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Scarica CSV filtrato", data=csv, file_name="brogliaccio.csv", mime="text/csv")

    # ✅ HTML REPORT con selettori:
    # - squadra
    # - stampa con/senza mappa
    # - mappa: ultime posizioni / tutti eventi / percorso
    st.divider()
    st.subheader("🖨️ Report HTML (stampa con/senza mappa + selettore mappa eventi squadra)")

    
    # Tipo mappa per report (valido anche per mappa dentro HTML)
    if "map_style" not in st.session_state:
        st.session_state.map_style = "Topografica"
    st.session_state.map_style = st.selectbox(
        "🗺️ Tipo mappa (report)",
        ["Topografica", "Stradale", "Satellite"],
        index=["Topografica", "Stradale", "Satellite"].index(st.session_state.map_style) if st.session_state.map_style in ["Topografica","Stradale","Satellite"] else 0,
        key="map_style_select_report",
    )
    rep_with_map = st.checkbox("Stampa con mappa", value=True, key="rep_with_map")

    meta = {
        "ev_data": str(st.session_state.ev_data),
        "ev_tipo": st.session_state.ev_tipo,
        "ev_nome": st.session_state.ev_nome,
        "ev_desc": st.session_state.ev_desc,
        "op_name": st.session_state.op_name,
        "map_style": st.session_state.map_style,
        "include_map": bool(rep_with_map),
    }


    # --- Filtro squadra (report) ---
    _sq_opts = sorted(list((st.session_state.squadre or {}).keys()))
    if "_rep_sq_filter" not in st.session_state:
        st.session_state._rep_sq_filter = ["Tutte"]
    _rep_sq = st.multiselect(
        "🧑‍🚒 Filtro squadra (report)",
        options=["Tutte"] + _sq_opts,
        default=st.session_state._rep_sq_filter,
        key="_rep_sq_filter",
        help="Seleziona una o più squadre. 'Tutte' include ogni evento.",
    )
    _use_all = ("Tutte" in _rep_sq) or (len(_rep_sq) == 0)
    _rep_sq_set = set(_sq_opts) if _use_all else set([x for x in _rep_sq if x != "Tutte"])


    # Cache report per velocizzare (foto escluse)
    _rep_brog = []
    for _e in (st.session_state.brogliaccio or []):
        # applica filtro squadra
        if isinstance(_e, dict):
            _sqv = _e.get('sq')
            if _sqv and _sqv not in _rep_sq_set:
                continue
        else:
            # se non è dict, non filtriamo
            pass
        if isinstance(_e, dict):
            _d = dict(_e)
            _d.pop('foto', None)
            _rep_brog.append(_d)
        else:
            _rep_brog.append(_e)
    _payload = {'squadre': st.session_state.squadre, 'brogliaccio': _rep_brog, 'center': st.session_state.pos_mappa}
    html_bytes = _cached_report_bytes(
        json.dumps(_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
        json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
    )

    st.download_button(
        "⬇️ Scarica REPORT HTML (mappa stampabile + selettore)",
        data=html_bytes,
        file_name="report_radio_manager.html",
        mime="text/html",
    )

    st.divider()
    st.markdown("#### ✏️ Modifica evento (correzione rapida)")
    _maxi = max(len(st.session_state.brogliaccio) - 1, 0)
    _idx_edit = st.number_input("Indice evento (#) da modificare", min_value=0, max_value=_maxi, value=0, step=1, key="rep_edit_idx")
    if st.button("✏️ Apri modifica evento", key="rep_open_edit"):
        st.session_state.edit_event_idx = int(_idx_edit)
        st.rerun()


    st.caption("Apri l'HTML → scegli squadra → scegli modalità mappa (Ultime/Tutti/Percorso) → STAMPA con/senza mappa.")
    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# REGISTRO EVENTI + MAPPA (FAST)
# =========================
# =========================
# MODIFICA EVENTO (correzione rapida)
# =========================
if "edit_event_idx" not in st.session_state:
    st.session_state.edit_event_idx = None

if st.session_state.edit_event_idx is not None:
    _i = int(st.session_state.edit_event_idx)
    if 0 <= _i < len(st.session_state.brogliaccio):
        _ev = st.session_state.brogliaccio[_i]
        _STATI = globals().get("STATI_EVENTO", ["uscita", "intervento", "concluso", "info"])
        with st.expander(f"✏️ Modifica evento #{_i}", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 2])
            _sq = c1.selectbox("SQUADRA", options=sorted(list(st.session_state.squadre.keys())), index=(sorted(list(st.session_state.squadre.keys())).index(_ev.get("sq")) if _ev.get("sq") in st.session_state.squadre else 0), key=f"edit_sq_{_i}")
            _st = c2.selectbox("STATO", options=_STATI, index=(_STATI.index(_ev.get("st")) if _ev.get("st") in _STATI else 0), key=f"edit_st_{_i}")
            _ts = c3.text_input("DATA/ORA", value=str(_ev.get("ts","")), key=f"edit_ts_{_i}", help="Lascia invariato se va bene (es. 2026-01-24 13:10)")
            _chi = st.text_input("CHIAMA", value=str(_ev.get("chi","")), key=f"edit_chi_{_i}")
            _mit = st.text_input("MITTENTE", value=str(_ev.get("mit","")), key=f"edit_mit_{_i}")
            _ris = st.text_input("RICEVE", value=str(_ev.get("ris","")), key=f"edit_ris_{_i}")
            _op  = st.text_area("OPERAZIONE / NOTE", value=str(_ev.get("op","")), key=f"edit_op_{_i}", height=90)

            _pos = _ev.get("pos") or {}
            if isinstance(_pos, (list, tuple)) and len(_pos) >= 2:
                _lat0, _lon0 = float(_pos[0]), float(_pos[1])
            else:
                _lat0, _lon0 = float(_pos.get("lat", 0) or 0), float(_pos.get("lon", 0) or 0)

            cc1, cc2 = st.columns(2)
            _lat = cc1.number_input("LAT", value=_lat0, format="%.6f", key=f"edit_lat_{_i}")
            _lon = cc2.number_input("LON", value=_lon0, format="%.6f", key=f"edit_lon_{_i}")

            b1, b2 = st.columns(2)
            if b1.button("💾 Salva modifiche", use_container_width=True, key=f"edit_save_{_i}"):
                st.session_state.brogliaccio[_i] = {
                    "ts": _ts or datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "sq": _sq,
                    "st": _st,
                    "chi": _chi,
                    "mit": _mit,
                    "ris": _ris,
                    "op": _op,
                    "pos": {"lat": float(_lat), "lon": float(_lon)},
                }
                save_data_to_disk()
                st.session_state.edit_event_idx = None
                st.success("Evento aggiornato.")
                st.rerun()

            if b2.button("✖️ Annulla", use_container_width=True, key=f"edit_cancel_{_i}"):
                st.session_state.edit_event_idx = None
                st.rerun()
    else:
        st.session_state.edit_event_idx = None

st.markdown("### 📋 REGISTRO EVENTI")

# Registro: modalità tabella (molto più veloce) + dettaglio singolo
view_mode = st.selectbox("Vista registro:", ["Classica", "Veloce"], index=0, key="log_view_mode")
mode_fast = (view_mode == "Veloce")

# Limite eventi caricati (evita rallentamenti con migliaia di righe)
_lim_opts = [100, 250, 500, 1000, "Tutti"]
_lim = st.selectbox("Carica eventi:", _lim_opts, index=1, key="log_limit")
all_events = st.session_state.brogliaccio
events_loaded = all_events if _lim == "Tutti" else all_events[:int(_lim)]

# --- Filtro squadra (registro) ---
_sq_opts_reg = sorted(list((st.session_state.squadre or {}).keys()))
_reg_sq = st.selectbox(
    "🧑‍🚒 Filtro squadra (registro)",
    options=["Tutte"] + _sq_opts_reg,
    index=0,
    key="log_sq_filter",
    help="Mostra solo gli interventi della squadra selezionata oppure tutti.",
)
if _reg_sq != "Tutte":
    events_loaded = [e for e in events_loaded if isinstance(e, dict) and e.get("sq") == _reg_sq]
    st.caption(f"Filtro attivo: **{_reg_sq}** — eventi mostrati: **{len(events_loaded)}**.")


if _lim != "Tutti" and len(all_events) > int(_lim):
    st.caption(f"Caricati i primi **{int(_lim)}** eventi su **{len(all_events)}** totali (per velocità).")

# Mappa evento selezionato (una alla volta)
if st.session_state.open_map_event is not None:
    idx = st.session_state.open_map_event
    if 0 <= idx < len(all_events):
        row = all_events[idx]
        pos = row.get("pos")

        st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
        st.subheader("🗺️ Mappa evento selezionato")

        if isinstance(pos, list) and len(pos) == 2:
            fast_ev = st.toggle("⚡ Mappa rapida evento (immagine)", value=False, key="fast_event_map_img")
            if fast_ev:
                try:
                    pts = [(float(pos[0]), float(pos[1]), f"{row.get('sq','')} · {row.get('st','')}")]
                except Exception:
                    pts = []
                ck = _hash_obj({"ev": idx, "p": pts})
                png = _static_map_png_cached(ck, pts, zoom=15)
                if png:
                    st.image(png, use_container_width=True)
                else:
                    st.info("Per la mappa rapida serve 'staticmap' in requirements.txt. Disattiva il toggle per la mappa interattiva.")
            else:
                m_ev = folium.Map(location=pos, zoom_start=15, tiles=None, prefer_canvas=True)
                _folium_apply_base_layer(m_ev)
                folium.Marker(
                    pos,
                    tooltip=f"{row.get('sq','')} · {row.get('st','')}",
                    icon=folium.Icon(color=COLORI_STATI.get(row.get('st',''), {}).get('color', 'blue')),
                ).add_to(m_ev)
                st_folium(m_ev, width="100%", height=420, returned_objects=[], key="map_event")
        else:
            st.info("Evento senza coordinate GPS (OMISSIS).")

        if st.button("❌ CHIUDI MAPPA", key="close_event_map"):
            st.session_state.open_map_event = None
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

# -------- Modalità veloce (tabella + dettaglio) --------
if mode_fast:
    # Paginazione leggera
    page_size = st.select_slider("Righe per pagina:", options=[25, 50, 100, 200], value=50, key="log_page_size")
    total = len(events_loaded)
    if total == 0:
        st.info("Nessun evento nel registro.")
    else:
        max_pages = max(1, (total + page_size - 1) // page_size)
        if "log_page" not in st.session_state:
            st.session_state.log_page = 1
        st.session_state.log_page = max(1, min(st.session_state.log_page, max_pages))

        colp1, colp2, colp3 = st.columns([1, 2, 1])
        with colp1:
            if st.button("⬅️", disabled=(st.session_state.log_page <= 1), key="log_prev"):
                st.session_state.log_page -= 1
                st.rerun()
        with colp2:
            st.markdown(f"<div style='text-align:center; padding-top:.35rem;'><b>Pagina {st.session_state.log_page} / {max_pages}</b></div>", unsafe_allow_html=True)
        with colp3:
            if st.button("➡️", disabled=(st.session_state.log_page >= max_pages), key="log_next"):
                st.session_state.log_page += 1
                st.rerun()

        start_i = (st.session_state.log_page - 1) * page_size
        end_i = min(total, start_i + page_size)
        page_events = events_loaded[start_i:end_i]

        # Tabella compatta (virtualizzata)
        rows = []
        for j, b in enumerate(page_events, start=start_i):
            gps_ok = isinstance(b.get("pos"), list) and len(b["pos"]) == 2
            a, c = call_flow_from_row(b)
            rows.append({
                "#": j,
                "ORA": b.get("ora", ""),
                "SQ": b.get("sq", ""),
                "STATO": b.get("st", ""),
                "DA": a,
                "A": c,
                "GPS": "✅" if gps_ok else "—",
                "MSG": (b.get("mit", "") or "")[:60],
            })

        df_log = pd.DataFrame(rows)
        st.dataframe(df_log, use_container_width=True, height=420)

        # Selezione evento (dettaglio singolo, non 200 expander)
        pick = st.number_input(
            "Apri dettaglio evento #",
            min_value=int(df_log["#"].min()),
            max_value=int(df_log["#"].max()),
            value=int(df_log["#"].min()),
            step=1,
            key="log_pick_idx",
        )

        if 0 <= int(pick) < len(all_events):
            b = all_events[int(pick)]
            gps_ok = isinstance(b.get("pos"), list) and len(b["pos"]) == 2
            gps_t = f"GPS: {b['pos'][0]:.4f}, {b['pos'][1]:.4f}" if gps_ok else "GPS: OMISSIS"
            a, c = call_flow_from_row(b)
            titolo = f"{b.get('ora','')} | 📞 {a} ➜ 🎧 {c} | {b.get('sq','')} | {gps_t}"

            with st.expander(f"🔎 Dettaglio evento  #{int(pick)}  —  {titolo}", expanded=False):
                st.markdown(chip_call_flow(b), unsafe_allow_html=True)
                st.markdown(chip_stato(b.get("st", "")), unsafe_allow_html=True)

                sq_event = (b.get("sq") or "").strip()
                if sq_event and sq_event in st.session_state.squadre:
                    inf = get_squadra_info(sq_event)
                    st.markdown(f"**👤 Caposquadra:** {inf['capo'] or '—'} &nbsp;&nbsp; | &nbsp;&nbsp; **📞 Tel:** {inf['tel'] or '—'}")

                st.write(
                    f"💬 **MSG:** {b.get('mit','')}  \n"
                    f"📩 **RIS:** {b.get('ris','')}  \n"
                    f"👤 **OP:** {b.get('op','')}"
                )

                col_a, col_b, col_c = st.columns([1, 1, 2])
                if col_a.button("✏️ MODIFICA", key=f"edit_ev_pick_{int(pick)}"):
                    st.session_state.edit_event_idx = int(pick)
                    st.rerun()
                if gps_ok:
                    if col_b.button("🗺️ MAPPA", key=f"open_map_pick_{int(pick)}"):
                        st.session_state.open_map_event = int(pick)
                        st.rerun()
                    col_c.caption("Apre una mappa dedicata in alto al registro (una alla volta).")
                else:
                    col_b.button("🗺️ N/D", key=f"no_map_pick_{int(pick)}", disabled=True)
                    col_c.caption("Coordinate non presenti (OMISSIS).")

# -------- Modalità classica (expander per evento) --------
else:
    _events = events_loaded
    for i, b in enumerate(_events):
        gps_ok = isinstance(b.get("pos"), list) and len(b["pos"]) == 2
        gps_t = f"GPS: {b['pos'][0]:.4f}, {b['pos'][1]:.4f}" if gps_ok else "GPS: OMISSIS"
        a, c = call_flow_from_row(b)
        titolo = f"{b.get('ora','')} | 📞 {a} ➜ 🎧 {c} | {b.get('sq','')} | {gps_t}"

        with st.expander(titolo):
            st.markdown(chip_call_flow(b), unsafe_allow_html=True)
            st.markdown(chip_stato(b.get("st", "")), unsafe_allow_html=True)

            sq_event = (b.get("sq") or "").strip()
            if sq_event and sq_event in st.session_state.squadre:
                inf = get_squadra_info(sq_event)
                st.markdown(f"**👤 Caposquadra:** {inf['capo'] or '—'} &nbsp;&nbsp; | &nbsp;&nbsp; **📞 Tel:** {inf['tel'] or '—'}")

            st.write(
                f"💬 **MSG:** {b.get('mit','')}  \n"
                f"📩 **RIS:** {b.get('ris','')}  \n"
                f"👤 **OP:** {b.get('op','')}"
            )

            col_a, col_b, col_c = st.columns([1, 1, 2])
            if col_a.button("✏️ MODIFICA", key=f"edit_ev_{i}"):
                st.session_state.edit_event_idx = int(i)
                st.rerun()
            if gps_ok:
                if col_b.button("🗺️ MAPPA", key=f"open_map_{i}"):
                    st.session_state.open_map_event = i
                    st.rerun()
                col_c.caption("Apre una mappa dedicata in alto al registro (una alla volta).")
            else:
                col_b.button("🗺️ N/D", key=f"no_map_{i}", disabled=True)
                col_c.caption("Coordinate non presenti (OMISSIS).")


# =========================
# RESET
# =========================
st.divider()
st.subheader("💾 Gestione Memoria Dati")
col_m1, col_m2 = st.columns(2)

if col_m1.button("🧹 CANCELLA TUTTI I DATI"):
    d = default_state_payload()
    st.session_state.brogliaccio = d["brogliaccio"]
    st.session_state.inbox = d["inbox"]
    ensure_inbox_ids()
    st.session_state.squadre = d["squadre"]
    st.session_state.pos_mappa = d["pos_mappa"]
    st.session_state.op_name = d["op_name"]
    st.session_state.ev_data = datetime.fromisoformat(d["ev_data"]).date()
    st.session_state.ev_tipo = d["ev_tipo"]
    st.session_state.ev_nome = d["ev_nome"]
    st.session_state.ev_desc = d["ev_desc"]
    st.session_state.BASE_URL = d["BASE_URL"]
    st.session_state.open_map_event = None
    st.session_state.team_edit_open = None
    st.session_state.team_qr_open = None
    save_data_to_disk()
    st.success("Tutti i dati sono stati cancellati.")
    st.rerun()

if col_m2.button("💾 SALVA ORA SU DISCO"):
    save_data_to_disk()
    st.success("Salvato.")
# =========================
# REPORT CACHE (GLOBAL)
# =========================
@st.cache_data(show_spinner=False)
def _cached_report_bytes(payload_json: str, meta_json: str) -> bytes:
    payload = json.loads(payload_json) if payload_json else {}
    meta = json.loads(meta_json) if meta_json else {}
    return make_html_report_bytes(
        squads=payload.get("squadre", {}),
        brogliaccio=payload.get("brogliaccio", []),
        center=payload.get("center", []),
        meta=meta,
    )



# =========================
# FOOTER
# =========================
st.markdown("""
<style>
.pc-footer{position:fixed;bottom:0;left:0;width:100%;z-index:999;
background:#0d1b2a;color:#ffffffcc;text-align:center;padding:6px 0;font-size:.75rem;}
.pc-footer b{color:#fff;}
</style>
<div class="pc-footer"><b>Protezione Civile Thiene</b> · Powered by <b>JokArt</b></div>
""", unsafe_allow_html=True)


# =========================
# FOOTER
# =========================
st.markdown("""
<style>
.footer {
  position: fixed;
  bottom: 0;
  left: 0;
  width: 100%;
  background: #0d1b2a;
  color: rgba(255,255,255,.85);
  text-align: center;
  padding: 7px 10px;
  font-size: 0.72rem;
  z-index: 999;
  border-top: 1px solid rgba(255,255,255,.12);
}
.footer .row {
  display:flex;
  gap:8px;
  flex-wrap:wrap;
  justify-content:center;
  align-items:center;
  line-height: 1.15;
}
.footer b { color: #fff; }
.footer .sep { opacity:.55; }
@media (max-width: 520px){
  .footer { font-size: 0.68rem; padding: 8px 8px; }
}
/* evita che il contenuto venga coperto dal footer */
section.main .block-container { padding-bottom: 3.2rem; }
</style>
<div class="footer">
  <div class="row">
    <b>Gruppo Comunale Volontari Protezione Civile Thiene</b>
    <span class="sep">•</span>
    <span>Via dell'Aeroporto 33, Thiene</span>
    <span class="sep">•</span>
    <span>pcthiene@gmail.com</span>
    <span class="sep">•</span>
    <span>Powered by <b>JokArt</b> · 2026</span>
  </div>
</div>
""", unsafe_allow_html=True)