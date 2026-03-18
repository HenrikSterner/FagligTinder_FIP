import os
import sys

import pandas as pd
import streamlit as st

from db_sqlite import execute as db_execute
from db_sqlite import fetchall as db_fetchall
from db_sqlite import fetchone as db_fetchone
from db_sqlite import init_db
from db_sqlite import is_mysql
from db_sqlite import is_postgres

APP_TITLE = "KBH FIP"


def console_log(message: str):
    print(f"[FagligTinder] {message}", file=sys.stdout, flush=True)

st.set_page_config(page_title=APP_TITLE, layout="centered")

@st.cache_resource(show_spinner=False)
def ensure_db_ready():
    console_log("init_db start")
    init_db()
    console_log("init_db done")
    return True


def invalidate_user_related_caches(user_id: int | None = None):
    if user_id is not None:
        my_votes.clear(user_id)
        count_choices.clear(user_id)

    # A vote can affect multiple users' matches, so clear this cache function-wide.
    matches_for_user.clear()


def invalidate_problem_related_caches():
    list_problems.clear()


def invalidate_problem_overview_caches():
    fetch_problem_overview_rows.clear()
    fetch_table_counts.clear()


def invalidate_user_overview_caches():
    fetch_user_overview_rows.clear()
    fetch_all_users.clear()


def invalidate_vote_overview_caches():
    fetch_problem_overview_rows.clear()
    fetch_user_overview_rows.clear()
    fetch_table_counts.clear()
    fetch_user_network_edges.clear()
    fetch_all_users.clear()
    fetch_vote_links.clear()


def invalidate_after_user_create():
    invalidate_user_overview_caches()
    fetch_table_counts.clear()


def invalidate_after_problem_create():
    invalidate_problem_related_caches()
    invalidate_problem_overview_caches()


def invalidate_after_vote_change(user_id: int):
    invalidate_user_related_caches(user_id)
    invalidate_vote_overview_caches()


ensure_db_ready()
console_log(
    f"app started title='{APP_TITLE}' backend="
    f"{'mysql' if is_mysql() else 'postgres' if is_postgres() else 'sqlite'}"
)

# -------------------------
# App helpers
# -------------------------
def ensure_user_strict(navn: str) -> int:
    """Create-only. If name exists, raise ValueError."""
    navn = navn.strip()
    console_log(f"ensure_user_strict called with navn='{navn}'")
    if not navn:
        raise ValueError("Indtast et brugernavn")

    row = db_fetchone("SELECT id FROM Users WHERE navn = ?", (navn,))
    if row:
        raise ValueError("Brugernavnet er optaget. Indtast et andet brugernavn")

    try:
        user_id = db_execute("INSERT INTO Users (navn) VALUES (?) RETURNING id", (navn,))
        console_log(f"user created id={user_id} navn='{navn}'")
        invalidate_after_user_create()
        return int(user_id)
    except Exception as e:
        console_log(f"user create failed navn='{navn}' error={e}")
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg:
            raise ValueError("Brugernavnet er optaget. Indtast et andet brugernavn")
        raise

@st.cache_data(ttl=30, show_spinner=False)
def list_problems():
    return db_fetchall(
        "SELECT p.id, p.tekst, p.userId AS user_id, u.navn AS oprettet_af "
        "FROM Problem p LEFT JOIN Users u ON u.id = p.userId "
        "ORDER BY p.id DESC"
    )

def create_problem(user_id: int, tekst: str) -> int:
    tekst = tekst.strip()
    pid = int(db_execute("INSERT INTO Problem (tekst, userId) VALUES (?, ?) RETURNING id", (tekst, user_id)))
    invalidate_after_problem_create()
    return pid

def vote_yes(user_id: int, problem_id: int):
    try:
        db_execute(
            "INSERT INTO Vote (problemId, userId) VALUES (?, ?)",
            (problem_id, user_id),
        )
        invalidate_after_vote_change(user_id)
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
    invalidate_after_vote_change(user_id)


