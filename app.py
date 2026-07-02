"""HITPC Transcript Explorer — Streamlit app over hitpc.db.

Run:  .venv/bin/streamlit run app.py
"""

import re
import sqlite3
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DB = Path(__file__).parent / "hitpc.db"

st.set_page_config(page_title="HITPC Transcript Explorer", layout="wide")

TOPIC_LABELS = {
    "nhin": "NHIN / NwHIN",
    "hie": "HIE / RHIOs",
    "direct": "Direct Project",
    "interoperability": "Interoperability",
    "meaningful_use": "Meaningful Use",
    "privacy_security": "Privacy & Security",
    "certification": "Certification",
    "patient_engagement": "Patient Engagement",
    "info_blocking": "Information Blocking",
    "standards": "Standards",
    "quality_measures": "Quality Measures",
    "epic_mention": "Epic (mentions)",
    "vendor_mention": "Other vendors (mentions)",
}


@st.cache_resource
def get_con():
    return sqlite3.connect(DB, check_same_thread=False)


@st.cache_data
def q(sql, params=()):
    return pd.read_sql_query(sql, get_con(), params=params)


def year_of(date_str):
    return date_str[:4]


# ---------------------------------------------------------------- utterance UI

def show_utterances(df, page_size=25, key="utt"):
    """Render utterances with speaker, meeting date, text."""
    total = len(df)
    if total == 0:
        st.info("No utterances match.")
        return
    pages = (total - 1) // page_size + 1
    page = st.number_input(
        f"Page (of {pages}, {total} utterances)", 1, pages, 1, key=key + "_pg")
    view = df.iloc[(page - 1) * page_size: page * page_size]
    for _, r in view.iterrows():
        st.markdown(
            f"**{r['name']}** ({r['org']}) — *{r['date']}*  \n{r['text']}")
        st.divider()


# ---------------------------------------------------------------------- pages

def page_overview():
    st.title("HIT Policy Committee — Transcript Explorer")
    m = q("SELECT * FROM meetings ORDER BY date")
    stats = q("""SELECT (SELECT COUNT(*) FROM meetings) meetings,
                        (SELECT COUNT(*) FROM speakers) speakers,
                        (SELECT COUNT(*) FROM utterances) utterances,
                        (SELECT SUM(word_count) FROM utterances) words""")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Meetings", int(stats.meetings[0]))
    c2.metric("Speakers", int(stats.speakers[0]))
    c3.metric("Utterances", f"{int(stats.utterances[0]):,}")
    c4.metric("Words", f"{int(stats.words[0]):,}")

    st.subheader("Meetings over time")
    m["date"] = pd.to_datetime(m["date"])
    chart = alt.Chart(m).mark_bar().encode(
        x=alt.X("date:T", title="Meeting date"),
        y=alt.Y("n_words:Q", title="Words in transcript"),
        tooltip=["date:T", "filename", "n_utterances", "n_words"],
    ).properties(height=250)
    st.altair_chart(chart, width="stretch")

    st.subheader("Most active speakers (words spoken, non-ONC)")
    top = q("""
        SELECT s.name || ' — ' || s.org AS speaker, SUM(u.word_count) words
        FROM utterances u JOIN speakers s ON s.id=u.speaker_id
        WHERE s.is_onc_staff=0 AND s.name != '(unidentified)'
        GROUP BY s.id ORDER BY words DESC LIMIT 20""")
    st.altair_chart(
        alt.Chart(top).mark_bar().encode(
            x=alt.X("words:Q", title="Total words"),
            y=alt.Y("speaker:N", sort="-x", title=None,
                    axis=alt.Axis(labelLimit=320, labelOverlap=False)),
        ).properties(height=26 * len(top)),
        width="stretch")


