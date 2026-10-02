"""
Delinquency walk through the King George Treasurer's Real Estate Public Inquiry.

  python -m engine.delinquency --mode priority          # board + watch + obituary parcels (~1,100)
  python -m engine.delinquency --mode shard --shard 0   # one quarter of the county
  python -m engine.delinquency --join                   # no network: apply what is on file to the board

How the site works (verified 2026-10-01):
  GET  REPublicInquiry/webform1.aspx  -> redirects to TRdisclaimer (one click-through,
       an SSN / liability statement with no clause on automated or commercial use)
  POST "I Accept These Terms"         -> the inquiry form
  POST "Account No." tab, then Search -> ListTickets.aspx: every tax ticket since 1999
       with its balance. ONE request per parcel.
  The Treasurer's account number is the parcel's PID in the county GIS layer.
  Account numbers were re-used around 2002, so only rows whose Map ID equals the
  parcel's PIN are kept.

Pace: one request, then a 1.5 s pause. The server takes about 3 s per answer, so
the whole county (14,435 parcels) is about 18 hours. It is split into four
shards run on four consecutive nights once a month; each fits a 6-hour job.

Outputs
  data/delinquency/balances.json   every parcel with a past-due balance
  data/delinquency/state.json      when each parcel was last checked (compact)
  data/delinquency/leads.json      the Delinquent tab (opportunities only)
"""
import argparse
import datetime as dt
import html
import json
import logging
import os
import re
import sqlite3
import time

import requests

from engine import config, title_scan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("delinquency")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "delinquency")
BAL, STATE, LEADS = (os.path.join(OUT, n) for n in ("balances.json", "state.json", "leads.json"))
URL = "https://eservices.kinggeorgecountyva.gov/applications/REPublicInquiry/webform1.aspx"
PAUSE_S = 1.5
SHARDS = 4

CLASS_LABEL = {
    "T1": "Sale-eligible: 2+ years unpaid",
    "T2": "Delinquent: prior year unpaid",
    "P1": "Old title, bill mailed elsewhere, taxes unpaid",
}
NEXT_STEP = {
    "T1": "Taxes are unpaid from a year old enough that the county may now sue to sell the property (Va. Code 58.1-3965: "
          "delinquent on December 31 after the second anniversary of the due date). The county must mail a 30-day notice and "
          "publish before filing. The owner can stop it by paying before the sale date or by a payment plan with the "
          "Treasurer; after the sale there is no redemption. Check the balance on the Treasurer's site yourself before you "
          "call, and do not tell an owner a sale is scheduled unless counsel (Sands Anderson) has listed one.",
    "T2": "A prior year's taxes are unpaid, but not yet old enough for the county to sue. This is early. The balance may "
          "be an oversight; confirm it on the Treasurer's site before contacting anyone.",
    "P1": "Nothing on record says this owner has died. The pattern does: title is 40+ years old, the bill goes somewhere "
          "other than the property, and the taxes have stopped being paid. Treat it as a possible unreported death and "
          "verify first: obituary search by name, the Clerk's will book index, and a neighbor or the care-of name.",
}


def fields(page):
    out = {}
    for m in re.finditer(r"<input[^>]*>", page):
        tag = m.group(0)
        n = re.search(r'name="([^"]*)"', tag)
        if n:
            v = re.search(r'value="([^"]*)"', tag)
            t = re.search(r'type="([^"]*)"', tag)
            out[n.group(1)] = (t.group(1) if t else "", html.unescape(v.group(1)) if v else "")
    return out


