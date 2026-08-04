# HITPC Transcript Explorer

Interactive explorer for the meeting transcripts of the **HIT Policy Committee** (HITPC) — the federal advisory committee to ONC created by the HITECH Act — covering 75 full-committee meetings from May 2009 through late 2015.

The committee's original transcripts vanished from public view when ONC reorganized its sites after the 21st Century Cures Act folded HITPC into HITAC. This project recovers them from the Internet Archive's Wayback Machine, parses them into a structured, speaker-attributed database, and layers analysis on top.

## What's inside

- **`hitpc.db`** — SQLite database: 75 meetings, 23,299 speaker-attributed utterances (2.6M words), 357 normalized speakers, keyword topic tags, and full-text search (FTS5). Includes **29 per-speaker position analyses** — committee members (Judy Faulkner/Epic, Neal Patterson/Cerner, Paul Tang, Deven McGraw, Micky Tripathi, Christine Bechtel, Gayle Harrell, David Lansky, Paul Egerman, Larry Wolf, Neil Calman, Marc Probst, David Bates, Charles Kennedy, George Hripcsak, John Lumpkin, Arthur Davidson, Theresa Cullen…) and the ONC/CMS officials who ran the program (Blumenthal, Mostashari, DeSalvo, Daniel, Fridsma, Posnack, Anthony…) — plus a narrative of how the NHIN/HIE debate evolved. Every quote was checked against the transcripts.
- **`app.py`** — Streamlit app: **Speakers** (leaderboard → per-person record: activity vs the committee average, topic mix, position analysis, every quote, and how others referred to them), **Topics** (trend charts — watch NHIN die in real time), **Search** (full-text), and **Meetings & Transcripts** (full transcript of any meeting, downloadable, with a link back to the original ONC source).
- **`pipeline/`** — the full reproducible pipeline: Wayback CDX discovery (`collect_hitpc_corpus.py`), text extraction, transcript parsing (three transcription-vendor grammars), speaker normalization, and topic tagging.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

The app runs entirely off the committed `hitpc.db` — no other data needed.

## Rebuild from scratch (optional)

```bash
# 1. Re-download the transcript corpus from the Wayback Machine (~30 min)
.venv/bin/python collect_hitpc_corpus.py        # writes hitpc_corpus/
# 2. Rebuild the database
.venv/bin/python -m pipeline.build_db           # writes hitpc.db
```

Requires `pdftotext` (poppler) on PATH for step 2.

## Notes

- Transcripts are public U.S. government records (FACA committee proceedings).
- Speaker attribution is parsed from transcript headers; name variants are normalized (e.g., "Judy Faulkner, Epic" = "Judith Faulkner, MS – EPIC Systems Corporation"). Roll-call one-liners are retained but easy to filter by word count.
- One meeting file's parsed date (2009-05-27) reflects its publication date; the meeting occurred 2009-05-11.
