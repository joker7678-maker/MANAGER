import streamlit as st
import pandas as pd
from datetime import datetime
import folium
from streamlit_folium import st_folium
import os
import base64
import html as html_escape
from typing import Optional, Tuple, Dict, Any

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="RADIO MANAGER - PROTEZIONE CIVILE THIENE", layout="wide")

# --- STATI ---
COLORI_STATI = {
    "In attesa al COC": {"color": "black", "hex": "#455a64"},
    "In uscita dal COC": {"color": "cadetblue", "hex": "#fff176"},
    "Arrivata sul luogo di intervento": {"color": "blue", "hex": "#2196f3"},
    "Intervento in corso": {"color": "red", "hex": "#e57373"},
    "Intervento concluso": {"color": "purple", "hex": "#9575cd"},
    "Rientro in corso": {"color": "orange", "hex": "#ffb74d"},
    "Rientrata al Coc": {"color": "green", "hex": "#81c784"},
}

# --- UTILS ---
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

def folium_map_iframe(map_obj: folium.Map, height: int = 520) -> str:
    raw = map_obj.get_root().render()
    safe = html_escape.escape(raw, quote=True)
    return f"""
    <iframe
      srcdoc="{safe}"
      style="width:100%; height:{height}px; border:0; border-radius:12px;"
      loading="lazy"
      referrerpolicy="no-referrer"
    ></iframe>
    """

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

def table_html_highlight(df_print: pd.DataFrame) -> str:
    if df_print.empty:
        return "<p>Nessun dato.</p>"

    sty = (
        df_print.style
        .set_table_styles([
            {"selector": "th", "props": "background:#f1f5f9; font-weight:900; border:1px solid #000; padding:6px;"},
            {"selector": "td", "props": "border:1px solid #000; padding:6px; vertical-align:top;"},
            {"selector": "table", "props": "border-collapse:collapse; width:100%; font-size:12px;"},
        ])
        .set_properties(subset=["CHI CHIAMA"], **{"background-color": "#fff7cc", "font-weight": "900"})
        .set_properties(subset=["CHI RICEVE"], **{"background-color": "#dbeafe", "font-weight": "900"})
    )
    return sty.to_html()

