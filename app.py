import streamlit as st
import pandas as pd
from datetime import datetime
import folium
from streamlit_folium import st_folium
import os
import base64
import json
from typing import Optional, Tuple, Dict, Any

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="RADIO MANAGER - PROTEZIONE CIVILE THIENE", layout="wide")

DATA_PATH = "data.json"
LOGO_PATH = "logo.png"

COLORI_STATI = {
    "In attesa al COC": {"color": "black", "hex": "#455a64"},
    "In uscita dal COC": {"color": "cadetblue", "hex": "#fff176"},
    "Arrivata sul luogo di intervento": {"color": "blue", "hex": "#2196f3"},
    "Intervento in corso": {"color": "red", "hex": "#e57373"},
    "Intervento concluso": {"color": "purple", "hex": "#9575cd"},
    "Rientro in corso": {"color": "orange", "hex": "#ffb74d"},
    "Rientrata al Coc": {"color": "green", "hex": "#81c784"},
}

# =========================
# LOGIN (Password)
# =========================
def require_login():
    pw = st.secrets.get("APP_PASSWORD", None)
    if not pw:
        st.warning("⚠️ APP_PASSWORD non impostata in Secrets. Streamlit Cloud → Settings → Secrets")
        return

    if "auth_ok" not in st.session_state:
        st.session_state.auth_ok = False

    if st.session_state.auth_ok:
        return

    st.markdown("### 🔐 Accesso protetto")
    st.caption("Inserisci la password per entrare nell'app.")
    p = st.text_input("Password", type="password")
    if st.button("Entra"):
        if p == pw:
            st.session_state.auth_ok = True
            st.rerun()
        else:
            st.error("Password errata.")
    st.stop()

require_login()

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

