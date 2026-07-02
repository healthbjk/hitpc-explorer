# HITPC Transcript Explorer

Interactive explorer for the meeting transcripts of the **HIT Policy Committee** (HITPC) — the federal advisory committee to ONC created by the HITECH Act — covering 75 full-committee meetings from May 2009 through late 2015.

The committee's original transcripts vanished from public view when ONC reorganized its sites after the 21st Century Cures Act folded HITPC into HITAC. This project recovers them from the Internet Archive's Wayback Machine, parses them into a structured, speaker-attributed database, and layers analysis on top.

## What's inside

- **`hitpc.db`** — SQLite database: 75 meetings, 23,298 speaker-attributed utterances (2.6M words), 361 normalized speakers, keyword topic tags, and full-text search (FTS5). Includes synthesized position analyses for 8 key members (Judy Faulkner/Epic, Neal Patterson/Cerner, Paul Tang, Deven McGraw, Micky Tripathi, Christine Bechtel, Gayle Harrell, David Lansky, Paul Egerman) and a narrative of how the NHIN/HIE debate evolved — every quote verified against the transcripts.
- **`app.py`** — Streamlit app: speaker leaderboards and drill-downs, a Judy Faulkner/Epic deep-dive, topic trend charts (watch NHIN die in real time), full-text search, and a meeting browser.
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
