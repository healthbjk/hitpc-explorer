"""Segment transcript text into (speaker_raw, text) utterances.

Two header grammars exist in the corpus:
  * Dash headers (2010+): "Judy Faulkner – Epic Systems – Founder", segments
    separated by en/em dashes (or spaced hyphens), sometimes wrapped onto a
    second line when the org name is long.
  * Bare-name headers (2009 era): the speaker's name alone on a line
    ("Dr. Neil Calman"), with Vcall footer blocks and repeated page headers
    as junk.
"""

import re

# En/em dashes split freely; plain hyphens only with surrounding space (or
# glued to a capital, "-The Institute") and never as part of a "--" prose dash.
DASH_SPLIT = re.compile(r"\s*[–—]\s*|\s+-\s+(?!-)|\s+-(?=[A-Z])")

# A person name: optional honorific, 1-6 capitalized tokens, optional
# trailing credential list ("Paul Tang, MD, MS", "Judy Faulkner, MS").
NAME_RE = re.compile(
    r"^(?:Dr\.|Mr\.|Ms\.|Mrs\.)?\s*"
    r"[A-Z][A-Za-z'’.]*(?:[\s\-][A-Za-z'’.()]+){0,5}"
    r"(?:,\s*[A-Za-z.,&/\- ]{1,60})?$"
)

UNIDENTIFIED_RE = re.compile(r"^Unidentified (Speaker|Male|Female|Participant)", re.I)

# Junk lines stripped before parsing.
PAGE_NUM_RE = re.compile(r"^\d{1,3}$")
JUNK_EXACT = {
    "Vcall", "601 Moorefield Park Dr.", "Richmond, VA 23236",
    "info@vcall.com", "www.vcall.com", "www.investorcalendar.com",
    "Altarum - EV", "TRANSCRIPT", "Presentation", "Participants",
}
JUNK_PREFIX = ("Phone:", "Fax:", "www.", "http")
STANDALONE_DATE_RE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October"
    r"|November|December) \d{1,2}, \d{4}$"
)
STANDALONE_TITLE_RE = re.compile(
    r"^(HIT Policy Committee|Health IT Policy Committee|HIT Policy Committee, .*)$"
)

# Not real speakers even though they match the name shape.
HEADER_STOPLIST = {
    "public comment", "roll call", "agenda", "action item", "next steps",
    "altarum", "audio", "operator", "recording",
    # org-name fragments from wrapped lines, not people
    "healthcare", "technology", "foundation", "university", "corporation",
    "administration", "association", "committee", "moderator", "conclusion",
    "informatics", "nursing", "medicine", "coordinator", "prevention",
}

CONNECTORS = {"and", "of", "for", "the", "&", "to", "at", "in", "on"}


def _clean_lines(text):
    out = []
    for raw in text.split("\n"):
        line = raw.strip().lstrip("﻿")
        if PAGE_NUM_RE.match(line):
            continue
        if line in JUNK_EXACT:
            continue
        if line.startswith(JUNK_PREFIX):
            continue
        if STANDALONE_DATE_RE.match(line):
            continue
        if STANDALONE_TITLE_RE.match(line):
            continue
        out.append(line)
    return out


def _looks_like_dash_header(line):
    """Return list of segments if line looks like 'Name – seg [– seg]'."""
    if not (5 < len(line) <= 220) or line.count("http") or "?" in line:
        return None
    segs = [s for s in DASH_SPLIT.split(line) if s]
    if not (2 <= len(segs) <= 4):
        return None
    name = segs[0].strip()
    if len(name) > 60:
        return None
    if not (NAME_RE.match(name) or UNIDENTIFIED_RE.match(name)):
        return None
    if name.lower() in HEADER_STOPLIST:
        return None
    # Name tokens (before any credential comma) must be capitalized words,
    # which rejects prose fragments like "Okay. I think".
    for tok in name.split(",")[0].split():
        if not (tok[0].isupper() or tok in ("van", "de", "von")):
            return None
    # Segments after the name shouldn't read like prose (sentences with
    # lowercase starts or sentence-ending punctuation mid-line).
    for seg in segs[1:]:
        if len(seg) > 110:
            return None
        if re.search(r"[.!?]\s+[a-z]", seg):
            return None
        if seg and seg[0].islower() and seg.split()[0] not in CONNECTORS:
            return None
    return segs


