"""
Email the new strong surplus leads through the shared-notes Apps Script
(ported from md-property-leads engine2/alert.py).

The Apps Script accepts POST {action:"alert", token, subject, html} and sends it with
MailApp to the addresses in its Settings sheet. The token is the GitHub Actions secret
ALERT_TOKEN, matched against the script's own, so a visitor who finds the web-app URL
cannot make it send mail. With no secret set, nothing is sent.

Sent only when a lead is NEW today and STRONG, or POSSIBLE with $50,000+ at the top of
its range.
"""
import json
import logging
import os
import re
import sys

import requests

log = logging.getLogger("alert")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUCTIONS = os.path.join(ROOT, "data", "surplus", "auctions.json")
CONFIG_JS = os.path.join(ROOT, "static", "js", "config.js")
DASH = "https://pagesofpurposellc.com/va-property-leads/#surplus"
STAGE = {"TAX_SALE_SOLD": "Tax sale sold: surplus held by the Circuit Court", "AUCTION_SOLD": "Foreclosure sold: surplus likely",
         "AUCTION_SCHEDULED": "Foreclosure scheduled: owner still holds title"}


def notes_url():
    m = re.search(r'SHARED_NOTES_URL:\s*"([^"]+)"', open(CONFIG_JS, encoding="utf-8").read())
    return m.group(1) if m else ""


def money(v):
    return "$" + f"{round(v):,}" if v else "—"


def pick(rows):
    return [r for r in rows if r.get("is_new") and (r["tier"] == "STRONG" or (r.get("surplus_est") and r["surplus_est"][2] >= 50000 and r["tier"] == "POSSIBLE"))]


def block(r):
    se = r.get("surplus_est") or [0, 0, 0]
    sold = r["stage"] != "AUCTION_SCHEDULED"
    return (f"<p style='margin:0 0 14px'><b style='font-size:16px'>{r.get('address') or 'Tax map ' + str(r.get('pin') or '')}</b> — {r['county']} County<br>"
            f"<b>{'Former owner' if sold else 'Owner'}:</b> {r.get('former_owner') or r.get('owner_of_record') or '—'}"
            + (f" · mail: {r['mail']}" if r.get("mail") else "") + "<br>"
            + (f"<b>Sold {r.get('sale_date')}</b> for <b>{money(r.get('hammer'))}</b> · " if sold else f"<b>Sale {r.get('sale_date')}</b> · assessed {money(r.get('assessed_value'))} · ")
            + f"<b style='color:#0a7'>est. {'surplus' if sold else 'equity'} {money(se[0])} to {money(se[2])}</b><br>"
            + f"<span style='color:#666'>{r.get('why', '')}</span></p>")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    url, token = notes_url(), os.environ.get("ALERT_TOKEN", "")
    if not url or not token:
        log.info("no notes URL or no ALERT_TOKEN secret; no email sent")
        return 0
    rows = pick(json.load(open(AUCTIONS, encoding="utf-8"))["rows"])
    if not rows:
        log.info("nothing new and strong today")
        return 0
    rows.sort(key=lambda r: -(r["surplus_est"][1] if r.get("surplus_est") else 0))
    html = ("<div style='font-family:Arial,sans-serif;font-size:14px;max-width:680px'>"
            f"<p>{len(rows)} new Virginia lead{'s' if len(rows) != 1 else ''} this morning. Open the dashboard, Surplus Funds tab, for the letter and the find-them links.</p>")
    for stage, label in STAGE.items():
        part = [r for r in rows if r["stage"] == stage]
        if part:
            html += f"<h3 style='margin:18px 0 8px'>{label} ({len(part)})</h3>" + "".join(block(r) for r in part)
    html += (f"<p style='margin-top:18px'><a href='{DASH}'>Open the dashboard</a></p>"
             "<p style='color:#888;font-size:12px'>Ranges are estimates from public records, not balances. Check with the Clerk or the trustee. "
             "Any agreement goes through a Virginia lawyer first (Va. Code §§ 55.1-324, 58.1-3967, 59.1-200.1, 54.1-3904).</p></div>")
    subj = f"🔔 VA: {len(rows)} surplus lead{'s' if len(rows) != 1 else ''}: " + ", ".join(
        f"{(r.get('address') or r.get('former_owner') or 'parcel')} ({money((r.get('surplus_est') or [0, 0, 0])[1])})" for r in rows[:3])
    r = requests.post(url, data=json.dumps({"action": "alert", "token": token, "subject": subj, "html": html}),
                      headers={"Content-Type": "text/plain"}, timeout=60, allow_redirects=True)
    log.info("alert POST %s: %s", r.status_code, r.text[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
