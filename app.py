import streamlit as st
import sqlite3

import time

from db_sqlite import execute as db_execute
from db_sqlite import fetchall as db_fetchall
from db_sqlite import fetchone as db_fetchone
from db_sqlite import init_db

st.set_page_config(page_title="Faglig Tinder", layout="centered")

st.write("VERSION:", "2026-02-28-TEST")
st.write("FILE:", __file__)
st.write("TIME:", time.time())

init_db()

# -------------------------
# App helpers
# -------------------------
def ensure_user_strict(navn: str) -> int:
    """Create-only. If name exists, raise ValueError."""
    navn = navn.strip()
    if not navn:
        raise ValueError("Indtast et brugernavn")

    row = db_fetchone("SELECT id FROM Users WHERE navn = ?", (navn,))
    if row:
        raise ValueError("Brugernavnet er optaget. Indtast et andet brugernavn")

    try:
        user_id = db_execute("INSERT INTO Users (navn) VALUES (?)", (navn,))
        return int(user_id)
    except sqlite3.IntegrityError:
        raise ValueError("Brugernavnet er optaget. Indtast et andet brugernavn")

def list_problems():
    return db_fetchall(
        "SELECT p.id, p.tekst, p.userId, u.navn AS oprettet_af "
        "FROM Problem p LEFT JOIN Users u ON u.id = p.userId "
        "ORDER BY p.id DESC"
    )

def create_problem(user_id: int, tekst: str) -> int:
    tekst = tekst.strip()
    pid = int(db_execute("INSERT INTO Problem (tekst, userId) VALUES (?, ?)", (tekst, user_id)))
    return pid

def vote_yes(user_id: int, problem_id: int):
    try:
        db_execute(
            "INSERT INTO Vote (problemId, userId) VALUES (?, ?)",
            (problem_id, user_id),
        )
    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg:
            return
        raise

def vote_remove(user_id: int, problem_id: int):
    db_execute(
        "DELETE FROM Vote WHERE problemId = ? AND userId = ?",
        (problem_id, user_id),
    )
def has_voted_db(user_id: int, problem_id: int) -> bool:
    row = db_fetchone(
        "SELECT 1 FROM Vote WHERE problemId=? AND userId=? LIMIT 1",
        (problem_id, user_id),
    )
    return row is not None


def my_votes(user_id: int):
    return db_fetchall(
        "SELECT DISTINCT v.problemId, p.tekst "
        "FROM Vote v JOIN Problem p ON p.id = v.problemId "
        "WHERE v.userId = ? "
        "ORDER BY v.problemId DESC",
        (user_id,),
    )

def count_choices(user_id: int) -> int:
    row = db_fetchone(
        "SELECT COUNT(DISTINCT problemId) AS c FROM Vote WHERE userId = ?",
        (user_id,)
    )
    return int(row["c"] or 0)

def matches_for_user(user_id: int):
    return db_fetchall(
        """
        SELECT
          p.id AS problemId,
          p.tekst AS problemTekst,
          u2.id AS otherUserId,
          u2.navn AS otherNavn
        FROM Vote v_me
        JOIN Problem p ON p.id = v_me.problemId
        JOIN Vote v_other ON v_other.problemId = v_me.problemId AND v_other.userId <> v_me.userId
        JOIN Users u2 ON u2.id = v_other.userId
        WHERE v_me.userId = ?
        ORDER BY p.id DESC, u2.navn
        """,
        (user_id,),
    )


def fetch_problem_overview_rows():
        return db_fetchall(
                """
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
        )


def fetch_user_overview_rows():
        return db_fetchall(
                """
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
        )


def fetch_table_counts():
        row = db_fetchone(
                """
                SELECT
                    (SELECT COUNT(*) FROM Users) AS users_count,
                    (SELECT COUNT(*) FROM Problem) AS problem_count,
                    (SELECT COUNT(*) FROM Vote) AS vote_count
                """
        )
        if not row:
                return {"users_count": 0, "problem_count": 0, "vote_count": 0}
        return row


