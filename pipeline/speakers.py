"""Normalize raw speaker headers into canonical people and organizations.

Raw headers vary per era and transcription vendor:
    "Judy Faulkner – Epic Systems – Founder"
    "Judy Faulkner, MS – Founder and Chief Executive Officer – EPIC Systems Corporation"
    "Judy Faulkner, Epic"
    "Judith Faulkner"
"""

import re

from .parse import DASH_SPLIT

HONORIFICS = re.compile(r"^(Dr|Mr|Ms|Mrs|Prof)\.?\s+", re.I)

CREDENTIALS = {
    "md", "phd", "ph.d", "ph.d.", "mph", "mba", "jd", "rn", "ms", "ma", "msc",
    "scm", "mhs", "mpa", "facp", "fache", "faap", "facmi", "abfp", "faafp",
    "cphims", "pmp", "llm", "rn-bc", "msn", "bsn", "md(hon)", "np", "pa",
    "esq", "cpa", "mssw", "mhsa", "dr", "iii", "jr", "sr", "unac/uhcp",
}

# Explicit person aliases: transcription typos and nickname variants that the
# automatic (last name + first-name prefix) merge can't catch.
NAME_ALIASES = {
    "judy faulkner": "Judith Faulkner",
    "david landsky": "David Lansky",
    "devin mcgraw": "Deven McGraw",
    "devon mcgraw": "Deven McGraw",
    "christine beck": "Christine Bechtel",
    "mark probst": "Marc Probst",
    "micky tripathy": "Micky Tripathi",
    "frank nemic": "Frank Nemec",
    "farzad mostashari": "Farzad Mostashari",
    "fazad mostashari": "Farzad Mostashari",
    "unidentified speaker": "(unidentified)",
    "unidentified male": "(unidentified)",
    "unidentified female": "(unidentified)",
    "unidentified participant": "(unidentified)",
}

NICKNAMES = {
    "judy": "judith", "mike": "michael", "bob": "robert", "rob": "robert",
    "bill": "william", "dave": "david", "tom": "thomas", "dick": "richard",
    "rick": "richard", "jim": "james", "joe": "joseph", "chris": "christopher",
    "chuck": "charles", "ted": "theodore", "tony": "anthony", "liz": "elizabeth",
    "beth": "elizabeth", "kathy": "katherine", "kate": "katherine",
    "deb": "deborah", "debbie": "deborah", "steve": "steven", "greg": "gregory",
    "doug": "douglas", "dan": "daniel", "matt": "matthew", "pat": "patricia",
}

# Organization canonicalization: first regex that matches wins.
ORG_RULES = [
    (re.compile(r"\bepic\b", re.I), "Epic"),
    (re.compile(r"\bcerner\b", re.I), "Cerner"),
    (re.compile(r"office of the national coordinator|\bonc\b", re.I), "ONC"),
    (re.compile(r"centers for medicare|\bcms\b", re.I), "CMS"),
    (re.compile(r"department of hhs|health (and|&) human services|\bhhs\b", re.I), "HHS"),
    (re.compile(r"veterans (affairs|administration)|\bva\b(?!\w)", re.I), "VA"),
    (re.compile(r"centers for disease|\bcdc\b", re.I), "CDC"),
    (re.compile(r"social security", re.I), "SSA"),
    (re.compile(r"palo alto medical", re.I), "Palo Alto Medical Foundation"),
    (re.compile(r"pacific business group", re.I), "Pacific Business Group on Health"),
    (re.compile(r"center for democracy", re.I), "Center for Democracy & Technology"),
    (re.compile(r"national partnership", re.I), "National Partnership for Women & Families"),
    (re.compile(r"intermountain", re.I), "Intermountain Healthcare"),
    (re.compile(r"kindred", re.I), "Kindred Healthcare"),
    (re.compile(r"institute for family health", re.I), "Institute for Family Health"),
    (re.compile(r"brigham|partners healthcare", re.I), "Brigham & Women's / Partners"),
    (re.compile(r"massachusetts ehealth", re.I), "Massachusetts eHealth Collaborative"),
    (re.compile(r"lance armstrong|fastercures", re.I), "FasterCures / Lance Armstrong Fdn"),
    (re.compile(r"markle", re.I), "Markle Foundation"),
    (re.compile(r"manatt", re.I), "Manatt, Phelps & Phillips"),
    (re.compile(r"kaiser", re.I), "Kaiser Permanente"),
    (re.compile(r"aetna", re.I), "Aetna"),
    (re.compile(r"wellpoint", re.I), "WellPoint"),
    (re.compile(r"intel", re.I), "Intel"),
    (re.compile(r"microsoft", re.I), "Microsoft"),
    (re.compile(r"1199|seiu|service employees", re.I), "SEIU 1199"),
    (re.compile(r"university of minnesota", re.I), "University of Minnesota"),
    (re.compile(r"carnegie mellon", re.I), "Carnegie Mellon University"),
    (re.compile(r"harvard", re.I), "Harvard"),
    (re.compile(r"johns hopkins|bloomberg school", re.I), "Johns Hopkins"),
    (re.compile(r"vanderbilt", re.I), "Vanderbilt"),
    (re.compile(r"dartmouth", re.I), "Dartmouth"),
    (re.compile(r"florida", re.I), "Florida State Legislature"),
    (re.compile(r"denver (public )?health", re.I), "Denver Public Health"),
    (re.compile(r"american enterprise", re.I), "American Enterprise Institute"),
    (re.compile(r"american heart", re.I), "American Heart Association"),
    (re.compile(r"lupus", re.I), "Lupus Foundation of America"),
    (re.compile(r"national cancer|\bnci\b", re.I), "NCI"),
    (re.compile(r"altarum", re.I), "Altarum"),
]

