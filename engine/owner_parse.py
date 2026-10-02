"""
Owner classification for King George County CAMA owner strings.

The county stores the owner in LNAM (35 chars, "LAST FIRST MIDDLE", parties
separated by ";") with an overflow / second-owner / care-of line in FNAM.
Virginia's survivorship shorthand is "A OR B".

classify() puts every owner into exactly one type, in the priority order of
docs/HANDOFF (first match wins):

  1 ESTATE   estate / heirs / deceased / life estate / executor
  2 ET_AL    et al, et als, et ux
  3 TRUST    trustee, trust, revocable ...
  4 CHURCH   church-shaped phrases only (CHURCH, TEMPLE, PARISH are surnames)
  5 CEMETERY
  6 GOVERNMENT
  7 ASSOCIATION  HOA / club / lodge / post / nonprofit
  8 BUSINESS LLC / INC / CORP / LP / bank ...
  9 INDIVIDUAL
  - BLANK

The raw string is always kept next to the type.
"""
import re

TYPES = ("ESTATE", "ET_AL", "TRUST", "CHURCH", "CEMETERY", "GOVERNMENT",
         "ASSOCIATION", "BUSINESS", "INDIVIDUAL", "BLANK")

_SUFFIXES = {"SR", "JR", "II", "III", "IV"}


def clean(s):
    return re.sub(r"\s+", " ", (s or "").upper().replace("’", "'")).strip()


def care_of(fnam):
    """FNAM that is a mail handler, not an owner: '%GREGORY K HART', 'C/O JOHN JANNEY'."""
    f = clean(fnam)
    m = re.match(r"^(?:%|C/O\b|ATTN:?|ATTENTION:?)\s*(.*)$", f)
    return m.group(1).strip() if m else ""


def owner_text(lnam, fnam):
    """One display string for the owner, care-of line removed."""
    l, f = clean(lnam), clean(fnam)
    if care_of(f):
        f = ""
    # a care-of can also trail the owner line
    l = re.split(r"\s(?:C/O|%)\s?", l)[0].strip()
    return (l + (" " if l and f else "") + f).strip()


# ---- 1. estate family -------------------------------------------------------
_REAL_ESTATE = re.compile(r"\bREAL\s+ESTATE\b|\bREALESTATE\b")
_LIFE = re.compile(r"\bLIFE\s+(?:ESTATE|EST\b|INT(?:EREST)?\b|TENANT)|\bL\s?/\s?E\b|\bL\s+EST\b|\bFOR\s+LIFE\b|\bLIFE\s+RIGHTS?\b")
_HEIRS = re.compile(r"\bHEIRS?\b")
_DECEASED = re.compile(r"\bDEC'?D\b|\bDECEASED\b")
_FIDUCIARY = re.compile(r"\bEXEC(?:UTOR|UTRIX|UTORS)?\b(?!\s+SUITES)|\bEXR\b|\bEXRX\b|\bADM(?:INISTRAT(?:OR|RIX))\b|\bADMR\b|\bPERSONAL REP")
# "ESTATE" singular, or "EST" closing a party / before OF. "ESTATES" (subdivision
# names) and "EST.PROP.OWNERS" never match.
_ESTATE = re.compile(r"\bESTATE\b(?!S)|\bEST\s+OF\b|\bEST\s*(?:;|$)")

# ---- 2. et al ---------------------------------------------------------------
_ET_AL = re.compile(r"\bET\s?ALS?\b|\bET\s?UX\b|\bET\s?VIR\b")

# ---- 3. trust ---------------------------------------------------------------
_TRUST = re.compile(r"\bTRS?\b|\bTRUSTEES?\b|\bTRUST\b|\bTRST\b|\bREVOCABLE\b|\bIRREVOCABLE\b|\bREV\s+(?:LIV|TR)|\bLIVING\s+TR")
_BANK_TRUST = re.compile(r"\bBANK\b|\bTRUST\s+(?:CO|COMPANY|N\.?A)\b|\bN\.?A\.?$")

