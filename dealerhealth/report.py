"""Outputs: report.html, dealer-review.md and the CSVs (dealers, interfaces, claims at risk, rejections, catalogue, actions, findings)."""
from __future__ import annotations

import csv
import html
from pathlib import Path

from .checks import (AREAS, CRITICAL, INFO, WARNING, Finding, area_status, catalogue_rows, claim_rows, dealer_rows, dms_rows, interface_rows,
                     onboarding_rows, terminated_rows)
from .model import INTERFACE_NAMES, INTERFACES, Data

e = html.escape


def build(d: Data) -> dict:
    return dict(itf=interface_rows(d), claims=claim_rows(d), cat=catalogue_rows(d), dms=dms_rows(d), onb=onboarding_rows(d), term=terminated_rows(d))


def summary(d: Data, findings: list[Finding], b: dict) -> dict:
    dl = dealer_rows(d, b, findings)
    live = [r for r in dl if r["status"] == "active"]
    c = b["claims"]
    risk = [r for r in c["at_risk"]]
    return dict(dealers=len(live), onboarding=sum(r["status"] == "onboarding" for r in dl), red=sum(r["rag"] == "red" for r in live),
                amber=sum(r["rag"] == "amber" for r in live), green=sum(r["rag"] == "green" for r in live),
                feeds=sum(r["verdict"] != "no data" for r in b["itf"]), feeds_bad=sum(r["verdict"] in ("failing", "errors", "silent") for r in b["itf"]),
                claims=len(d.claims), at_risk=len(risk), at_risk_amount=round(sum(r["claim"].amount for r in risk), 2),
                pending=len(c["pending"]), rate=c["rate"], unpaid_amount=round(sum(r["claim"].amount for r in c["unpaid"]), 2),
                cat_ok=sum(r["verdict"] == "ok" for r in b["cat"]), cat_total=len(b["cat"]),
                critical=sum(f.severity == CRITICAL for f in findings), warning=sum(f.severity == WARNING for f in findings),
                info=sum(f.severity == INFO for f in findings))


# ---------------------------------------------------------------- csv

def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def write_findings(findings: list[Finding], path: Path) -> None:
    _w(path, ["severity", "area", "code", "subject", "detail", "next_step", "owner", "dealers", "items"],
       [[f.severity, f.area, f.code, f.subject, f.detail, f.fix, f.owner, "; ".join(f.dealers), "; ".join(f.items)] for f in findings])


def write_actions(findings: list[Finding], path: Path) -> int:
    rows = [[f.code, f.subject, f.fix, f.owner, f.severity, "", ""] for f in findings if f.severity != INFO]
    _w(path, ["ref", "action", "next_step", "owner", "severity", "due", "done"], rows)
    return len(rows)


def write_dealers(d: Data, b: dict, findings: list[Finding], path: Path) -> None:
    _w(path, ["dealer", "name", "country", "city", "status", "dms", "feeds_ok", "feeds", "rejection_pct", "claims_decided", "catalogue",
              "price_file", "rag", "findings", "area_manager"],
       [[r["dealer"], r["name"], r["country"], r["city"], r["status"], r["dms"], r["feeds_ok"], r["feeds"], "" if r["rate"] is None else r["rate"],
         r["decided"], r["catalogue"], r["price"], r["rag"], " ".join(r["codes"]), r["manager"]] for r in dealer_rows(d, b, findings)])


def write_interfaces(b: dict, path: Path) -> None:
    _w(path, ["dealer", "name", "interface", "critical", "last_success", "hours_since_success", "runs", "failed_runs", "records", "errors",
              "error_pct", "zero_days", "verdict", "issues"],
       [[r["dealer"], r["name"], r["interface"], "yes" if r["critical"] else "no", r["last_ok"].strftime("%Y-%m-%d %H:%M") if r["last_ok"] else "",
         "" if r["hours"] is None else r["hours"], r["runs"], r["failed"], r["records"], r["errors"], r["err_pct"], r["zero_days"], r["verdict"],
         " | ".join(r["issues"])] for r in b["itf"]])


