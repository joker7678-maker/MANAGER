import streamlit as st
import pandas as pd
from datetime import datetime
import folium
from streamlit_folium import st_folium
import os
import base64
import json
import uuid
import qrcode
from io import BytesIO
from typing import Optional, Tuple, Dict, Any

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="RADIO MANAGER - PC THIENE", layout="wide")

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
# QUERY PARAMS
# =========================
try:
    qp = st.query_params
    qp_mode = (qp.get("mode") or "").strip()
    qp_team = (qp.get("team") or "").strip().upper()
    qp_token = (qp.get("token") or "").strip()
except Exception:
    qp_mode, qp_team, qp_token = "", "", ""

# =========================
# UTILS
# =========================
def img_to_base64(path: str) -> Optional[str]:
    if not path or not os.path.exists(path): return None
    ext = os.path.splitext(path)[1].lower().replace(".", "")
    mime = "image/png" if ext == "png" else "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def text_color_for_bg(hex_color: str) -> str:
    h = (hex_color or "").lstrip("#")
    if len(h) != 6: return "#0b1220"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    lum = (0.299 * r + 0.587 * g + 0.114 * b)
    return "#0b1220" if lum > 160 else "#ffffff"

def chip_stato(stato: str) -> str:
    bg = COLORI_STATI.get(stato, {}).get("hex", "#e2e8f0")
    fg = text_color_for_bg(bg)
    return f"<span class='pc-chip' style='background:{bg};color:{fg};'><span class='pc-dot'></span>{stato}</span>"

def get_squadra_info(nome_sq: str) -> Dict[str, Any]:
    info = st.session_state.squadre.get(nome_sq, {})
    return {
        "capo": (info.get("capo") or "").strip(),
        "tel": (info.get("tel") or "").strip(),
        "stato": info.get("stato", "In attesa al COC"),
        "token": (info.get("token") or "").strip(),
    }

def call_flow_from_row(row: dict) -> Tuple[str, str]:
    chi, sq = (row.get("chi") or "").strip(), (row.get("sq") or "").strip()
    if chi.upper() == "SALA OPERATIVA": return "SALA OPERATIVA", (sq if sq else "—")
    return (sq if sq else "SQUADRA"), "SALA OPERATIVA"

def chip_call_flow(row: dict) -> str:
    a, b = call_flow_from_row(row)
    return f"<div class='pc-flow'>📞 <b>{a}</b> <span class='pc-arrow'>➜</span> 🎧 <b>{b}</b></div>"

def build_folium_map_from_df(df: pd.DataFrame, center: list, zoom: int = 13) -> folium.Map:
    m = folium.Map(location=center, zoom_start=zoom)
    ultime_pos = {}
    if not df.empty:
        for _, row in df.iterrows():
            pos, sq, stt = row.get("pos"), row.get("sq"), row.get("st")
            if isinstance(pos, list) and len(pos) == 2: ultime_pos[sq] = {"pos": pos, "st": stt}
    for sq, info in ultime_pos.items():
        folium.Marker(info["pos"], tooltip=f"{sq}: {info['st']}",
                      icon=folium.Icon(color=COLORI_STATI.get(info["st"], {}).get("color", "blue"))).add_to(m)
    return m