# ---- 4. church: organisational phrases, never a bare word -------------------
_CHURCH = re.compile(
    r"\b(?:BAPTIST|METHODIST|EPISCOPAL|PRESBYTERIAN|LUTHERAN|CATHOLIC|PENTECOSTAL|APOSTOLIC|HOLINESS|"
    r"A\s?M\s?E|U\s?M|UNITED METHODIST|CHRISTIAN|COMMUNITY|BIBLE|GOSPEL|UNION|ZION|ASSEMBLY OF GOD|"
    r"SEVENTH DAY ADVENTIST|EVANGELICAL|FELLOWSHIP|MISSIONARY|FREE WILL|FULL GOSPEL|TABERNACLE)\b.{0,25}\bCHURCH\b"
    r"|\bCHURCH\s+OF\b|\bCHURCH\s+(?:TRUSTEES|TRS|INC)\b|\b(?:TRUSTEES|TRS|DEACONS)\b.{0,40}\bCHURCH\b"
    r"|\bCHURCH\b.{0,30}\b(?:TRUSTEES|TRS)\b|^(?:ST|SAINT)\.?\s.{0,30}\bCHURCH\b|\b(?:MT|MOUNT)\.?\s.{0,25}\bCHURCH\b"
    r"|\bMINISTR(?:Y|IES)\b|\bCONGREGATION\b|\bDIOCESE\b|\bBISHOP\s+OF\b|\bPARISH\s+(?:OF|CHURCH)\b"
    r"|\bTABERNACLE\b|\bCHAPEL\s+(?:OF|INC)\b|\bBAPTIST\s+(?:ASSOC|ASSN|ASSOCIATION|CONVENTION)\b"
    r"|\b(?:TRUSTEES|TRS)\b.{0,40}\b(?:BAPTIST|METHODIST|EPISCOPAL|PRESBYTERIAN|LUTHERAN|PARISH|PAR\.)|\bBAPTIST\s+CH\b"
    r"|\bKINGDOM\s+HALL\b|\bJEHOVAH'?S?\s+WITNESS|\bSYNAGOGUE\b|\bMOSQUE\b|\bTEMPLE\s+OF\b|\bCHURCH$"
    r"|(?<!^)(?<!\bOR )(?<!& )(?<!\bAND )\bCHURCH\b(?=\s+[A-Z]{2,}\s+(?:OF|IN)\b)")
# "CHURCH$" as the last word catches "X CHURCH" names; a person named CHURCH is
# "CHURCH JOHN A" (surname first), so the word is never last for a person.

_CEMETERY = re.compile(r"\bCEMETERY\b|\bCEMETARY\b|\bBURIAL\b|\bGRAVEYARD\b|\bMEMORIAL\s+(?:PARK|GARDENS?)\b")

_GOVERNMENT = re.compile(
    r"\bCOUNTY\s+OF\b|\bKING\s+GEORGE\s+(?:COUNTY|CO)\b(?!.*\b(?:LLC|INC|CLUB|ASSOC|FARM BUREAU|RURITAN|LIONS|MASONIC|YMCA|HISTORICAL|FIRE|RESCUE|LITTLE LEAGUE)\b)"
    r"|\bBOARD\s+OF\s+SUP|\bBD\s+OF\s+SUP|\bSANITARY\s+DIST|\bAUTHORITY\b|\bKING\s+GEORGE\s+SCHOOL|\bSCHOOL\s+BOARD\b|\bSERVICE\s+AUTHORITY\b"
    r"|\bCOMMONWEALTH\b|\bUNITED\s+STATES\b|\bU\s?S\s?A$|\bU\.S\.A\b|\bUS\s+(?:GOVERNMENT|NAVY|GOVT)\b|\bVDOT\b"
    r"|\bDEPT\.?\s+OF\b|\bDEPARTMENT\s+OF\b|\bNAVY\b|\bTOWN\s+OF\b|\bCITY\s+OF\b|\bSTATE\s+OF\b"
    r"|\bVIRGINIA\s+(?:DEPT|DEPARTMENT|OUTDOORS)\b|\bHOUSING\s+AUTHORITY\b|\bPUBLIC\s+SCHOOLS\b"
    r"|\bSECRETARY\s+OF\b|\bVETERANS\s+AFFAIRS\b|\bFEDERAL\s+(?:NATIONAL|HOME)\b")