def page_speakers():
    st.title("Speakers")
    years = q("SELECT DISTINCT substr(date,1,4) y FROM meetings ORDER BY y")["y"].tolist()
    c1, c2 = st.columns([2, 1])
    year = c1.selectbox("Year", ["All"] + years)
    hide_onc = c2.toggle("Hide ONC staff/moderators", value=True)

    where = "WHERE s.name != '(unidentified)'"
    params = []
    if year != "All":
        where += " AND substr(m.date,1,4)=?"
        params.append(year)
    if hide_onc:
        where += " AND s.is_onc_staff=0"

    lb = q(f"""
        SELECT s.id, s.name, s.org, COUNT(*) utterances, SUM(u.word_count) words,
               COUNT(DISTINCT u.meeting_id) meetings
        FROM utterances u
        JOIN speakers s ON s.id=u.speaker_id
        JOIN meetings m ON m.id=u.meeting_id
        {where}
        GROUP BY s.id ORDER BY words DESC LIMIT 100""", params)
    st.dataframe(lb.drop(columns=["id"]), width="stretch", height=350)

    st.subheader("Speaker detail")
    options = lb["name"] + " — " + lb["org"]
    pick = st.selectbox("Choose a speaker", options)
    if pick:
        sid = int(lb.iloc[options.tolist().index(pick)]["id"])
        detail_speaker(sid)


def detail_speaker(sid):
    note = q("""SELECT ss.content FROM speaker_summaries ss
                JOIN speakers s ON s.key = ss.speaker_key WHERE s.id=?""", (sid,))
    if not note.empty:
        with st.expander("Position analysis (LLM synthesis)", expanded=False):
            st.markdown(note.content[0])
    tl = q("""
        SELECT m.date, SUM(u.word_count) words, COUNT(*) utts
        FROM utterances u JOIN meetings m ON m.id=u.meeting_id
        WHERE u.speaker_id=? GROUP BY m.date ORDER BY m.date""", (sid,))
    tl["date"] = pd.to_datetime(tl["date"])
    st.altair_chart(
        alt.Chart(tl).mark_bar().encode(
            x=alt.X("date:T"), y=alt.Y("words:Q", title="Words per meeting"),
            tooltip=["date:T", "words", "utts"]).properties(height=200),
        width="stretch")

    topics = q("""
        SELECT ut.topic, COUNT(*) n FROM utterance_topics ut
        JOIN utterances u ON u.id=ut.utterance_id
        WHERE u.speaker_id=? GROUP BY ut.topic ORDER BY n DESC""", (sid,))
    topics["topic"] = topics["topic"].map(lambda t: TOPIC_LABELS.get(t, t))
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown("**Topic mix** (tagged utterances)")
        st.dataframe(topics, width="stretch", height=300, hide_index=True)
    with c2:
        st.markdown("**Utterances** (longest first)")
        utts = q("""
            SELECT s.name, s.org, m.date, u.text
            FROM utterances u
            JOIN meetings m ON m.id=u.meeting_id
            JOIN speakers s ON s.id=u.speaker_id
            WHERE u.speaker_id=? ORDER BY u.word_count DESC LIMIT 500""", (sid,))
        show_utterances(utts, key=f"spk{sid}")