def make_html_report(
    titolo: str,
    ev_data,
    ev_tipo: str,
    ev_nome: str,
    ev_desc: str,
    table_html: str,
    map_iframe_html: Optional[str] = None,
) -> str:
    safe_desc = (ev_desc or "").replace("\n", "<br>")
    safe_nome = (ev_nome or "")

    map_section = ""
    if map_iframe_html:
        map_section = f"""
        <div class="card map">
          <h3 style="margin:0 0 10px 0;">Mappa</h3>
          {map_iframe_html}
        </div>
        """

    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{titolo}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; margin: 18px; color:#0b1220; }}
  .header {{
    display:flex; align-items:center; justify-content:space-between; gap:12px;
    padding:16px 18px; border-radius:14px;
    background: linear-gradient(135deg, #0d47a1 0%, #0b1f3a 80%);
    color:white;
  }}
  .h-title {{ font-size: 20px; font-weight: 900; text-transform: uppercase; letter-spacing: .8px; margin:0; }}
  .h-sub {{ margin: 4px 0 0 0; opacity:.9; font-size: 13px; }}
  .badge {{ padding:8px 12px; border-radius:999px; background: rgba(255,255,255,.15); border: 1px solid rgba(255,255,255,.22); font-weight:800; }}
  .card {{ margin-top: 12px; border: 1px solid rgba(15,23,42,.15); border-radius: 14px; padding: 14px; }}
  .grid {{ display:grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
  .kv b {{ display:inline-block; width: 120px; color:#334155; }}
  @media print {{
    .no-print {{ display:none !important; }}
    body {{ margin: 0; }}
    .card {{ border: none; }}
  }}
</style>
</head>
<body>
  <div class="header">
    <div>
      <p class="h-title">{titolo}</p>
      <p class="h-sub">Protezione Civile Thiene · Radio Manager Pro</p>
    </div>
    <div class="badge">{ev_tipo}</div>
  </div>

  <div class="card">
    <div class="grid">
      <div class="kv"><b>Data:</b> {ev_data}</div>
      <div class="kv"><b>Evento:</b> {safe_nome}</div>
      <div class="kv" style="grid-column: 1 / span 2;"><b>Descrizione:</b> {safe_desc}</div>
    </div>
  </div>

  {map_section}

  <div class="card">
    <h3 style="margin:0 0 10px 0;">Brogliaccio</h3>
    {table_html}
  </div>

  <div class="no-print" style="margin-top:10px;color:#64748b;font-size:12px;">
    Suggerimento: usa CTRL+P per stampare o salvare in PDF.
  </div>
</body>
</html>"""

# --- LOGICA MODIFICA SQUADRA ---
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
    return True, f"Aggiornata: {old_name} → {new_name}"

# --- CSS UI ---
st.markdown(
    """
<style>
header[data-testid="stHeader"] { background: transparent; border:none; }
section[data-testid="stSidebar"] { background: #0b1f3a; }
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

div[data-baseweb="input"], div[data-baseweb="select"], div[data-baseweb="textarea"], .stNumberInput input {
  border: 1px solid rgba(15, 23, 42, .22) !important;
  border-radius: 12px !important;
}
div[data-baseweb="input"]:focus-within,
div[data-baseweb="select"]:focus-within,
div[data-baseweb="textarea"]:focus-within{
  box-shadow: 0 0 0 3px rgba(13,71,161,.18) !important;
  border-color: rgba(13,71,161,.55) !important;
}

.stButton>button{
  border-radius: 12px;
  padding: .55rem .9rem;
  border: 1px solid rgba(15, 23, 42, .18);
  box-shadow: 0 6px 14px rgba(2,6,23,.08);
}
.stButton>button:hover{ transform: translateY(-1px); }

section[data-testid="stSidebar"] * { color: #e5e7eb !important; }
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.15); }
section[data-testid="stSidebar"] input[type="text"]{
  background: rgba(15, 23, 42, .78) !important;
  color: #ffffff !important;
  border: 1px solid rgba(255,255,255,.28) !important;
  border-radius: 12px !important;
}
section[data-testid="stSidebar"] input::placeholder{ color: rgba(229,231,235,.70) !important; }
section[data-testid="stSidebar"] div[data-baseweb="select"] > div{
  background: rgba(15, 23, 42, .78) !important;
  border: 1px solid rgba(255,255,255,.28) !important;
  border-radius: 12px !important;
}
section[data-testid="stSidebar"] div[data-baseweb="select"] span{ color: #ffffff !important; font-weight: 900 !important; }
div[role="listbox"]{ background: #0b1f3a !important; border: 1px solid rgba(255,255,255,.18) !important; }
div[role="option"]{ color: #e5e7eb !important; }
div[role="option"]:hover{ background: rgba(255,255,255,.10) !important; }
section[data-testid="stSidebar"] .stButton>button{
  width: 100% !important;
  background: rgba(255,255,255,.10) !important;
  color: #e5e7eb !important;
  border: 1px solid rgba(255,255,255,.20) !important;
  border-radius: 12px !important;
}
section[data-testid="stSidebar"] .stButton>button:hover{ background: rgba(255,255,255,.16) !important; }

@media print {
  .no-print, [data-testid="stSidebar"], [data-testid="stHeader"], [data-testid="stTabList"],
  button, .stButton, footer, .stExpander, .stForm, .stTabs, .stTabsContent { display: none !important; }
  .stApp { background: white !important; }
}
</style>
""",
    unsafe_allow_html=True,
)

# --- STATE ---
if "brogliaccio" not in st.session_state:
    st.session_state.brogliaccio = []
if "squadre" not in st.session_state:
    st.session_state.squadre = {"SQUADRA 1": {"stato": "In attesa al COC", "capo": "", "tel": ""}}
if "inbox" not in st.session_state:
    st.session_state.inbox = []
if "pos_mappa" not in st.session_state:
    st.session_state.pos_mappa = [45.7075, 11.4772]
if "op_name" not in st.session_state:
    st.session_state.op_name = ""
if "ev_data" not in st.session_state:
    st.session_state.ev_data = datetime.now().date()
if "ev_tipo" not in st.session_state:
    st.session_state.ev_tipo = "Emergenza"
if "ev_nome" not in st.session_state:
    st.session_state.ev_nome = ""
if "ev_desc" not in st.session_state:
    st.session_state.ev_desc = ""
if "open_map_event" not in st.session_state:
    st.session_state.open_map_event = None  # indice evento da mostrare su mappa

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("## 🛡️ NAVIGAZIONE")
    ruolo = st.radio("RUOLO ATTIVO:", ["SALA OPERATIVA", "MODULO CAPOSQUADRA"])
    st.divider()

    if ruolo == "SALA OPERATIVA":
        st.markdown("### ➕ CREA SQUADRA (con contatti)")
        with st.form("form_add_team", clear_on_submit=True):
            n_sq = st.text_input("Nome squadra", placeholder="Es. Squadra 2 / Alfa / Delta…")
            capo = st.text_input("Nome caposquadra", placeholder="Es. Rossi Mario")
            tel = st.text_input("Telefono caposquadra", placeholder="Es. 3331234567")
            submitted = st.form_submit_button("AGGIUNGI SQUADRA")

        if submitted:
            nome = (n_sq or "").strip().upper()
            if not nome:
                st.warning("Inserisci il nome squadra.")
            elif nome in st.session_state.squadre:
                st.warning("Esiste già una squadra con questo nome.")
            else:
                st.session_state.squadre[nome] = {"stato": "In attesa al COC", "capo": (capo or "").strip(), "tel": (tel or "").strip()}
                st.success("Squadra creata.")
                st.rerun()

        st.divider()
        st.markdown("### 🛠️ MODIFICA SQUADRA (nome + dati)")
        if len(st.session_state.squadre) > 0:
            sel = st.selectbox("Seleziona squadra da modificare:", list(st.session_state.squadre.keys()), key="edit_team_sel")
            inf = get_squadra_info(sel)

            with st.form("form_edit_team"):
                new_name = st.text_input("Nuovo nome squadra", value=sel, placeholder="Nome aggiornato")
                new_capo = st.text_input("Caposquadra", value=inf["capo"], placeholder="Nome e cognome")
                new_tel = st.text_input("Telefono", value=inf["tel"], placeholder="Numero telefono")
                save = st.form_submit_button("💾 SALVA MODIFICHE")

            if save:
                ok, msg = update_team(sel, new_name, new_capo, new_tel)
                (st.success if ok else st.warning)(msg)
                if ok:
                    st.rerun()
        else:
            st.info("Nessuna squadra presente.")

        st.divider()
        st.markdown("### 📋 ELENCO SQUADRE")
        for sq, info in list(st.session_state.squadre.items()):
            stato_sq = info.get("stato", "In attesa al COC")
            capo_sq = (info.get("capo") or "").strip()
            tel_sq = (info.get("tel") or "").strip()

            col_sq, col_del = st.columns([4, 1])
            contatti = []
            if capo_sq:
                contatti.append(f"👤 {capo_sq}")
            if tel_sq:
                contatti.append(f"📞 {tel_sq}")
            cont_str = " · ".join(contatti) if contatti else "—"

            col_sq.markdown(
                f"**{sq}**  \n{chip_stato(stato_sq)}  \n<small style='opacity:.85'>{cont_str}</small>",
                unsafe_allow_html=True,
            )
            if col_del.button("🗑️", key=f"d_{sq}"):
                del st.session_state.squadre[sq]
                st.rerun()

# --- HEADER HERO ---
logo_data_uri = img_to_base64("logo.png")
logo_html = f"<img class='pc-logo' src='{logo_data_uri}' />" if logo_data_uri else ""
st.markdown(
    f"""
<div class="pc-hero no-print">
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

# --- MODULO CAPOSQUADRA ---
if ruolo == "MODULO CAPOSQUADRA":
    st.markdown("<h1 style='text-align:center;color:#0d47a1;'>📱 MODULO DA CAMPO</h1>", unsafe_allow_html=True)
    st.markdown("<div class='pc-card'>", unsafe_allow_html=True)

    sq_c = st.selectbox("TUA SQUADRA:", list(st.session_state.squadre.keys()))
    info_sq = get_squadra_info(sq_c)
    st.markdown(f"**👤 Caposquadra:** {info_sq['capo'] or '—'} &nbsp;&nbsp; | &nbsp;&nbsp; **📞 Tel:** {info_sq['tel'] or '—'}")

    share_gps = st.checkbox("📍 Includi posizione GPS (Privacy)", value=True)

    st.subheader("📍 INVIO RAPIDO")
    msg_rapido = st.text_input("Nota breve:", placeholder="In movimento, arrivati...")

    if st.button("🚀 INVIA COORDINATE E MESSAGGIO"):
        pos_da_inviare = st.session_state.pos_mappa if share_gps else None
        st.session_state.inbox.append(
            {"ora": datetime.now().strftime("%H:%M"), "sq": sq_c, "msg": msg_rapido or "Aggiornamento posizione", "foto": None, "pos": pos_da_inviare}
        )
        st.success("✅ Inviato!")

    st.divider()
    with st.form("form_c"):
        st.subheader("📸 RAPPORTO COMPLETO")
        msg_c = st.text_area("DESCRIZIONE:")
        foto = st.file_uploader("FOTO:", type=["jpg", "jpeg", "png"])
        if st.form_submit_button("INVIA TUTTO + GPS"):
            pos_da_inviare = st.session_state.pos_mappa if share_gps else None
            st.session_state.inbox.append(
                {"ora": datetime.now().strftime("%H:%M"), "sq": sq_c, "msg": msg_c, "foto": foto.read() if foto else None, "pos": pos_da_inviare}
            )
            st.success("✅ Inviato!")

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# --- SALA OPERATIVA ---
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

# --- INBOX APPROVAZIONE ---
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
                    {"ora": data["ora"], "chi": sq_in, "sq": sq_in, "st": st_v, "mit": f"{pref} {data['msg']}",
                     "ris": "VALIDATO", "op": st.session_state.op_name, "pos": data["pos"], "foto": data["foto"]}
                )
                st.session_state.squadre[sq_in]["stato"] = st_v
                st.session_state.inbox.pop(i)
                st.rerun()

            if cb2.button("🗑️ SCARTA", key=f"sc_{i}"):
                st.session_state.inbox.pop(i)
                st.rerun()

# --- DATI INTERVENTO ---
st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
st.subheader("📋 Dati Intervento ed Evento")
cd1, cd2, cd3, cd4 = st.columns([1, 1, 1, 2])
st.session_state.ev_data = cd1.date_input("DATA", value=st.session_state.ev_data)
st.session_state.ev_tipo = cd2.selectbox("TIPO INTERVENTO", ["Emergenza", "Esercitazione", "Monitoraggio", "Altro"])
st.session_state.ev_nome = cd3.text_input("NOME EVENTO", value=st.session_state.ev_nome, placeholder="es. Alluvione, Gara...")
st.session_state.ev_desc = cd4.text_input("DESCRIZIONE DETTAGLIATA", value=st.session_state.ev_desc, placeholder="Note generali del servizio")
st.markdown("</div>", unsafe_allow_html=True)

t_rad, t_rep = st.tabs(["🖥️ SALA RADIO", "📊 REPORT"])

# --- SALA RADIO TAB ---
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
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with r:
        st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
        df_all = pd.DataFrame(st.session_state.brogliaccio)
        m = build_folium_map_from_df(df_all, center=st.session_state.pos_mappa, zoom=14)
        st_folium(m, width="100%", height=450)
        st.markdown("</div>", unsafe_allow_html=True)

# --- REPORT TAB (immutato rispetto alle versioni precedenti: omesso per brevità) ---
with t_rep:
    st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
    st.subheader("📊 Report per Squadra")

    df = pd.DataFrame(st.session_state.brogliaccio)
    squad_list = list(st.session_state.squadre.keys())
    filtro = st.selectbox("Seleziona squadra:", ["TUTTE"] + squad_list, index=0)

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
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        df_f = df[df["sq"] == filtro].copy() if filtro != "TUTTE" else df.copy()

        st.markdown("#### Conteggi per stato")
        counts = df_f["st"].value_counts().reset_index()
        counts.columns = ["STATO", "N"]
        st.dataframe(counts, use_container_width=True)

        st.divider()
        st.markdown("#### Log filtrato (CHI CHIAMA / CHI RICEVE evidenziati)")
        df_view = df_for_report(df_f)
        st.dataframe(df_view, use_container_width=True, height=360)

        st.divider()
        csv = df_f.to_csv(index=False).encode("utf-8")
        fname_csv = f"brogliaccio_{'tutte' if filtro=='TUTTE' else filtro.lower()}.csv".replace(" ", "_")
        st.download_button("⬇️ Scarica CSV filtrato", data=csv, file_name=fname_csv, mime="text/csv")

        st.divider()
        st.markdown("#### Report stampabile (HTML)")
        include_map = st.checkbox("🗺️ Includi mappa nel report", value=False)

        center = st.session_state.pos_mappa
        if not df_f.empty:
            last_pos = None
            for _, row in df_f.iterrows():
                pos = row.get("pos")
                if isinstance(pos, list) and len(pos) == 2:
                    last_pos = pos
            if last_pos:
                center = last_pos

        map_iframe = None
        if include_map:
            m_report = build_folium_map_from_df(df_f, center=center, zoom=13)
            map_iframe = folium_map_iframe(m_report, height=520)

        table_html = table_html_highlight(df_view)
        titolo = "REPORT TOTALE" if filtro == "TUTTE" else f"REPORT SQUADRA {filtro}"

        html_report = make_html_report(
            titolo=titolo,
            ev_data=st.session_state.ev_data,
            ev_tipo=st.session_state.ev_tipo,
            ev_nome=st.session_state.ev_nome,
            ev_desc=st.session_state.ev_desc,
            table_html=table_html,
            map_iframe_html=map_iframe,
        ).encode("utf-8")

        fname_html = f"report_{'tutte' if filtro=='TUTTE' else filtro.lower()}.html".replace(" ", "_")
        st.download_button("⬇️ Scarica Report HTML", data=html_report, file_name=fname_html, mime="text/html")

        st.markdown("</div>", unsafe_allow_html=True)

# --- REGISTRO EVENTI + PULSANTE MAPPA ---
st.markdown("### 📋 REGISTRO EVENTI")

# pannello mappa "apri/chiudi" (una sola mappa visiva alla volta)
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
            st.info("Questo evento non ha coordinate GPS (OMISSIS).")

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

        # --- PULSANTE MAPPA VISIVA ---
        col_a, col_b = st.columns([1, 2])
        if gps_ok:
            if col_a.button("🗺️ APRI MAPPA VISIVA", key=f"open_map_{i}"):
                st.session_state.open_map_event = i
                st.rerun()
            col_b.caption("Apre una mappa dedicata in alto al registro (una alla volta).")
        else:
            col_a.button("🗺️ MAPPA NON DISPONIBILE", key=f"no_map_{i}", disabled=True)
            col_b.caption("Coordinate non presenti (OMISSIS).")

        if b.get("foto"):
            st.image(b["foto"], width=320)

# --- SEZIONE MEMORIA ---
st.divider()
st.subheader("💾 Gestione Memoria Dati")
col_m1, col_m2, col_m3 = st.columns(3)

if col_m1.button("💾 SALVA DATI ATTUALI"):
    st.toast("Dati salvati correttamente nella sessione!")

if col_m2.button("🧹 CANCELLA TUTTI I DATI"):
    st.session_state.brogliaccio = []
    st.session_state.inbox = []
    st.session_state.open_map_event = None
    st.success("Tutti i dati sono stati cancellati.")
    st.rerun()

if col_m3.button("📄 GENERA REPORT TOTALE"):
    st.success("Vai in tab 📊 REPORT → seleziona TUTTE → (opzionale) spunta la mappa → Scarica Report HTML/CSV.")