_ASSOCIATION = re.compile(
    r"\bHOMEOWNERS?\b|\bHOME\s?OWNERS?\b|\bHOA(?:\s+INC)?$|\bPOA(?:\s+INC)?$|\bPROP(?:ERTY)?\.?\s*OWNERS?\b|\bOWNERS?\s+ASS"
    r"|\bASSOC(?:IATION)?\b|\bASSN\b|\bCIVIC\b|\b(?:COUNTRY|HUNT|GUN|YACHT|BOAT|SWIM|GARDEN|GOLF|SPORTSMANS?|RURITAN|LIONS|ROTARY)\s+CLUB\b|\bCLUB\s+(?:INC|OF)\b|\bCLUB$"
    r"|\bLODGE\s+(?:NO|#|\d|INC)|\bMASONIC\b|\bAMERICAN\s+LEGION\b|\bPOST\s+(?:NO\.?\s*)?\d+\b|\bV\.?F\.?W\b|\bRURITAN\b"
    r"|\bVOL(?:UNTEER)?\.?\s+FIRE\b|\bFIRE\s+(?:DEPT|DEPARTMENT|COMPANY|CO)\b|\bRESCUE\s+SQUAD\b|\bSOCIETY\b"
    r"|\bFOUNDATION$|\bFOUNDATION\s+(?:INC|OF)\b|\bLEAGUE\b|\bCONSERVANCY\b|\bLAND\s+TRUST\b|\bHABITAT\s+FOR\b|\bYMCA\b|\bUNIVERSITY\b|\bCOLLEGE\s+OF\b|\bFDN\b|\bCOMMUNITY\s+ASSOC")

_BUSINESS = re.compile(
    r"\bL\.?\s?L\.?\s?C\b|\bINC\b|\bINCORPORATED\b|\bCORP\b|\bCORPORATION\b|\bCO$|\bCO\s+(?:INC|LLC)\b|\bCOMPANY\b|\bLTD\b|\bL\.?P\.?$|\bL\.?L\.?P\b|\bL\.?C\.?$"
    r"|\bPARTN|\bLIMITED\b|\bLIMIT\s+FAMILY\b|\bMGT\b|\bSALES\b|\bRENTALS?\b|\bHOLDINGS?\b|\bPROPERTIES\b|\bENTERPRISES?\b|\bBANK\b|\bMORTGAGE\b|\bINVESTMENTS?\b"
    r"|\bVENTURES?\b|\bDEVELOPMENT\b|\bDEVELOPERS?\b|\bBUILDERS?\b|\bHOMES\b|\bREALTY\b|\bREAL\s+ESTATE\b|\bGROUP\b|\bASSOCIATES\b"
    r"|\bFARMS?\s+(?:INC|LLC)\b|\bELECTRIC\b|\bTELEPHONE\b|\bRAILROAD\b|\bPOWER\b|\bUTILIT|\bCOOPERATIVE\b|\bCO-?OP\b|\bN\.?A\.?$"
    r"|\bCREDIT\s+UNION\b|\bSAVINGS\b|\bFINANCIAL\b|\bCAPITAL\b|\bMANAGEMENT\b|\bSERVICES\b|\bCONSTRUCTION\b|\bLAND\s+(?:CO|COMPANY)\b"
    r"|\bVERIZON\b|\bDOMINION\b|\bCOMCAST\b|\bWAL-?MART\b|\bSTORES?\b|\bSUITES\b|\bCENTER\b|\bAUTO\b|\bMARINA\b|\bCAMPGROUND\b|\bTIMBER\b")


def estate_subtype(text):
    """'ESTATE' | 'HEIRS' | 'LIFE_ESTATE' | 'FIDUCIARY' | '' for the estate family."""
    t = _REAL_ESTATE.sub(" REALTY ", text)
    if _HEIRS.search(t):
        return "HEIRS"
    no_life = _LIFE.sub(" ", t)
    if _ESTATE.search(no_life) or _DECEASED.search(no_life):
        return "ESTATE"
    if _LIFE.search(t):
        return "LIFE_ESTATE"
    if _FIDUCIARY.search(t):
        return "FIDUCIARY"
    return ""


def is_church(text):
    return bool(_CHURCH.search(text))


