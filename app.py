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
from typing import Optional, Tuple, Dict, Any, List

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="RADIO MANAGER - PROTEZIONE CIVILE THIENE", layout="wide")

DATA_PATH = "data.json"
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

def get_squadra_info(nome_sq: str) -> Dict[str, Any]:
    info = st.session_state.squadre.get(nome_sq, {})
    return {
        "capo": (info.get("capo") or "").strip(),
        "tel": (info.get("tel") or "").strip(),
        "stato": info.get("stato", "In attesa al COC"),
        "token": (info.get("token") or "").strip(),
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
        for (lat, lon, label) in points:
            # marker blu
            smap.add_marker(CircleMarker((lon, lat), "#2563eb", 10))
            # (staticmap non stampa label sul tile; ma almeno i punti ci sono)

        image = smap.render(zoom=zoom)
        buf = BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None

def make_html_report_bytes(
    squads: Dict[str, Any],
    brogliaccio: list,
    center: list,
    meta: dict,
) -> bytes:
    """
    HTML con:
    - selettore squadra (TUTTE o singola)
    - selettore MAPPA (Ultime posizioni / Tutti eventi / Percorso)
    - checkbox "Stampa con mappa"
    MAPPA in HTML è un'IMMAGINE base64 -> stampa sempre.
    """
    df_all = pd.DataFrame(brogliaccio)

    def _safe(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _df_to_html_table(df_view: pd.DataFrame) -> str:
        if df_view is None or df_view.empty:
            return "<div class='muted'>Nessun dato presente.</div>"
        return df_view.to_html(index=False, classes="tbl", escape=True)

    ev_data = _safe(str(meta.get("ev_data", "")))
    ev_tipo = _safe(str(meta.get("ev_tipo", "")))
    ev_nome = _safe(str(meta.get("ev_nome", "")))
    ev_desc = _safe(str(meta.get("ev_desc", "")))
    op_name = _safe(str(meta.get("op_name", "")))

    options_html = ["<option value='TUTTE'>TUTTE</option>"]
    sections_html = []

    # helper: produce 3 map images for a df
    def _maps_for_df(df_x: pd.DataFrame) -> Dict[str, str]:
        """
        returns dict: {LATEST: datauri, ALL: datauri, TRACK: datauri} or placeholders
        """
        # LATEST
        pts_latest = _extract_points_latest_by_team(df_x) if "sq" in df_x.columns else _extract_points_all_events(df_x)
        # se df_x è filtrato per squadra, latest_by_team = 1 punto (ok); se totale = multi-squadre (ok)
        png_latest = render_static_map_png(pts_latest, polyline=None, zoom=14)

        # ALL
        pts_all = _extract_points_all_events(df_x)
        png_all = render_static_map_png(pts_all, polyline=None, zoom=14)

        # TRACK (percorso)
        line = _extract_polyline_all_events(df_x)
        # per track: punti = punti all (così si vedono anche marker)
        png_track = render_static_map_png(pts_all, polyline=line if len(line) >= 2 else None, zoom=14)

        def _placeholder(text: str) -> str:
            # immagine "finta" via SVG (stampa sicuro)
            svg = f"""
            <svg xmlns='http://www.w3.org/2000/svg' width='1200' height='700'>
              <rect width='100%' height='100%' fill='#f8fafc'/>
              <rect x='20' y='20' width='1160' height='660' rx='18' fill='#ffffff' stroke='#cbd5e1' stroke-width='3'/>
              <text x='60' y='120' font-family='Arial' font-size='44' font-weight='900' fill='#0f172a'>MAPPA NON DISPONIBILE</text>
              <text x='60' y='200' font-family='Arial' font-size='28' font-weight='700' fill='#334155'>{_safe(text)}</text>
              <text x='60' y='260' font-family='Arial' font-size='24' font-weight='700' fill='#64748b'>Installa staticmap in requirements.txt per mappe stampabili.</text>
            </svg>
            """.encode("utf-8")
            return "data:image/svg+xml;base64," + base64.b64encode(svg).decode("utf-8")

        out = {}
        out["LATEST"] = bytes_to_data_uri_png(png_latest) if png_latest else _placeholder("Modalità: ULTIME POSIZIONI")
        out["ALL"] = bytes_to_data_uri_png(png_all) if png_all else _placeholder("Modalità: TUTTI EVENTI")
        out["TRACK"] = bytes_to_data_uri_png(png_track) if png_track else _placeholder("Modalità: PERCORSO")
        return out

    # ====== SEZIONE TUTTE
    df_view_tot = df_for_report(df_all) if not df_all.empty else pd.DataFrame()
    tab_tot = _df_to_html_table(df_view_tot)
    maps_tot = _maps_for_df(df_all) if not df_all.empty else {
        "LATEST": "",
        "ALL": "",
        "TRACK": "",
    }
    sections_html.append(f"""
      <section class="rep" id="rep_TUTTE">
        <div class="h2">REPORT TOTALE</div>
        <div class="meta">
          <span><b>Data:</b> {ev_data}</span>
          <span><b>Tipo:</b> {ev_tipo}</span>
          <span><b>Evento:</b> {ev_nome}</span>
          <span><b>Operatore:</b> {op_name}</span>
        </div>
        <div class="desc"><b>Descrizione:</b> {ev_desc}</div>
        <hr/>

        <div class="mapblock">
          <div class="h3">🗺️ MAPPA (seleziona cosa stampare)</div>

          <div class="mapmode">
            <label>Modalità mappa:</label>
            <select class="selMap" onchange="setMapModeForSection('rep_TUTTE', this.value)">
              <option value="LATEST">Ultime posizioni (per squadra)</option>
              <option value="ALL">Tutti eventi (punti)</option>
              <option value="TRACK">Percorso (linea + punti)</option>
            </select>
          </div>

          <div class="mapwrap">
            <img class="mapimg map-LATEST" src="{maps_tot.get('LATEST','')}" alt="mappa latest"/>
            <img class="mapimg map-ALL" src="{maps_tot.get('ALL','')}" alt="mappa all"/>
            <img class="mapimg map-TRACK" src="{maps_tot.get('TRACK','')}" alt="mappa track"/>
          </div>
        </div>

        <div class="h3">📋 LOG</div>
        {tab_tot}
      </section>
    """)

    # ====== SEZIONI SQUADRA
    for sq in sorted(list(squads.keys())):
        options_html.append(f"<option value='{_safe(sq)}'>{_safe(sq)}</option>")

        if df_all.empty:
            df_sq = pd.DataFrame()
        else:
            df_sq = df_all[df_all.get("sq", "") == sq].copy()

        df_view_sq = df_for_report(df_sq) if not df_sq.empty else pd.DataFrame()
        tab_sq = _df_to_html_table(df_view_sq)

        capo = _safe((squads.get(sq, {}) or {}).get("capo", "") or "—")
        tel = _safe((squads.get(sq, {}) or {}).get("tel", "") or "—")
        stato = _safe((squads.get(sq, {}) or {}).get("stato", "") or "—")

        maps_sq = _maps_for_df(df_sq) if not df_sq.empty else {
            "LATEST": "",
            "ALL": "",
            "TRACK": "",
        }

        sections_html.append(f"""
          <section class="rep" id="rep_{_safe(sq)}">
            <div class="h2">REPORT SQUADRA: {_safe(sq)}</div>
            <div class="meta">
              <span><b>Caposquadra:</b> {capo}</span>
              <span><b>Telefono:</b> {tel}</span>
              <span><b>Stato:</b> {stato}</span>
            </div>
            <div class="meta">
              <span><b>Data:</b> {ev_data}</span>
              <span><b>Tipo:</b> {ev_tipo}</span>
              <span><b>Evento:</b> {ev_nome}</span>
              <span><b>Operatore:</b> {op_name}</span>
            </div>
            <div class="desc"><b>Descrizione:</b> {ev_desc}</div>
            <hr/>

            <div class="mapblock">
              <div class="h3">🗺️ MAPPA EVENTI SQUADRA (scegli cosa stampare)</div>

              <div class="mapmode">
                <label>Modalità mappa:</label>
                <select class="selMap" onchange="setMapModeForSection('rep_{_safe(sq)}', this.value)">
                  <option value="LATEST">Ultimo punto squadra</option>
                  <option value="ALL">Tutti eventi (punti)</option>
                  <option value="TRACK">Percorso (linea + punti)</option>
                </select>
              </div>

              <div class="mapwrap">
                <img class="mapimg map-LATEST" src="{maps_sq.get('LATEST','')}" alt="mappa latest"/>
                <img class="mapimg map-ALL" src="{maps_sq.get('ALL','')}" alt="mappa all"/>
                <img class="mapimg map-TRACK" src="{maps_sq.get('TRACK','')}" alt="mappa track"/>
              </div>
            </div>

            <div class="h3">📋 LOG</div>
            {tab_sq}
          </section>
        """)

    html = f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Report Radio Manager - Protezione Civile Thiene</title>

<style>
  :root {{
    --bg: #eef3f7;
    --card: #ffffff;
    --ink: #0b1220;
    --muted: #475569;
    --pri: #0d47a1;
    --border: rgba(15,23,42,.15);
  }}
  body {{
    margin:0; font-family: Arial, Helvetica, sans-serif;
    background: var(--bg); color: var(--ink);
  }}
  .wrap {{ max-width: 1200px; margin: 18px auto; padding: 0 14px; }}
  .top {{
    background: linear-gradient(135deg, var(--pri), #0b1f3a);
    color: white; border-radius: 16px; padding: 16px 18px;
    box-shadow: 0 10px 28px rgba(2,6,23,.12);
  }}
  .title {{ font-size: 22px; font-weight: 900; letter-spacing:.5px; text-transform: uppercase; }}
  .sub {{ opacity:.9; margin-top:4px; font-weight: 700; }}
  .controls {{
    margin-top: 12px; background: rgba(255,255,255,.14);
    border: 1px solid rgba(255,255,255,.18);
    border-radius: 14px; padding: 12px;
    display:flex; gap:10px; flex-wrap: wrap; align-items:center;
  }}
  label {{ font-weight: 900; }}
  select {{
    padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(15,23,42,.2);
    font-weight: 800; min-width: 240px;
  }}
  .btn {{
    padding: 10px 14px; border-radius: 12px; border: 1px solid rgba(255,255,255,.22);
    background: #111827; color: white; font-weight: 900; cursor: pointer;
  }}
  .btn.secondary {{ background: #334155; }}
  .toggle {{
    display:flex; align-items:center; gap:10px;
    background: rgba(255,255,255,.10);
    border: 1px solid rgba(255,255,255,.18);
    padding: 10px 12px; border-radius: 12px;
    font-weight: 900;
  }}
  .toggle input[type="checkbox"] {{
    width: 18px; height: 18px;
    accent-color: #fbbf24;
  }}

  .rep {{
    margin-top: 14px; background: var(--card);
    border: 1px solid var(--border); border-radius: 16px;
    padding: 16px; box-shadow: 0 8px 22px rgba(2,6,23,.08);
    display:none;
  }}
  .h2 {{ font-size: 18px; font-weight: 950; color: var(--pri); }}
  .h3 {{ margin-top: 12px; font-size: 14px; font-weight: 950; }}
  .meta {{
    margin-top: 8px;
    display:flex; gap:14px; flex-wrap: wrap;
    color: var(--muted); font-weight: 800;
  }}
  .desc {{ margin-top: 8px; color: var(--ink); font-weight: 700; }}
  hr {{ border: none; border-top: 1px solid rgba(15,23,42,.12); margin: 12px 0; }}

  .mapmode {{
    display:flex; gap:10px; align-items:center; flex-wrap:wrap;
    background: #f1f5f9;
    border: 1px solid rgba(15,23,42,.10);
    border-radius: 12px;
    padding: 10px 12px;
    margin-bottom: 10px;
  }}
  .mapwrap {{
    border: 1px solid rgba(15,23,42,.12);
    border-radius: 14px;
    overflow: hidden;
    background: #fff;
  }}
  .mapimg {{
    width: 100%;
    height: auto;
    display: none;
  }}

  .tbl {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }}
  .tbl th {{
    background: var(--pri);
    color: white;
    text-align: left;
    padding: 8px;
    position: sticky; top: 0;
  }}
  .tbl td {{
    border-top: 1px solid rgba(15,23,42,.10);
    padding: 7px 8px;
    vertical-align: top;
  }}
  .muted {{ color: var(--muted); font-weight: 800; }}

  /* Print */
  @media print {{
    body {{ background: white; }}
    .top .controls {{ display:none !important; }}
    .wrap {{ max-width: none; margin: 0; padding: 0; }}
    .rep {{ box-shadow: none; border: none; border-radius: 0; }}
    .rep {{ display:none; }}
    .rep.printme {{ display:block !important; }}
    .tbl th {{ position: static; }}
    .no-map .mapblock {{ display:none !important; }}
  }}


</style>
</head>

<body>
  <div class="wrap">
    <div class="top">
      <div class="title">Protezione Civile Thiene — Report Radio Manager</div>
      <div class="sub">Seleziona cosa stampare. La mappa è un'immagine: in stampa esce sempre.</div>

      <div class="controls">
        <label for="sel">Seleziona stampa:</label>
        <select id="sel" onchange="showSection()">
          {''.join(options_html)}
        </select>

        <div class="toggle">
          <input id="chkMap" type="checkbox" checked onchange="toggleMapClass()"/>
          <span>Stampa con mappa</span>
        </div>

        <button class="btn" onclick="doPrint()">🖨️ STAMPA</button>
        <button class="btn secondary" onclick="showAll()">👁️ Mostra tutto</button>
      </div>
    </div>

    {''.join(sections_html)}
  </div>

<script>
  function hideAllSections(){{
    document.querySelectorAll('.rep').forEach(s => {{
      s.classList.remove('printme');
      s.style.display = 'none';
    }});
  }}

  function toggleMapClass(){{
    const withMap = document.getElementById('chkMap').checked;
    const body = document.body;
    if(withMap) body.classList.remove('no-map');
    else body.classList.add('no-map');
  }}

  function setMapModeForSection(sectionId, mode){{
    const sec = document.getElementById(sectionId);
    if(!sec) return;

    // nascondi tutte
    sec.querySelectorAll('.mapimg').forEach(img => img.style.display = 'none');

    // mostra quella scelta
    const img = sec.querySelector('.map-' + mode);
    if(img) img.style.display = 'block';

    // salva su dataset per stampa coerente
    sec.dataset.mapmode = mode;
  }}

  function ensureDefaultMapVisible(sectionId){{
    const sec = document.getElementById(sectionId);
    if(!sec) return;
    const current = sec.dataset.mapmode || 'LATEST';
    setMapModeForSection(sectionId, current);

    // allinea select
    const sel = sec.querySelector('.selMap');
    if(sel) sel.value = current;
  }}

  function showSection(){{
    const v = document.getElementById('sel').value;
    hideAllSections();

    const sec = document.getElementById('rep_' + v);
    if(sec){{
      sec.style.display = 'block';
      sec.classList.add('printme');

      // assicura che una mappa sia visibile (se mappa attiva)
      ensureDefaultMapVisible('rep_' + v);

      window.scrollTo(0, sec.offsetTop - 10);
    }}

    toggleMapClass();
  }}

  function showAll(){{
    document.querySelectorAll('.rep').forEach(s => {{
      s.classList.remove('printme');
      s.style.display = 'block';

      // assicura mappa visibile per ogni sezione
      ensureDefaultMapVisible(s.id);
    }});
    toggleMapClass();
    window.scrollTo(0, 0);
  }}

  function doPrint(){{
    showSection();
    setTimeout(() => {{
      window.print();
    }}, 300);
  }}

  (function init(){{
    // default: mostra totale
    showSection();
  }})();
</script>

</body>
</html>
"""
    return html.encode("utf-8")

# =========================
# PERSISTENZA
# =========================
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
        "BASE_URL": st.session_state.get("BASE_URL", ""),
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
    st.session_state.BASE_URL = payload.get("BASE_URL", "") or ""
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
    st.session_state.BASE_URL = payload.get("BASE_URL", "") or ""
    save_data_to_disk()

# =========================
# INIT STATE
# =========================
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.open_map_event = None
    st.session_state.team_edit_open = None
    st.session_state.team_qr_open = None

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
        st.session_state.BASE_URL = d["BASE_URL"]
        save_data_to_disk()

# assicura token a tutte le squadre
for _, info in st.session_state.squadre.items():
    if "token" not in info or not info["token"]:
        info["token"] = uuid.uuid4().hex

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

save_data_to_disk()

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
    # Accesso diretto caposquadra via link QR
    if (
        qp_mode.lower() == "campo"
        and qp_team in st.session_state.get("squadre", {})
        and qp_token
        and qp_token == st.session_state.squadre[qp_team].get("token")
    ):
        st.session_state.auth_ok = False
        st.session_state.field_ok = True
        st.session_state.field_team = qp_team
        return

    pw = st.secrets.get("APP_PASSWORD", None)
    if not pw:
        st.warning("⚠️ APP_PASSWORD non impostata in Secrets.")
        st.stop()

    if "auth_ok" not in st.session_state:
        st.session_state.auth_ok = False
    if "field_ok" not in st.session_state:
        st.session_state.field_ok = False

    if st.session_state.auth_ok:
        return

    st.markdown("### 🔐 Accesso protetto (SALA OPERATIVA)")
    st.caption("Inserisci la password per entrare nella console.")
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

</style>
""", unsafe_allow_html=True)

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("## 🛡️ NAVIGAZIONE")

    if st.session_state.get("field_ok"):
        ruolo = "MODULO CAPOSQUADRA"
    else:
        ruolo = st.radio("RUOLO ATTIVO:", ["SALA OPERATIVA", "MODULO CAPOSQUADRA"])

    st.divider()

    if ruolo == "SALA OPERATIVA":
        st.markdown("## 👥 SQUADRE")
        st.caption(f"Totale: **{len(st.session_state.squadre)}**")

        # --- Lista compatta (niente cerca squadre) ---
        squadre_sorted = sorted(list(st.session_state.squadre.keys()))
        for team in squadre_sorted:
            inf = get_squadra_info(team)
            stato_hex = COLORI_STATI.get(inf["stato"], {}).get("hex", "#e2e8f0")
            capo_txt = inf["capo"] if inf["capo"] else "—"
            tel_txt = inf["tel"] if inf["tel"] else "—"

            c0, c1, c2 = st.columns([0.18, 1, 0.60])
            c0.markdown(
                f"<div class='pc-sqdot' style='background:{stato_hex};'></div>",
                unsafe_allow_html=True,
            )
            c1.markdown(
                f"<div class='pc-sqrow'><div class='pc-sqname'>{team}</div>"
                f"<div class='pc-sqsub'>👤 {capo_txt} · 📞 {tel_txt}</div></div>",
                unsafe_allow_html=True,
            )
            b_edit, b_qr = c2.columns(2)
            if b_edit.button("✏️", key=f"btn_edit_{team}"):
                st.session_state.team_edit_open = team
                st.session_state.team_qr_open = None
                st.rerun()
            if b_qr.button("📱", key=f"btn_qr_{team}"):
                st.session_state.team_qr_open = team
                st.session_state.team_edit_open = None
                st.rerun()

        # --- Modulo gestione (pulito e centralizzato) ---
        st.divider()
        st.markdown("## 🧰 Gestione squadra")

        # se non c'è una selezione attiva, usa la prima
        if st.session_state.get("team_edit_open") not in st.session_state.squadre and st.session_state.squadre:
            st.session_state.team_edit_open = sorted(list(st.session_state.squadre.keys()))[0]

        team_sel = st.selectbox(
            "Seleziona squadra",
            options=sorted(list(st.session_state.squadre.keys())),
            index=sorted(list(st.session_state.squadre.keys())).index(st.session_state.team_edit_open)
            if st.session_state.get("team_edit_open") in st.session_state.squadre
            else 0,
            key="team_manage_sel",
        )
        st.session_state.team_edit_open = team_sel
        inf = get_squadra_info(team_sel)
        st.markdown(chip_stato(inf["stato"]), unsafe_allow_html=True)

        with st.form("form_team_manage"):
            new_name = st.text_input("Nome squadra", value=team_sel, help="Il nome viene salvato in MAIUSCOLO")
            new_capo = st.text_input("Caposquadra", value=inf["capo"], placeholder="Es. Rossi Mario")
            new_tel = st.text_input("Telefono", value=inf["tel"], placeholder="Es. 3331234567")
            s1, s2 = st.columns(2)
            save = s1.form_submit_button("💾 Salva")
            open_qr = s2.form_submit_button("📱 Apri QR")

        if save:
            ok, msg = update_team(team_sel, new_name, new_capo, new_tel)
            (st.success if ok else st.warning)(msg)
            if ok:
                # allinea selezione su nuovo nome
                st.session_state.team_edit_open = (new_name or "").strip().upper()
                st.session_state.team_qr_open = None
                st.rerun()

        if open_qr:
            st.session_state.team_qr_open = team_sel
            st.rerun()

        st.caption("Se il QR è stato condiviso per errore, rigenera il token.")
        ctk1, ctk2 = st.columns(2)
        if ctk1.button("♻️ Rigenera token", key="regen_token_manage"):
            regenerate_team_token(team_sel)
            st.success("Token rigenerato ✅")
            st.session_state.team_qr_open = team_sel
            st.rerun()

        if ctk2.button("🗑️ Elimina", key="delete_team_manage"):
            st.session_state["_del_arm"] = team_sel

        if st.session_state.get("_del_arm") == team_sel:
            st.warning("Conferma eliminazione: questa azione è irreversibile.")
            conf = st.checkbox("Confermo eliminazione squadra", key="confdel_manage")
            if st.button("✅ Conferma elimina", disabled=not conf, key="confirm_delete_manage"):
                ok, msg = delete_team(team_sel)
                (st.success if ok else st.warning)(msg)
                st.session_state["_del_arm"] = None
                st.rerun()
            if st.button("❌ Annulla", key="cancel_delete_manage"):
                st.session_state["_del_arm"] = None
                st.rerun()

        if st.session_state.get("team_qr_open") == team_sel:
            st.divider()
            st.markdown("### 📱 QR accesso caposquadra")

            base_url = (st.session_state.get("BASE_URL") or "").strip().rstrip("/")
            token = st.session_state.squadre[team_sel].get("token", "")

            if not base_url.startswith("http"):
                st.warning("⚠️ Imposta l'URL base: https://…streamlit.app")
            else:
                link = f"{base_url}/?mode=campo&team={team_sel}&token={token}"
                st.code(link, language="text")
                png = qr_png_bytes(link)
                st.image(png, width=230)
                st.download_button(
                    "⬇️ Scarica QR (PNG)",
                    data=png,
                    file_name=f"QR_{team_sel.replace(' ', '_')}.png",
                    mime="image/png",
                    key=f"dlqr_{team_sel}",
                )

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
                st.session_state.squadre[nome] = {
                    "stato": "In attesa al COC",
                    "capo": (capo or "").strip(),
                    "tel": (tel or "").strip(),
                    "token": token,
                }
                save_data_to_disk()
                st.session_state.team_qr_open = nome
                st.success("✅ Squadra creata! (QR aperto)")
                st.rerun()

        st.divider()
        st.markdown("## 🌐 URL APP (per QR)")
        st.caption("Se hai streamlit-js-eval si compila da solo; altrimenti incolla l'URL.")
        st.session_state.BASE_URL = st.text_input(
            "Base URL Streamlit Cloud",
            value=(st.session_state.get("BASE_URL") or ""),
            placeholder="https://nome-app.streamlit.app",
            help="URL della tua app pubblicata (serve per generare i QR)."
        ).strip()

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
badge_ruolo = "MODULO CAPOSQUADRA" if st.session_state.get("field_ok") else ruolo

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
  <div class="pc-badge">📡 {badge_ruolo}</div>
</div>
""",
    unsafe_allow_html=True,
)

# =========================
# MODULO CAPOSQUADRA
# =========================
if badge_ruolo == "MODULO CAPOSQUADRA":
    st.markdown("<div class='pc-card'>", unsafe_allow_html=True)
    st.subheader("📱 Modulo da campo")

    if st.session_state.get("field_ok"):
        sq_c = st.session_state.get("field_team")
        st.info(f"🔒 Accesso campo abilitato per: **{sq_c}**")
    else:
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

save_data_to_disk()
st.markdown("</div>", unsafe_allow_html=True)

# =========================
# TABS
# =========================
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
        # =========================
        # NATO – Convertitore (solo sala radio)
        # =========================
        st.markdown("<div class='nato-title'>📻 Alfabeto NATO – convertitore</div>", unsafe_allow_html=True)

        mode = st.radio(
            "Modalità:",
            ["Testo → NATO", "NATO → Frase"],
            horizontal=True,
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

    meta = {
        "ev_data": str(st.session_state.ev_data),
        "ev_tipo": st.session_state.ev_tipo,
        "ev_nome": st.session_state.ev_nome,
        "ev_desc": st.session_state.ev_desc,
        "op_name": st.session_state.op_name,
    }

    html_bytes = make_html_report_bytes(
        squads=st.session_state.squadre,
        brogliaccio=st.session_state.brogliaccio,
        center=st.session_state.pos_mappa,
        meta=meta,
    )

    st.download_button(
        "⬇️ Scarica REPORT HTML (mappa stampabile + selettore)",
        data=html_bytes,
        file_name="report_radio_manager.html",
        mime="text/html",
    )

    st.caption("Apri l'HTML → scegli squadra → scegli modalità mappa (Ultime/Tutti/Percorso) → STAMPA con/senza mappa.")
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