def has_voted_db(user_id: int, problem_id: int) -> bool:
    row = db_fetchone(
        "SELECT 1 FROM Vote WHERE problemId=? AND userId=? LIMIT 1",
        (problem_id, user_id),
    )
    return row is not None


@st.cache_data(ttl=30, show_spinner=False)
def my_votes(user_id: int):
    return db_fetchall(
        "SELECT DISTINCT v.problemId AS problem_id, p.tekst "
        "FROM Vote v JOIN Problem p ON p.id = v.problemId "
        "WHERE v.userId = ? "
        "ORDER BY v.problemId DESC",
        (user_id,),
    )

@st.cache_data(ttl=30, show_spinner=False)
def count_choices(user_id: int) -> int:
    row = db_fetchone(
        "SELECT COUNT(DISTINCT problemId) AS c FROM Vote WHERE userId = ?",
        (user_id,)
    )
    return int(row["c"] or 0)

@st.cache_data(ttl=30, show_spinner=False)
def matches_for_user(user_id: int):
    return db_fetchall(
        """
        SELECT
                    p.id AS problem_id,
                    p.tekst AS problem_tekst,
                    u2.id AS other_user_id,
                    u2.navn AS other_navn
        FROM Vote v_me
        JOIN Problem p ON p.id = v_me.problemId
        JOIN Vote v_other ON v_other.problemId = v_me.problemId AND v_other.userId <> v_me.userId
        JOIN Users u2 ON u2.id = v_other.userId
        WHERE v_me.userId = ?
        ORDER BY p.id DESC, u2.navn
        """,
        (user_id,),
    )