def _is_header_continuation(prev_segs, line):
    """Wrapped org name: short title-case fragment finishing the last segment."""
    if not line or len(line) > 60:
        return False
    if len(prev_segs[-1]) < 40:
        return False
    words = line.split()
    if len(words) > 5:
        return False
    if re.search(r"[.!?,;:]$", line):
        return False
    for w in words:
        if not (w[0].isupper() or w.lower() in CONNECTORS):
            return False
    return True


# Comma headers (mid-2009 era): "Judy Sparrow, ONC" / "Dr. Paul Tang, Palo
# Alto Medical Foundation". No trailing period (roll-call echoes of the same
# text inside utterances DO end with a period, which distinguishes them).
COMMA_HEADER_RE = re.compile(
    r"^(?:Dr\.\s+)?"
    r"([A-Z][A-Za-z'’.\-]+(?:\s+[A-Z][A-Za-z'’.\-]+){1,3}),\s+"
    r"([A-Z][A-Za-z&'’.\-]*(?:\s+\S+){0,9})$"
)


def _looks_like_comma_header(line):
    if not line or len(line) > 80 or re.search(r"[.!?;:]$", line):
        return False
    m = COMMA_HEADER_RE.match(line)
    if not m:
        return False
    if m.group(1).lower() in HEADER_STOPLIST:
        return False
    # Org tokens: capitalized words or lowercase connectors only.
    for tok in m.group(2).split():
        if not (tok[0].isupper() or tok[0].isdigit() or tok.lower() in CONNECTORS
                or tok.lower() in ("from", "with")):
            return False
    return True


def _looks_like_bare_name_header(line, next_line):
    if not line or len(line) > 45:
        return False
    if line.lower() in HEADER_STOPLIST:
        return False
    words = line.split()
    if len(words) > 6:
        return False
    if re.search(r"[.!?,;:]$", line):
        return False
    if UNIDENTIFIED_RE.match(line):
        return True
    if not NAME_RE.match(line):
        return False
    # Every word capitalized (allowing honorific periods / hyphenated names)
    for w in words:
        if not w[0].isupper():
            return False
    # Must be followed by prose, not another short line (participants list).
    return bool(next_line) and len(next_line) > 30


def parse_utterances(text):
    """Return list of (speaker_raw_header, utterance_text)."""
    lines = _clean_lines(text)

    # Choose grammar by header density: a file's participants list often uses
    # a different separator style than its body headers, so pick whichever
    # grammar matches the most lines (dash wins ties; a bare-name file's
    # speaker turns vastly outnumber its comma-style participants list).
    dash_headers = sum(1 for l in lines if _looks_like_dash_header(l))
    comma_headers = sum(1 for l in lines if _looks_like_comma_header(l))
    bare_headers = sum(
        1 for i, l in enumerate(lines)
        if _looks_like_bare_name_header(l, lines[i + 1] if i + 1 < len(lines) else "")
    )
    best = max(dash_headers, comma_headers, bare_headers)
    use_dash = best >= 10 and dash_headers == best
    use_comma = not use_dash and best >= 10 and comma_headers == best

    utterances = []
    speaker = None
    buf = []

    def flush():
        nonlocal buf
        if speaker is not None:
            body = " ".join(l for l in buf if l).strip()
            body = re.sub(r"\s+", " ", body)
            if body:
                utterances.append((speaker, body))
        buf = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if use_dash:
            segs = _looks_like_dash_header(line)
            if segs:
                header = line
                if i + 1 < n and _is_header_continuation(segs, lines[i + 1]):
                    header = header + " " + lines[i + 1]
                    i += 1
                flush()
                speaker = re.sub(r"\s+", " ", header).strip()
                i += 1
                continue
        elif use_comma:
            if _looks_like_comma_header(line):
                flush()
                speaker = line
                i += 1
                continue
        else:
            nxt = lines[i + 1] if i + 1 < n else ""
            if _looks_like_bare_name_header(line, nxt):
                flush()
                speaker = line
                i += 1
                continue
        buf.append(line)
        i += 1
    flush()
    return utterances


if __name__ == "__main__":
    import sys
    from collections import Counter
    text = open(sys.argv[1], encoding="utf8").read()
    utts = parse_utterances(text)
    print(f"{len(utts)} utterances")
    c = Counter(u[0] for u in utts)
    for spk, cnt in c.most_common(15):
        print(f"  {cnt:4d}  {spk[:90]}")
