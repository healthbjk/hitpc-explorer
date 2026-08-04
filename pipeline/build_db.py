"""Build hitpc.db from the transcript corpus.

Steps: extract text -> pick one canonical file per meeting date (final beats
draft, longer beats shorter) -> parse utterances -> normalize speakers ->
load SQLite with FTS5 index and topic tags.

Run:  .venv/bin/python -m pipeline.build_db
"""

import re
import sqlite3
import sys
from pathlib import Path

from .extract import extract_all
from .parse import parse_utterances
from .speakers import SpeakerRegistry
from .topics import tag

DB_PATH = Path(__file__).resolve().parent.parent / "hitpc.db"

SCHEMA = """
DROP TABLE IF EXISTS meetings;
DROP TABLE IF EXISTS speakers;
DROP TABLE IF EXISTS utterances;
DROP TABLE IF EXISTS utterance_topics;
DROP TABLE IF EXISTS utt_fts;
CREATE TABLE meetings (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    filename TEXT NOT NULL,
    n_utterances INTEGER,
    n_words INTEGER,
    source_url TEXT          -- original ONC URL, from the Wayback manifest
);
CREATE TABLE speakers (
    id INTEGER PRIMARY KEY,
    key TEXT UNIQUE,
    name TEXT,
    org TEXT,
    is_onc_staff INTEGER DEFAULT 0
);
CREATE TABLE utterances (
    id INTEGER PRIMARY KEY,
    meeting_id INTEGER REFERENCES meetings(id),
    seq INTEGER,
    speaker_id INTEGER REFERENCES speakers(id),
    speaker_raw TEXT,
    text TEXT,
    word_count INTEGER
);
CREATE TABLE utterance_topics (
    utterance_id INTEGER REFERENCES utterances(id),
    topic TEXT,
    PRIMARY KEY (utterance_id, topic)
);
CREATE INDEX idx_utt_meeting ON utterances(meeting_id);
CREATE INDEX idx_utt_speaker ON utterances(speaker_id);
CREATE INDEX idx_topic ON utterance_topics(topic);
CREATE VIRTUAL TABLE utt_fts USING fts5(text, content='utterances', content_rowid='id');
CREATE TABLE IF NOT EXISTS meeting_summaries (
    meeting_id INTEGER PRIMARY KEY REFERENCES meetings(id),
    summary TEXT, model TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS analysis_notes (
    id INTEGER PRIMARY KEY,
    kind TEXT,            -- e.g. 'faulkner_positions', 'nhin_arc'
    content TEXT, model TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS speaker_summaries (
    speaker_key TEXT PRIMARY KEY,   -- speakers.key (stable across rebuilds)
    content TEXT, model TEXT, created_at TEXT
);
"""


def pick_canonical(files):
    """files: list of (name, date, path). One per date: final > draft > other,
    then longest extracted text."""
    def rank(item):
        name, _d, path = item
        low = name.lower()
        pref = 2 if "final" in low else (0 if "draft" in low else 1)
        return (pref, path.stat().st_size)

    by_date = {}
    for item in files:
        d = item[1]
        by_date.setdefault(d, []).append(item)
    chosen, skipped = [], []
    for d, items in sorted(by_date.items()):
        items.sort(key=rank, reverse=True)
        chosen.append(items[0])
        skipped.extend(items[1:])
    return chosen, skipped


def source_urls():
    """local filename -> original ONC url, from the corpus download manifest."""
    import csv as _csv
    path = Path(__file__).resolve().parent.parent / "hitpc_corpus" / "manifest.csv"
    if not path.exists():
        return {}
    out = {}
    with open(path, newline="") as f:
        for row in _csv.DictReader(f):
            out[Path(row["local_path"]).name] = row["original_url"]
    return out


def main():
    files = extract_all()
    chosen, skipped = pick_canonical(files)
    print(f"{len(files)} files -> {len(chosen)} unique meetings "
          f"({len(skipped)} draft/duplicate versions skipped)", file=sys.stderr)

    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)

    registry = SpeakerRegistry()
    parsed = []  # (date, name, [(raw_speaker, text), ...])
    for name, d, path in chosen:
        utts = parse_utterances(path.read_text(encoding="utf8"))
        for raw, _text in utts:
            registry.observe(raw)
        parsed.append((d, name, utts))

    resolved = registry.resolve()
    speaker_ids = {}
    for key, (display, org, staff) in sorted(resolved.items()):
        cur = con.execute(
            "INSERT INTO speakers (key, name, org, is_onc_staff) VALUES (?,?,?,?)",
            (key, display, org, int(staff)),
        )
        speaker_ids[key] = cur.lastrowid

    urls = source_urls()
    for d, name, utts in parsed:
        n_words = sum(len(t.split()) for _r, t in utts)
        cur = con.execute(
            "INSERT INTO meetings (date, filename, n_utterances, n_words, source_url)"
            " VALUES (?,?,?,?,?)",
            (d.isoformat(), name, len(utts), n_words, urls.get(name)),
        )
        mid = cur.lastrowid
        for seq, (raw, text) in enumerate(utts):
            key = registry.observe(raw)  # observe is idempotent for key lookup
            wc = len(text.split())
            ucur = con.execute(
                "INSERT INTO utterances (meeting_id, seq, speaker_id, speaker_raw, text, word_count)"
                " VALUES (?,?,?,?,?,?)",
                (mid, seq, speaker_ids[key], raw, text, wc),
            )
            uid = ucur.lastrowid
            for topic in tag(text):
                con.execute(
                    "INSERT OR IGNORE INTO utterance_topics VALUES (?,?)", (uid, topic))

    con.execute("INSERT INTO utt_fts(rowid, text) SELECT id, text FROM utterances")
    con.commit()

    n_m = con.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
    n_s = con.execute("SELECT COUNT(*) FROM speakers").fetchone()[0]
    n_u = con.execute("SELECT COUNT(*) FROM utterances").fetchone()[0]
    n_t = con.execute("SELECT COUNT(*) FROM utterance_topics").fetchone()[0]
    print(f"db built: {n_m} meetings, {n_s} speakers, {n_u} utterances, {n_t} topic tags")
    con.close()


if __name__ == "__main__":
    main()