def fetch_user_network_edges():
    return db_fetchall(
        """
        SELECT
          u1.id AS source_id,
          u1.navn AS source_name,
          u2.id AS target_id,
          u2.navn AS target_name,
          COUNT(DISTINCT v1.problemId) AS shared_count
        FROM Vote v1
        JOIN Vote v2
          ON v1.problemId = v2.problemId
         AND v1.userId < v2.userId
        JOIN Users u1 ON u1.id = v1.userId
        JOIN Users u2 ON u2.id = v2.userId
        GROUP BY u1.id, u1.navn, u2.id, u2.navn
        ORDER BY shared_count DESC, u1.navn, u2.navn
        """
    )


def fetch_all_users():
    return db_fetchall(
        """
                SELECT
                    u.id,
                    u.navn,
                    COALESCE((
                        SELECT COUNT(DISTINCT v.problemId)
                        FROM Vote v
                        WHERE v.userId = u.id
                    ), 0) AS vote_count
        FROM Users
        ORDER BY navn COLLATE NOCASE
        """
    )


def _dot_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _color_for_votes(vote_count: int, max_votes: int) -> str:
    # Warm beige -> brown gradient used by the rest of the UI.
    if max_votes <= 0:
        return "#f7ead0"
    ratio = max(0.0, min(1.0, vote_count / max_votes))
    if ratio < 0.2:
        return "#f7ead0"
    if ratio < 0.4:
        return "#efd1a8"
    if ratio < 0.6:
        return "#dfb07b"
    if ratio < 0.8:
        return "#c9874d"
    return "#a8612f"


def build_user_network_dot(users, edges):
    max_votes = 0
    for user in users:
        max_votes = max(max_votes, int(user.get("vote_count", 0)))

    lines = [
        "graph G {",
        "  layout=neato;",
        "  overlap=false;",
        "  splines=true;",
        "  node [shape=circle, style=filled, color=\"#8B4513\", fontname=\"Helvetica\", fontcolor=\"#2c1d10\"];",
        "  edge [color=\"#b08a5a\", fontname=\"Helvetica\", fontsize=10];",
    ]

    for user in users:
        uid = int(user["id"])
        label = _dot_escape(str(user["navn"]))
        votes = int(user.get("vote_count", 0))
        fill = _color_for_votes(votes, max_votes)
        width = 0.9 + (1.2 * (votes / max_votes)) if max_votes > 0 else 0.9
        lines.append(
            f'  u{uid} [label="{label}\\n({votes})", fillcolor="{fill}", width={width:.2f}, height={width:.2f}, fixedsize=true];'
        )

    for edge in edges:
        a = int(edge["source_id"])
        b = int(edge["target_id"])
        w = int(edge["shared_count"])
        penwidth = min(1 + w, 8)
        lines.append(f'  u{a} -- u{b} [label="{w}", penwidth={penwidth}];')

    lines.append("}")
    return "\n".join(lines)


def handle_pending_vote():
    pid = st.session_state.get("busy_vote_pid")
    action = st.session_state.get("busy_vote_action")
    user_id = st.session_state.get("user_id")

    if not pid or not action or not user_id:
        return

    st.session_state["vote_busy"] = True

    try:
        if action == "yes":
            vote_yes(user_id, pid)
        elif action == "undo":
            vote_remove(user_id, pid)
    finally:
        st.session_state["busy_vote_pid"] = None
        st.session_state["busy_vote_action"] = None
        st.session_state["vote_busy"] = False
# -------------------------
# UI
# -------------------------
st.title("Faglig Tinder")

st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_name", "")
st.session_state.setdefault("voted_problem_ids", set())  # session-only guard
st.session_state.setdefault("creating_user", False)
st.session_state.setdefault("pending_user_name", "")
st.session_state.setdefault("creating_problem", False)
st.session_state.setdefault("busy_vote_pid", None)
st.session_state.setdefault("busy_vote_action", None)   # "yes" eller "undo"
st.session_state.setdefault("vote_busy", False)

MAX_CHOICES = 2