class Inquiry:
    """One browser-like session held for the whole walk."""

    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = config.USER_AGENT
        self.form = None
        self.open()

    def _post(self, resp, extra, submit):
        f = fields(resp.text)
        data = {k: v[1] for k, v in f.items() if v[0] in ("hidden", "text")}
        data.update(extra)
        data[submit] = f[submit][1]
        time.sleep(PAUSE_S)
        r = self.s.post(resp.url, data=data, timeout=90)
        r.raise_for_status()
        return r

    def open(self):
        r = self.s.get(URL, timeout=90)
        r.raise_for_status()
        if "ctl00$MainContent$btnAccept" in fields(r.text):
            r = self._post(r, {}, "ctl00$MainContent$btnAccept")
        self.form = self._post(r, {}, "ctl00$MainContent$btnAccount")
        if "ctl00$MainContent$txtAccount" not in fields(self.form.text):
            raise RuntimeError("inquiry form not reached; the site flow has changed")

    def tickets(self, account):
        """All ticket rows for one account number, or None if the page is not a ticket list."""
        r = self._post(self.form, {"ctl00$MainContent$txtAccount": str(account)}, "ctl00$MainContent$btnSearch")
        if "ListTickets" not in r.url:
            return None
        return parse_tickets(r.text)


def parse_tickets(page):
    i = page.find('id="ctl00_MainContent_contentbody"')
    body = page[i:page.find('id="contentfooter"')] if i >= 0 else ""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ") for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 10 or not cells[0].strip().startswith("RE"):
            continue
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", cells[4].strip())
        try:
            bal = float(cells[9].replace("$", "").replace(",", "").replace("(", "-").replace(")", "").strip() or 0)
        except ValueError:
            bal = 0.0
        out.append({"year": int(re.sub(r"\D", "", cells[0]) or 0), "ticket": cells[1].strip(), "seq": cells[2].strip(),
                    "due": f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else "",
                    "name": re.sub(r"\s+", " ", cells[5]).strip(), "map": re.sub(r"\s+", "", cells[8]), "balance": bal})
    return out


def sale_eligible_on(due_iso):
    """Va. Code 58.1-3965(A): December 31 following the second anniversary of the due date."""
    d = dt.date.fromisoformat(due_iso)
    return dt.date(d.year + 2, 12, 31)


def summarise(rows, pin_nospace, today):
    """Past-due position for one parcel from its ticket rows."""
    mine = [t for t in rows if t["map"] == pin_nospace] or []
    past = [t for t in mine if t["balance"] > 0 and t["due"] and t["due"] < today.isoformat()]
    if not mine:
        return {"tickets": 0}
    latest = max(mine, key=lambda t: (t["due"], t["seq"]))
    out = {"tickets": len(mine), "name": latest["name"],
           "not_yet_due": round(sum(t["balance"] for t in mine if t["balance"] > 0 and t["due"] >= today.isoformat()), 2)}
    if past:
        oldest = min(t["due"] for t in past)
        out.update({"past_due": round(sum(t["balance"] for t in past), 2), "oldest_due": oldest,
                    "years": sorted({t["year"] for t in past}), "installments": len(past),
                    "sale_eligible": sale_eligible_on(oldest) < today,
                    "sale_eligible_on": sale_eligible_on(oldest).isoformat()})
    return out


def load(path, default):
    return json.load(open(path)) if os.path.exists(path) else default


def targets(mode, shard, rows):
    if mode == "shard":
        return [r for r in rows if r["pid"] % SHARDS == shard]
    want = set()
    for path, key in (("data/title/leads.json", "rows"), ("data/obits/matches.json", "rows")):
        p = os.path.join(ROOT, path)
        if os.path.exists(p):
            for lead in json.load(open(p))[key]:
                want.update(x["pid"] for x in lead["parcels"])
    p = os.path.join(ROOT, "data", "title", "watch.json")
    if os.path.exists(p):
        want.update(x["pid"] for x in json.load(open(p))["rows"])
    return [r for r in rows if r["pid"] in want]


