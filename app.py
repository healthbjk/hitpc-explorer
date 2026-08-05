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

# Org words too generic to use as a "mentioned by others" search term.
GENERIC_ORG_WORDS = {
    "office", "national", "center", "centre", "university", "health",
    "healthcare", "department", "foundation", "group", "association",
    "institute", "partners", "state", "federal", "coordinator", "services",
    "systems", "corporation", "medical", "public", "school", "college",
    "hospital", "of", "for", "the", "and", "&", "business", "technology",
    "information", "policy", "research", "advisory", "society", "council",
}


@st.cache_resource
def get_con():
    return sqlite3.connect(DB, check_same_thread=False)


@st.cache_data
def q(sql, params=()):
    return pd.read_sql_query(sql, get_con(), params=params)


@st.cache_data
def n_meetings():
    return int(q("SELECT COUNT(*) c FROM meetings").c[0])


def bar(df, value, label, height_per=26, min_height=120):
    return alt.Chart(df).mark_bar().encode(
        x=alt.X(f"{value}:Q", title=None),
        y=alt.Y(f"{label}:N", sort="-x", title=None,
                axis=alt.Axis(labelLimit=320, labelOverlap=False)),
        tooltip=[label, value],
    ).properties(height=max(min_height, height_per * len(df)))


def show_utterances(df, page_size=25, key="utt"):
    """Render utterances with speaker, meeting date, text."""
    total = len(df)
    if total == 0:
        st.info("No utterances match.")
        return
    pages = (total - 1) // page_size + 1
    page = 1
    if pages > 1:
        page = st.number_input(
            f"Page (of {pages:,} — {total:,} utterances)", 1, pages, 1, key=key + "_pg")
    else:
        st.caption(f"{total:,} utterance{'s' if total != 1 else ''}")
    view = df.iloc[(page - 1) * page_size: page * page_size]
    for _, r in view.iterrows():
        st.markdown(f"**{r['name']}** ({r['org']}) — *{r['date']}*  \n{r['text']}")
        st.divider()


# ---------------------------------------------------------------------- pages

