import streamlit as st
from datetime import datetime
import pandas as pd
from streamlit_folium import st_folium
import folium

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Radio Manager – Sala Radio", layout="wide")

# =========================
# SESSION STATE
# =========================
if "brogliaccio" not in st.session_state:
    st.session_state.brogliaccio = []

if "inbox" not in st.session_state:
    st.session_state.inbox = []

if "pos_mappa" not in st.session_state:
    st.session_state.pos_mappa = [45.713, 11.478]

if "op_name" not in st.session_state:
    st.session_state.op_name = ""

if "squadre" not in st.session_state:
    st.session_state.squadre = {
        "Squadra Alpha": {"capo": "Rossi", "tel": "3331111111", "stato": "IN ATTESA"},
        "Squadra Bravo": {"capo": "Bianchi", "tel": "3332222222", "stato": "IN ATTESA"},
        "Squadra Charlie": {"capo": "Verdi", "tel": "3333333333", "stato": "IN ATTESA"},
    }

COLORI_STATI = {
    "IN ATTESA": "#9e9e9e",
    "IN MOVIMENTO": "#1976d2",
    "SUL POSTO": "#f57c00",
    "INTERVENTO": "#c62828",
    "CONCLUSO": "#2e7d32",
}

# =========================
# FUNZIONI
# =========================
def chip_stato(stato):
    colore = COLORI_STATI.get(stato, "#999")
    return f"""
    <span style='
        padding:4px 10px;
        border-radius:14px;
        background:{colore};
        color:white;
        font-weight:600;
        font-size:12px;'>
        {stato}
    </span>
    """

def get_squadra_info(nome):
    return st.session_state.squadre.get(nome, {"capo": "", "tel": ""})

def build_map(df, center):
    m = folium.Map(location=center, zoom_start=14)
    for _, r in df.iterrows():
        if isinstance(r.get("pos"), list):
            folium.Marker(
                r["pos"],
                popup=f"{r['sq']} – {r['st']}"
            ).add_to(m)
    return m

# =========================
# STILE
# =========================
st.markdown("""
<style>
.pc-card{
    background:#ffffff;
    padding:14px;
    border-radius:14px;
    border:1px solid #e0e0e0;
    margin-bottom:12px;
}
</style>
""", unsafe_allow_html=True)

# =========================
# APP
# =========================
st.title("📻 Sala Radio – Radio Manager")

col_l, col_r = st.columns([1, 1.3])

# =========================
# SINISTRA – LOG RADIO
# =========================
with col_l:
    st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
    with st.form("radio_form"):
        st.session_state.op_name = st.text_input("Operatore radio", st.session_state.op_name)
        squadra = st.selectbox("Squadra", list(st.session_state.squadre.keys()))
        info = get_squadra_info(squadra)
        st.caption(f"👤 Caposquadra: {info['capo']} · 📞 {info['tel']}")

        stato = st.selectbox("Stato", list(COLORI_STATI.keys()))
        msg = st.text_area("Messaggio")

        c1, c2 = st.columns(2)
        lat = c1.number_input("Lat", value=st.session_state.pos_mappa[0], format="%.6f")
        lon = c2.number_input("Lon", value=st.session_state.pos_mappa[1], format="%.6f")

        st.markdown(chip_stato(stato), unsafe_allow_html=True)

        if st.form_submit_button("Registra"):
            st.session_state.brogliaccio.insert(0, {
                "ora": datetime.now().strftime("%H:%M"),
                "sq": squadra,
                "st": stato,
                "msg": msg,
                "pos": [lat, lon]
            })
            st.session_state.pos_mappa = [lat, lon]
            st.session_state.squadre[squadra]["stato"] = stato
            st.experimental_rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# DESTRA – MAPPA + NATO
# =========================
with col_r:
    st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
    df = pd.DataFrame(st.session_state.brogliaccio)
    mappa = build_map(df, st.session_state.pos_mappa)
    st_folium(mappa, height=420, width="100%")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
    st.subheader("🧾 Alfabeto NATO (compatto)")

    st.markdown("""
    <style>
    .nato-grid{
        display:grid;
        grid-template-columns: repeat(4, 1fr);
        gap:5px;
    }
    .nato-chip{
        display:flex;
        align-items:center;
        gap:6px;
        padding:4px 6px;
        background:#f4f6f9;
        border:1px solid #dfe3eb;
        border-radius:8px;
        font-size:12px;
    }
    .nato-letter{
        font-weight:800;
        background:#fff;
        border:1px solid #ccd3df;
        border-radius:6px;
        width:20px;
        height:20px;
        display:flex;
        align-items:center;
        justify-content:center;
    }
    </style>
    """, unsafe_allow_html=True)

    nato = [
        ("A","Alfa"),("B","Bravo"),("C","Charlie"),("D","Delta"),
        ("E","Echo"),("F","Foxtrot"),("G","Golf"),("H","Hotel"),
        ("I","India"),("J","Juliett"),("K","Kilo"),("L","Lima"),
        ("M","Mike"),("N","November"),("O","Oscar"),("P","Papa"),
        ("Q","Quebec"),("R","Romeo"),("S","Sierra"),("T","Tango"),
        ("U","Uniform"),("V","Victor"),("W","Whiskey"),("X","X-ray"),
        ("Y","Yankee"),("Z","Zulu"),
    ]

    html = "<div class='nato-grid'>"
    for l, c in nato:
        html += f"""
        <div class='nato-chip'>
            <div class='nato-letter'>{l}</div>
            <div>{c}</div>
        </div>
        """
    html += "</div>"

    st.markdown(html, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