@st.cache_data(ttl=60, show_spinner=False)
def fetch_problem_overview_rows():
    if is_postgres():
        return db_fetchall(
            """
            SELECT
                p.id AS problem_id,
                p.tekst AS udfordring,
                COALESCE(v_count.antal_valg, 0) AS antal_valg,
                COALESCE(v_names.valgt_af, '') AS valgt_af
            FROM Problem p
            LEFT JOIN (
                SELECT v.problemId, COUNT(DISTINCT v.userId) AS antal_valg
                FROM Vote v
                GROUP BY v.problemId
            ) v_count ON v_count.problemId = p.id
            LEFT JOIN (
                SELECT x.problemId, STRING_AGG(x.navn, ', ' ORDER BY x.navn) AS valgt_af
                FROM (
                    SELECT DISTINCT v.problemId, u.navn
                    FROM Vote v
                    JOIN Users u ON u.id = v.userId
                ) x
                GROUP BY x.problemId
            ) v_names ON v_names.problemId = p.id
            ORDER BY p.id ASC
            """
        )

    if is_mysql():
        return db_fetchall(
            """
            SELECT
                p.id AS problem_id,
                p.tekst AS udfordring,
                COALESCE(v_count.antal_valg, 0) AS antal_valg,
                COALESCE(v_names.valgt_af, '') AS valgt_af
            FROM Problem p
            LEFT JOIN (
                SELECT v.problemId, COUNT(DISTINCT v.userId) AS antal_valg
                FROM Vote v
                GROUP BY v.problemId
            ) v_count ON v_count.problemId = p.id
            LEFT JOIN (
                SELECT x.problemId, GROUP_CONCAT(x.navn ORDER BY x.navn SEPARATOR ', ') AS valgt_af
                FROM (
                    SELECT DISTINCT v.problemId, u.navn
                    FROM Vote v
                    JOIN Users u ON u.id = v.userId
                ) x
                GROUP BY x.problemId
            ) v_names ON v_names.problemId = p.id
            ORDER BY p.id ASC
            """
        )

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
        ORDER BY p.id ASC
        """
    )


@st.cache_data(ttl=60, show_spinner=False)
def fetch_user_overview_rows():
    if is_postgres():
        return db_fetchall(
            """
            SELECT
                u.id AS user_id,
                u.navn AS bruger,
                COALESCE(v_count.antal_valg, 0) AS antal_valg,
                COALESCE(v_picks.valgte_udfordringer, '') AS valgte_udfordringer
            FROM Users u
            LEFT JOIN (
                SELECT v.userId, COUNT(DISTINCT v.problemId) AS antal_valg
                FROM Vote v
                GROUP BY v.userId
            ) v_count ON v_count.userId = u.id
            LEFT JOIN (
                SELECT
                    x.userId,
                    STRING_AGG(x.problem_txt, ' | ' ORDER BY x.problem_id) AS valgte_udfordringer
                FROM (
                    SELECT DISTINCT
                        v.userId,
                        p.id AS problem_id,
                        ('#' || p.id::text || ' ' || p.tekst) AS problem_txt
                    FROM Vote v
                    JOIN Problem p ON p.id = v.problemId
                ) x
                GROUP BY x.userId
            ) v_picks ON v_picks.userId = u.id
            ORDER BY LOWER(u.navn)
            """
        )

    if is_mysql():
        return db_fetchall(
            """
            SELECT
                u.id AS user_id,
                u.navn AS bruger,
                COALESCE(v_count.antal_valg, 0) AS antal_valg,
                COALESCE(v_picks.valgte_udfordringer, '') AS valgte_udfordringer
            FROM Users u
            LEFT JOIN (
                SELECT v.userId, COUNT(DISTINCT v.problemId) AS antal_valg
                FROM Vote v
                GROUP BY v.userId
            ) v_count ON v_count.userId = u.id
            LEFT JOIN (
                SELECT
                    x.userId,
                    GROUP_CONCAT(x.problem_txt ORDER BY x.problem_id SEPARATOR ' | ') AS valgte_udfordringer
                FROM (
                    SELECT DISTINCT
                        v.userId,
                        p.id AS problem_id,
                        CONCAT('#', p.id, ' ', p.tekst) AS problem_txt
                    FROM Vote v
                    JOIN Problem p ON p.id = v.problemId
                ) x
                GROUP BY x.userId
            ) v_picks ON v_picks.userId = u.id
            ORDER BY LOWER(u.navn)
            """
        )

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
        ORDER BY u.navn COLLATE NOCASE
        """
    )


@st.cache_data(ttl=60, show_spinner=False)
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


@st.cache_data(ttl=60, show_spinner=False)
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


@st.cache_data(ttl=60, show_spinner=False)
def fetch_all_users():
    return db_fetchall(
        """
        SELECT
            u.id,
            u.navn,
            COUNT(DISTINCT v.problemId) AS vote_count
        FROM Users u
        LEFT JOIN Vote v ON v.userId = u.id
        GROUP BY u.id, u.navn
        ORDER BY LOWER(u.navn)
        """
    )


@st.cache_data(ttl=60, show_spinner=False)
def fetch_vote_links():
    return db_fetchall(
        """
        SELECT
            u.id AS user_id,
            u.navn AS bruger,
            p.id AS problem_id,
            p.tekst AS udfordring
        FROM Vote v
        JOIN Users u ON u.id = v.userId
        JOIN Problem p ON p.id = v.problemId
        ORDER BY LOWER(u.navn), p.id
        """
    )