def page_faulkner():
    st.title("Judy Faulkner / Epic — Deep Dive")
    frow = q("SELECT id FROM speakers WHERE key LIKE '%faulkner%'")
    if frow.empty:
        st.error("Faulkner not found in speaker table.")
        return
    fid = int(frow.id[0])

    stats = q("""
        SELECT COUNT(*) utts, SUM(word_count) words, COUNT(DISTINCT meeting_id) mtgs
        FROM utterances WHERE speaker_id=?""", (fid,))
    n_m = int(q("SELECT COUNT(*) c FROM meetings").c[0])
    c1, c2, c3 = st.columns(3)
    c1.metric("Utterances", f"{int(stats.utts[0]):,}")
    c2.metric("Words", f"{int(stats.words[0]):,}")
    c3.metric("Meetings attended (spoke)", f"{int(stats.mtgs[0])} / {n_m}")

    st.subheader("Speaking volume vs committee average")
    vol = q("""
        SELECT m.date,
          SUM(CASE WHEN u.speaker_id=? THEN u.word_count ELSE 0 END) faulkner,
          SUM(u.word_count) * 1.0 / MAX(1, (
             SELECT COUNT(DISTINCT u2.speaker_id) FROM utterances u2
             JOIN speakers s2 ON s2.id = u2.speaker_id
             WHERE u2.meeting_id=m.id AND s2.is_onc_staff=0
                   AND s2.name != '(unidentified)')) avg_member
        FROM utterances u JOIN meetings m ON m.id=u.meeting_id
        GROUP BY m.id ORDER BY m.date""", (fid,))
    vol["date"] = pd.to_datetime(vol["date"])
    long = vol.melt("date", ["faulkner", "avg_member"], "series", "words")
    long["series"] = long["series"].map(
        {"faulkner": "Faulkner", "avg_member": "Avg member (per speaker)"})
    st.altair_chart(
        alt.Chart(long).mark_line(point=True).encode(
            x="date:T", y=alt.Y("words:Q", title="Words"),
            color=alt.Color("series:N", title=None),
            tooltip=["date:T", "series", "words"]).properties(height=250),
        width="stretch")

    st.subheader("What she talked about")
    topics = q("""
        SELECT ut.topic, COUNT(*) n FROM utterance_topics ut
        JOIN utterances u ON u.id=ut.utterance_id
        WHERE u.speaker_id=? GROUP BY ut.topic ORDER BY n DESC""", (fid,))
    topics["topic"] = topics["topic"].map(lambda t: TOPIC_LABELS.get(t, t))
    st.altair_chart(
        alt.Chart(topics).mark_bar().encode(
            x=alt.X("n:Q", title="Tagged utterances"),
            y=alt.Y("topic:N", sort="-x", title=None,
                    axis=alt.Axis(labelLimit=320, labelOverlap=False)),
        ).properties(height=max(120, 26 * len(topics))),
        width="stretch")

    tab1, tab2, tab3 = st.tabs(
        ["Her utterances", "Epic mentioned by others", "LLM position summaries"])
    with tab1:
        kw = st.text_input("Filter her remarks by keyword (optional)")
        sql = """
            SELECT s.name, s.org, m.date, u.text FROM utterances u
            JOIN meetings m ON m.id=u.meeting_id
            JOIN speakers s ON s.id=u.speaker_id
            WHERE u.speaker_id=? AND u.word_count >= 20"""
        params = [fid]
        if kw:
            sql += " AND u.text LIKE ?"
            params.append(f"%{kw}%")
        sql += " ORDER BY m.date, u.seq"
        show_utterances(q(sql, params), key="faulk")
    with tab2:
        others = q("""
            SELECT s.name, s.org, m.date, u.text FROM utterances u
            JOIN utterance_topics ut ON ut.utterance_id=u.id AND ut.topic='epic_mention'
            JOIN meetings m ON m.id=u.meeting_id
            JOIN speakers s ON s.id=u.speaker_id
            WHERE u.speaker_id != ? ORDER BY m.date""", (fid,))
        show_utterances(others, key="epicoth")
    with tab3:
        notes = q("SELECT content FROM analysis_notes WHERE kind='faulkner_positions' ORDER BY id DESC LIMIT 1")
        if notes.empty:
            st.info("Run the LLM pass (pipeline/llm_pass.py) to generate position summaries.")
        else:
            st.markdown(notes.content[0])


def page_topics():
    st.title("Topic Trends")
    picks = st.multiselect(
        "Topics", list(TOPIC_LABELS), default=["nhin", "hie", "interoperability"],
        format_func=lambda t: TOPIC_LABELS[t])
    if not picks:
        return
    ph = ",".join("?" * len(picks))
    trend = q(f"""
        SELECT m.date, ut.topic, COUNT(*) n
        FROM utterance_topics ut
        JOIN utterances u ON u.id=ut.utterance_id
        JOIN meetings m ON m.id=u.meeting_id
        WHERE ut.topic IN ({ph})
        GROUP BY m.date, ut.topic ORDER BY m.date""", picks)
    trend["date"] = pd.to_datetime(trend["date"])
    trend["topic"] = trend["topic"].map(lambda t: TOPIC_LABELS.get(t, t))
    st.altair_chart(
        alt.Chart(trend).mark_line(point=True).encode(
            x="date:T", y=alt.Y("n:Q", title="Utterances mentioning topic"),
            color=alt.Color("topic:N", title=None),
            tooltip=["date:T", "topic", "n"]).properties(height=300),
        width="stretch")

    focus = st.selectbox("Drill into topic", picks, format_func=lambda t: TOPIC_LABELS[t])
    if focus in ("nhin", "hie"):
        arc = q("SELECT content FROM analysis_notes WHERE kind='nhin_arc' ORDER BY id DESC LIMIT 1")
        if not arc.empty:
            with st.expander("How the NHIN/HIE debate evolved (LLM synthesis)", expanded=False):
                st.markdown(arc.content[0])
    st.subheader(f"Top speakers on {TOPIC_LABELS[focus]}")
    top = q("""
        SELECT s.name || ' — ' || s.org speaker, COUNT(*) n
        FROM utterance_topics ut
        JOIN utterances u ON u.id=ut.utterance_id
        JOIN speakers s ON s.id=u.speaker_id
        WHERE ut.topic=? AND s.name != '(unidentified)'
        GROUP BY s.id ORDER BY n DESC LIMIT 15""", (focus,))
    st.altair_chart(
        alt.Chart(top).mark_bar().encode(
            x=alt.X("n:Q", title="Utterances"),
            y=alt.Y("speaker:N", sort="-x", title=None,
                    axis=alt.Axis(labelLimit=320, labelOverlap=False)),
        ).properties(height=max(120, 26 * len(top))),
        width="stretch")

    st.subheader("Utterances")
    utts = q("""
        SELECT s.name, s.org, m.date, u.text
        FROM utterance_topics ut
        JOIN utterances u ON u.id=ut.utterance_id
        JOIN meetings m ON m.id=u.meeting_id
        JOIN speakers s ON s.id=u.speaker_id
        WHERE ut.topic=? AND u.word_count>=20 ORDER BY m.date""", (focus,))
    show_utterances(utts, key=f"topic_{focus}")


