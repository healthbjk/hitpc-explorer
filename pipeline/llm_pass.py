"""LLM analysis pass over hitpc.db using the Claude API.

Produces, incrementally (each item cached in the DB, safe to re-run):
  1. meeting_summaries  — one summary per meeting
  2. analysis_notes(kind='faulkner_positions') — Faulkner's positions by topic
  3. analysis_notes(kind='nhin_arc') — how the NHIN/HIE debate evolved

Requires ANTHROPIC_API_KEY. Run:
  .venv/bin/python -m pipeline.llm_pass                # everything missing
  .venv/bin/python -m pipeline.llm_pass --meetings 2   # only first 2 missing summaries
  .venv/bin/python -m pipeline.llm_pass --skip-meetings  # only the synthesis notes
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

DB_PATH = Path(__file__).resolve().parent.parent / "hitpc.db"
MODEL = "claude-sonnet-5"
MAX_MEETING_CHARS = 350_000   # ~90k tokens, fits comfortably in context

MEETING_PROMPT = """\
You are analyzing a meeting transcript of the US HIT Policy Committee \
(a FACA advisory committee to ONC, 2009-2015). Summarize this {date} meeting in \
markdown with these sections:

**Agenda & key decisions** — what was discussed and decided/recommended.
**Notable debates** — points of real disagreement, and who took which side.
**NHIN / HIE / interoperability** — anything said about nationwide health \
information network, health information exchange, or interoperability (say \
"nothing notable" if absent).
**Vendor dynamics** — anything involving EHR vendors (Epic, Cerner, etc.), \
including remarks BY vendor representatives on the committee.

Be specific: name speakers. Keep it under 500 words.

TRANSCRIPT:
{transcript}"""

FAULKNER_PROMPT = """\
Below are all substantive remarks by Judy Faulkner (founder/CEO of Epic \
Systems) as a member of the US HIT Policy Committee, 2009-2015, with meeting \
dates. Write a markdown analysis of her participation:

1. **Themes** — the recurring topics she engaged on, with her position on each \
and 2-3 short representative quotes (with dates).
2. **Positions relevant to Epic's business interests** — where her stated views \
aligned with or diverged from Epic's commercial interests (data sharing, \
interoperability, certification, vendor regulation). Be factual and fair; \
distinguish what she said from interpretation.
3. **Evolution** — how her focus or tone changed 2009→2015, if at all.

REMARKS:
{remarks}"""

NHIN_PROMPT = """\
Below are utterances from US HIT Policy Committee meetings (2009-2015) that \
mention NHIN/NwHIN (nationwide health information network) or HIE (health \
information exchange), with speaker names and dates, in chronological order. \
Write a markdown narrative of how the committee's NHIN/HIE discussion evolved: \
the early NHIN vision, the pivot to Direct and market-led HIE, governance \
debates, and where things stood by 2015. Name the main protagonists and what \
each argued. Under 800 words.

UTTERANCES:
{utterances}"""


def _client():
    return anthropic.Anthropic()


def _ask(client, prompt, max_tokens=2000):
    resp = client.messages.create(
        model=MODEL, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def summarize_meetings(con, client, limit=None):
    todo = con.execute("""
        SELECT m.id, m.date FROM meetings m
        LEFT JOIN meeting_summaries s ON s.meeting_id = m.id
        WHERE s.meeting_id IS NULL ORDER BY m.date""").fetchall()
    if limit:
        todo = todo[:limit]
    print(f"{len(todo)} meetings to summarize", file=sys.stderr)
    for mid, date in todo:
        rows = con.execute("""
            SELECT s.name, u.text FROM utterances u
            JOIN speakers s ON s.id=u.speaker_id
            WHERE u.meeting_id=? ORDER BY u.seq""", (mid,)).fetchall()
        transcript = "\n\n".join(f"{n}: {t}" for n, t in rows)[:MAX_MEETING_CHARS]
        summary = _ask(client, MEETING_PROMPT.format(date=date, transcript=transcript))
        con.execute(
            "INSERT OR REPLACE INTO meeting_summaries VALUES (?,?,?,?)",
            (mid, summary, MODEL, datetime.now(timezone.utc).isoformat()))
        con.commit()
        print(f"  summarized {date}", file=sys.stderr)


def faulkner_positions(con, client):
    rows = con.execute("""
        SELECT m.date, u.text FROM utterances u
        JOIN speakers s ON s.id=u.speaker_id
        JOIN meetings m ON m.id=u.meeting_id
        WHERE s.key LIKE '%faulkner%' AND u.word_count >= 25
        ORDER BY m.date, u.seq""").fetchall()
    remarks = "\n\n".join(f"[{d}] {t}" for d, t in rows)
    print(f"faulkner: {len(rows)} remarks, {len(remarks):,} chars", file=sys.stderr)
    content = _ask(client, FAULKNER_PROMPT.format(remarks=remarks), max_tokens=4000)
    con.execute(
        "INSERT INTO analysis_notes (kind, content, model, created_at) VALUES (?,?,?,?)",
        ("faulkner_positions", content, MODEL, datetime.now(timezone.utc).isoformat()))
    con.commit()


def nhin_arc(con, client):
    rows = con.execute("""
        SELECT DISTINCT m.date, s.name, u.text FROM utterances u
        JOIN utterance_topics ut ON ut.utterance_id=u.id AND ut.topic IN ('nhin','hie')
        JOIN speakers s ON s.id=u.speaker_id
        JOIN meetings m ON m.id=u.meeting_id
        WHERE u.word_count >= 40
        ORDER BY m.date, u.seq""").fetchall()
    text = "\n\n".join(f"[{d}] {n}: {t}" for d, n, t in rows)
    # Trim from the middle if enormous, keeping early + late years intact.
    if len(text) > 600_000:
        text = text[:300_000] + "\n\n[... middle years trimmed ...]\n\n" + text[-300_000:]
    print(f"nhin/hie: {len(rows)} utterances, {len(text):,} chars", file=sys.stderr)
    content = _ask(client, NHIN_PROMPT.format(utterances=text), max_tokens=4000)
    con.execute(
        "INSERT INTO analysis_notes (kind, content, model, created_at) VALUES (?,?,?,?)",
        ("nhin_arc", content, MODEL, datetime.now(timezone.utc).isoformat()))
    con.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meetings", type=int, default=None,
                    help="summarize at most N missing meetings")
    ap.add_argument("--skip-meetings", action="store_true")
    ap.add_argument("--skip-notes", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH)
    client = _client()
    if not args.skip_meetings:
        summarize_meetings(con, client, args.meetings)
    if not args.skip_notes:
        faulkner_positions(con, client)
        nhin_arc(con, client)
    con.close()


if __name__ == "__main__":
    main()
