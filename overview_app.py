import streamlit as st
import streamlit.components.v1 as components

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


def fetch_problem_overview_rows():
		sql = """
		SELECT
			p.id AS problem_id,
			p.tekst AS udfordring,
			COALESCE((
				SELECT COUNT(DISTINCT v.userId)
				FROM Vote v
				WHERE v.problemId = p.id
			), 0) AS antal_valg,
			COALESCE((
				SELECT GROUP_CONCAT(navn, ', ')
				FROM (
					SELECT DISTINCT u2.navn AS navn
					FROM Vote v
					JOIN Users u2 ON u2.id = v.userId
					WHERE v.problemId = p.id
					ORDER BY u2.navn COLLATE NOCASE
				)
			), '') AS valgt_af
		FROM Problem p
		ORDER BY p.id ASC;
		"""
		return fetchall(sql)


def fetch_user_overview_rows():
		sql = """
		SELECT
			u.id AS user_id,
			u.navn AS bruger,
			COALESCE((
				SELECT COUNT(DISTINCT v.problemId)
				FROM Vote v
				WHERE v.userId = u.id
			), 0) AS antal_valg,
			COALESCE((
				SELECT GROUP_CONCAT(problem_txt, ' | ')
				FROM (
					SELECT DISTINCT printf('#%d %s', p.id, p.tekst) AS problem_txt
					FROM Vote v
					JOIN Problem p ON p.id = v.problemId
					WHERE v.userId = u.id
					ORDER BY p.id
				)
			), '') AS valgte_udfordringer
		FROM Users u
		ORDER BY u.navn COLLATE NOCASE;
		"""
		return fetchall(sql)


def fetch_table_counts():
		row = fetchall(
				"""
				SELECT
					(SELECT COUNT(*) FROM Users) AS users_count,
					(SELECT COUNT(*) FROM Problem) AS problem_count,
					(SELECT COUNT(*) FROM Vote) AS vote_count
				"""
		)
		if not row:
				return {"users_count": 0, "problem_count": 0, "vote_count": 0}
		return row[0]


st.title("Oversigt")

refresh_seconds = 60
components.html(f"<meta http-equiv='refresh' content='{refresh_seconds}'>", height=0)

try:
		problem_rows = fetch_problem_overview_rows()
		user_rows = fetch_user_overview_rows()
		counts = fetch_table_counts()
except Exception as e:
		st.error(f"Kunne ikke hente data: {e}")
		st.stop()

st.subheader("Debug")
c1, c2, c3 = st.columns(3)
c1.metric("Users", int(counts.get("users_count", 0)))
c2.metric("Problem", int(counts.get("problem_count", 0)))
c3.metric("Vote", int(counts.get("vote_count", 0)))

st.divider()

st.subheader("Udfordringer og stemmer")
if not problem_rows:
		st.info("Ingen udfordringer i databasen endnu.")
else:
		st.dataframe(problem_rows, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Brugere og deres valg")
if not user_rows:
		st.info("Ingen brugere i databasen endnu.")
else:
		st.dataframe(user_rows, use_container_width=True, hide_index=True)

st.caption(f"Opdaterer automatisk hver {refresh_seconds} sek.")
