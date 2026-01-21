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
# CSS (SIDEBAR BOTTONI SCURI)
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

/* BOTTONI SIDEBAR SCURI (TUTTI) */
section[data-testid="stSidebar"] .stButton > button{
  width: 100% !important;
  background: linear-gradient(180deg, #0f172a 0%, #111827 100%) !important;
  color: #f8fafc !important;
  border: 1px solid rgba(255,255,255,.14) !important;
  border-radius: 12px !important;
  font-weight: 950 !important;
  box-shadow: 0 12px 26px rgba(2,6,23,.28) !important;
}
section[data-testid="stSidebar"] .stButton > button *{
  color: #f8fafc !important;
  font-weight: 950 !important;
}
section[data-testid="stSidebar"] .stButton > button:hover{
  filter: brightness(1.06);
  transform: translateY(-1px);
}
section[data-testid="stSidebar"] .stButton > button:hover *{
  color: #f8fafc !important;
}

/* Download button (backup json) resta giallo */
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
</style>
""", unsafe_allow_html=True)

# =========================
# SIDEBAR (Backup in fondo)
# =========================
with st.sidebar:
    st.markdown("## 🛡️ NAVIGAZIONE")
    ruolo = st.radio("RUOLO ATTIVO:", ["SALA OPERATIVA", "MODULO CAPOSQUADRA"])
    st.divider()

    # --- gestione squadre ---
    if ruolo == "SALA OPERATIVA":
        st.markdown("### ➕ CREA SQUADRA")
        with st.form("form_add_team", clear_on_submit=True):
            n_sq = st.text_input("Nome squadra", placeholder="Es. Squadra 2 / Alfa / Delta…")
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
            save = st.form_submit_button("💾 SALVA MODIFICHE")

        if save:
            ok, msg = update_team(sel, new_name, new_capo, new_tel)
            (st.success if ok else st.warning)(msg)
            if ok:
                st.rerun()

    # --- BACKUP E RIPRISTINO IN FONDO ---
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

# ... (RESTO DEL FILE)
st.info("✅ Il resto del file rimane IDENTICO al tuo: Inbox, Evento, Sala Radio, Report, Registro Eventi, Reset.")
