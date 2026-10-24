"""The checks: DMS interfaces, warranty claims, parts catalogue and price file, and the dealer network (DMS versions, onboarding,
terminated dealers). Each rule is a plain function over the loaded data, and each finding says what to do and who owns it."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .model import INTERFACE_NAMES, INTERFACES, Data, Dealer

CRITICAL, WARNING, INFO = "critical", "warning", "info"
ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}
AREAS = ("Interfaces", "Warranty", "Parts", "Network")


@dataclass
class Finding:
    severity: str
    area: str
    code: str
    subject: str
    detail: str
    fix: str
    owner: str = ""
    items: list[str] = field(default_factory=list)
    dealers: list[str] = field(default_factory=list)


def _n(k: int, word: str, plural: str | None = None) -> str:
    return f"{k} {word if k == 1 else (plural or word + 's')}"


def _money(d: Data, v: float) -> str:
    return f"{d.settings.currency}{v:,.0f}"


def _top(items: list[str], k: int = 5) -> str:
    return ", ".join(items[:k]) + (f" and {len(items) - k} more" if len(items) > k else "")


def live_dealers(d: Data) -> list[Dealer]:
    return [x for x in d.dealers if x.status == "active"]


# ---------------------------------------------------------------- interfaces

def interface_rows(d: Data) -> list[dict]:
    s = d.settings
    since = d.as_of - timedelta(days=s.window_days)
    runs = defaultdict(list)
    for r in d.runs:
        if r.run_at <= d.as_of:
            runs[(r.dealer_id, r.interface)].append(r)
    out = []
    for dl in live_dealers(d):
        for itf in INTERFACES:
            cfg = s.interfaces.get(itf)
            if cfg is None:
                continue
            rs = sorted(runs.get((dl.dealer_id, itf), []), key=lambda r: r.run_at)
            win = [r for r in rs if r.run_at >= since]
            last_ok = max((r.run_at for r in rs if r.status != "failed"), default=None)
            hours = round((d.as_of - last_ok).total_seconds() / 3600, 1) if last_ok else None
            recs, errs = sum(r.records for r in win), sum(r.errors for r in win)
            err_pct = round(100 * errs / (recs + errs), 1) if recs + errs else 0.0
            # consecutive days, counting back from the latest run, on which a run that did not fail carried nothing
            days = defaultdict(int)
            for r in win:
                if r.status != "failed":
                    days[r.run_at.date()] += r.records
            zero = 0
            for day in sorted(days, reverse=True):
                if days[day] == 0:
                    zero += 1
                else:
                    break
            issues, verdict = [], "ok"
            if not rs:
                verdict, issues = "no data", ["no runs in the log"]
            elif hours is None or hours > cfg["stale_hours"]:
                verdict = "failing"
                issues.append(f"no successful run for {hours:.0f} h (limit {cfg['stale_hours']} h)" if hours is not None else "never succeeded")
            if rs and err_pct > s.error_rate_max_pct:
                verdict = "failing" if verdict == "failing" else "errors"
                issues.append(f"{err_pct:g}% of records rejected in {s.window_days} days (limit {s.error_rate_max_pct:g}%)")
            if rs and zero >= s.silent_days and verdict != "failing":
                verdict = "silent" if verdict == "ok" else verdict
                issues.append(f"runs succeed but carry 0 records for {zero} days")
            out.append(dict(dealer=dl.dealer_id, name=dl.name, interface=itf, critical=bool(cfg.get("critical")), last_ok=last_ok, hours=hours,
                            runs=len(win), failed=sum(r.status == "failed" for r in win), records=recs, errors=errs, err_pct=err_pct,
                            zero_days=zero, verdict=verdict, issues=issues))
    return out


# ---------------------------------------------------------------- warranty

def claim_rows(d: Data) -> dict:
    s, today = d.settings, d.today
    at_risk, pending, info, unpaid = [], [], [], []
    for c in d.claims:
        if c.status == "draft" and c.repair_date:
            left = (c.repair_date + timedelta(days=s.claim_submit_days) - today).days
            if left <= s.claim_warn_days:
                at_risk.append(dict(claim=c, days_left=left))
        elif c.status == "submitted" and c.submitted and (today - c.submitted).days > s.claim_pending_days:
            pending.append(dict(claim=c, days=(today - c.submitted).days))
        elif c.status == "info" and (today - (c.status_date or c.submitted or today)).days > s.info_request_days:
            info.append(dict(claim=c, days=(today - (c.status_date or c.submitted)).days))
        elif c.status == "accepted" and not c.paid_date and (today - (c.status_date or today)).days > s.unpaid_days:
            unpaid.append(dict(claim=c, days=(today - c.status_date).days))
    # duplicates: same VIN and labour operation within the window, ignoring drafts and rejected claims
    by_key = defaultdict(list)
    for c in d.claims:
        if c.status not in ("draft", "rejected") and c.vin and c.labour_op and c.repair_date:
            by_key[(c.vin, c.labour_op)].append(c)
    dups = []
    for (vin, op), cs in by_key.items():
        cs.sort(key=lambda c: c.repair_date)
        for a, b in zip(cs, cs[1:]):
            if (b.repair_date - a.repair_date).days <= s.duplicate_window_days:
                dups.append(dict(first=a, second=b, vin=vin, op=op, gap=(b.repair_date - a.repair_date).days))
    # rejection rate per dealer over the decisions taken in the claims window
    since = today - timedelta(days=s.claims_window_days)
    dec = defaultdict(lambda: dict(decided=0, rejected=0, reasons=Counter(), amount=0.0))
    for c in d.claims:
        if c.status in ("accepted", "rejected", "paid") and (c.status_date or c.paid_date or today) >= since:
            x = dec[c.dealer_id]
            x["decided"] += 1
            if c.status == "rejected":
                x["rejected"] += 1
                x["amount"] += c.amount
                x["reasons"][c.reason or "no reason given"] += 1
    rates = []
    for did, x in dec.items():
        dl = d.dealer(did)
        if dl and dl.status == "terminated":
            continue
        rate = round(100 * x["rejected"] / x["decided"], 1) if x["decided"] else 0.0
        rates.append(dict(dealer=did, name=dl.name if dl else did, decided=x["decided"], rejected=x["rejected"], rate=rate,
                          amount=round(x["amount"], 2), reasons=x["reasons"].most_common(3),
                          high=x["decided"] >= s.min_claims_for_rate and rate > s.rejection_rate_max_pct))
    rates.sort(key=lambda r: -r["rate"])
    all_reasons = Counter()
    for x in dec.values():
        all_reasons.update(x["reasons"])
    decided = sum(x["decided"] for x in dec.values())
    rejected = sum(x["rejected"] for x in dec.values())
    return dict(at_risk=sorted(at_risk, key=lambda r: r["days_left"]), pending=sorted(pending, key=lambda r: -r["days"]),
                info=sorted(info, key=lambda r: -r["days"]), unpaid=sorted(unpaid, key=lambda r: -r["days"]), dups=dups, rates=rates,
                reasons=all_reasons.most_common(), decided=decided, rejected=rejected,
                rate=round(100 * rejected / decided, 1) if decided else 0.0)


# ---------------------------------------------------------------- parts

def _behind(versions: list[str], current: str, have: str) -> int | None:
    if not have:
        return None
    if have == current:
        return 0
    if have in versions and current in versions:
        return versions.index(have) - versions.index(current)
    return 1


def catalogue_rows(d: Data) -> list[dict]:
    s, today = d.settings, d.today
    have = {c.dealer_id: c for c in d.catalogue}
    out = []
    for dl in live_dealers(d):
        c = have.get(dl.dealer_id)
        cat_behind = _behind(s.catalogue_versions, s.catalogue_version, c.catalogue_version if c else "")
        price_ok = bool(c and c.price_version == s.price_version)
        cat_late = (today - s.catalogue_released).days - s.catalogue_grace_days if s.catalogue_released else 0
        price_late = (today - s.price_released).days - s.price_grace_days if s.price_released else 0
        issues, verdict = [], "ok"
        if c is None or cat_behind is None:
            verdict, issues = "unknown", ["no catalogue status reported"]
        else:
            if cat_behind >= 2:
                verdict = "critical"
                issues.append(f"catalogue {c.catalogue_version}, {cat_behind} versions behind {s.catalogue_version}")
            elif cat_behind == 1 and cat_late > 0:
                verdict = "behind"
                issues.append(f"catalogue {c.catalogue_version}; {s.catalogue_version} released {s.catalogue_released:%d %b}, grace ended {cat_late} days ago")
            if not price_ok and price_late > 0:
                verdict = "critical"
                issues.append(f"price file {c.price_version or 'none'} instead of {s.price_version}; grace ended {price_late} days ago")
        out.append(dict(dealer=dl.dealer_id, name=dl.name, catalogue=c.catalogue_version if c else "", catalogue_date=c.catalogue_date if c else None,
                        behind=cat_behind, price=c.price_version if c else "", price_date=c.price_date if c else None, price_ok=price_ok,
                        verdict=verdict, issues=issues))
    return out


# ---------------------------------------------------------------- network

def dms_rows(d: Data) -> list[dict]:
    s, today = d.settings, d.today
    out = []
    for dl in d.dealers:
        if dl.status == "terminated":
            continue
        sup = s.supported_dms.get(dl.dms)
        supported = None if sup is None else dl.dms_version in [str(v) for v in sup]
        eos = s.dms_end_of_support.get(f"{dl.dms} {dl.dms_version}")
        eos_d = date.fromisoformat(eos) if eos else None
        verdict = "unsupported" if supported is False else "end of support" if eos_d and (eos_d - today).days <= s.eos_warn_days else "ok"
        out.append(dict(dealer=dl.dealer_id, name=dl.name, dms=dl.dms, version=dl.dms_version, supported=supported, eos=eos_d, verdict=verdict))
    return out


def onboarding_rows(d: Data) -> list[dict]:
    s, today = d.settings, d.today
    out = []
    for dl in d.dealers:
        if dl.status != "onboarding":
            continue
        done = d.onboarding.get(dl.dealer_id, {})
        open_items = [i for i in s.onboarding_items if not done.get(i)]
        days = (dl.go_live - today).days if dl.go_live else None
        verdict = "ok" if not open_items else "critical" if days is not None and days <= s.onboarding_critical_days else \
            "at risk" if days is None or days <= s.onboarding_warn_days else "in progress"
        out.append(dict(dealer=dl.dealer_id, name=dl.name, go_live=dl.go_live, days=days, open=open_items,
                        done=len(s.onboarding_items) - len(open_items), total=len(s.onboarding_items), verdict=verdict))
    return out


def terminated_rows(d: Data) -> list[dict]:
    out = []
    for dl in d.dealers:
        if dl.status != "terminated" or not dl.end_date:
            continue
        after = [r for r in d.runs if r.dealer_id == dl.dealer_id and r.run_at.date() > dl.end_date]
        claims = [c for c in d.claims if c.dealer_id == dl.dealer_id and c.submitted and c.submitted > dl.end_date]
        if after or claims:
            out.append(dict(dealer=dl.dealer_id, name=dl.name, end=dl.end_date, runs=len(after),
                            interfaces=sorted({r.interface for r in after}), last=max((r.run_at for r in after), default=None), claims=len(claims)))
    return out


# ---------------------------------------------------------------- findings

def run_all(d: Data, b: dict | None = None) -> list[Finding]:
    s = d.settings
    b = b or dict(itf=interface_rows(d), claims=claim_rows(d), cat=catalogue_rows(d), dms=dms_rows(d), onb=onboarding_rows(d), term=terminated_rows(d))
    f: list[Finding] = []
    lab = lambda did: (lambda x: x.label if x else did)(d.dealer(did))  # noqa: E731

    # interfaces
    fail = [r for r in b["itf"] if r["verdict"] == "failing" and any("successful" in i or "never" in i for i in r["issues"])]
    for crit in (True, False):
        rows = [r for r in fail if r["critical"] == crit]
        if rows:
            names = sorted({INTERFACE_NAMES[r["interface"]] for r in rows})
            f.append(Finding(CRITICAL if crit else WARNING, "Interfaces", "INT-01",
                             f"{_n(len(rows), 'DMS feed')} not delivering ({', '.join(names)})",
                             "No successful run within the limit: " + _top([f"{lab(r['dealer'])} · {INTERFACE_NAMES[r['interface']]} "
                                                                           f"({r['hours']:.0f} h)" if r['hours'] is not None else f"{lab(r['dealer'])} · never" for r in rows], 6),
                             "Check the dealer's DMS job and credentials with the DMS vendor; re-send the backlog once fixed and confirm the record counts."
                             + (" Warranty and repair-order data stop reaching the brand while this is open." if crit else ""),
                             s.owner("interfaces"), [f"{r['dealer']} {r['interface']} {r['hours']} h" for r in rows], sorted({r["dealer"] for r in rows})))
    err = [r for r in b["itf"] if any("rejected" in i for i in r["issues"])]
    if err:
        f.append(Finding(WARNING, "Interfaces", "INT-02", f"{_n(len(err), 'feed')} rejecting records above {s.error_rate_max_pct:g}%",
                         _top([f"{lab(r['dealer'])} · {INTERFACE_NAMES[r['interface']]} {r['err_pct']:g}%" for r in sorted(err, key=lambda r: -r['err_pct'])], 6),
                         "Pull the rejected messages from the integration log, group them by error code and fix the mapping or the master data "
                         "(labour ops, part numbers, VINs) at the source.", s.owner("interfaces"),
                         [f"{r['dealer']} {r['interface']} {r['err_pct']}%" for r in err], sorted({r["dealer"] for r in err})))
    sil = [r for r in b["itf"] if r["verdict"] == "silent"]
    if sil:
        f.append(Finding(WARNING, "Interfaces", "INT-03", f"{_n(len(sil), 'feed')} succeeding with nothing in them",
                         _top([f"{lab(r['dealer'])} · {INTERFACE_NAMES[r['interface']]} ({r['zero_days']} days at 0)" for r in sil], 6),
                         "A job that succeeds with zero records usually means a changed filter or a disabled export on the DMS side; confirm with "
                         "the dealer that they did trade on those days.", s.owner("interfaces"),
                         [f"{r['dealer']} {r['interface']}" for r in sil], sorted({r["dealer"] for r in sil})))
    nod = [r for r in b["itf"] if r["verdict"] == "no data"]
    if nod:
        f.append(Finding(INFO, "Interfaces", "INT-04", f"{_n(len(nod), 'expected feed')} with no runs in the log",
                         _top([f"{lab(r['dealer'])} · {INTERFACE_NAMES[r['interface']]}" for r in nod], 6),
                         "Confirm whether the dealer should send this feed (service-only dealers send no vehicle sales) and adjust the expected feeds.",
                         s.owner("interfaces"), [f"{r['dealer']} {r['interface']}" for r in nod], sorted({r["dealer"] for r in nod})))

    # warranty
    c = b["claims"]
    lost = [r for r in c["at_risk"] if r["days_left"] < 0]
    soon = [r for r in c["at_risk"] if r["days_left"] >= 0]
    if lost:
        amt = sum(r["claim"].amount for r in lost)
        f.append(Finding(CRITICAL, "Warranty", "WAR-01", f"{_n(len(lost), 'draft claim')} past the {s.claim_submit_days}-day submission limit ({_money(d, amt)})",
                         "Repairs done but never submitted: " + _top([f"{lab(k)} ({v})" for k, v in Counter(r['claim'].dealer_id for r in lost).most_common()], 6),
                         "Ask the dealers to submit with the reason for the delay; the warranty team decides case by case whether to accept a late claim.",
                         s.owner("warranty"), [r["claim"].claim_id for r in lost], sorted({r["claim"].dealer_id for r in lost})))
    if soon:
        amt = sum(r["claim"].amount for r in soon)
        f.append(Finding(WARNING, "Warranty", "WAR-02", f"{_n(len(soon), 'draft claim')} due in the next {s.claim_warn_days} days ({_money(d, amt)})",
                         _top([f"{lab(k)} ({v})" for k, v in Counter(r['claim'].dealer_id for r in soon).most_common()], 6),
                         "Send each dealer its list today; most drafts are waiting for a photo, a part return or the technician's report.",
                         s.owner("warranty"), [r["claim"].claim_id for r in soon], sorted({r["claim"].dealer_id for r in soon})))
    if c["pending"]:
        amt = sum(r["claim"].amount for r in c["pending"])
        f.append(Finding(WARNING, "Warranty", "WAR-03", f"{_n(len(c['pending']), 'claim')} waiting for the brand over {s.claim_pending_days} days ({_money(d, amt)})",
                         f"Oldest {c['pending'][0]['days']} days. This one is on our side: the dealer has done its part.",
                         "Work the queue oldest first and agree a target for the brand's own decision time; dealers notice this before anyone else.",
                         s.owner("warranty"), [r["claim"].claim_id for r in c["pending"]]))
    if c["info"]:
        f.append(Finding(WARNING, "Warranty", "WAR-04", f"{_n(len(c['info']), 'claim')} returned for information and not answered in {s.info_request_days} days",
                         _top([f"{lab(k)} ({v})" for k, v in Counter(r['claim'].dealer_id for r in c['info']).most_common()], 6),
                         "Remind the dealers with the exact information requested; claims left unanswered are closed as rejected.",
                         s.owner("warranty"), [r["claim"].claim_id for r in c["info"]], sorted({r["claim"].dealer_id for r in c["info"]})))
    high = [r for r in c["rates"] if r["high"]]
    if high:
        f.append(Finding(WARNING, "Warranty", "WAR-05", f"{_n(len(high), 'dealer')} with a rejection rate above {s.rejection_rate_max_pct:g}%",
                         "; ".join(f"{lab(r['dealer'])} {r['rate']:g}% of {r['decided']} (mostly: {r['reasons'][0][0]})" for r in high[:5]),
                         "Review the top rejection reasons with each dealer's warranty administrator; a reason that repeats is a training or "
                         "master-data problem, not bad claims.", s.owner("warranty"), [f"{r['dealer']} {r['rate']}%" for r in high], [r["dealer"] for r in high]))
    if c["dups"]:
        f.append(Finding(WARNING, "Warranty", "WAR-06", f"{_n(len(c['dups']), 'possible duplicate claim')}",
                         _top([f"{r['second'].claim_id} repeats {r['first'].claim_id} (VIN …{r['vin'][-6:]}, op {r['op']}, {r['gap']} days apart)" for r in c['dups']], 4),
                         "Check each pair before payment: a genuine repeat repair needs a note on the second claim, a duplicate is cancelled.",
                         s.owner("warranty"), [f"{r['first'].claim_id}/{r['second'].claim_id}" for r in c["dups"]],
                         sorted({r["second"].dealer_id for r in c["dups"]})))
    if c["unpaid"]:
        amt = sum(r["claim"].amount for r in c["unpaid"])
        f.append(Finding(WARNING, "Warranty", "WAR-07", f"{_n(len(c['unpaid']), 'accepted claim')} not paid after {s.unpaid_days} days ({_money(d, amt)})",
                         _top([f"{lab(k)} ({v})" for k, v in Counter(r['claim'].dealer_id for r in c['unpaid']).most_common()], 6),
                         "Check the last payment runs with finance: claims accepted but not credited usually point to a failed run or a blocked dealer account.",
                         s.owner("payments"), [r["claim"].claim_id for r in c["unpaid"]], sorted({r["claim"].dealer_id for r in c["unpaid"]})))

    # parts
    price = [r for r in b["cat"] if any("price file" in i for i in r["issues"])]
    if price:
        f.append(Finding(CRITICAL, "Parts", "PRT-01", f"{_n(len(price), 'dealer')} invoicing with an old price file",
                         f"{s.price_version} released {s.price_released:%d %b}: " + _top([f"{lab(r['dealer'])} ({r['price'] or 'none'})" for r in price], 6),
                         "Push the price file again and confirm it is applied in the DMS; parts sold since the grace period ended were priced wrong.",
                         s.owner("parts"), [r["dealer"] for r in price], [r["dealer"] for r in price]))
    old = [r for r in b["cat"] if any(i.startswith("catalogue") for i in r["issues"])]
    two = [r for r in old if (r["behind"] or 0) >= 2]
    one = [r for r in old if r not in two]
    if two:
        f.append(Finding(CRITICAL, "Parts", "PRT-02", f"{_n(len(two), 'dealer')} two or more catalogue versions behind",
                         f"Current {s.catalogue_version}: " + _top([f"{lab(r['dealer'])} ({r['catalogue']})" for r in two], 6),
                         "Catalogues this old carry superseded part numbers and labour operations the warranty system no longer accepts; "
                         "update this week and re-check the dealer's rejected claims afterwards.", s.owner("parts"),
                         [f"{r['dealer']} {r['catalogue']}" for r in two], [r["dealer"] for r in two]))
    if one:
        f.append(Finding(WARNING, "Parts", "PRT-03", f"{_n(len(one), 'dealer')} still on the previous catalogue after the grace period",
                         f"Current {s.catalogue_version}: " + _top([f"{lab(r['dealer'])} ({r['catalogue']})" for r in one], 6),
                         "Schedule the update with each dealer's parts manager.", s.owner("parts"),
                         [f"{r['dealer']} {r['catalogue']}" for r in one], [r["dealer"] for r in one]))
    unk = [r for r in b["cat"] if r["verdict"] == "unknown"]
    if unk:
        f.append(Finding(INFO, "Parts", "PRT-04", f"{_n(len(unk), 'dealer')} with no catalogue status", _top([lab(r["dealer"]) for r in unk], 6),
                         "Add these dealers to the catalogue status report.", s.owner("parts"), [r["dealer"] for r in unk], [r["dealer"] for r in unk]))

    # network
    uns = [r for r in b["dms"] if r["verdict"] == "unsupported"]
    if uns:
        f.append(Finding(WARNING, "Network", "NET-01", f"{_n(len(uns), 'dealer')} on a DMS version not certified for the brand interfaces",
                         _top([f"{lab(r['dealer'])} ({r['dms']} {r['version']})" for r in uns], 6),
                         "Agree an upgrade date with the DMS vendor and the dealer; until then, these dealers are the first suspects for interface errors.",
                         s.owner("dms"), [f"{r['dealer']} {r['dms']} {r['version']}" for r in uns], [r["dealer"] for r in uns]))
    eos = [r for r in b["dms"] if r["verdict"] == "end of support"]
    if eos:
        f.append(Finding(INFO, "Network", "NET-02", f"{_n(len(eos), 'dealer')} on a DMS version that leaves support within {s.eos_warn_days} days",
                         _top([f"{lab(r['dealer'])} ({r['dms']} {r['version']}, {r['eos']:%d %b %Y})" for r in eos], 6),
                         "Ask the vendor for the upgrade plan per dealer.", s.owner("dms"), [r["dealer"] for r in eos], [r["dealer"] for r in eos]))
    for r in b["onb"]:
        if r["verdict"] in ("critical", "at risk"):
            when = f"go-live in {r['days']} days ({r['go_live']:%d %b})" if r["days"] is not None else "no go-live date"
            f.append(Finding(CRITICAL if r["verdict"] == "critical" else WARNING, "Network", "NET-03",
                             f"{lab(r['dealer'])}: {when}, {_n(len(r['open']), 'item')} open", "Open: " + ", ".join(r["open"]),
                             "Close the open items or move the go-live; a dealer that opens without tested interfaces cannot claim warranty from day 1.",
                             s.owner("onboarding"), r["open"], [r["dealer"]]))
    for r in b["term"]:
        what = []
        if r["runs"]:
            what.append(f"{_n(r['runs'], 'interface run')} ({', '.join(INTERFACE_NAMES.get(i, i) for i in r['interfaces'])}), last {r['last']:%d %b}")
        if r["claims"]:
            what.append(f"{_n(r['claims'], 'claim')} submitted")
        f.append(Finding(CRITICAL, "Network", "NET-04", f"{lab(r['dealer'])}: terminated {r['end']:%d %b} and still connected",
                         "Since the end date: " + "; ".join(what) + ".",
                         "Disable the interface credentials and the dealer's portal accounts, and agree with the network team how its last claims are settled.",
                         s.owner("onboarding"), what, [r["dealer"]]))
    f.sort(key=lambda x: (ORDER[x.severity], AREAS.index(x.area), x.code))
    return f


def area_status(findings: list[Finding]) -> dict[str, str]:
    st = {}
    for a in AREAS:
        sev = [f.severity for f in findings if f.area == a and f.severity != INFO]
        st[a] = CRITICAL if CRITICAL in sev else WARNING if sev else "ok"
    return st


# ---------------------------------------------------------------- dealer scorecard

def dealer_rows(d: Data, b: dict, findings: list[Finding]) -> list[dict]:
    out = []
    for dl in d.dealers:
        mine = [f for f in findings if dl.dealer_id in f.dealers and f.severity != INFO]
        itf = [r for r in b["itf"] if r["dealer"] == dl.dealer_id]
        rate = next((r for r in b["claims"]["rates"] if r["dealer"] == dl.dealer_id), None)
        cat = next((r for r in b["cat"] if r["dealer"] == dl.dealer_id), None)
        rag = "red" if any(f.severity == CRITICAL for f in mine) else "amber" if mine else "green"
        out.append(dict(dealer=dl.dealer_id, name=dl.name, country=dl.country, city=dl.city, status=dl.status, dms=f"{dl.dms} {dl.dms_version}".strip(),
                        feeds_ok=sum(r["verdict"] == "ok" for r in itf), feeds=len(itf), rate=rate["rate"] if rate else None,
                        decided=rate["decided"] if rate else 0, catalogue=cat["catalogue"] if cat else "", price=cat["price"] if cat else "",
                        rag=rag, codes=sorted({f.code for f in mine}), manager=dl.manager))
    order = {"red": 0, "amber": 1, "green": 2}
    out.sort(key=lambda r: (order[r["rag"]], r["dealer"]))
    return out