def page_search():
    st.title("Full-Text Search")
    query = st.text_input("Search transcripts (FTS5 syntax: AND/OR/NEAR, \"phrases\")",
                          placeholder='e.g. "information blocking" OR "data blocking"')
    c1, c2 = st.columns(2)
    speaker_filter = c1.text_input("Speaker name contains (optional)")
    year_filter = c2.selectbox(
        "Year", ["All"] + q("SELECT DISTINCT substr(date,1,4) y FROM meetings ORDER BY y")["y"].tolist())
    if not query:
        return
    sql = """
        SELECT s.name, s.org, m.date, u.text
        FROM utt_fts f
        JOIN utterances u ON u.id=f.rowid
        JOIN meetings m ON m.id=u.meeting_id
        JOIN speakers s ON s.id=u.speaker_id
        WHERE utt_fts MATCH ?"""
    params = [query]
    if speaker_filter:
        sql += " AND s.name LIKE ?"
        params.append(f"%{speaker_filter}%")
    if year_filter != "All":
        sql += " AND substr(m.date,1,4)=?"
        params.append(year_filter)
    sql += " ORDER BY m.date"
    try:
        res = q(sql, params)
    except Exception as e:
        st.error(f"Query error: {e}")
        return
    show_utterances(res, key="search")


def page_meetings():
    st.title("Meetings")
    m = q("SELECT id, date, filename, n_utterances, n_words FROM meetings ORDER BY date")
    pick = st.selectbox("Meeting", m["date"] + "  (" + m["n_words"].astype(str) + " words)")
    mid = int(m.iloc[(m["date"] + "  (" + m["n_words"].astype(str) + " words)").tolist().index(pick)]["id"])

    summ = q("SELECT summary FROM meeting_summaries WHERE meeting_id=?", (mid,))
    if not summ.empty:
        st.subheader("Summary")
        st.markdown(summ.summary[0])
    else:
        st.caption("No LLM summary yet — run pipeline/llm_pass.py.")

    st.subheader("Participants")
    parts = q("""
        SELECT s.name, s.org, COUNT(*) utterances, SUM(u.word_count) words
        FROM utterances u JOIN speakers s ON s.id=u.speaker_id
        WHERE u.meeting_id=? GROUP BY s.id ORDER BY words DESC""", (mid,))
    st.dataframe(parts, width="stretch", height=300, hide_index=True)

    st.subheader("Transcript")
    utts = q("""
        SELECT s.name, s.org, m.date, u.text
        FROM utterances u
        JOIN meetings m ON m.id=u.meeting_id
        JOIN speakers s ON s.id=u.speaker_id
        WHERE u.meeting_id=? ORDER BY u.seq""", (mid,))
    show_utterances(utts, page_size=50, key=f"mtg{mid}")


PAGES = {
    "Overview": page_overview,
    "Speakers": page_speakers,
    "Faulkner / Epic": page_faulkner,
    "Topics": page_topics,
    "Search": page_search,
    "Meetings": page_meetings,
}

choice = st.sidebar.radio("Page", list(PAGES))
st.sidebar.caption(
    "HIT Policy Committee transcripts 2009–2015, recovered from the Wayback "
    "Machine. Built from hitpc.db — see pipeline/.")
PAGES[choice]()
