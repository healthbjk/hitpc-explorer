"""Keyword-family topic definitions. Each family is a list of compiled
regexes; an utterance is tagged with the family if any regex matches.

Case matters for acronyms (HIE, MU, Epic) to avoid false hits on ordinary
words; phrases match case-insensitively.
"""

import re


def _ci(p):
    return re.compile(p, re.I)


def _cs(p):
    return re.compile(p)


TOPICS = {
    "nhin": [
        _cs(r"\bNH?w?IN\b"),          # NHIN / NwIN typo forms
        _cs(r"\bNwHIN\b"),
        _ci(r"nationwide health information network"),
        _ci(r"national health information network"),
        _cs(r"\bCONNECT\b"),          # federal NHIN CONNECT software
    ],
    "hie": [
        _cs(r"\bHIEs?\b"),
        _ci(r"health information exchange"),
        _ci(r"\bRHIOs?\b"),
        _ci(r"regional health information organi[sz]ation"),
    ],
    "direct": [
        _ci(r"\bdirect project\b"),
        _ci(r"\bNH?w?IN direct\b"),
        _ci(r"\bdirect (protocol|messag\w+|exchange|address\w*)\b"),
    ],
    "interoperability": [
        _ci(r"interoperab"),
    ],
    "meaningful_use": [
        _ci(r"meaningful use"),
        _cs(r"\bMU\b"),
    ],
    "privacy_security": [
        _ci(r"\bprivacy\b"),
        _ci(r"\bsecurity\b"),
        _ci(r"tiger team"),
        _ci(r"\bHIPAA\b"),
        _ci(r"\bconsent\b"),
    ],
    "certification": [
        _ci(r"certif"),
        _ci(r"\bCCHIT\b"),
    ],
    "patient_engagement": [
        _ci(r"patient engagement"),
        _ci(r"patient access"),
        _ci(r"blue button"),
        _ci(r"view,? download,? (and |& )?transmit"),
        _cs(r"\bVDT\b"),
        _ci(r"patient portal"),
        _ci(r"\bPHRs?\b"),
        _ci(r"personal health record"),
    ],
    "info_blocking": [
        _ci(r"information blocking"),
        _ci(r"data blocking"),
        _ci(r"data hoarding"),
    ],
    "standards": [
        _ci(r"\bstandards?\b"),
        _cs(r"\bHL7\b"),
        _cs(r"\bCCDA?\b"),
        _ci(r"\bFHIR\b"),
    ],
    "quality_measures": [
        _ci(r"quality measur"),
        _ci(r"clinical quality"),
        _cs(r"\bCQMs?\b"),
    ],
    "epic_mention": [
        _cs(r"\bEpic\b"),
        _cs(r"\bEPIC\b"),
    ],
    "vendor_mention": [
        _ci(r"\bCerner\b"),
        _ci(r"\bMeditech\b"),
        _ci(r"\bAllscripts\b"),
        _ci(r"\bathenahealth\b"),
        _ci(r"eClinicalWorks"),
        _ci(r"\bMcKesson\b"),
        _ci(r"\bSurescripts\b"),
        _ci(r"\bGE Healthcare\b"),
        _ci(r"\bCentricity\b"),
        _ci(r"\bNextGen\b"),
        _ci(r"CommonWell"),
    ],
}


def tag(text):
    """Return set of topic keys matching this text."""
    found = set()
    for topic, patterns in TOPICS.items():
        for rx in patterns:
            if rx.search(text):
                found.add(topic)
                break
    return found