def walk(mode, shard, limit=None, budget_minutes=320):
    con = sqlite3.connect(title_scan.DB_PATH)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT pid, pin, pin_nospace, owner FROM parcels ORDER BY pid")]
    con.close()
    todo = targets(mode, shard, rows)
    balances = load(BAL, {"rows": {}})["rows"]
    state = load(STATE, {"checked": {}})["checked"]
    today = dt.date.today()
    # oldest-checked first, so an interrupted run resumes where it stopped
    todo.sort(key=lambda r: (state.get(str(r["pid"]), ""), r["pid"]))
    if limit:
        todo = todo[:limit]
    log.info("%s parcels to check (%s)", len(todo), mode if mode != "shard" else f"shard {shard} of {SHARDS}")
    inq, started, done, errors = Inquiry(), time.time(), 0, 0
    for r in todo:
        if (time.time() - started) / 60 > budget_minutes:
            log.info("time budget reached after %s parcels; the rest resume next run", done)
            break
        try:
            t = inq.tickets(r["pid"])
            if t is None:                       # session expired or an odd page: reopen once
                inq.open()
                t = inq.tickets(r["pid"]) or []
        except Exception as e:  # noqa: BLE001
            errors += 1
            log.warning("pid %s failed: %s", r["pid"], e)
            if errors > 25:
                log.error("too many errors; stopping")
                break
            time.sleep(30)
            try:
                inq.open()
            except Exception:  # noqa: BLE001
                pass
            continue
        s = summarise(t, re.sub(r"\s+", "", r["pin"]), today)
        key = str(r["pid"])
        state[key] = today.isoformat()
        if s.get("past_due"):
            balances[key] = dict(s, pid=r["pid"], pin=r["pin"], checked=today.isoformat())
        else:
            balances.pop(key, None)
        done += 1
        if done % 100 == 0:
            log.info("%s checked, %s with a past-due balance on file", done, len(balances))
            save(balances, state)
    save(balances, state)
    log.info("walk done: %s checked, %s errors, %s parcels past due on file", done, errors, len(balances))


