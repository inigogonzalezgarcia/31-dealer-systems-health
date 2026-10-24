"""Fictional demo: VanArsdel Motors Iberia, the made-up importer of a car brand with 53 dealers in Spain and Portugal, with the
problems placed on purpose. Deterministic (seed 31)."""
from __future__ import annotations

import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

AS_OF = datetime(2026, 10, 25, 8, 0)
TODAY = AS_OF.date()

CITIES = [
    ("ES", "Madrid", "Centre"), ("ES", "Madrid Norte", "Centre"), ("ES", "Alcalá de Henares", "Centre"), ("ES", "Toledo", "Centre"),
    ("ES", "Guadalajara", "Centre"), ("ES", "Valladolid", "Centre"), ("ES", "Salamanca", "Centre"), ("ES", "Burgos", "North"),
    ("ES", "Bilbao", "North"), ("ES", "Vitoria", "North"), ("ES", "San Sebastián", "North"), ("ES", "Santander", "North"),
    ("ES", "Oviedo", "North"), ("ES", "Gijón", "North"), ("ES", "A Coruña", "North"), ("ES", "Vigo", "North"),
    ("ES", "Pamplona", "North"), ("ES", "Logroño", "North"), ("ES", "Zaragoza", "East"), ("ES", "Barcelona", "East"),
    ("ES", "Barcelona Sud", "East"), ("ES", "Girona", "East"), ("ES", "Tarragona", "East"), ("ES", "Lleida", "East"),
    ("ES", "Valencia", "East"), ("ES", "Castellón", "East"), ("ES", "Alicante", "East"), ("ES", "Murcia", "East"),
    ("ES", "Palma", "East"), ("ES", "Sevilla", "South"), ("ES", "Málaga", "South"), ("ES", "Granada", "South"),
    ("ES", "Córdoba", "South"), ("ES", "Cádiz", "South"), ("ES", "Almería", "South"), ("ES", "Badajoz", "South"),
    ("PT", "Lisboa", "Portugal"), ("PT", "Lisboa Oeste", "Portugal"), ("PT", "Porto", "Portugal"), ("PT", "Braga", "Portugal"),
    ("PT", "Coimbra", "Portugal"), ("PT", "Aveiro", "Portugal"), ("PT", "Faro", "Portugal"), ("PT", "Setúbal", "Portugal"),
    ("PT", "Leiria", "Portugal"), ("PT", "Viseu", "Portugal"), ("PT", "Évora", "Portugal"), ("PT", "Funchal", "Portugal"),
    # onboarding (49-51) and terminated (52-53)
    ("ES", "Las Palmas", "South"), ("ES", "Huelva", "South"), ("PT", "Guimarães", "Portugal"), ("ES", "Cáceres", "South"), ("PT", "Viana do Castelo", "Portugal"),
]
SUFFIX = ["Motor", "Automoción", "Cars", "Auto Center", "Motor Group"]
SERVICE_ONLY = {"D006", "D013", "D025", "D034", "D044", "D048"}
INTERFACE_TIMES = {"repair_orders": (2, 15), "warranty_claims": (2, 30), "parts_orders": (2, 45), "vehicle_sales": (3, 0), "stock": (3, 30)}
LABOUR_OPS = ["ENG-0112", "ENG-0340", "ELE-0207", "ELE-0415", "ELE-0520", "BRK-0101", "SUS-0230", "HVA-0310", "BOD-0450", "TRN-0122",
              "INF-0105", "BAT-0601", "BAT-0612", "CHG-0700"]
REASONS = ["Missing photos", "Labour time above standard", "Part not returned", "Vehicle out of warranty", "Labour operation not in catalogue",
           "Duplicate claim", "Causal part not stated"]


def dealer_table() -> list[dict]:
    out = []
    dms_plan = (["DriveLedger 7.3"] * 16 + ["DriveLedger 7.2"] * 8 + ["DriveLedger 7.1"] * 4 + ["GarageOne 2026.1"] * 9 +
                ["GarageOne 2025.2"] * 5 + ["GarageOne 2024.4"] * 3 + ["MotorDesk 5"] * 6)
    order = list(range(51))
    random.Random(7).shuffle(order)
    # pin the placed versions so the story in the README stays true
    pinned = {41: "GarageOne 2024.4", 42: "GarageOne 2024.4", 43: "GarageOne 2024.4", 27: "DriveLedger 7.2"}
    rest = [v for v in dms_plan]
    for v in pinned.values():
        rest.remove(v)
    it = iter([rest[i] for i in order if i < len(rest)])
    for i, (country, city, region) in enumerate(CITIES, start=1):
        did = f"D{i:03d}"
        if i in pinned:
            dms = pinned[i]
        elif i <= 51:
            dms = next(it)
        else:
            dms = "DriveLedger 7.2"
        name, ver = dms.split(" ")
        status = "onboarding" if 49 <= i <= 51 else "terminated" if i >= 52 else "active"
        go_live = {49: date(2026, 10, 30), 50: date(2026, 11, 9), 51: date(2026, 12, 1)}.get(i, date(2014 + i % 11, 1 + i % 12, 1))
        end = {52: date(2026, 9, 30), 53: date(2026, 8, 31)}.get(i)
        out.append(dict(dealer_id=did, name=f"{city} {SUFFIX[i % len(SUFFIX)]}", country=country, city=city,
                        kind="service only" if did in SERVICE_ONLY else "sales and service", dms=name, dms_version=ver, status=status,
                        go_live=go_live.isoformat(), end_date=end.isoformat() if end else "", manager=f"Area manager {region}"))
    return out