def write_claims_at_risk(d: Data, b: dict, path: Path) -> None:
    c, rows = b["claims"], []
    for r in c["at_risk"]:
        x = r["claim"]
        rows.append(["past submission limit" if r["days_left"] < 0 else "due soon", x.claim_id, x.dealer_id, x.vin, x.repair_date, "", x.labour_op,
                     x.amount, f"{r['days_left']} days left" if r["days_left"] >= 0 else f"{-r['days_left']} days late", "", ""])
    for key, label, owner in (("pending", "waiting for brand", "brand"), ("info", "info requested", "dealer"), ("unpaid", "accepted, not paid", "finance")):
        for r in c[key]:
            x = r["claim"]
            rows.append([label, x.claim_id, x.dealer_id, x.vin, x.repair_date, x.submitted or "", x.labour_op, x.amount, f"{r['days']} days",
                         x.reason if key == "info" else "", owner])
    for r in c["dups"]:
        x = r["second"]
        rows.append(["possible duplicate", x.claim_id, x.dealer_id, x.vin, x.repair_date, x.submitted or "", x.labour_op, x.amount,
                     f"repeats {r['first'].claim_id} after {r['gap']} days", "", "warranty"])
    _w(path, ["queue", "claim", "dealer", "vin", "repair_date", "submitted", "labour_op", "amount", "age", "info_requested", "waiting_on"], rows)


def write_rejections(b: dict, path: Path) -> None:
    _w(path, ["dealer", "name", "decided", "rejected", "rejection_pct", "rejected_amount", "top_reasons", "above_limit"],
       [[r["dealer"], r["name"], r["decided"], r["rejected"], r["rate"], r["amount"], "; ".join(f"{k} ({v})" for k, v in r["reasons"]),
         "yes" if r["high"] else "no"] for r in b["claims"]["rates"]])


def write_catalogue(b: dict, path: Path) -> None:
    _w(path, ["dealer", "name", "catalogue", "catalogue_date", "versions_behind", "price_file", "price_file_date", "verdict", "issues"],
       [[r["dealer"], r["name"], r["catalogue"], r["catalogue_date"] or "", "" if r["behind"] is None else r["behind"], r["price"],
         r["price_date"] or "", r["verdict"], " | ".join(r["issues"])] for r in b["cat"]])


# ---------------------------------------------------------------- markdown