def _dot_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _short_problem_label(text: str, limit: int = 28) -> str:
    text = str(text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


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


def build_bipartite_dot(user_rows, problem_rows, vote_links):
    lines = [
        "digraph G {",
        "  rankdir=LR;",
        "  graph [overlap=false, splines=true, nodesep=0.5, ranksep=1.2];",
        "  node [fontname=\"Helvetica\", style=filled];",
        "  edge [color=\"#9b7a52\"];",
        "  { rank=same;",
    ]

    for user in user_rows:
        uid = int(user["user_id"])
        label = _dot_escape(str(user["bruger"]))
        lines.append(
            f'    u{uid} [label="{label}", shape=ellipse, fillcolor="#efd1a8", color="#8B4513", fontcolor="#2c1d10"];'
        )

    lines.append("  }")
    lines.append("  { rank=same;")

    for problem in problem_rows:
        pid = int(problem["problem_id"])
        text = _short_problem_label(problem["udfordring"])
        label = _dot_escape(f"#{pid} {text}")
        lines.append(
            f'    p{pid} [label="{label}", shape=box, fillcolor="#f7ead0", color="#a8612f", fontcolor="#2c1d10"];'
        )

    lines.append("  }")

    for link in vote_links:
        uid = int(link["user_id"])
        pid = int(link["problem_id"])
        lines.append(f"  u{uid} -> p{pid};")

    lines.append("}")
    return "\n".join(lines)


def build_heatmap_dataframe(user_rows, problem_rows, vote_links):
    user_labels = [str(row["bruger"]) for row in user_rows]
    problem_labels = {int(row["problem_id"]): f"#{row['problem_id']}" for row in problem_rows}

    if not user_labels or not problem_labels:
        return pd.DataFrame()

    matrix = pd.DataFrame(
        0,
        index=user_labels,
        columns=[problem_labels[int(row["problem_id"])] for row in problem_rows],
        dtype=int,
    )

    user_name_by_id = {int(row["user_id"]): str(row["bruger"]) for row in user_rows}
    for link in vote_links:
        user_name = user_name_by_id.get(int(link["user_id"]))
        problem_label = problem_labels.get(int(link["problem_id"]))
        if user_name and problem_label:
            matrix.loc[user_name, problem_label] = 1

    return matrix


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
st.title(APP_TITLE)

st.session_state.setdefault("user_id", None)
st.session_state.setdefault("user_name", "")
st.session_state.setdefault("voted_problem_ids", set())  # session-only guard
st.session_state.setdefault("just_created_problem_id", None)
st.session_state.setdefault("busy_vote_pid", None)
st.session_state.setdefault("busy_vote_action", None)   # "yes" eller "undo"
st.session_state.setdefault("vote_busy", False)
st.session_state.setdefault("vote_form_seed", None)
st.session_state.setdefault("vote_selected_problem_id", None)

MAX_CHOICES = 1

active_page = st.radio(
    "Side",
    ["Udfordringer", "Matches", "Oversigt"],
    horizontal=True,
    label_visibility="collapsed",
)

# -------------------------
# SIDE 1: Udfordringer
# -------------------------
if active_page == "Udfordringer":
    if not st.session_state["user_id"]:
        st.subheader("Opret brugernavn")
        st.write("Når du er oprettet, bliver du præsenteret for de udfordringer der allerede findes.")

        with st.form("create_user_form"):
            name = st.text_input("Brugernavn", value=st.session_state["user_name"], placeholder="Fx Kathrine")
            submitted = st.form_submit_button("Opret", type="primary")

        if submitted:
            console_log(f"create_user_form submitted navn='{name.strip()}'")
            with st.spinner("Opretter bruger..."):
                try:
                    uid = ensure_user_strict(name)
                    st.session_state["user_id"] = uid
                    st.session_state["user_name"] = name.strip()
                    st.success(f"Bruger oprettet: {name.strip()} (id {uid})")
                    console_log(f"create_user_form success id={uid} navn='{name.strip()}'")
                    st.rerun()
                except ValueError as e:
                    console_log(f"create_user_form warning navn='{name.strip()}' warning={e}")
                    st.warning(str(e))
                except Exception as e:
                    console_log(f"create_user_form error navn='{name.strip()}' error={e}")
                    st.error(f"Kunne ikke oprette bruger: {e}")
    else:
        # --- Status / begrænsning ---
        used = count_choices(st.session_state["user_id"])
        limit_reached = used >= MAX_CHOICES

        with st.sidebar:
            st.subheader("Status")
            st.metric("Valg brugt", f"{used}/{MAX_CHOICES}")
            if limit_reached:
                st.info("Du har valgt en udfordring, men du kan stadig ændre dit valg.")
            else:
                st.success("Du kan vælge en udfordring.")

        st.subheader(f"Velkommen {st.session_state['user_name']} ")
        st.write("Vælg den udfordring du gerne vil tale om, og klik derefter **Gem valg**.")

        if st.session_state.get("just_created_problem_id") is not None:
            st.success(f"Udfordring oprettet (#{st.session_state['just_created_problem_id']}).")
            st.session_state["just_created_problem_id"] = None

        # --- Liste over udfordringer ---
        try:
            problems = list_problems()
            existing_votes = my_votes(st.session_state["user_id"])
        except Exception as e:
            st.error(f"Kunne ikke hente udfordringer: {e}")
            problems = []
            existing_votes = []

        problem_filter = st.selectbox(
            "Vis udfordringer",
            ["Alle", "Kun andres", "Kun mine"],
            index=1,
        )
        if problem_filter == "Kun andres":
            problems = [p for p in problems if p.get("user_id") != st.session_state["user_id"]]
        elif problem_filter == "Kun mine":
            problems = [p for p in problems if p.get("user_id") == st.session_state["user_id"]]

        if not problems:
            st.info("Ingen udfordringer endnu.")
        else:
                  
            # beregn én gang
            existing_ids = {int(v["problem_id"]) for v in existing_votes}
            visible_ids = {int(p["id"]) for p in problems}
            current_selected_id = next(iter(sorted(existing_ids)), None)
            vote_form_seed = (
                st.session_state["user_id"],
                current_selected_id,
                tuple(sorted(visible_ids)),
            )

            if st.session_state.get("vote_form_seed") != vote_form_seed:
                st.session_state["vote_selected_problem_id"] = (
                    current_selected_id if current_selected_id in visible_ids else None
                )
                st.session_state["vote_form_seed"] = vote_form_seed

            with st.form("vote_form"):
                st.caption("Du kan kun vælge én udfordring ad gangen.")

                if current_selected_id is not None and current_selected_id not in visible_ids:
                    st.info("Dit nuværende valg er skjult af filtret. Vælg en synlig udfordring for at skifte.")

                option_ids = [None] + [int(p["id"]) for p in problems]
                labels_by_id = {}
                for p in problems:
                    pid = int(p["id"])
                    oprettet_af = p.get("oprettet_af") or "ukendt"
                    labels_by_id[pid] = f"#{pid} - {p['tekst']} (oprettet af: {oprettet_af})"

                st.radio(
                    "Udfordring",
                    options=option_ids,
                    key="vote_selected_problem_id",
                    format_func=lambda pid: "Ingen valgt" if pid is None else labels_by_id.get(pid, str(pid)),
                )

                submitted = st.form_submit_button("Gem valg", type="primary")

            if submitted:
                hidden_existing_ids = existing_ids - visible_ids
                selected_visible_id = st.session_state.get("vote_selected_problem_id")

                if selected_visible_id is not None:
                    desired_ids = {int(selected_visible_id)}
                elif problem_filter == "Alle":
                    desired_ids = set()
                else:
                    desired_ids = set(hidden_existing_ids)

                to_add = desired_ids - existing_ids
                to_remove = existing_ids - desired_ids

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
        mv = existing_votes

        if not mv:
            st.write("Du har ikke valgt endnu.")
        else:
            for row in mv:
                st.write(f"• **#{row['problem_id']}** — {row['tekst']}")

        # --- Opret egen udfordring nederst ---
        st.divider()
        st.subheader("Kan du ikke finde en lignende? Opret din egen")

        max_len = 280
        with st.form("create_problem_form", clear_on_submit=True):
            tekst = st.text_input("Din udfordring")
            submit_problem = st.form_submit_button("Indsend udfordring", type="primary")

        if submit_problem:
            candidate = tekst.strip()
            if not candidate:
                st.warning("Skriv en udfordring foerst.")
            elif len(candidate) > max_len:
                st.warning(f"Din udfordring er for lang (max {max_len} tegn).")
            else:
                with st.spinner("Opretter udfordring..."):
                    try:
                        pid = create_problem(st.session_state["user_id"], candidate)
                        st.session_state["just_created_problem_id"] = pid
                        st.rerun()
                    except Exception as e:
                        st.error(f"Kunne ikke oprette udfordring: {e}")
# -------------------------
# SIDE 2: Matches
# -------------------------
elif active_page == "Matches":
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
                pid = int(r["problem_id"])
                by_problem.setdefault(pid, {"tekst": r["problem_tekst"], "people": []})
                by_problem[pid]["people"].append(r["other_navn"])

            for pid, info in by_problem.items():
                with st.expander(f"#{pid} — {info['tekst']}", expanded=True):
                    uniq_people = sorted(set(info["people"]))
                    st.write("**Andre der har stemt ja:**")
                    st.write(", ".join(uniq_people))

# -------------------------
# SIDE 3: Oversigt
# -------------------------
else:
    st.subheader("Oversigt")
    st.write("Overblik over udfordringer, stemmer og brugernes valg.")

    try:
        problem_rows = fetch_problem_overview_rows()
        user_rows = fetch_user_overview_rows()
        counts = fetch_table_counts()
        vote_links = fetch_vote_links()
    except Exception as e:
        st.error(f"Kunne ikke hente oversigt: {e}")
        st.stop()

    st.markdown("**Hurtigt overblik over udfordringer**")
    if not problem_rows:
        st.info("Ingen udfordringer i databasen endnu.")
    else:
        for row in problem_rows:
            valgt_af = row.get("valgt_af") or "Ingen endnu"
            st.write(f"**#{row['problem_id']} - {row['udfordring']}**")
            st.write(f"Valgt af: {valgt_af}")

    st.divider()
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
    st.markdown("**Bipartite graf: brugere og udfordringer**")
    if not user_rows or not problem_rows:
        st.info("Der skal være både brugere og udfordringer for at vise grafen.")
    elif not vote_links:
        st.info("Der er endnu ingen stemmer at tegne relationer ud fra.")
    else:
        bipartite_dot = build_bipartite_dot(user_rows, problem_rows, vote_links)
        st.graphviz_chart(bipartite_dot, use_container_width=True)

    st.divider()
    st.markdown("**Heatmap over valg**")
    if not user_rows or not problem_rows:
        st.info("Der skal være både brugere og udfordringer for at vise heatmap.")
    else:
        heatmap_df = build_heatmap_dataframe(user_rows, problem_rows, vote_links)
        if heatmap_df.empty:
            st.info("Ingen data at vise i heatmap endnu.")
        else:
            st.caption("Rækker er brugere. Kolonner er udfordringer. 1 betyder valgt.")
            st.dataframe(
                heatmap_df.style.background_gradient(cmap="YlOrBr", axis=None),
                use_container_width=True,
            )

    st.divider()
    st.markdown("**Netvaerksgraf over brugerrelationer**")
    st.caption("Kant vaegt = antal faelles udfordringer, som to brugere begge har valgt.")
    show_network_graph = st.checkbox("Vis netvaerksgraf", value=False)

    if show_network_graph:
        try:
            users = fetch_all_users()
            network_edges = fetch_user_network_edges()
        except Exception as e:
            st.error(f"Kunne ikke hente netvaerksgraf: {e}")
        else:
            if len(users) < 2:
                st.info("Der skal vaere mindst 2 brugere for at vise netvaerksgrafen.")
            elif not network_edges:
                st.info("Der er endnu ingen faelles valg mellem brugere.")
            else:
                dot = build_user_network_dot(users, network_edges)
                st.graphviz_chart(dot, use_container_width=True)