def _runs(rng: random.Random, dealers: list[dict]) -> list[list]:
    rows = []
    start = TODAY - timedelta(days=16)
    for dl in dealers:
        did = dl["dealer_id"]
        if dl["status"] == "onboarding" or did == "D053":
            continue
        size = 1 + (int(did[1:]) % 3)
        last_day = TODAY if dl["status"] == "active" or did == "D052" else date.fromisoformat(dl["end_date"])
        day = start
        while day <= last_day:
            wd = day.weekday()
            for itf, (hh, mm) in INTERFACE_TIMES.items():
                if itf == "vehicle_sales" and did in SERVICE_ONLY:
                    continue
                t = datetime.combine(day, datetime.min.time()) + timedelta(hours=hh, minutes=mm + rng.randint(0, 6))
                base = {"repair_orders": 22, "warranty_claims": 6, "parts_orders": 14, "vehicle_sales": 4, "stock": 900}[itf] * size
                # the night run carries the previous day's activity: Monday's run carries Sunday (closed)
                prev = (day - timedelta(days=1)).weekday()
                factor = 0 if prev == 6 and itf != "stock" else 0.5 if prev == 5 and itf != "stock" else 1
                recs = int(base * factor * rng.uniform(0.7, 1.3))
                errs = sum(rng.random() < 0.004 for _ in range(recs)) if itf != "stock" else rng.randint(0, 2)
                status = "ok"
                # placed problems
                if did == "D014" and itf == "warranty_claims" and day >= TODAY - timedelta(days=2):
                    status, recs, errs = "failed", 0, 0
                if did == "D022" and itf == "repair_orders" and day >= TODAY - timedelta(days=1):
                    status, recs, errs = "failed", 0, 0
                if did == "D037" and itf == "parts_orders" and day >= TODAY - timedelta(days=1):
                    status, recs, errs = "failed", 0, 0
                if did == "D031" and itf == "stock":
                    errs = int(recs * rng.uniform(0.18, 0.26))
                    status = "partial"
                if did in ("D041", "D042", "D043") and itf == "parts_orders" and recs:
                    errs = max(1, int(recs * rng.uniform(0.07, 0.13)))
                    status = "partial"
                if did == "D027" and itf == "warranty_claims" and recs:
                    errs = max(1, int(recs * rng.uniform(0.05, 0.12)))
                    status = "partial"
                if did == "D009" and itf == "vehicle_sales" and day >= TODAY - timedelta(days=5):
                    recs, errs = 0, 0
                rows.append([did, itf, t.strftime("%Y-%m-%d %H:%M"), status, recs, errs])
            day += timedelta(days=1)
    return rows