def get_squadra_info(nome_sq: str) -> Dict[str, Any]:
    info = st.session_state.squadre.get(nome_sq, {})
    return {
        "capo": (info.get("capo") or "").strip(),
        "tel": (info.get("tel") or "").strip(),
        "stato": info.get("stato", "In attesa al COC"),
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

def build_folium_map_from_df(df: pd.DataFrame, center: list, zoom: int = 13) -> folium.Map:
    m = folium.Map(location=center, zoom_start=zoom)
    ultime_pos = {}
    if not df.empty:
        for _, row in df.iterrows():
            pos = row.get("pos")
            sq = row.get("sq")
            stt = row.get("st")
            if isinstance(pos, list) and len(pos) == 2:
                ultime_pos[sq] = {"pos": pos, "st": stt}

    for sq, info in ultime_pos.items():
        stt = info["st"]
        folium.Marker(
            info["pos"],
            tooltip=f"{sq}: {stt}",
            icon=folium.Icon(color=COLORI_STATI.get(stt, {}).get("color", "blue")),
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
# PERSISTENZA
# =========================
def default_state_payload():
    return {
        "brogliaccio": [],
        "inbox": [],
        "squadre": {"SQUADRA 1": {"stato": "In attesa al COC", "capo": "", "tel": ""}},
        "pos_mappa": [45.7075, 11.4772],
        "op_name": "",
        "ev_data": datetime.now().date().isoformat(),
        "ev_tipo": "Emergenza",
        "ev_nome": "",
        "ev_desc": "",
    }

def save_data_to_disk():
    payload = {
        "brogliaccio": st.session_state.brogliaccio,
        "inbox": st.session_state.inbox,
        "squadre": st.session_state.squadre,
        "pos_mappa": st.session_state.pos_mappa,
        "op_name": st.session_state.op_name,
        "ev_data": str(st.session_state.ev_data),
        "ev_tipo": st.session_state.ev_tipo,
        "ev_nome": st.session_state.ev_nome,
        "ev_desc": st.session_state.ev_desc,
    }
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

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
    return True

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
    save_data_to_disk()

# =========================
# INIT STATE
# =========================
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.open_map_event = None

    ok = load_data_from_disk()
    if not ok:
        d = default_state_payload()
        st.session_state.brogliaccio = d["brogliaccio"]
        st.session_state.inbox = d["inbox"]
        st.session_state.squadre = d["squadre"]
        st.session_state.pos_mappa = d["pos_mappa"]
        st.session_state.op_name = d["op_name"]
        st.session_state.ev_data = datetime.fromisoformat(d["ev_data"]).date()
        st.session_state.ev_tipo = d["ev_tipo"]
        st.session_state.ev_nome = d["ev_nome"]
        st.session_state.ev_desc = d["ev_desc"]
        save_data_to_disk()

# =========================
# RINOMINA / MODIFICA SQUADRA
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
            if msg.get("sq") == old_name:
                msg["sq"] = new_name

        for b in st.session_state.brogliaccio:
            if b.get("sq") == old_name:
                b["sq"] = new_name
            if b.get("chi") == old_name:
                b["chi"] = new_name

    st.session_state.squadre[new_name]["capo"] = capo
    st.session_state.squadre[new_name]["tel"] = tel

    save_data_to_disk()
    return True, f"Aggiornata: {old_name} → {new_name}"

# =========================
# CSS (SIDEBAR + BOTTONI SPECIALI)
# =========================
st.markdown("""
<style>
header[data-testid="stHeader"] { background: transparent; border:none; }
.stApp { background: linear-gradient(180deg,#e9eef3 0%, #dfe7ee 100%); color:#0b1220; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }

/* HERO */
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

/* SIDEBAR */
section[data-testid="stSidebar"]{
  background: linear-gradient(180deg, #0b1f3a 0%, #071426 100%) !important;
  border-right: 1px solid rgba(255,255,255,.08) !important;
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
  color: rgba(248,250,252,.92) !important;
  font-weight: 800 !important;
}
section[data-testid="stSidebar"] hr{ border-color: rgba(255,255,255,.12) !important; }

/* INPUT sidebar */
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] textarea{
  background: #ffffff !important;
  color: #0b1220 !important;
  border: 1px solid rgba(15,23,42,.25) !important;
  border-radius: 12px !important;
  font-weight: 700 !important;
}
section[data-testid="stSidebar"] input::placeholder,
section[data-testid="stSidebar"] textarea::placeholder{
  color: rgba(15,23,42,.50) !important;
}

/* Selectbox */
section[data-testid="stSidebar"] div[data-baseweb="select"] > div{
  background: #ffffff !important;
  border: 1px solid rgba(15,23,42,.25) !important;
  border-radius: 12px !important;
}
section[data-testid="stSidebar"] div[data-baseweb="select"] span{
  color: #0b1220 !important;
  font-weight: 800 !important;
}

/* Dropdown menu */
div[role="listbox"]{
  background: #ffffff !important;
  border: 1px solid rgba(15,23,42,.25) !important;
}
div[role="option"]{
  color: #0b1220 !important;
  font-weight: 700 !important;
}
div[role="option"]:hover{ background: rgba(2,6,23,.06) !important; }

/* File uploader */
section[data-testid="stSidebar"] div[data-testid="stFileUploader"]{
  background: #ffffff !important;
  border: 1px dashed rgba(15,23,42,.35) !important;
  padding: 10px !important;
  border-radius: 14px !important;
}
section[data-testid="stSidebar"] div[data-testid="stFileUploader"] *{
  color: #0b1220 !important;
  font-weight: 800 !important;
}

/* BOTTONI DEFAULT sidebar (testo scuro anche dentro span) */
section[data-testid="stSidebar"] .stButton > button{
  width: 100% !important;
  background: linear-gradient(180deg, #f1f5f9 0%, #e2e8f0 100%) !important;
  color: #0b1220 !important;
  border: 1px solid rgba(15,23,42,.18) !important;
  border-radius: 12px !important;
  font-weight: 950 !important;
  box-shadow: 0 10px 22px rgba(2,6,23,.18) !important;
}
section[data-testid="stSidebar"] .stButton > button *{
  color: #0b1220 !important;
  font-weight: 950 !important;
}
section[data-testid="stSidebar"] .stButton > button:hover{
  background: #ffffff !important;
}
section[data-testid="stSidebar"] .stDownloadButton > button{
  width: 100% !important;
  background: linear-gradient(180deg, #fde68a 0%, #fbbf24 100%) !important;
  color: #0b1220 !important;
  border: 1px solid rgba(15,23,42,.18) !important;
  border-radius: 12px !important;
  font-weight: 950 !important;
  box-shadow: 0 10px 22px rgba(2,6,23,.18) !important;
}
section[data-testid="stSidebar"] .stDownloadButton > button *{
  color: #0b1220 !important;
  font-weight: 950 !important;
}

/* BOTTONI SPECIALI: add/salva squadra */
#btn-add-team + div button{
  background: linear-gradient(180deg, #93c5fd 0%, #60a5fa 100%) !important;
  color: #0b1220 !important;
  font-weight: 950 !important;
}
#btn-add-team + div button *{
  color: #0b1220 !important;
  font-weight: 950 !important;
}
#btn-save-team + div button{
  background: linear-gradient(180deg, #86efac 0%, #4ade80 100%) !important;
  color: #0b1220 !important;
  font-weight: 950 !important;
}
#btn-save-team + div button *{
  color: #0b1220 !important;
  font-weight: 950 !important;
}
#btn-add-team + div button:hover,
#btn-save-team + div button:hover{
  filter: brightness(1.04);
  transform: translateY(-1px);
}
</style>
""", unsafe_allow_html=True)

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("## 🛡️ NAVIGAZIONE")
    ruolo = st.radio("RUOLO ATTIVO:", ["SALA OPERATIVA", "MODULO CAPOSQUADRA"])
    st.divider()

    st.markdown("### 💾 Backup / Ripristino")
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
    }

    st.download_button(
        "⬇️ Scarica BACKUP JSON",
        data=json.dumps(payload_now, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="backup_radio_manager.json",
        mime="application/json",
    )

    up = st.file_uploader("⬆️ Ripristina da backup JSON", type=["json"])
    if up is not None:
        if st.button("🔁 RIPRISTINA ORA"):
            load_data_from_uploaded_json(up.read())
            st.success("Ripristino completato.")
            st.rerun()

    st.divider()

    if ruolo == "SALA OPERATIVA":
        st.markdown("### ➕ CREA SQUADRA")
        with st.form("form_add_team", clear_on_submit=True):
            n_sq = st.text_input("Nome squadra", placeholder="Es. Squadra 2 / Alfa / Delta…")
            capo = st.text_input("Nome caposquadra", placeholder="Es. Rossi Mario")
            tel = st.text_input("Telefono caposquadra", placeholder="Es. 3331234567")
            st.markdown("<div id='btn-add-team'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("➕ AGGIUNGI SQUADRA")

        if submitted:
            nome = (n_sq or "").strip().upper()
            if not nome:
                st.warning("Inserisci il nome squadra.")
            elif nome in st.session_state.squadre:
                st.warning("Esiste già una squadra con questo nome.")
            else:
                st.session_state.squadre[nome] = {
                    "stato": "In attesa al COC",
                    "capo": (capo or "").strip(),
                    "tel": (tel or "").strip(),
                }
                save_data_to_disk()
                st.success("Squadra creata.")
                st.rerun()

        st.divider()
        st.markdown("### 🛠️ MODIFICA SQUADRA")
        sel = st.selectbox("Seleziona squadra:", list(st.session_state.squadre.keys()), key="edit_team_sel")
        inf = get_squadra_info(sel)

        with st.form("form_edit_team"):
            new_name = st.text_input("Nuovo nome squadra", value=sel)
            new_capo = st.text_input("Caposquadra", value=inf["capo"])
            new_tel = st.text_input("Telefono", value=inf["tel"])
            st.markdown("<div id='btn-save-team'></div>", unsafe_allow_html=True)
            save = st.form_submit_button("💾 SALVA MODIFICHE")

        if save:
            ok, msg = update_team(sel, new_name, new_capo, new_tel)
            (st.success if ok else st.warning)(msg)
            if ok:
                st.rerun()

# =========================
# HEADER
# =========================
logo_data_uri = img_to_base64(LOGO_PATH)
logo_html = f"<img class='pc-logo' src='{logo_data_uri}' />" if logo_data_uri else ""
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
  <div class="pc-badge">📡 {ruolo}</div>
</div>
""",
    unsafe_allow_html=True,
)

# =========================
# MODULO CAPOSQUADRA
# =========================
if ruolo == "MODULO CAPOSQUADRA":
    st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
    st.subheader("📱 Modulo da campo")

    sq_c = st.selectbox("TUA SQUADRA:", list(st.session_state.squadre.keys()))
    info_sq = get_squadra_info(sq_c)
    st.markdown(f"**👤 Caposquadra:** {info_sq['capo'] or '—'} &nbsp;&nbsp; | &nbsp;&nbsp; **📞 Tel:** {info_sq['tel'] or '—'}")

    share_gps = st.checkbox("📍 Includi posizione GPS (Privacy)", value=True)

    st.subheader("📍 Invio rapido")
    msg_rapido = st.text_input("Nota breve:", placeholder="In movimento, arrivati...")

    if st.button("🚀 INVIA COORDINATE E MESSAGGIO"):
        pos_da_inviare = st.session_state.pos_mappa if share_gps else None
        st.session_state.inbox.append(
            {"ora": datetime.now().strftime("%H:%M"), "sq": sq_c, "msg": msg_rapido or "Aggiornamento posizione", "foto": None, "pos": pos_da_inviare}
        )
        save_data_to_disk()
        st.success("✅ Inviato!")

    st.divider()
    with st.form("form_c"):
        st.subheader("📸 Rapporto completo")
        msg_c = st.text_area("DESCRIZIONE:")
        foto = st.file_uploader("FOTO:", type=["jpg", "jpeg", "png"])
        if st.form_submit_button("INVIA TUTTO + GPS"):
            pos_da_inviare = st.session_state.pos_mappa if share_gps else None
            st.session_state.inbox.append(
                {"ora": datetime.now().strftime("%H:%M"), "sq": sq_c, "msg": msg_c, "foto": foto.read() if foto else None, "pos": pos_da_inviare}
            )
            save_data_to_disk()
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
c3.markdown(metric_box(COLORI_STATI["Intervento concluso"]["hex"], "✅", "Conclusi", st_lista.count("Intervento concluso")), unsafe_allow_html=True)
c4.markdown(metric_box(COLORI_STATI["Rientrata al Coc"]["hex"], "↩️", "Rientro", st_lista.count("Rientrata al Coc")), unsafe_allow_html=True)
c5.markdown(metric_box(COLORI_STATI["In attesa al COC"]["hex"], "🏠", "Al COC", st_lista.count("In attesa al COC")), unsafe_allow_html=True)

# =========================
# INBOX APPROVAZIONE
# =========================
if st.session_state.inbox:
    st.markdown(f"<div class='pc-alert'>⚠️ RICEVUTI {len(st.session_state.inbox)} AGGIORNAMENTI DA VALIDARE</div>", unsafe_allow_html=True)

    for i, data in enumerate(st.session_state.inbox):
        sq_in = data["sq"]
        inf_in = get_squadra_info(sq_in)

        with st.expander(f"📥 APPROVAZIONE: {sq_in} ({data['ora']})", expanded=True):
            st.markdown(f"<div class='pc-flow'>📞 <b>{sq_in}</b> <span class='pc-arrow'>➜</span> 🎧 <b>SALA OPERATIVA</b></div>", unsafe_allow_html=True)
            st.markdown(f"**👤 Caposquadra:** {inf_in['capo'] or '—'} &nbsp;&nbsp; | &nbsp;&nbsp; **📞 Tel:** {inf_in['tel'] or '—'}")

            st.write(f"**MSG:** {data['msg']}")
            if data["pos"]:
                st.info(f"📍 GPS acquisito: {data['pos']}")
            if data["foto"]:
                st.image(data["foto"], width=220)

            st_v = st.selectbox("Nuovo Stato:", list(COLORI_STATI.keys()), key=f"sv_inbox_{i}")
            st.markdown(chip_stato(st_v), unsafe_allow_html=True)

            cb1, cb2 = st.columns(2)
            if cb1.button("✅ APPROVA", key=f"ap_{i}"):
                pref = "[AUTO]" if data["pos"] else "[AUTO-PRIVACY]"
                st.session_state.brogliaccio.insert(
                    0,
                    {"ora": data["ora"], "chi": sq_in, "sq": sq_in, "st": st_v,
                     "mit": f"{pref} {data['msg']}", "ris": "VALIDATO", "op": st.session_state.op_name,
                     "pos": data["pos"], "foto": data["foto"]}
                )
                st.session_state.squadre[sq_in]["stato"] = st_v
                st.session_state.inbox.pop(i)
                save_data_to_disk()
                st.rerun()

            if cb2.button("🗑️ SCARTA", key=f"sc_{i}"):
                st.session_state.inbox.pop(i)
                save_data_to_disk()
                st.rerun()

# =========================
# DATI EVENTO + TABS
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

save_data_to_disk()
st.markdown("</div>", unsafe_allow_html=True)

t_rad, t_rep = st.tabs(["🖥️ SALA RADIO", "📊 REPORT"])

with t_rad:
    l, r = st.columns([1, 1.2])

    with l:
        st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
        with st.form("radio_form"):
            st.session_state.op_name = st.text_input("OPERATORE RADIO", value=st.session_state.op_name)
            chi = st.radio("CHI CHIAMA?", ["SALA OPERATIVA", "SQUADRA ESTERNA"])

            sq = st.selectbox("SQUADRA", list(st.session_state.squadre.keys()))
            inf = get_squadra_info(sq)
            st.caption(f"👤 Caposquadra: {inf['capo'] or '—'} · 📞 {inf['tel'] or '—'}")

            st_s = st.selectbox("STATO", list(COLORI_STATI.keys()))
            mit = st.text_area("MESSAGGIO")
            ris = st.text_area("RISPOSTA")
            st.markdown(chip_stato(st_s), unsafe_allow_html=True)

            c_g1, c_g2 = st.columns(2)
            lat = c_g1.number_input("LAT", value=float(st.session_state.pos_mappa[0]), format="%.6f")
            lon = c_g2.number_input("LON", value=float(st.session_state.pos_mappa[1]), format="%.6f")

            if st.form_submit_button("REGISTRA A LOG"):
                st.session_state.brogliaccio.insert(
                    0,
                    {"ora": datetime.now().strftime("%H:%M"), "chi": chi, "sq": sq, "st": st_s,
                     "mit": mit, "ris": ris, "op": st.session_state.op_name, "pos": [lat, lon], "foto": None}
                )
                st.session_state.squadre[sq]["stato"] = st_s
                st.session_state.pos_mappa = [lat, lon]
                save_data_to_disk()
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with r:
        st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
        df_all = pd.DataFrame(st.session_state.brogliaccio)
        m = build_folium_map_from_df(df_all, center=st.session_state.pos_mappa, zoom=14)
        st_folium(m, width="100%", height=450)
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
    else:
        df_f = df[df["sq"] == filtro].copy() if filtro != "TUTTE" else df.copy()
        df_view = df_for_report(df_f)
        st.dataframe(df_view, use_container_width=True, height=360)

        st.divider()
        csv = df_f.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Scarica CSV filtrato", data=csv, file_name="brogliaccio.csv", mime="text/csv")

    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# REGISTRO EVENTI + MAPPA
# =========================
st.markdown("### 📋 REGISTRO EVENTI")

if st.session_state.open_map_event is not None:
    idx = st.session_state.open_map_event
    if 0 <= idx < len(st.session_state.brogliaccio):
        row = st.session_state.brogliaccio[idx]
        pos = row.get("pos")

        st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
        st.subheader("🗺️ Mappa evento selezionato")

        if isinstance(pos, list) and len(pos) == 2:
            m_ev = folium.Map(location=pos, zoom_start=16)
            folium.Marker(
                pos,
                tooltip=f"{row.get('sq','')} · {row.get('st','')}",
                icon=folium.Icon(color=COLORI_STATI.get(row.get("st",""), {}).get("color", "blue")),
            ).add_to(m_ev)
            st_folium(m_ev, width="100%", height=420)
        else:
            st.info("Evento senza coordinate GPS (OMISSIS).")

        if st.button("❌ CHIUDI MAPPA", key="close_event_map"):
            st.session_state.open_map_event = None
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

for i, b in enumerate(st.session_state.brogliaccio):
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

        col_a, col_b = st.columns([1, 2])
        if gps_ok:
            if col_a.button("🗺️ APRI MAPPA VISIVA", key=f"open_map_{i}"):
                st.session_state.open_map_event = i
                st.rerun()
            col_b.caption("Apre una mappa dedicata in alto al registro (una alla volta).")
        else:
            col_a.button("🗺️ MAPPA NON DISPONIBILE", key=f"no_map_{i}", disabled=True)
            col_b.caption("Coordinate non presenti (OMISSIS).")

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
    st.session_state.squadre = d["squadre"]
    st.session_state.pos_mappa = d["pos_mappa"]
    st.session_state.op_name = d["op_name"]
    st.session_state.ev_data = datetime.fromisoformat(d["ev_data"]).date()
    st.session_state.ev_tipo = d["ev_tipo"]
    st.session_state.ev_nome = d["ev_nome"]
    st.session_state.ev_desc = d["ev_desc"]
    st.session_state.open_map_event = None
    save_data_to_disk()
    st.success("Tutti i dati sono stati cancellati.")
    st.rerun()

if col_m2.button("💾 SALVA ORA SU DISCO"):
    save_data_to_disk()
    st.success("Salvato.")

