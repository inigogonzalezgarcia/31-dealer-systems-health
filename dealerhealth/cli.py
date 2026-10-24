"""Command line: `demo` builds everything from the fictional dealer network, `review` runs on your own exports."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import report, simulate
from .checks import run_all
from .model import load, parse_date

OUTPUTS = ("report.html", "dealer-review.md", "dealers.csv", "interfaces.csv", "claims-at-risk.csv", "rejections.csv", "catalogue.csv",
           "actions.csv", "findings.csv")


def run(data: Path, out: Path, title: str, as_of: date | None = None) -> dict:
    d = load(data, as_of)
    b = report.build(d)
    findings = run_all(d, b)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(report.render_html(d, findings, title, b), encoding="utf-8")
    (out / "dealer-review.md").write_text(report.review_md(d, findings, b), encoding="utf-8")
    report.write_dealers(d, b, findings, out / "dealers.csv")
    report.write_interfaces(b, out / "interfaces.csv")
    report.write_claims_at_risk(d, b, out / "claims-at-risk.csv")
    report.write_rejections(b, out / "rejections.csv")
    report.write_catalogue(b, out / "catalogue.csv")
    report.write_actions(findings, out / "actions.csv")
    report.write_findings(findings, out / "findings.csv")
    return report.summary(d, findings, b)


def _date(value: str) -> date:
    d = parse_date(value)
    if not d:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD): {value}")
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dealerhealth", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    dm = sub.add_parser("demo", help="write the fictional dealer network to sample_data/ and build the outputs")
    dm.add_argument("--data", type=Path, default=Path("sample_data"))
    dm.add_argument("--out", type=Path, default=Path("output"))
    rv = sub.add_parser("review", help="build the outputs from your own exports")
    rv.add_argument("data", type=Path, help="folder with dealers.csv (required) and interface_runs.csv, warranty_claims.csv, catalogue_status.csv, "
                                            "onboarding.csv, settings.json (optional)")
    rv.add_argument("--out", type=Path, default=Path("output"))
    rv.add_argument("--title", default="Dealer systems review")
    rv.add_argument("--as-of", type=_date, help="review date, YYYY-MM-DD (default: settings.json, or the latest interface run)")
    a = p.parse_args(argv)
    if a.cmd == "demo":
        simulate.write(a.data)
        sm = run(a.data, a.out, "VanArsdel Motors Iberia · Dealer systems review")
    else:
        try:
            sm = run(a.data, a.out, a.title, a.as_of)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    print(f"{sm['dealers']} live dealers ({sm['red']} red, {sm['amber']} amber, {sm['green']} green) · feeds {sm['feeds_bad']}/{sm['feeds']} with a problem · "
          f"{sm['at_risk']} claims at risk ({sm['at_risk_amount']:,.0f}) · {sm['pending']} waiting for the brand · rejection {sm['rate']:g}% · "
          f"{sm['unpaid_amount']:,.0f} not paid · catalogue {sm['cat_ok']}/{sm['cat_total']} · {sm['critical']} critical, {sm['warning']} warnings")
    print(f"outputs in {a.out}/: {', '.join(OUTPUTS)}")
    return 0