tab1, tab2, tab3 = st.tabs(["Udfordringer", "Matches", "Oversigt"])

# -------------------------
# TAB 1: Udfordringer
# -------------------------
with tab1:
    if not st.session_state["user_id"]:
        st.subheader("Opret brugernavn")
        st.write("Når du er oprettet, bliver du præsenteret for de udfordringer der allerede findes.")

        name = st.text_input("Brugernavn", value=st.session_state["user_name"], placeholder="Fx Kathrine")

        if st.button("Opret", type="primary", disabled=st.session_state["creating_user"]):
            st.session_state["pending_user_name"] = name.strip()
            st.session_state["creating_user"] = True
            st.rerun()

        if st.session_state["creating_user"] and not st.session_state["user_id"]:
            with st.spinner("Opretter bruger..."):
                try:
                    uid = ensure_user_strict(st.session_state["pending_user_name"])
                    st.session_state["user_id"] = uid
                    st.session_state["user_name"] = st.session_state["pending_user_name"]
                    st.session_state["creating_user"] = False
                    st.rerun()
                except ValueError as e:
                    st.session_state["creating_user"] = False
                    st.warning(str(e))
                except Exception as e:
                    st.session_state["creating_user"] = False
                    st.error(f"Kunne ikke oprette bruger: {e}")
    else:
        # --- Status / begrænsning ---
        used = count_choices(st.session_state["user_id"])
        limit_reached = used >= MAX_CHOICES

        with st.sidebar:
            st.subheader("Status")
            st.metric("Valg brugt", f"{used}/{MAX_CHOICES}")
            if limit_reached:
                st.error("Du har nået maksimum.")
            else:
                st.success("Du kan stadig vælge.")

        st.subheader(f"Velkommen {st.session_state['user_name']} ")
        st.write("Vaelg foerst de udfordringer du gerne vil tale om, og klik derefter **Gem valg**.")
        # --- Liste over udfordringer ---
        try:
            problems = list_problems()
        except Exception as e:
            st.error(f"Kunne ikke hente udfordringer: {e}")
            problems = []

        hide_own = st.checkbox("Skjul mine egne udfordringer", value=True)
        if hide_own:
            problems = [p for p in problems if p.get("userId") != st.session_state["user_id"]]

        if not problems:
            st.info("Ingen udfordringer endnu.")
        else:
                  
            # beregn én gang
            existing_votes = my_votes(st.session_state["user_id"])
            existing_ids = {int(v["problemId"]) for v in existing_votes}
            visible_ids = {int(p["id"]) for p in problems}

            with st.form("vote_form"):
                st.caption(f"Du kan vaelge op til {MAX_CHOICES} udfordringer.")

                for p in problems:
                    pid = int(p["id"])
                    tekst = p["tekst"]
                    oprettet_af = p.get("oprettet_af") or "ukendt"

                    key = f"vote_pick_{st.session_state['user_id']}_{pid}"
                    if key not in st.session_state:
                        st.session_state[key] = pid in existing_ids

                    st.checkbox(
                        f"#{pid} - {tekst} (oprettet af: {oprettet_af})",
                        key=key,
                    )

                submitted = st.form_submit_button("Gem valg", type="primary")

            if submitted:
                selected_visible_ids = {
                    int(p["id"])
                    for p in problems
                    if st.session_state.get(f"vote_pick_{st.session_state['user_id']}_{int(p['id'])}", False)
                }

                if len(selected_visible_ids) > MAX_CHOICES:
                    st.error(f"Du kan maks vaelge {MAX_CHOICES} udfordringer.")
                else:
                    current_visible_ids = existing_ids & visible_ids
                    to_add = selected_visible_ids - current_visible_ids
                    to_remove = current_visible_ids - selected_visible_ids

                    try:
                        for pid in to_add:
                            vote_yes(st.session_state["user_id"], pid)
                        for pid in to_remove:
                            vote_remove(st.session_state["user_id"], pid)
                        st.success("Dine valg er gemt.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Kunne ikke gemme valg: {e}")


        # --- Mine valg ---
        st.divider()
        st.subheader("Mine valg")
        try:
            mv = my_votes(st.session_state["user_id"])
        except Exception as e:
            mv = []
            st.error(f"Kunne ikke hente dine valg: {e}")

        if not mv:
            st.write("Du har ikke stemt ja endnu.")
        else:
            for row in mv:
                st.write(f"• **#{row['problemId']}** — {row['tekst']}")

        # --- Opret egen udfordring nederst ---
        st.divider()
        st.subheader("Kan du ikke finde en lignende? Opret din egen")

        max_len = 280
        tekst = st.text_area("Din udfordring", height=120)

        if st.button("Indsend udfordring", type="primary", disabled=st.session_state["creating_problem"]):
            st.session_state["pending_problem_text"] = tekst.strip()
            st.session_state["creating_problem"] = True
            st.rerun()

        if st.session_state["creating_problem"]:
            with st.spinner("Opretter udfordring..."):
                try:
                    pid = create_problem(st.session_state["user_id"], st.session_state["pending_problem_text"])
                    st.session_state["creating_problem"] = False
                    st.success(f"Udfordring oprettet (#{pid}).")
                    st.rerun()
                except Exception as e:
                    st.session_state["creating_problem"] = False
                    st.error(f"Kunne ikke oprette udfordring: {e}")