TITLE_WORDS = {
    "director", "officer", "president", "vp", "vice", "chief", "chair",
    "chairman", "dean", "advisor", "adviser", "founder", "ceo", "cio", "cmio",
    "coo", "cto", "lead", "professor", "manager", "consultant", "architect",
    "internist", "physician", "entrepreneur", "businessman", "senior",
    "executive", "fellow", "analyst", "specialist", "liaison", "cofounder",
    "co-founder", "representative", "legislator", "partner", "principal",
}


def _clean_name(name):
    name = HONORIFICS.sub("", name.strip())
    # Drop credential tokens after commas: "Paul Tang, MD, MS" -> "Paul Tang"
    parts = [p.strip() for p in name.split(",")]
    kept = [parts[0]]
    for p in parts[1:]:
        if p.lower().replace(".", "") not in {c.replace(".", "") for c in CREDENTIALS}:
            kept.append(p)
    name = kept[0]
    # Strip stray middle-initial-only periods and collapse space
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _title_score(seg):
    words = re.split(r"[\s,&/]+", seg.lower())
    return sum(1 for w in words if w in TITLE_WORDS)


def normalize_org(seg):
    for rx, canon in ORG_RULES:
        if rx.search(seg):
            return canon
    return re.sub(r"\s+", " ", seg).strip(" .")


def split_header(raw):
    """raw header -> (clean person name, org_guess or None)."""
    raw = raw.strip()
    segs = [s.strip(" .") for s in DASH_SPLIT.split(raw) if s.strip(" .")]
    if len(segs) >= 2:
        name = _clean_name(segs[0])
        rest = segs[1:]
        # Pick the segment that reads least like a job title as the org.
        rest_sorted = sorted(rest, key=_title_score)
        return name, rest_sorted[0]
    # Comma style: "Judy Sparrow, ONC"
    if "," in raw:
        name_part, org_part = raw.split(",", 1)
        cleaned = _clean_name(name_part)
        org = org_part.strip()
        if org.lower().replace(".", "") in {c.replace(".", "") for c in CREDENTIALS}:
            org = None
        return cleaned, org
    return _clean_name(raw), None


class SpeakerRegistry:
    """Accumulates raw headers, resolves canonical people."""

    def __init__(self):
        self.people = {}   # key -> dict(name, orgs Counter)

    @staticmethod
    def _key_for(name):
        low = re.sub(r"\s+", " ", name.lower().replace(".", "")).strip()
        if low in NAME_ALIASES:
            return NAME_ALIASES[low].lower()
        toks = low.split()
        if len(toks) >= 2:
            first, last = toks[0], toks[-1]
            first = NICKNAMES.get(first, first)
            return f"{first} {last}"
        return low

    def observe(self, raw_header):
        from collections import Counter
        name, org = split_header(raw_header)
        key = self._key_for(name)
        rec = self.people.setdefault(key, {"names": Counter(), "orgs": Counter()})
        rec["names"][name] += 1
        if org:
            rec["orgs"][normalize_org(org)] += 1
        return key

    def resolve(self):
        """key -> (canonical display name, canonical org, is_onc_staff)."""
        out = {}
        for key, rec in self.people.items():
            low_key_alias = {v.lower(): v for v in NAME_ALIASES.values()}
            if key in low_key_alias:
                display = low_key_alias[key]
            else:
                display = rec["names"].most_common(1)[0][0]
            org = rec["orgs"].most_common(1)[0][0] if rec["orgs"] else ""
            is_staff = org in ("ONC", "HHS", "Altarum")
            out[key] = (display, org, is_staff)
        return out