def classify(lnam, fnam=""):
    """Return (type, subtype). First rule that matches wins."""
    text = owner_text(lnam, fnam)
    if not text:
        return "BLANK", ""
    sub = estate_subtype(text)
    # "LILY PAD ESTATE LLC" is a company; "ESTATE OF X" / "X HEIRS" never is.
    if sub == "ESTATE" and re.search(r"\bL\.?L\.?C\b|\bINC\b|\bCORP\b", text) and not re.search(r"\bEST(?:ATE)?\s+OF\b", text):
        sub = ""
    if sub:
        return "ESTATE", sub
    if re.search(r"\b(?:TRUSTEES|TRS)\s+OF\b.{0,40}\b(?:CHURCH|PARISH|PAR\.)", text):
        return "CHURCH", ""
    if _ET_AL.search(text):
        return "ET_AL", ""
    if _TRUST.search(text):
        # "TRUSTEES OF MT CARMEL BAPTIST CHURCH" is a church held by trustees,
        # and "... BANK & TRUST CO" is a bank: both are named exceptions.
        if is_church(text):
            return "CHURCH", ""
        if _CEMETERY.search(text):
            return "CEMETERY", ""
        if _BANK_TRUST.search(text) and not re.search(r"\bTRUSTEES?\b|\bTRS?\b", text):
            return "BUSINESS", "BANK"
        if re.search(r"\bLAND\s+TRUST\b|\bCONSERVANCY\b", text) and _ASSOCIATION.search(text) and not re.search(r"\bTRUSTEES?\b|\bTRS?\b", text):
            return "ASSOCIATION", ""
        return "TRUST", ""
    # An LLC/INC marker beats a church-shaped word ("FOUNDATION PROPERTIES LLC",
    # "CHURCH HILL LLC"), but an incorporated church is still a church.
    if is_church(text) and not re.search(r"\bL\.?L\.?C\b|\bPROPERTIES\b|\bHOLDINGS\b", text):
        return "CHURCH", ""
    if _CEMETERY.search(text):
        return "CEMETERY", ""
    if _GOVERNMENT.search(text):
        return "GOVERNMENT", ""
    if _ASSOCIATION.search(text) and not re.search(r"\bL\.?L\.?C\b|\bPROPERTIES\s+(?:LLC|INC)\b", text):
        return "ASSOCIATION", ""
    if _BUSINESS.search(text):
        return "BUSINESS", "BANK" if re.search(r"\bBANK\b|\bMORTGAGE\b|\bN\.?A\.?$|\bCREDIT UNION\b", text) else ""
    return "INDIVIDUAL", ""


# ---- people -----------------------------------------------------------------
_NOISE = re.compile(
    r"\bLIFE\s+(?:ESTATE|EST|INT(?:EREST)?|TENANT)\b|\bL\s?/\s?E\b|\bL\s+EST\b|\bFOR\s+LIFE(?:\s+TH)?\b|\bTHEN\s+TO\b"
    r"|\bHEIRS?\s+OF\b|\bHEIRS?\b|\bDEC'?D\b|\bDECEASED\b|\bET\s?ALS?\b|\bET\s?UX\b|\bET\s?VIR\b|\bTRUSTEES?\b|\bTRS?\b"
    r"|\bEXEC(?:UTOR|UTRIX)?\b|\bADMR?\b|\bSURV(?:IVOR|IVING)?\b|\bREMAINDER(?:MAN|MEN)?\b|\bJTWROS\b|\bT/E\b|\bH/W\b"
    r"|\bJT\b|\bREV\b|\bGUARDIANS?\s+OF\b|\(?\d+/\d+\s*INT\.?\)?|\(?\d+\s?%\)?|\bINT\.")
_ESTATE_WORDS = re.compile(r"\bESTATE\s+OF\b|\bEST\s+OF\b|\bESTATE\b|\bEST\b")
_TRUST_NAME = re.compile(r"\b(?:REVOCABLE|IRREVOCABLE|LIVING|FAMILY)?\s*(?:REVOCABLE|IRREVOCABLE|LIVING|FAMILY)?\s*\bTRUST\b.*$|\bOF\s+THE\b|^THE\s+")
_JOIN = re.compile(r"\s+(?:OR|0R|AND|AND/OR)\s+|\s*&\s*|\s*,\s*")
_WORD = re.compile(r"[A-Z][A-Z'\-]*")

# Learned from the county's own owner list (learn_names) so "PENDER ELIZA" after a
# joiner reads as LAST FIRST and "JACKIE LEE" as FIRST MIDDLE.
_GIVEN, _SURNAME = {}, {}


def learn_names(owner_texts):
    """Count first-position (surname) and second-position (given) tokens of plain names."""
    _GIVEN.clear(); _SURNAME.clear()
    for t in owner_texts:
        toks = _WORD.findall(clean(t).split(";")[0])
        if 2 <= len(toks) <= 4 and not _BUSINESS.search(clean(t)):
            _SURNAME[toks[0]] = _SURNAME.get(toks[0], 0) + 1
            _GIVEN[toks[1]] = _GIVEN.get(toks[1], 0) + 1


def _is_given(tok):
    g, sn = _GIVEN.get(tok, 0), _SURNAME.get(tok, 0)
    return g >= 2 and g >= sn