def page_overview():
    st.title("HIT Policy Committee — Transcript Explorer")
    st.caption(
        "75 full-committee meetings, May 2009 – November 2015, recovered from the "
        "Internet Archive after ONC retired the original pages.")
    m = q("SELECT * FROM meetings ORDER BY date")
    stats = q("""SELECT (SELECT COUNT(*) FROM meetings) meetings,
                        (SELECT COUNT(*) FROM speakers) speakers,
                        (SELECT COUNT(*) FROM utterances) utterances,
                        (SELECT SUM(word_count) FROM utterances) words,
                        (SELECT COUNT(*) FROM speaker_summaries) analyses""")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Meetings", int(stats.meetings[0]))
    c2.metric("Speakers", int(stats.speakers[0]))
    c3.metric("Utterances", f"{int(stats.utterances[0]):,}")
    c4.metric("Words", f"{int(stats.words[0]):,}")
    c5.metric("Position analyses", int(stats.analyses[0]))

    st.subheader("Meetings over time")
    m["date"] = pd.to_datetime(m["date"])
    st.altair_chart(
        alt.Chart(m).mark_bar().encode(
            x=alt.X("date:T", title="Meeting date"),
            y=alt.Y("n_words:Q", title="Words in transcript"),
            tooltip=["date:T", "filename", "n_utterances", "n_words"],
        ).properties(height=250), width="stretch")

    st.subheader("Most active speakers")
    c1, c2 = st.columns([2, 1])
    METRICS = {
        "Total words spoken": ("words", "SUM(u.word_count)"),
        "Number of times they spoke": ("times_spoke", "COUNT(*)"),
        "Words per meeting attended":
            ("words_per_meeting", "SUM(u.word_count)*1.0/COUNT(DISTINCT u.meeting_id)"),
    }
    metric = c1.radio("Rank by", list(METRICS), horizontal=True, key="ov_metric")
    incl_staff = c2.toggle("Include ONC/CMS staff", value=False, key="ov_staff")
    col, expr = METRICS[metric]
    where = "WHERE s.name != '(unidentified)'" + ("" if incl_staff else " AND s.is_gov_staff=0")
    top = q(f"""
        SELECT s.name || ' — ' || s.org AS speaker, ROUND({expr}) {col}
        FROM utterances u JOIN speakers s ON s.id=u.speaker_id
        {where} GROUP BY s.id ORDER BY {col} DESC LIMIT 20""")
    st.altair_chart(bar(top, col, "speaker"), width="stretch")
    st.caption(
        "**Word counts favour long presentations and whoever chairs the meeting.** "
        "Switch to *number of times they spoke* for a different picture: Judy "
        "Faulkner is 11th by words but 5th by interventions — she spoke up often, "
        "in short bursts (64 words on average). Open **Speakers** for per-person "
        "analysis, quotes and topic mix.")

    with st.expander("How this corpus was built — and how the counts reconcile"):
        st.markdown(f"""
**{q("SELECT COUNT(*) c FROM meetings").c[0]} meetings from 105 files.** The Wayback sweep recovered
**105 transcript files**, but that is a file count, not a meeting count. ONC
published most meetings twice (a *draft* and a *final* transcript), and the
Internet Archive captured some documents at several different timestamps.
Collapsing those leaves **75 unique meetings**: 26 dates had more than one
file, accounting for the 30 extras. Where a draft and a final exist, the
final is used.

**Dates come from the transcript, not the filename.** Every meeting date was
checked against the date printed inside the document. 73 of 75 agreed; the two
that did not were corrected:

| Filename says | Transcript says | What happened |
|---|---|---|
| 2009-05-27 | **2009-05-11** | Filename carried the publication date. This is the committee's first meeting. |
| 2011-01-10 | **2012-01-10** | Mistyped by ONC. Robert Anthony's remarks in it recap "how we closed 2011". |

**Known gaps.** The corpus covers May 2009 – November 2015. Coverage is
roughly monthly and thickest in 2010–2013; a handful of meetings announced in
the *Federal Register* (e.g. 2009-12-15, 2010-05-19, 2010-09-28) have no
surviving transcript at the URLs the Archive captured. Meetings per year:
2009: 5 · 2010: 13 · 2011: 12 · 2012: 13 · 2013: 11 · 2014: 11 · 2015: 10.

**Attendance is measured against tenure.** On a speaker's page, "meetings
spoke at" is out of the meetings held between their first and last recorded
remark — not out of all 75 — because most members served only part of the
committee's life. Judy Faulkner, for instance, spoke at **52 of the 59**
meetings held during her 2009–2014 tenure (88%), not 52 of 75.
""")


def page_speakers():
    st.title("Speakers")
    st.caption(
        "Pick anyone to see their record: activity over time, topic mix, every "
        "quote, how others referred to them, and — for 30 key figures — a "
        "position analysis grounded in their own words.")

    years = q("SELECT DISTINCT substr(date,1,4) y FROM meetings ORDER BY y")["y"].tolist()
    c1, c2, c3 = st.columns([1.4, 1, 1])
    year = c1.selectbox("Year", ["All"] + years)
    hide_onc = c2.toggle("Hide ONC/CMS staff", value=True, key="hide_onc",
                         help="Hides the ONC, HHS and CMS officials who ran the "
                              "programme and briefed the committee. Federal "
                              "committee *members* (e.g. VHA) are not hidden.")
    only_analyzed = c3.toggle("Only with analysis", value=False)

    where = "WHERE s.name != '(unidentified)'"
    params = []
    if year != "All":
        where += " AND substr(m.date,1,4)=?"
        params.append(year)
    if hide_onc:
        where += " AND s.is_gov_staff=0"
    if only_analyzed:
        where += " AND EXISTS (SELECT 1 FROM speaker_summaries ss WHERE ss.speaker_key=s.key)"

    lb = q(f"""
        SELECT s.id, s.name, s.org,
               CASE WHEN EXISTS (SELECT 1 FROM speaker_summaries ss
                                 WHERE ss.speaker_key=s.key) THEN '✓' ELSE '' END AS analysis,
               COUNT(*) utterances, SUM(u.word_count) words,
               COUNT(DISTINCT u.meeting_id) meetings
        FROM utterances u
        JOIN speakers s ON s.id=u.speaker_id
        JOIN meetings m ON m.id=u.meeting_id
        {where}
        GROUP BY s.id ORDER BY words DESC LIMIT 150""", params)
    if lb.empty:
        st.info("No speakers match these filters.")
        return
    st.dataframe(lb.drop(columns=["id"]), width="stretch", height=300, hide_index=True)

    st.divider()
    options = (lb["name"] + " — " + lb["org"]).tolist()
    pick = st.selectbox("Speaker", options, index=0)
    detail_speaker(int(lb.iloc[options.index(pick)]["id"]))