def df_for_report(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    out = df.copy()
    out["GPS"] = out["pos"].apply(lambda x: f"{x[0]:.4f}, {x[1]:.4f}" if isinstance(x, list) else "OMISSIS")
    cr = out.apply(lambda r: call_flow_from_row(r), axis=1, result_type="expand")
    out["CHI CHIAMA"], out["CHI RICEVE"] = cr[0], cr[1]
    cols = ["ora", "CHI CHIAMA", "CHI RICEVE", "sq", "st", "mit", "ris", "GPS", "op"]
    out = out.reindex(columns=cols).fillna("")
    return out.rename(columns={"ora":"ORA","sq":"SQUADRA","st":"STATO","mit":"MESSAGGIO","ris":"RISPOSTA","op":"OPERATORE"})

def qr_png_bytes(url: str) -> bytes:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO(); img.save(buf, format="PNG")
    return buf.getvalue()

# =========================
# PERSISTENZA
# =========================
def default_state_payload():
    return {
        "brogliaccio": [], "inbox": [], "pos_mappa": [45.7075, 11.4772], "op_name": "",
        "ev_data": datetime.now().date().isoformat(), "ev_tipo": "Emergenza", "ev_nome": "", "ev_desc": "",
        "squadre": {"SQUADRA 1": {"stato": "In attesa al COC", "capo": "", "tel": "", "token": uuid.uuid4().hex}},
    }

def save_data_to_disk():
    payload = {k: st.session_state[k] for k in ["brogliaccio", "inbox", "squadre", "pos_mappa", "op_name", "ev_tipo", "ev_nome", "ev_desc"]}
    payload["ev_data"] = str(st.session_state.ev_data)
    with open(DATA_PATH, "w", encoding="utf-8") as f: json.dump(payload, f, ensure_ascii=False, indent=2)

def load_data_from_disk():
    if not os.path.exists(DATA_PATH): return False
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f: payload = json.load(f)
        for k, v in payload.items():
            if k == "ev_data": st.session_state[k] = datetime.fromisoformat(v).date()
            else: st.session_state[k] = v
        return True
    except: return False

# =========================
# INIT STATE
# =========================
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.open_map_event = None
    st.session_state.team_edit_open = None
    st.session_state.team_qr_open = None
    st.session_state.BASE_URL = ""
    if not load_data_from_disk():
        d = default_state_payload()
        for k, v in d.items():
            st.session_state[k] = datetime.fromisoformat(v).date() if k=="ev_data" else v
    save_data_to_disk()

# =========================
# TEAM OPS
# =========================
def update_team(old, new, capo, tel):
    old, new = old.strip().upper(), new.strip().upper()
    if not new or (new != old and new in st.session_state.squadre): return False, "Errore nome."
    if new != old: st.session_state.squadre[new] = st.session_state.squadre.pop(old)
    st.session_state.squadre[new].update({"capo": capo, "tel": tel})
    save_data_to_disk(); return True, "Aggiornato."

def delete_team(team):
    if len(st.session_state.squadre) <= 1: return False, "Minimo 1 squadra."
    del st.session_state.squadre[team.upper()]
    save_data_to_disk(); return True, "Eliminata."

# =========================
# LOGIN / AUTH
# =========================
def require_login():
    if qp_mode.lower() == "campo" and qp_team in st.session_state.squadre and qp_token == st.session_state.squadre[qp_team].get("token"):
        st.session_state.auth_ok, st.session_state.field_ok, st.session_state.field_team = False, True, qp_team
        return
    pw = st.secrets.get("APP_PASSWORD")
    if not pw: st.error("Configura APP_PASSWORD"); st.stop()
    if st.session_state.get("auth_ok"): return
    st.markdown("### 🔐 Accesso protetto (SALA OPERATIVA)")
    p = st.text_input("Password", type="password")
    if st.button("Entra") and p == pw:
        st.session_state.auth_ok = True
        st.rerun()
    st.stop()

require_login()

# =========================
# CSS (VERSIONE ULTRA-LEGGIBILE SIDEBAR)
# =========================
st.markdown("""
<style>
header[data-testid="stHeader"] { background: transparent; }
.stApp { background: linear-gradient(180deg,#e9eef3 0%, #dfe7ee 100%); color:#0b1220; }

/* HERO */
.pc-hero{
  background: linear-gradient(135deg, #0d47a1 0%, #0b1f3a 80%);
  color:white; border-radius: 18px; padding: 18px 22px; margin-top: -60px; margin-bottom: 18px;
  display:flex; align-items:center; justify-content:space-between;
}
.pc-hero .title{ font-size: 1.8rem; font-weight: 900; text-transform: uppercase; margin:0; }

/* ===== SIDEBAR FIX ===== */
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0b1f3a 0%, #071426 100%) !important;
}
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] p {
  color: #ffffff !important; font-weight: 800 !important; opacity: 1 !important;
}
/* Input bianchi con testo nero nella sidebar */
section[data-testid="stSidebar"] input, section[data-testid="stSidebar"] select, section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
  background-color: #ffffff !important; color: #000000 !important; border-radius: 8px !important;
}
/* Bottoni sidebar */
section[data-testid="stSidebar"] .stButton > button {
  background: #1e293b !important; color: white !important; border: 1px solid rgba(255,255,255,0.2) !important; font-weight: 700 !important;
}
/* Download button giallo */
section[data-testid="stSidebar"] .stDownloadButton > button {
  background: #fbbf24 !important; color: black !important; font-weight: 800 !important; border:none !important;
}
/* Expander Sidebar */
section[data-testid="stSidebar"] .st-emotion-cache-p4mowd {
    background-color: rgba(255,255,255,0.08) !important; border-radius: 10px !important;
}

.pc-card{ background: #fff; border-radius: 16px; padding: 18px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 14px; }
.pc-chip{ display:inline-flex; align-items:center; gap:8px; padding:5px 12px; border-radius:999px; font-weight:800; font-size:.8rem; }
.pc-dot{ width:8px; height:8px; border-radius:50%; background: white; }
.pc-flow{ background: #f1f5f9; padding: 8px; border-radius: 10px; font-weight: 800; border: 1px solid #ddd; }
</style>
""", unsafe_allow_html=True)

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("## 🛡️ SQUADRE")
    
    if not st.session_state.get("field_ok"):
        ruolo = st.radio("RUOLO:", ["SALA OPERATIVA", "MODULO CAPOSQUADRA"])
        st.divider()
        
        if ruolo == "SALA OPERATIVA":
            # Lista squadre con bottoni chiari
            for team in sorted(st.session_state.squadre.keys()):
                inf = get_squadra_info(team)
                with st.expander(f"👥 {team}"):
                    st.markdown(chip_stato(inf["stato"]), unsafe_allow_html=True)
                    if st.button("✏️ MODIFICA", key=f"ed_{team}"): st.session_state.team_edit_open = team
                    if st.button("📱 QR", key=f"qr_{team}"): st.session_state.team_qr_open = team
                    
                    if st.session_state.team_edit_open == team:
                        with st.form(f"f_ed_{team}"):
                            n_n = st.text_input("Nuovo Nome", value=team)
                            n_c = st.text_input("Capo", value=inf["capo"])
                            n_t = st.text_input("Tel", value=inf["tel"])
                            if st.form_submit_button("SALVA"):
                                ok, m = update_team(team, n_n, n_c, n_t)
                                if ok: st.session_state.team_edit_open = None; st.rerun()
                    
                    if st.session_state.team_qr_open == team:
                        link = f"{st.session_state.BASE_URL}/?mode=campo&team={team}&token={inf['token']}"
                        st.image(qr_png_bytes(link), width=150)
                        if st.button("CHIUDI QR", key=f"cq_{team}"): st.session_state.team_qr_open = None; st.rerun()

            st.divider()
            st.markdown("### ➕ AGGIUNGI")
            with st.form("add_sq", clear_on_submit=True):
                ns = st.text_input("Nome Squadra").upper()
                if st.form_submit_button("AGGIUNGI") and ns:
                    st.session_state.squadre[ns] = {"stato":"In attesa al COC","capo":"","tel":"","token":uuid.uuid4().hex}
                    save_data_to_disk(); st.rerun()

    st.divider()
    st.session_state.BASE_URL = st.text_input("URL APP (per QR)", value=st.session_state.BASE_URL)

# =========================
# MAIN UI
# =========================
logo_uri = img_to_base64(LOGO_PATH)
l_html = f"<img src='{logo_uri}' style='width:50px; margin-right:15px;'>" if logo_uri else ""
st.markdown(f"<div class='pc-hero'>{l_html}<div class='title'>PC THIENE - RADIO MANAGER</div></div>", unsafe_allow_html=True)

if st.session_state.get("field_ok") or (not st.session_state.get("field_ok") and ruolo == "MODULO CAPOSQUADRA"):
    # --- MODULO CAPOSQUADRA ---
    sq_c = st.session_state.field_team if st.session_state.get("field_ok") else st.selectbox("SQUADRA:", list(st.session_state.squadre.keys()))
    st.subheader(f"📱 Console Campo: {sq_c}")
    msg = st.text_area("Messaggio dalla squadra:")
    if st.button("🚀 INVIA A SALA RADIO"):
        st.session_state.inbox.append({"ora": datetime.now().strftime("%H:%M"), "sq": sq_c, "msg": msg, "pos": st.session_state.pos_mappa, "foto": None})
        save_data_to_disk(); st.success("Inviato!")
else:
    # --- SALA OPERATIVA ---
    t1, t2 = st.tabs(["SALA RADIO", "REPORT"])
    
    with t1:
        # Gestione Inbox
        if st.session_state.inbox:
            st.error(f"🔔 {len(st.session_state.inbox)} messaggi da approvare!")
            for i, m in enumerate(st.session_state.inbox):
                with st.expander(f"Messaggio da {m['sq']}"):
                    st.write(m['msg'])
                    if st.button("✅ APPROVA", key=f"ok_{i}"):
                        st.session_state.brogliaccio.insert(0, {"ora":m['ora'], "chi":m['sq'], "sq":m['sq'], "st":"Intervento in corso", "mit":m['msg'], "ris":"Ricevuto", "op":st.session_state.op_name, "pos":m['pos']})
                        st.session_state.inbox.pop(i); save_data_to_disk(); st.rerun()

        col_l, col_r = st.columns([1, 1])
        with col_l:
            st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
            with st.form("radio_log"):
                op = st.text_input("Operatore", value=st.session_state.op_name)
                sq = st.selectbox("Squadra", list(st.session_state.squadre.keys()))
                stt = st.selectbox("Stato", list(COLORI_STATI.keys()))
                txt = st.text_area("Comunicazione")
                if st.form_submit_button("REGISTRA"):
                    st.session_state.op_name = op
                    st.session_state.brogliaccio.insert(0, {"ora": datetime.now().strftime("%H:%M"), "chi":"SALA OPERATIVA", "sq":sq, "st":stt, "mit":txt, "ris":"—", "op":op, "pos":st.session_state.pos_mappa})
                    st.session_state.squadre[sq]["stato"] = stt
                    save_data_to_disk(); st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_r:
            st_folium(build_folium_map_from_df(pd.DataFrame(st.session_state.brogliaccio), [45.7075, 11.4772]), width="100%", height=400)

# =========================
# MEMORIA DATI (FONDO PAGINA)
# =========================
st.divider()
st.subheader("💾 GESTIONE DATI")
cm1, cm2 = st.columns(2)
if cm1.button("🧹 CANCELLA TUTTO"):
    for k, v in default_state_payload().items(): st.session_state[k] = v
    save_data_to_disk(); st.rerun()
if cm2.button("💾 SALVA ORA"):
    save_data_to_disk(); st.success("Dati salvati con successo!")