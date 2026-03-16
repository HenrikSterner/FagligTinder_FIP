import streamlit as st
import streamlit.components.v1 as components
import html

from db_sqlite import fetchall, init_db

st.set_page_config(layout="wide")
init_db()

# Skjul Streamlit top bar + footer
hide_streamlit_style = """
    <style>
        header {visibility: hidden;}
        footer {visibility: hidden;}
        #MainMenu {visibility: hidden;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

def fetch_overview_rows():
    sql = """
    SELECT
        p.id AS problem_id,
        p.tekst AS udfordring,
        COALESCE((
            SELECT GROUP_CONCAT(navn, ', ')
            FROM (
                SELECT DISTINCT
                    u2.navn AS navn,
                    CASE WHEN u2.id = p.userId THEN 0 ELSE 1 END AS sort_creator
                FROM Vote v
                JOIN Users u2 ON u2.id = v.userId
                WHERE v.problemId = p.id
                ORDER BY sort_creator, navn COLLATE NOCASE
            )
        ), '') AS valgt_af
    FROM Problem p
    ORDER BY p.id ASC;
    """
    return fetchall(sql)

# -------------------------
# UI
# -------------------------
st.title("Oversigt: Udfordringer og hvem der har valgt dem")

refresh_seconds = 60
components.html(f"<meta http-equiv='refresh' content='{refresh_seconds}'>", height=0)

try:
    rows = fetch_overview_rows()
except Exception as e:
    st.error(f"Kunne ikke hente data: {e}")
    st.stop()

# Byg HTML-rækker
rows_html = ""
for r in rows:
    udf = f"{r['problem_id']}. {r['udfordring']}"
    valgt = r["valgt_af"] or ""
    rows_html += (
        "<tr>"
        f"<td class='udf'>{html.escape(udf)}</td>"
        f"<td class='valg'>{html.escape(valgt)}</td>"
        "</tr>"
    )

# Hele tabellen som HTML (stor tekst, 2 kolonner)
table_html = f"""
<style>
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 24px;
    table-layout: fixed;
  }}
  th {{
    text-align: left;
    font-size: 24px;
    padding: 12px 14px;
    border-bottom: 3px solid #ddd;
    background: #f5f5f5;
  }}
  td {{
    padding: 10px 14px;
    border-bottom: 1px solid #eee;
    vertical-align: top;
    word-wrap: break-word;
    overflow-wrap: anywhere;
  }}
  .udf {{ width: 65%; }}
  .valg {{ width: 35%; }}
</style>

<table>
  <thead>
    <tr>
      <th>Udfordring</th>
      <th>Valgt af</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>
"""

# RENDER HTML korrekt (ikke som tekst)
components.html(table_html, height=2200, scrolling=True)

st.caption(f"Opdaterer automatisk hver {refresh_seconds} sek.")