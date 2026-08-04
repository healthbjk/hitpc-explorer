"""Extract plain text from the transcript corpus (PDF via pdftotext, docx via
zipfile/XML), caching results in corpus_text/ keyed by source filename."""

import os
import re
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent.parent / "hitpc_corpus"
TEXT_DIR = Path(__file__).resolve().parent.parent / "corpus_text"

SKIP_FILES = {"manifest.csv", "candidates.csv", "run.log", "run2.log", "run3.log"}


def parse_meeting_date(filename):
    """Meeting date embedded in the transcript filename. Filenames are
    '<capture_ts>__<original_basename>'; the meeting date lives in the original
    basename (e.g. 2011-02-02, 2010_10_20, or 20100113), so strip the capture
    prefix before matching."""
    base = filename.split("__", 1)[-1]
    m = re.search(r"(\d{4})[-_](\d{2})[-_](\d{2})", base)
    if not m:
        m = re.search(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)", base)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # MMDDYY fallbacks seen in early filenames: "061609", "09-14-11"
    for pat in (r"(?<!\d)(\d{2})-(\d{2})-(\d{2})(?!\d)",
                r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)"):
        m = re.search(pat, base)
        if m:
            mo, dy, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mo <= 12 and 1 <= dy <= 31 and 9 <= yr <= 17:
                try:
                    return date(2000 + yr, mo, dy)
                except ValueError:
                    pass
    return None


MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
STATED_DATE_RE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october"
    r"|november|december)\s+(\d{1,2}),?\s+(20\d{2})\b", re.I)


def stated_meeting_date(text, head_chars=4000):
    """The meeting date printed in the transcript's own header block.

    Authoritative where it disagrees with the filename: ONC filenames
    sometimes carry the publication date instead of the meeting date, and at
    least one is simply mistyped (a January 2012 transcript named 2011-01-10).
    """
    from collections import Counter
    counts = Counter()
    for mo, dy, yr in STATED_DATE_RE.findall(text[:head_chars]):
        try:
            counts[date(int(yr), MONTHS[mo.lower()], int(dy))] += 1
        except ValueError:
            continue
    return counts.most_common(1)[0][0] if counts else None


def extract_pdf(path):
    out = subprocess.run(
        ["pdftotext", str(path), "-"],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {out.stderr[:200]}")
    return out.stdout


def extract_docx(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf8", errors="replace")
    # Paragraph boundaries -> newlines; all other tags stripped in place so
    # runs within a paragraph stay on one line.
    xml = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    text = (text.replace("&amp;", "&").replace("&lt;", "<")
                .replace("&gt;", ">").replace("&quot;", '"')
                .replace("&#8217;", "’").replace("&#8211;", "–"))
    return text


def extract_all(force=False):
    """Extract every transcript to corpus_text/<name>.txt. Returns list of
    (source_filename, meeting_date, text_path)."""
    TEXT_DIR.mkdir(exist_ok=True)
    results = []
    files = sorted(f for f in os.listdir(CORPUS_DIR) if f not in SKIP_FILES)
    for name in files:
        src = CORPUS_DIR / name
        dst = TEXT_DIR / (name + ".txt")
        if force or not dst.exists():
            try:
                if name.lower().endswith(".docx"):
                    text = extract_docx(src)
                elif name.lower().endswith(".pdf"):
                    text = extract_pdf(src)
                else:
                    print(f"  skip (unknown type): {name}", file=sys.stderr)
                    continue
            except Exception as e:
                print(f"  ! extract failed {name}: {e}", file=sys.stderr)
                continue
            dst.write_text(text, encoding="utf8")
        results.append((name, parse_meeting_date(name), dst))
    return results


if __name__ == "__main__":
    for name, d, p in extract_all():
        print(f"{d}  {name}  ({p.stat().st_size} bytes)")