# -------------------------
# TAB 2: Matches
# -------------------------
with tab2:
    st.subheader("Matches")
    if not st.session_state["user_id"]:
        st.info("Opret et brugernavn på fanen **Udfordringer** for at se matches.")
    else:
        st.write("Her er personer, der også har stemt ja til de samme udfordringer som dig.")

        try:
            rows = matches_for_user(st.session_state["user_id"])
        except Exception as e:
            rows = []
            st.error(f"Kunne ikke hente matches: {e}")

        if not rows:
            st.info("Ingen matches endnu (eller ingen andre har stemt ja på de samme udfordringer).")
        else:
            by_problem = {}
            for r in rows:
                pid = int(r["problemId"])
                by_problem.setdefault(pid, {"tekst": r["problemTekst"], "people": []})
                by_problem[pid]["people"].append(r["otherNavn"])

            for pid, info in by_problem.items():
                with st.expander(f"#{pid} — {info['tekst']}", expanded=True):
                    uniq_people = sorted(set(info["people"]))
                    st.write("**Andre der har stemt ja:**")
                    st.write(", ".join(uniq_people))

# -------------------------
# TAB 3: Oversigt
# -------------------------
with tab3:
    st.subheader("Oversigt")
    st.write("Overblik over udfordringer, stemmer og brugernes valg.")

    try:
        problem_rows = fetch_problem_overview_rows()
        user_rows = fetch_user_overview_rows()
        counts = fetch_table_counts()
        users = fetch_all_users()
        network_edges = fetch_user_network_edges()
    except Exception as e:
        st.error(f"Kunne ikke hente oversigt: {e}")
        st.stop()

    c1, c2, c3 = st.columns(3)
    c1.metric("Users", int(counts.get("users_count", 0)))
    c2.metric("Problem", int(counts.get("problem_count", 0)))
    c3.metric("Vote", int(counts.get("vote_count", 0)))

    st.divider()
    st.markdown("**Udfordringer og stemmer**")
    if not problem_rows:
        st.info("Ingen udfordringer i databasen endnu.")
    else:
        st.dataframe(problem_rows, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**Brugere og deres valg**")
    if not user_rows:
        st.info("Ingen brugere i databasen endnu.")
    else:
        st.dataframe(user_rows, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**Netvaerksgraf over brugerrelationer**")
    st.caption("Kant vaegt = antal faelles udfordringer, som to brugere begge har valgt.")

    if len(users) < 2:
        st.info("Der skal vaere mindst 2 brugere for at vise netvaerksgrafen.")
    elif not network_edges:
        st.info("Der er endnu ingen faelles valg mellem brugere.")
    else:
        dot = build_user_network_dot(users, network_edges)
        st.graphviz_chart(dot, use_container_width=True)