def _claims(rng: random.Random, dealers: list[dict]) -> list[list]:
    rows = []
    vin_n = 100000
    n = 0

    def vin() -> str:
        nonlocal vin_n
        vin_n += 1
        return f"LVA1C2B3X{rng.choice('MNPR')}{vin_n:07d}"

    def add(did, v, rd, sub, status, sd, op, amt, reason="", paid=None):
        nonlocal n
        n += 1
        rows.append([f"WC-{2026}{n:05d}", did, v, rd.isoformat(), sub.isoformat() if sub else "", status, sd.isoformat() if sd else "",
                     op, f"{amt:.2f}", reason, paid.isoformat() if paid else ""])
        return rows[-1]

    pay_runs = [date(2026, m, d) for m in range(5, 12) for d in (5, 20)]
    active = [d for d in dealers if d["status"] == "active"]
    for dl in active + [d for d in dealers if d["dealer_id"] == "D052"]:
        did = dl["dealer_id"]
        size = 1 + (int(did[1:]) % 3)
        end = date.fromisoformat(dl["end_date"]) if dl["end_date"] else TODAY
        day = TODAY - timedelta(days=150)
        reject_p = {"D027": 0.34, "D045": 0.24}.get(did, 0.035)
        while day <= end:
            if day.weekday() < 6:
                for _ in range(sum(rng.random() < 0.18 * size for _ in range(2))):
                    op = rng.choice(LABOUR_OPS)
                    amt = round(rng.uniform(90, 1400) * (2.2 if op.startswith(("BAT", "TRN", "ENG")) else 1), 2)
                    v = vin()
                    age = (TODAY - day).days
                    if age <= 12 and rng.random() < 0.3:
                        add(did, v, day, None, "draft", None, op, amt)
                        continue
                    sub = day + timedelta(days=rng.randint(1, 9))
                    if sub > TODAY:
                        add(did, v, day, None, "draft", None, op, amt)
                        continue
                    dec = sub + timedelta(days=rng.randint(2, 11))
                    if dec > TODAY:
                        add(did, v, day, sub, "submitted", sub, op, amt)
                        continue
                    r = rng.random()
                    if r < reject_p:
                        reason = ("Labour operation not in catalogue" if did == "D027" and rng.random() < 0.7 else
                                  "Missing photos" if did == "D045" and rng.random() < 0.7 else rng.choice(REASONS[:5] + REASONS[6:]))
                        add(did, v, day, sub, "rejected", dec, op, amt, reason)
                        continue
                    if r < reject_p + 0.04:
                        answered = dec + timedelta(days=rng.randint(2, 8))
                        if answered > TODAY:
                            add(did, v, day, sub, "info requested", dec, op, amt, rng.choice(["Photo of the part label", "Diagnostic report", "Odometer photo"]))
                            continue
                        dec = answered + timedelta(days=rng.randint(1, 5))
                        if dec > TODAY:
                            add(did, v, day, sub, "submitted", answered, op, amt)
                            continue
                    paid = next((p for p in pay_runs if p >= dec + timedelta(days=2)), None)
                    if did == "D033" and dec >= date(2026, 8, 10):
                        paid = None   # bank details changed in August: the payment runs since then skipped the dealer
                    if paid and paid <= TODAY:
                        add(did, v, day, sub, "paid", dec, op, amt, "", paid)
                    else:
                        add(did, v, day, sub, "accepted", dec, op, amt)
            day += timedelta(days=1)

    # placed: drafts past the 30-day submission limit, and drafts about to miss it
    for did, k, lo, hi in (("D012", 6, 33, 46), ("D020", 4, 31, 39), ("D003", 2, 34, 36)):
        for _ in range(k):
            rd = TODAY - timedelta(days=rng.randint(lo, hi))
            add(did, vin(), rd, None, "draft", None, rng.choice(LABOUR_OPS), round(rng.uniform(250, 1900), 2))
    for did, k in (("D005", 5), ("D016", 3)):
        for _ in range(k):
            rd = TODAY - timedelta(days=rng.randint(24, 28))
            add(did, vin(), rd, None, "draft", None, rng.choice(LABOUR_OPS), round(rng.uniform(250, 1900), 2))
    # placed: battery and charging claims parked in technical review at the brand
    for _ in range(34):
        did = rng.choice(active)["dealer_id"]
        sub = TODAY - timedelta(days=rng.randint(18, 41))
        add(did, vin(), sub - timedelta(days=rng.randint(1, 5)), sub, "submitted", sub, rng.choice(["BAT-0601", "BAT-0612", "CHG-0700"]),
            round(rng.uniform(1800, 6400), 2))
    # placed: information requests one dealer has not answered
    for _ in range(9):
        dec = TODAY - timedelta(days=rng.randint(12, 31))
        sub = dec - timedelta(days=rng.randint(3, 8))
        add("D018", vin(), sub - timedelta(days=3), sub, "info requested", dec, rng.choice(LABOUR_OPS), round(rng.uniform(200, 1500), 2),
            rng.choice(["Photo of the part label", "Diagnostic report", "Odometer photo"]))
    # placed: duplicates (same VIN and labour operation, a few days apart)
    for did in ("D008", "D016", "D029", "D040"):
        v, op = vin(), rng.choice(LABOUR_OPS)
        r1 = TODAY - timedelta(days=rng.randint(40, 70))
        r2 = r1 + timedelta(days=rng.randint(3, 18))
        amt = round(rng.uniform(300, 1200), 2)
        add(did, v, r1, r1 + timedelta(days=2), "paid", r1 + timedelta(days=8), op, amt, "", next(p for p in pay_runs if p >= r1 + timedelta(days=10)))
        add(did, v, r2, r2 + timedelta(days=2), "accepted" if (TODAY - r2).days < 25 else "paid", r2 + timedelta(days=7), op, amt, "",
            None if (TODAY - r2).days < 25 else next(p for p in pay_runs if p >= r2 + timedelta(days=9)))
    return rows