def save(balances, state):
    os.makedirs(OUT, exist_ok=True)
    json.dump({"updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "rows": dict(sorted(balances.items(), key=lambda kv: int(kv[0])))}, open(BAL, "w"), separators=(",", ":"))
    json.dump({"checked": dict(sorted(state.items(), key=lambda kv: int(kv[0])))}, open(STATE, "w"), separators=(",", ":"))


def join(today=None):
    """Apply balances on file to the Title Leads board and build the Delinquent tab. No network."""
    today = today or dt.date.today()
    balances = load(BAL, {"rows": {}})["rows"]
    state = load(STATE, {"checked": {}})["checked"]
    con = sqlite3.connect(title_scan.DB_PATH)
    con.row_factory = sqlite3.Row
    rows = {r["pid"]: dict(r) for r in con.execute("SELECT * FROM parcels")}
    con.close()
    title_scan.learn_book_years(rows.values())
    this_year = today.year

    def position(b):
        """Re-evaluate eligibility as of today from what was recorded."""
        b = dict(b)
        b["sale_eligible"] = dt.date.fromisoformat(b["sale_eligible_on"]) < today
        b["prior_year"] = min(b["years"]) < this_year
        return b

    watch_path = os.path.join(ROOT, "data", "title", "watch.json")
    watch = {x["pid"] for x in load(watch_path, {"rows": []})["rows"]}

    groups = {}
    for key, b in balances.items():
        r = rows.get(int(key))
        if not r:
            continue
        b = position(b)
        if not b["prior_year"]:
            continue                             # only the current bill is late: not a lead
        if r["owner_type"] in ("GOVERNMENT", "CEMETERY"):
            continue
        g = groups.setdefault((r["owner"], r["mail_addr"].upper(), str(r["mail_zip"])), [])
        g.append((r, b))

    leads = []
    for (owner, mail_addr, _zip), items in groups.items():
        r0 = items[0][0]
        parcels = []
        for r, b in sorted(items, key=lambda x: -x[1]["past_due"]):
            cls, flags, detail = title_scan.scan_parcel(r, this_year)
            parcels.append(dict(title_scan.parcel_view(r, flags, detail, this_year), title_class=cls,
                                past_due=b["past_due"], years=b["years"], oldest_due=b["oldest_due"],
                                sale_eligible=b["sale_eligible"], sale_eligible_on=b["sale_eligible_on"],
                                treasurer_name=b.get("name", ""), checked=b["checked"]))
        eligible = any(p["sale_eligible"] for p in parcels)
        profile = any(p["pid"] in watch for p in parcels)
        cls = "P1" if profile else "T1" if eligible else "T2"
        past = round(sum(p["past_due"] for p in parcels), 2)
        years = sorted({y for p in parcels for y in p["years"]})
        value = sum(p["total_value"] for p in parcels)
        pts = {"P1": 70, "T1": 60, "T2": 35}[cls] + min(15, len(years) * 3) + (10 if any(p["title_class"] for p in parcels) else 0)
        tname = parcels[0]["treasurer_name"]
        leads.append({
            "id": "d" + str(parcels[0]["pid"]), "priority": min(100, pts), "delinquency_class": cls, "class_label": CLASS_LABEL[cls],
            "owner": owner, "owner_type": r0["owner_type"], "care_of": r0["care_of"],
            "mail": {"addr": r0["mail_addr"], "city": r0["mail_city"], "state": r0["mail_state"], "zip": r0["mail_zip"] or None},
            "past_due": past, "years": years, "oldest_due": min(p["oldest_due"] for p in parcels),
            "sale_eligible": eligible, "treasurer_name": tname,
            "name_differs": bool(tname) and re.sub(r"\W", "", tname.upper()) not in re.sub(r"\W", "", (r0["lnam"] + r0["fnam"]).upper()),
            "title_class": next((p["title_class"] for p in parcels if p["title_class"]), ""),
            "parcel_count": len(parcels), "total_value": value, "parcels": parcels,
        })
    leads.sort(key=lambda l: (-l["priority"], -l["past_due"]))

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    summary = {"generated_at": now, "parcels_checked": len(state), "parcels_in_county": len(rows),
               "last_checked": max(state.values()) if state else "", "leads": len(leads),
               "classes": {c: sum(1 for l in leads if l["delinquency_class"] == c) for c in CLASS_LABEL},
               "past_due_total": round(sum(l["past_due"] for l in leads), 2),
               "class_labels": CLASS_LABEL, "next_step": NEXT_STEP}
    os.makedirs(OUT, exist_ok=True)
    json.dump({"summary": summary, "rows": leads}, open(LEADS, "w"), separators=(",", ":"))

    # annotate Title Leads
    tpath = os.path.join(ROOT, "data", "title", "leads.json")
    if os.path.exists(tpath):
        tl = json.load(open(tpath))
        n = 0
        for lead in tl["rows"]:
            hit = [position(balances[str(p["pid"])]) for p in lead["parcels"] if str(p["pid"]) in balances]
            hit = [b for b in hit if b["prior_year"]]
            lead["flags"] = [f for f in lead["flags"] if not f.startswith("TAX_")]
            lead["reasons"] = [s for s in lead["reasons"] if "taxes" not in s]
            lead.pop("delinquency", None)
            base = lead["priority"]
            if hit:
                elig = any(b["sale_eligible"] for b in hit)
                add = 25 if elig else 15
                lead["flags"].append("TAX_SALE_ELIGIBLE" if elig else "TAX_DELINQUENT")
                lead["priority"] = min(100, base + add)
                yrs = sorted({y for b in hit for y in b["years"]})
                amt = round(sum(b["past_due"] for b in hit), 2)
                lead["reasons"].append(f"+{add} taxes unpaid for {yrs[0]}" + (f"–{yrs[-1]}" if len(yrs) > 1 else "") + f" (${amt:,.2f}, Treasurer's record)")
                lead["delinquency"] = {"past_due": amt, "years": yrs, "sale_eligible": elig, "checked": max(b["checked"] for b in hit)}
                n += 1
        tl["rows"].sort(key=lambda l: (-l["priority"], -l["total_value"], l["owner"]))
        json.dump(tl, open(tpath, "w"), separators=(",", ":"))
        log.info("%s Title Leads carry a delinquency", n)
    log.info("delinquent tab: %s", {k: summary[k] for k in ("leads", "classes", "parcels_checked", "past_due_total")})
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["priority", "shard"])
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--budget-minutes", type=int, default=320)
    ap.add_argument("--join", action="store_true")
    a = ap.parse_args()
    if a.mode:
        walk(a.mode, a.shard, a.limit, a.budget_minutes)
    join()