def _mk(last, given, suffix):
    given = [g for g in given if g]
    if not given or len(last) < 2:
        return None
    first, middle = given[0], " ".join(given[1:])
    if len(first) == 1 and len(given) > 1 and len(given[1]) > 1:      # "NORRIS C WILLIAM"
        first, middle = given[1], given[0]
    return {"last": last, "first": first, "middle": middle, "suffix": suffix,
            "name": " ".join(x for x in (first, middle, last, suffix) if x)}


def _person(tokens, default_last="", natural=False):
    suffix = next((t for t in tokens if t in _SUFFIXES), "")
    toks = [t for t in tokens if t not in _SUFFIXES and _WORD.fullmatch(t)]
    if not toks:
        return None
    if natural and len(toks) >= 2 and len(toks[-1]) > 1 and not (
            _SURNAME.get(toks[0], 0) > _GIVEN.get(toks[0], 0) and _GIVEN.get(toks[1], 0) > 0):
        return _mk(toks[-1], toks[:-1], suffix)          # "LEONARD BLAND", "JEFFERY A TEMPLE"
    if default_last:
        if len(toks) == 1:
            return _mk(default_last, toks, suffix)
        own = len(toks[1]) > 1 and (not _is_given(toks[0]) and (len(toks) >= 3 or _is_given(toks[1]) or "-" in toks[0])) \
            or (len(toks) >= 3 and _SURNAME.get(toks[0], 0) > _GIVEN.get(toks[0], 0)) \
            or toks[0] == default_last
        if not own:
            return _mk(default_last, toks, suffix)       # "& PATRICIA F", "OR JACKIE LEE"
    if len(toks) < 2:
        return None
    # A lone party written FIRST MIDDLE LAST ("ROBERT MILTON CURRY JR ESTATE")
    if not default_last and len(toks) >= 3 and len(toks[-1]) > 1 and _GIVEN.get(toks[0], 0) >= 20 \
            and _GIVEN.get(toks[0], 0) > 3 * max(1, _SURNAME.get(toks[0], 0)) \
            and _SURNAME.get(toks[-1], 0) >= _GIVEN.get(toks[-1], 0):
        return _mk(toks[-1], toks[:-1], suffix)
    return _mk(toks[0], toks[1:], suffix)


def split_people(lnam, fnam=""):
    """
    Every natural person named in the owner text; each one is matched to the death
    sources separately. 'ELLIS MISTY D OR JACKIE LEE' -> Misty D Ellis, Jackie Lee
    Ellis. Returns [] for organisations.
    """
    typ, _ = classify(lnam, fnam)
    if typ in ("CHURCH", "CEMETERY", "GOVERNMENT", "ASSOCIATION", "BUSINESS", "BLANK"):
        return []
    l, f = clean(lnam), clean(fnam)
    if care_of(f):
        f = ""
    l = re.split(r"\s(?:C/O|%)\s?", l)[0]
    # LNAM is 35 characters; a one-word FNAM is the overflow of the last name in it.
    if f and len(f.split()) == 1 and not re.search(r"(?:\bOR|\b0R|\bAND|&)\s*$", l):
        l, f = l + " " + f, ""
    segments = l.split(";") + ([f] if f else [])
    people, seen = [], set()
    last_surname = ""
    for seg in segments:
        natural = bool(re.search(r"\b(?:ESTATE|EST)\s+OF\s+[A-Z]", seg)) or bool(re.search(r"\bTRUST\b", seg) and not re.search(r"\bTR\b|\bTRUSTEES?\b", seg))
        s = _TRUST_NAME.sub(" ", seg) if re.search(r"\bTRUST\b", seg) else seg
        s = _ESTATE_WORDS.sub(" & " if natural else " ", s)
        s = _NOISE.sub(" ", s)
        s = re.sub(r"[.()]", " ", s)
        s = re.sub(r"\s+", " ", s).strip(" ,&")
        s = re.sub(r"\s(?:OR|0R|AND)$", "", s)
        s = re.sub(r"^(?:OF|THE)\s+", "", s)
        if not s or re.search(r"\d", s) or _BUSINESS.search(s) or _GOVERNMENT.search(s):
            continue
        first_in_seg = True
        for part in _JOIN.split(s):
            toks = part.replace(",", " ").split()
            if not toks or len(toks) > 6:
                continue
            p = _person(toks, default_last="" if first_in_seg else last_surname, natural=natural)
            first_in_seg = False
            if not p:
                continue
            last_surname = p["last"]
            key = frozenset((p["last"], p["first"]))
            if key not in seen:
                seen.add(key)
                people.append(p)
    return people[:8]
