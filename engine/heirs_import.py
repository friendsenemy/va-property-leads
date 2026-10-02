"""
List of Heirs / real-estate affidavit import: looked up by hand, joined by the tool.

  python -m engine.heirs_import

The Clerk's Secure Remote Access agreement bars automated and bulk access, so the
index is searched by a person, once a month. A List of Heirs (Va. Code 64.2-509)
is recorded in the WILL BOOK when someone qualifies as personal representative or
probates a will, and is indexed under the decedent and each heir. A real-estate
affidavit (64.2-510) is recorded the same way for an intestate decedent.

Put what you find in data/heirs/import.csv, one line per filing:

  decedent_last,decedent_first,decedent_middle,suffix,date_of_death,type,recorded,book,page,heirs
  heirs is "Name (relationship) address; Name (relationship) address; ..."

The decedent is then matched against every owner on title exactly as an obituary
is (same identity scoring), and the heirs ride along on the match so the lead
shows who to contact. This is a confirmation and heir-finding layer: it only
exists when somebody filed.
"""
import csv
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("heirs_import")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "heirs", "import.csv")
DEST = os.path.join(ROOT, "data", "obits", "clerk-filings.json")
HEADER = "decedent_last,decedent_first,decedent_middle,suffix,date_of_death,type,recorded,book,page,heirs\n"


def run():
    os.makedirs(os.path.dirname(SRC), exist_ok=True)
    if not os.path.exists(SRC):
        open(SRC, "w").write("# One line per List of Heirs or heirship affidavit found in the Clerk's index.\n"
                             "# date_of_death and recorded are YYYY-MM-DD. heirs: Name (relationship) address; Name ...\n" + HEADER)
    rows = []
    with open(SRC, newline="") as f:
        for n, row in enumerate(csv.DictReader(l for l in f if l.strip() and not l.startswith("#")), 1):
            g = lambda k: (row.get(k) or "").strip()
            if not g("decedent_last") or not g("decedent_first"):
                continue
            heirs = [h.strip() for h in g("heirs").split(";") if h.strip()]
            ref = " ".join(x for x in (g("type") or "List of Heirs", f"WB {g('book')}" if g("book") else "", f"PG {g('page')}" if g("page") else "") if x)
            rows.append({"id": n, "first": g("decedent_first"), "middle": g("decedent_middle"), "last": g("decedent_last"),
                         "suffix": g("suffix").strip("."), "death_date": g("date_of_death"), "age": None, "place": "King George",
                         "url": "", "source": f"Clerk's will book ({ref})", "heirs": heirs, "recorded": g("recorded")})
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    json.dump({"source": "Circuit Court Clerk, entered by hand", "count": len(rows), "rows": rows}, open(DEST, "w"), indent=0)
    log.info("%s clerk filings ready for the death match", len(rows))
    return rows


if __name__ == "__main__":
    run()