def review_md(d: Data, findings: list[Finding], b: dict) -> str:
    s, sm, c = d.settings, summary(d, findings, b), b["claims"]
    cur = s.currency
    out = [f"# Dealer systems review · {s.brand}", "",
           f"As of {d.as_of:%d %b %Y %H:%M} · {sm['dealers']} live dealers ({sm['onboarding']} onboarding) · {sm['feeds']} DMS feeds · "
           f"{sm['claims']:,} warranty claims in the export.", "", "## Summary", "",
           f"- Dealers: {sm['red']} red, {sm['amber']} amber, {sm['green']} green.",
           f"- Interfaces: {sm['feeds_bad']} of {sm['feeds']} feeds failing, rejecting records or empty.",
           f"- Warranty: {sm['at_risk']} draft claims at or past the {s.claim_submit_days}-day limit ({cur}{sm['at_risk_amount']:,.0f}); "
           f"{sm['pending']} waiting for the brand over {s.claim_pending_days} days; rejection rate {sm['rate']:g}% over {s.claims_window_days} days; "
           f"{cur}{sm['unpaid_amount']:,.0f} accepted and not paid after {s.unpaid_days} days.",
           f"- Parts: {sm['cat_ok']} of {sm['cat_total']} dealers on catalogue {s.catalogue_version} and price file {s.price_version}.",
           f"- Findings: {sm['critical']} critical, {sm['warning']} warnings, {sm['info']} for information.", "",
           "## Decisions for this review", ""]
    for f in [x for x in findings if x.severity != INFO]:
        out.append(f"- [ ] **{f.code} {f.subject}** ({f.owner or 'owner?'}): {f.detail} → {f.fix}")
    out += ["", "## For information", ""]
    out += [f"- {f.code} {f.subject}: {f.detail}" for f in findings if f.severity == INFO] or ["- Nothing."]
    out += ["", "## Top rejection reasons", "", "| Reason | Claims |", "|---|---:|"]
    out += [f"| {k} | {v} |" for k, v in c["reasons"][:6]]
    red = [r for r in dealer_rows(d, b, findings) if r["rag"] == "red"]
    out += ["", "## Red dealers", "", "| Dealer | Area manager | Findings |", "|---|---|---|"]
    out += [f"| {r['dealer']} {r['name']} | {r['manager']} | {', '.join(r['codes'])} |" for r in red] or ["| – | – | – |"]
    out += ["", "Generated by dealerhealth from the network's own exports. Each red dealer gets its list before the call with its area manager.", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#f6f7f8;--card:#fff;--ink:#1b2128;--muted:#66717c;--line:#e2e5e9;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--info:#0b6bcb;--na:#8a94a0}
@media (prefers-color-scheme:dark){:root{--bg:#13171b;--card:#1b2127;--ink:#e7eaee;--muted:#9aa5b0;--line:#2b333b;--ok:#4cc38a;--warn:#f0a83a;--bad:#f2685c;--info:#5aa9f0;--na:#6d7782}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:26px}
.areas{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.area{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--ok);border-radius:10px;padding:10px 14px}
.area.critical{border-left-color:var(--bad)}.area.warning{border-left-color:var(--warn)}
.area .lbl{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px}.area .cnt{display:block;font-size:13px;color:var(--muted);margin-top:4px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.critical,.red{color:var(--bad)}.warning,.amber{color:var(--warn)}.info{color:var(--info)}.ok,.green{color:var(--ok)}.na{color:var(--na)}
.area.critical,.area.warning,.area.ok{color:inherit}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(58px,1fr));gap:6px}
.cell{border-radius:6px;padding:6px 4px;text-align:center;font-size:12px;font-weight:600;color:#fff;background:var(--ok)}
.cell.amber{background:var(--warn)}.cell.red{background:var(--bad)}.cell span{display:block;font-weight:400;font-size:10px;opacity:.9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dot{display:inline-block;width:12px;height:12px;border-radius:3px;background:var(--ok)}.dot.failing{background:var(--bad)}.dot.errors,.dot.silent{background:var(--warn)}
.dot.no{background:var(--line)}.bar{height:10px;border-radius:5px;background:var(--line);overflow:hidden;min-width:110px}.bar i{display:block;height:100%;background:var(--info)}
.bar i.over{background:var(--bad)}td.nw{white-space:nowrap}td.fix{font-size:13px;color:var(--muted);max-width:380px}code{font-size:12px}
footer{margin-top:40px;font-size:13px}
"""


def _pill(cls: str, text: str) -> str:
    return f"<span class='pill {cls}'>{e(text)}</span>"


def render_html(d: Data, findings: list[Finding], title: str, b: dict) -> str:
    s, sm, st, c = d.settings, summary(d, findings, b), area_status(findings), b["claims"]
    cur = s.currency
    dl = dealer_rows(d, b, findings)
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>Aftersales dealer systems · as of {d.as_of:%d %b %Y %H:%M}</p><div class='tiles'>"]
    tiles = [("Live dealers", str(sm["dealers"]), f"{sm['onboarding']} onboarding"),
             ("Red", str(sm["red"]), f"{sm['amber']} amber · {sm['green']} green"),
             ("Feeds with a problem", f"{sm['feeds_bad']}/{sm['feeds']}", "failing, errors or empty"),
             ("Claims at risk", str(sm["at_risk"]), f"{cur}{sm['at_risk_amount']:,.0f} in drafts"),
             ("Waiting for brand", str(sm["pending"]), f"over {s.claim_pending_days} days"),
             ("Rejection rate", f"{sm['rate']:g}%", f"last {s.claims_window_days} days"),
             ("Not paid", f"{cur}{sm['unpaid_amount']:,.0f}", f"accepted {s.unpaid_days}+ days ago"),
             ("Catalogue and prices", f"{sm['cat_ok']}/{sm['cat_total']}", f"on {s.catalogue_version} · {s.price_version}"),
             ("Critical", str(sm["critical"]), f"{sm['warning']} warnings · {sm['info']} info")]
    h += [f"<div class='tile'><span class='muted'>{e(a)}</span><b>{e(x)}</b><span class='muted'>{e(y)}</span></div>" for a, x, y in tiles]
    h.append("</div><h2>Status by area</h2><div class='areas'>")
    for a in AREAS:
        n = sum(f.area == a and f.severity != INFO for f in findings)
        h.append(f"<div class='area {st[a]}'><span class='lbl'>{e(a)}</span>{_pill(st[a], 'OK' if st[a] == 'ok' else st[a].upper())}"
                 f"<span class='cnt'>{n} to act on</span></div>")
    h.append("</div><h2>Dealer network</h2><div class='grid'>")
    for r in [x for x in dl if x["status"] != "terminated"]:
        tip = f"{r['dealer']} {r['name']} · {r['status']} · {', '.join(r['codes']) or 'no findings'}"
        h.append(f"<div class='cell {r['rag']}' title='{e(tip)}'>{e(r['dealer'])}<span>{e(r['city'])}</span></div>")
    h.append("</div><p class='muted'>Red: at least one critical finding. Amber: warnings. Hover a dealer for its findings; the full list is in <code>dealers.csv</code>.</p>")
    crit = [f for f in findings if f.severity == CRITICAL]
    if crit:
        h.append("<h2>Fix first</h2><div class='wrap'><table><tr><th>Subject</th><th>What</th><th>Next step</th><th>Owner</th></tr>")
        h += [f"<tr><td><b>{e(f.subject)}</b><br><span class='muted'>{e(f.area)} · {e(f.code)}</span></td><td>{e(f.detail)}</td>"
              f"<td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in crit]
        h.append("</table></div>")
    # interfaces matrix for dealers with a problem
    bad = sorted({r["dealer"] for r in b["itf"] if r["verdict"] in ("failing", "errors", "silent")})
    if bad:
        h.append(f"<h2>DMS feeds with a problem ({len(bad)} dealers)</h2><div class='wrap'><table><tr><th>Dealer</th>"
                 + "".join(f"<th>{e(INTERFACE_NAMES[i])}</th>" for i in INTERFACES) + "<th>Issues</th></tr>")
        for did in bad:
            rows = {r["interface"]: r for r in b["itf"] if r["dealer"] == did}
            cells = "".join(f"<td><span class='dot {(rows[i]['verdict'] if rows[i]['verdict'] != 'no data' else 'no') if i in rows else 'no'}' "
                            f"title='{e(rows[i]['verdict']) if i in rows else ''}'></span></td>" for i in INTERFACES)
            iss = [f"{INTERFACE_NAMES[r['interface']]}: {'; '.join(r['issues'])}" for r in rows.values() if r["verdict"] in ("failing", "errors", "silent")]
            name = rows[next(iter(rows))]["name"]
            h.append(f"<tr><td class='nw'><b>{e(did)}</b><br><span class='muted'>{e(name)}</span></td>{cells}<td>{'<br>'.join(e(x) for x in iss)}</td></tr>")
        h.append(f"</table></div><p class='muted'>Window {s.window_days} days. Red: no successful run within the limit. Amber: more than "
                 f"{s.error_rate_max_pct:g}% of records rejected, or runs that succeed with nothing in them for {s.silent_days}+ days.</p>")
    # warranty
    h.append("<h2>Warranty queues</h2><div class='wrap'><table><tr><th>Queue</th><th class='num'>Claims</th><th class='num'>Amount</th><th>Waiting on</th></tr>")
    queues = [("Drafts past the submission limit", [r for r in c["at_risk"] if r["days_left"] < 0], "dealer"),
              (f"Drafts due in {s.claim_warn_days} days", [r for r in c["at_risk"] if r["days_left"] >= 0], "dealer"),
              (f"Submitted, no decision after {s.claim_pending_days} days", c["pending"], "brand"),
              (f"Information requested, no answer after {s.info_request_days} days", c["info"], "dealer"),
              (f"Accepted, not paid after {s.unpaid_days} days", c["unpaid"], "finance")]
    for label, rows, who in queues:
        h.append(f"<tr><td>{e(label)}</td><td class='num'>{len(rows)}</td><td class='num'>{cur}{sum(r['claim'].amount for r in rows):,.0f}</td><td>{who}</td></tr>")
    h.append("</table></div>")
    if c["rates"]:
        top = c["rates"][:8]
        mx = max(r["rate"] for r in top) or 1
        h.append(f"<h2>Rejection rate by dealer (top 8, last {s.claims_window_days} days)</h2><div class='wrap'><table><tr><th>Dealer</th>"
                 "<th class='num'>Decided</th><th>Rejected</th><th class='num'>Rate</th><th>Main reasons</th></tr>")
        for r in top:
            h.append(f"<tr><td class='nw'><b>{e(r['dealer'])}</b><br><span class='muted'>{e(r['name'])}</span></td><td class='num'>{r['decided']}</td>"
                     f"<td><div class='bar'><i class='{'over' if r['high'] else ''}' style='width:{100 * r['rate'] / mx:.0f}%'></i></div></td>"
                     f"<td class='num {'critical' if r['high'] else ''}'>{r['rate']:g}%</td><td>{e('; '.join(f'{k} ({v})' for k, v in r['reasons']))}</td></tr>")
        h.append(f"</table></div><p class='muted'>Network rate {c['rate']:g}% ({c['rejected']} of {c['decided']}). Limit {s.rejection_rate_max_pct:g}% "
                 f"for dealers with at least {s.min_claims_for_rate} decisions.</p>")
    # parts
    cat = [r for r in b["cat"] if r["verdict"] not in ("ok",)]
    if cat:
        h.append(f"<h2>Catalogue and price file ({len(cat)} dealers)</h2><div class='wrap'><table><tr><th>Dealer</th><th>Catalogue</th><th>Price file</th><th>Issue</th></tr>")
        for r in sorted(cat, key=lambda r: (r["verdict"] != "critical", r["dealer"])):
            h.append(f"<tr><td class='nw'><b>{e(r['dealer'])}</b><br><span class='muted'>{e(r['name'])}</span></td><td>{e(r['catalogue'] or '–')}</td>"
                     f"<td class='{'' if r['price_ok'] else 'critical'}'>{e(r['price'] or '–')}</td><td>{'<br>'.join(e(i) for i in r['issues'])}</td></tr>")
        h.append("</table></div>")
    # network
    onb = b["onb"]
    if onb:
        h.append("<h2>Dealers onboarding</h2><div class='wrap'><table><tr><th>Dealer</th><th>Go-live</th><th>Checklist</th><th>Open</th></tr>")
        for r in onb:
            cls = "critical" if r["verdict"] == "critical" else "warning" if r["verdict"] == "at risk" else ""
            h.append(f"<tr><td class='nw'><b>{e(r['dealer'])}</b><br><span class='muted'>{e(r['name'])}</span></td>"
                     f"<td class='nw {cls}'>{r['go_live']:%d %b} ({r['days']} days)</td><td class='nw'>{r['done']}/{r['total']}</td><td>{e(', '.join(r['open']) or '–')}</td></tr>")
        h.append("</table></div>")
    # findings
    h.append("<h2>All findings</h2><div class='wrap'><table><tr><th>Severity</th><th>Area</th><th>Subject</th><th>Detail</th><th>Next step</th><th>Owner</th></tr>")
    h += [f"<tr><td>{_pill(f.severity, f.severity.upper())}</td><td class='nw'>{e(f.area)}</td><td>{e(f.subject)}</td>"
          f"<td>{e(f.detail)}</td><td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in findings]
    h.append("</table></div><footer class='muted'>Generated by dealerhealth from the network's exports. Fictional demo data unless you ran it on your own network.</footer>"
             "</main></body></html>")
    return "".join(h)