def default_mention_terms(name, org):
    terms = [name.split()[-1]] if name else []
    for tok in re.split(r"[\s,/&]+", org or ""):
        tok = tok.strip(".")
        if len(tok) > 3 and tok.lower() not in GENERIC_ORG_WORDS and tok[0].isupper():
            terms.append(tok)
            break
        if tok.isupper() and 2 <= len(tok) <= 5 and tok.lower() not in GENERIC_ORG_WORDS:
            terms.append(tok)
            break
    return ", ".join(dict.fromkeys(terms))


def detail_speaker(sid):
    info = q("SELECT id, key, name, org, is_gov_staff FROM speakers WHERE id=?", (sid,)).iloc[0]
    st.header(f"{info['name']}")
    st.caption(f"{info['org']}" + ("  ·  ONC/HHS staff" if info["is_gov_staff"] else ""))

    stats = q("""
        SELECT COUNT(*) utts, SUM(word_count) words,
               COUNT(DISTINCT meeting_id) mtgs
        FROM utterances WHERE speaker_id=?""", (sid,)).iloc[0]
    span = q("""SELECT MIN(m.date) a, MAX(m.date) b FROM utterances u
                JOIN meetings m ON m.id=u.meeting_id WHERE u.speaker_id=?""", (sid,)).iloc[0]
    # Denominator is meetings held during their own tenure, not the whole
    # corpus: most members served only part of the committee's 2009-2015 life.
    tenure = int(q("SELECT COUNT(*) c FROM meetings WHERE date BETWEEN ? AND ?",
                   (span.a, span.b)).c[0])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Utterances", f"{int(stats.utts):,}")
    c2.metric("Words", f"{int(stats.words):,}")
    c3.metric("Meetings spoke at", f"{int(stats.mtgs)} of {tenure}",
              help=f"Meetings held between their first and last recorded remark "
                   f"({int(100*stats.mtgs/max(1,tenure))}% attendance). The full "
                   f"corpus has {n_meetings()} meetings; most members served only "
                   f"part of the committee's 2009–2015 life.")
    c4.metric("Active", f"{span.a[:7]} → {span.b[:7]}")

    note = q("""SELECT ss.content FROM speaker_summaries ss
                JOIN speakers s ON s.key = ss.speaker_key WHERE s.id=?""", (sid,))
    if not note.empty:
        with st.expander("📋 Position analysis — themes, quotes, evolution", expanded=True):
            st.markdown(note.content[0])
    else:
        st.caption(
            "No position analysis for this speaker yet — the analyses cover the "
            "30 most substantive voices.")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Speaking volume vs committee average")
        vol = q("""
            SELECT m.date,
              SUM(CASE WHEN u.speaker_id=? THEN u.word_count ELSE 0 END) speaker,
              SUM(u.word_count) * 1.0 / MAX(1, (
                 SELECT COUNT(DISTINCT u2.speaker_id) FROM utterances u2
                 JOIN speakers s2 ON s2.id = u2.speaker_id
                 WHERE u2.meeting_id=m.id AND s2.is_gov_staff=0
                       AND s2.name != '(unidentified)')) avg_member
            FROM utterances u JOIN meetings m ON m.id=u.meeting_id
            GROUP BY m.id ORDER BY m.date""", (sid,))
        vol["date"] = pd.to_datetime(vol["date"])
        long = vol.melt("date", ["speaker", "avg_member"], "series", "words")
        long["series"] = long["series"].map(
            {"speaker": info["name"], "avg_member": "Avg member (per speaker)"})
        st.altair_chart(
            alt.Chart(long).mark_line(point=True).encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("words:Q", title="Words"),
                color=alt.Color("series:N", title=None,
                                legend=alt.Legend(orient="top")),
                tooltip=["date:T", "series", "words"]).properties(height=260),
            width="stretch")
    with right:
        st.subheader("Topic mix")
        topics = q("""
            SELECT ut.topic, COUNT(*) n FROM utterance_topics ut
            JOIN utterances u ON u.id=ut.utterance_id
            WHERE u.speaker_id=? GROUP BY ut.topic ORDER BY n DESC""", (sid,))
        if topics.empty:
            st.info("No topic-tagged utterances.")
        else:
            topics["topic"] = topics["topic"].map(lambda t: TOPIC_LABELS.get(t, t))
            st.altair_chart(bar(topics, "n", "topic", height_per=22, min_height=260),
                            width="stretch")

    t1, t2, t3 = st.tabs(["Their remarks", "Mentioned by others", "Meeting-by-meeting"])
    with t1:
        c1, c2 = st.columns([3, 1])
        kw = c1.text_input("Filter by keyword", key=f"kw{sid}",
                           placeholder="e.g. interoperability, standards, patient")
        min_words = c2.number_input("Min words", 0, 500, 25, 25, key=f"mw{sid}")
        sql = """
            SELECT s.name, s.org, m.date, u.text FROM utterances u
            JOIN meetings m ON m.id=u.meeting_id
            JOIN speakers s ON s.id=u.speaker_id
            WHERE u.speaker_id=? AND u.word_count >= ?"""
        params = [sid, int(min_words)]
        if kw:
            sql += " AND u.text LIKE ?"
            params.append(f"%{kw}%")
        sql += " ORDER BY m.date, u.seq"
        show_utterances(q(sql, params), key=f"spk{sid}")
    with t2:
        default = default_mention_terms(info["name"], info["org"])
        terms = st.text_input(
            "Search other speakers' remarks for (comma-separated)",
            value=default, key=f"mt{sid}",
            help="Defaults to their surname and a distinctive word from their organization.")
        term_list = [t.strip() for t in terms.split(",") if t.strip()]
        if not term_list:
            st.info("Enter a term to search.")
        else:
            clause = " OR ".join(["u.text LIKE ?"] * len(term_list))
            show_utterances(q(f"""
                SELECT s.name, s.org, m.date, u.text FROM utterances u
                JOIN meetings m ON m.id=u.meeting_id
                JOIN speakers s ON s.id=u.speaker_id
                WHERE u.speaker_id != ? AND u.word_count >= 15 AND ({clause})
                ORDER BY m.date, u.seq""",
                [sid] + [f"%{t}%" for t in term_list]), key=f"men{sid}")
    with t3:
        per = q("""
            SELECT m.date, COUNT(*) utterances, SUM(u.word_count) words
            FROM utterances u JOIN meetings m ON m.id=u.meeting_id
            WHERE u.speaker_id=? GROUP BY m.id ORDER BY m.date""", (sid,))
        st.dataframe(per, width="stretch", height=420, hide_index=True)


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
            x=alt.X("date:T", title=None),
            y=alt.Y("n:Q", title="Utterances mentioning topic"),
            color=alt.Color("topic:N", title=None, legend=alt.Legend(orient="top")),
            tooltip=["date:T", "topic", "n"]).properties(height=300), width="stretch")

    focus = st.selectbox("Drill into topic", picks, format_func=lambda t: TOPIC_LABELS[t])
    if focus in ("nhin", "hie"):
        arc = q("SELECT content FROM analysis_notes WHERE kind='nhin_arc' ORDER BY id DESC LIMIT 1")
        if not arc.empty:
            with st.expander("How the NHIN/HIE debate evolved, 2009–2015", expanded=False):
                st.markdown(arc.content[0])

    st.subheader(f"Top speakers on {TOPIC_LABELS[focus]}")
    top = q("""
        SELECT s.name || ' — ' || s.org speaker, COUNT(*) n
        FROM utterance_topics ut
        JOIN utterances u ON u.id=ut.utterance_id
        JOIN speakers s ON s.id=u.speaker_id
        WHERE ut.topic=? AND s.name != '(unidentified)'
        GROUP BY s.id ORDER BY n DESC LIMIT 15""", (focus,))
    st.altair_chart(bar(top, "n", "speaker"), width="stretch")

    st.subheader("Utterances")
    show_utterances(q("""
        SELECT s.name, s.org, m.date, u.text
        FROM utterance_topics ut
        JOIN utterances u ON u.id=ut.utterance_id
        JOIN meetings m ON m.id=u.meeting_id
        JOIN speakers s ON s.id=u.speaker_id
        WHERE ut.topic=? AND u.word_count>=20 ORDER BY m.date""", (focus,)),
        key=f"topic_{focus}")