def _catalogue(rng: random.Random, dealers: list[dict]) -> list[list]:
    rows = []
    old1 = {"D011", "D019", "D024", "D038", "D046"}
    old2 = {"D027", "D035"}
    old_price = {"D007", "D021", "D044", "D047"}
    for dl in dealers:
        did = dl["dealer_id"]
        if dl["status"] != "active" or did == "D030":
            continue
        if did in old2:
            cv, cd = "2026.08", date(2026, 8, rng.randint(2, 9))
        elif did in old1:
            cv, cd = "2026.09", date(2026, 9, rng.randint(2, 10))
        else:
            cv, cd = "2026.10", date(2026, 10, rng.randint(2, 10))
        if did in old_price:
            pv, pd = "P2026-09", date(2026, 9, rng.randint(16, 19))
        else:
            pv, pd = "P2026-10", date(2026, 10, rng.randint(15, 19))
        rows.append([did, cv, cd.isoformat(), pv, pd.isoformat()])
    return rows


def _onboarding() -> list[list]:
    items = ["DMS certified", "Interfaces tested", "User accounts", "Catalogue installed", "Warranty training", "Network and VPN"]
    open_items = {"D049": {"Interfaces tested", "Warranty training"}, "D050": {"Interfaces tested", "Catalogue installed", "Warranty training"},
                  "D051": {"DMS certified", "Interfaces tested", "Catalogue installed", "Warranty training"}}
    return [[did, it, "no" if it in open_items[did] else "yes"] for did in open_items for it in items]


SETTINGS = {
    "brand": "VanArsdel Motors Iberia",
    "as_of": "2026-10-25 08:00",
    "currency": "€",
    "interfaces": {"repair_orders": {"stale_hours": 26, "critical": True}, "warranty_claims": {"stale_hours": 26, "critical": True},
                   "parts_orders": {"stale_hours": 26, "critical": False}, "vehicle_sales": {"stale_hours": 74, "critical": False},
                   "stock": {"stale_hours": 50, "critical": False}},
    "window_days": 14,
    "error_rate_max_pct": 5,
    "silent_days": 3,
    "supported_dms": {"DriveLedger": ["7.2", "7.3"], "GarageOne": ["2025.2", "2026.1"], "MotorDesk": ["5"]},
    "dms_end_of_support": {"MotorDesk 5": "2026-12-31", "DriveLedger 7.2": "2027-06-30"},
    "eos_warn_days": 90,
    "claim_submit_days": 30,
    "claim_warn_days": 7,
    "claim_pending_days": 15,
    "info_request_days": 10,
    "rejection_rate_max_pct": 12,
    "min_claims_for_rate": 10,
    "unpaid_days": 30,
    "duplicate_window_days": 30,
    "claims_window_days": 90,
    "catalogue_version": "2026.10",
    "catalogue_released": "2026-10-01",
    "catalogue_grace_days": 10,
    "catalogue_versions": ["2026.10", "2026.09", "2026.08", "2026.07"],
    "price_version": "P2026-10",
    "price_released": "2026-10-15",
    "price_grace_days": 5,
    "onboarding_items": ["DMS certified", "Interfaces tested", "User accounts", "Catalogue installed", "Warranty training", "Network and VPN"],
    "onboarding_warn_days": 21,
    "onboarding_critical_days": 7,
    "owners": {"interfaces": "Integration team", "warranty": "Warranty team", "payments": "Finance", "parts": "Parts team",
               "dms": "Dealer IT", "onboarding": "Network development"},
}


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def write(folder: Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(31)
    dealers = dealer_table()
    cols = ["dealer_id", "name", "country", "city", "kind", "dms", "dms_version", "status", "go_live", "end_date", "manager"]
    _write(folder / "dealers.csv", ["Dealer code", "Name", "Country", "City", "Type", "DMS", "DMS version", "Status", "Go live", "End date",
                                    "Area manager"], [[d[c] for c in cols] for d in dealers])
    _write(folder / "interface_runs.csv", ["Dealer code", "Interface", "Run at", "Status", "Records", "Errors"], _runs(rng, dealers))
    _write(folder / "warranty_claims.csv", ["Claim number", "Dealer code", "VIN", "Repair date", "Submitted", "Status", "Status date",
                                            "Labour op", "Amount", "Reason", "Paid date"], _claims(rng, dealers))
    _write(folder / "catalogue_status.csv", ["Dealer code", "Catalogue version", "Catalogue date", "Price file version", "Price file date"],
           _catalogue(rng, dealers))
    _write(folder / "onboarding.csv", ["Dealer code", "Item", "Done"], _onboarding())
    (folder / "settings.json").write_text(json.dumps(SETTINGS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return folder