def page_search():
    st.title("Full-Text Search")
    query = st.text_input(
        "Search 23,000 utterances (FTS5: AND/OR/NEAR, \"quoted phrases\")",
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
    st.title("Meetings & Full Transcripts")
    m = q("""SELECT id, date, filename, n_utterances, n_words, source_url
             FROM meetings ORDER BY date""")
    labels = m["date"] + "   (" + m["n_words"].map("{:,}".format) + " words)"
    pick = st.selectbox("Meeting", labels.tolist())
    row = m.iloc[labels.tolist().index(pick)]
    mid = int(row["id"])

    utts = q("""
        SELECT s.name, s.org, m.date, u.text
        FROM utterances u
        JOIN meetings m ON m.id=u.meeting_id
        JOIN speakers s ON s.id=u.speaker_id
        WHERE u.meeting_id=? ORDER BY u.seq""", (mid,))

    c1, c2, c3 = st.columns([1.2, 1.2, 2])
    c1.metric("Utterances", f"{int(row['n_utterances']):,}")
    c2.metric("Words", f"{int(row['n_words']):,}")
    plain = f"HIT Policy Committee — {row['date']}\n\n" + "\n\n".join(
        f"{r['name']} ({r['org']}):\n{r['text']}" for _, r in utts.iterrows())
    c3.download_button("⬇ Download full transcript (.txt)", plain,
                       file_name=f"hitpc_{row['date']}.txt", mime="text/plain")
    if row["source_url"]:
        st.caption(f"Source: [original ONC file]({row['source_url']}) "
                   f"· archived copy: `{row['filename']}`")

    summ = q("SELECT summary FROM meeting_summaries WHERE meeting_id=?", (mid,))
    if not summ.empty:
        st.subheader("Summary")
        st.markdown(summ.summary[0])

    st.subheader("Participants")
    st.dataframe(q("""
        SELECT s.name, s.org, COUNT(*) utterances, SUM(u.word_count) words
        FROM utterances u JOIN speakers s ON s.id=u.speaker_id
        WHERE u.meeting_id=? GROUP BY s.id ORDER BY words DESC""", (mid,)),
        width="stretch", height=280, hide_index=True)

    st.subheader("Full transcript")
    show_utterances(utts, page_size=50, key=f"mtg{mid}")


PAGES = {
    "Overview": page_overview,
    "Speakers": page_speakers,
    "Topics": page_topics,
    "Search": page_search,
    "Meetings & Transcripts": page_meetings,
}

choice = st.sidebar.radio("Page", list(PAGES))
st.sidebar.divider()
st.sidebar.caption(
    "HIT Policy Committee transcripts 2009–2015, recovered from the Wayback "
    "Machine after ONC retired the original pages. Public U.S. government "
    "records (FACA proceedings).\n\n"
    "Position analyses are LLM-written from each speaker's own remarks; every "
    "quote was checked against the transcripts.")
PAGES[choice]()
