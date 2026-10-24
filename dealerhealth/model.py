"""Loading: the dealer register, the interface run log, warranty claims, catalogue status, onboarding checklist and settings.json,
with forgiving column names, into plain dataclasses."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

INTERFACES = ("repair_orders", "warranty_claims", "parts_orders", "vehicle_sales", "stock")
INTERFACE_NAMES = {"repair_orders": "Repair orders", "warranty_claims": "Warranty claims", "parts_orders": "Parts orders",
                   "vehicle_sales": "Vehicle sales", "stock": "Parts stock"}

DEALER_ALIASES = {
    "dealer_id": ["dealer id", "dealer", "dealer code", "id", "code", "codigo", "concesionario"],
    "name": ["name", "dealer name", "nombre", "razon social"],
    "country": ["country", "pais", "país"],
    "city": ["city", "ciudad", "location"],
    "kind": ["type", "kind", "dealer type", "tipo"],
    "dms": ["dms", "dms product", "dms vendor", "system"],
    "dms_version": ["dms version", "version", "versión"],
    "status": ["status", "estado"],
    "go_live": ["go live", "go-live", "go live date", "start", "alta"],
    "end_date": ["end date", "terminated", "termination date", "baja", "contract end"],
    "manager": ["area manager", "manager", "aftersales manager", "responsable", "owner"],
}
RUN_ALIASES = {
    "dealer_id": ["dealer id", "dealer", "dealer code", "codigo"],
    "interface": ["interface", "feed", "flow", "job", "interfaz"],
    "run_at": ["run at", "started", "start time", "timestamp", "run time", "date", "fecha"],
    "status": ["status", "result", "estado"],
    "records": ["records", "rows", "messages", "count", "registros"],
    "errors": ["errors", "rejected", "failed records", "errores"],
}
CLAIM_ALIASES = {
    "claim_id": ["claim id", "claim", "claim number", "id", "reclamacion"],
    "dealer_id": ["dealer id", "dealer", "dealer code"],
    "vin": ["vin", "chassis", "bastidor"],
    "repair_date": ["repair date", "repair order date", "ro date", "fecha reparacion"],
    "submitted": ["submitted", "submission date", "sent", "fecha envio"],
    "status": ["status", "claim status", "estado"],
    "status_date": ["status date", "last update", "updated", "decision date"],
    "labour_op": ["labour op", "labor op", "operation", "op code", "operacion"],
    "amount": ["amount", "claimed amount", "total", "importe"],
    "reason": ["reason", "reject reason", "rejection reason", "info requested", "motivo"],
    "paid_date": ["paid date", "payment date", "paid", "fecha pago"],
}
CATALOGUE_ALIASES = {
    "dealer_id": ["dealer id", "dealer", "dealer code"],
    "catalogue_version": ["catalogue version", "catalog version", "epc version", "catalogue"],
    "catalogue_date": ["catalogue date", "catalogue downloaded", "catalog date", "last download"],
    "price_version": ["price file version", "price version", "price file", "tarifa"],
    "price_date": ["price file date", "price date", "price applied", "price file applied"],
}
ONBOARDING_ALIASES = {
    "dealer_id": ["dealer id", "dealer", "dealer code"],
    "item": ["item", "task", "check", "tarea"],
    "done": ["done", "completed", "status", "hecho"],
}
YES = {"yes", "y", "true", "1", "si", "x", "done", "completed", "ok"}
RUN_STATUS = {"ok": "ok", "success": "ok", "succeeded": "ok", "completed": "ok", "partial": "partial", "warning": "partial",
              "failed": "failed", "error": "failed", "failure": "failed", "timeout": "failed", "aborted": "failed"}
CLAIM_STATUS = {"draft": "draft", "open": "draft", "submitted": "submitted", "pending": "submitted", "in review": "submitted",
                "info requested": "info", "returned": "info", "more info": "info", "accepted": "accepted", "approved": "accepted",
                "rejected": "rejected", "declined": "rejected", "paid": "paid", "credited": "paid"}
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d %b %Y")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in s if not unicodedata.combining(ch))).strip()


def yes(v) -> bool:
    return _norm(v) in YES


def parse_dt(v) -> datetime | None:
    s = str(v or "").strip()
    if not s or _norm(s) in {"never", "n a", "na", "none", "nunca"}:
        return None
    s = s.replace("Z", "")
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s[:19] if "T" in s else s, f)
        except ValueError:
            continue
    return None


def parse_date(v) -> date | None:
    d = parse_dt(v)
    return d.date() if d else None


def num(v, default: float = 0.0) -> float:
    s = str(v or "").strip().replace("€", "").replace(" ", "")
    if not s:
        return default
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return default


def _rows(path: Path, aliases: dict[str, list[str]]) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        heads = {_norm(h): h for h in (reader.fieldnames or [])}
        cols = {}
        for key, names in aliases.items():
            for n in [key.replace("_", " ")] + names:
                if _norm(n) in heads:
                    cols[key] = heads[_norm(n)]
                    break
        return [{k: (r.get(c) or "").strip() for k, c in cols.items()} for r in reader]


def interface_key(v: str) -> str:
    n = _norm(v).replace(" ", "_")
    if not n:
        return n
    for k in INTERFACES:
        if n == k or n.startswith(k[:-1]) or k.startswith(n):
            return k
    synonyms = {"ro": "repair_orders", "workshop": "repair_orders", "warranty": "warranty_claims", "claims": "warranty_claims",
                "parts": "parts_orders", "orders": "parts_orders", "sales": "vehicle_sales", "vehicles": "vehicle_sales", "inventory": "stock"}
    return synonyms.get(n.split("_")[0], n)


@dataclass
class Dealer:
    dealer_id: str
    name: str
    country: str = ""
    city: str = ""
    kind: str = "sales and service"
    dms: str = ""
    dms_version: str = ""
    status: str = "active"           # active | onboarding | terminated
    go_live: date | None = None
    end_date: date | None = None
    manager: str = ""

    @property
    def label(self) -> str:
        return f"{self.dealer_id} {self.name}"


@dataclass
class Run:
    dealer_id: str
    interface: str
    run_at: datetime
    status: str                      # ok | partial | failed
    records: int = 0
    errors: int = 0


@dataclass
class Claim:
    claim_id: str
    dealer_id: str
    vin: str
    repair_date: date | None
    submitted: date | None
    status: str                      # draft | submitted | info | accepted | rejected | paid
    status_date: date | None = None
    labour_op: str = ""
    amount: float = 0.0
    reason: str = ""
    paid_date: date | None = None


@dataclass
class Catalogue:
    dealer_id: str
    catalogue_version: str = ""
    catalogue_date: date | None = None
    price_version: str = ""
    price_date: date | None = None


@dataclass
class Settings:
    brand: str = "Brand"
    as_of: datetime | None = None
    currency: str = "€"
    interfaces: dict = field(default_factory=lambda: {
        "repair_orders": {"stale_hours": 26, "critical": True}, "warranty_claims": {"stale_hours": 26, "critical": True},
        "parts_orders": {"stale_hours": 26, "critical": False}, "vehicle_sales": {"stale_hours": 50, "critical": False},
        "stock": {"stale_hours": 50, "critical": False}})
    window_days: int = 14
    error_rate_max_pct: float = 5.0
    silent_days: int = 3
    supported_dms: dict = field(default_factory=dict)        # {"DMS name": ["7.2", "7.3"]}
    dms_end_of_support: dict = field(default_factory=dict)   # {"DMS 5": "2026-12-31"}
    eos_warn_days: int = 90
    claim_submit_days: int = 30
    claim_warn_days: int = 7
    claim_pending_days: int = 15
    info_request_days: int = 10
    rejection_rate_max_pct: float = 12.0
    min_claims_for_rate: int = 10
    unpaid_days: int = 30
    duplicate_window_days: int = 30
    claims_window_days: int = 90
    catalogue_version: str = ""
    catalogue_released: date | None = None
    catalogue_grace_days: int = 10
    catalogue_versions: list = field(default_factory=list)  # newest first, to count how far behind a dealer is
    price_version: str = ""
    price_released: date | None = None
    price_grace_days: int = 5
    onboarding_items: list = field(default_factory=lambda: ["DMS certified", "Interfaces tested", "User accounts", "Catalogue installed",
                                                             "Warranty training", "Network and VPN"])
    onboarding_warn_days: int = 21
    onboarding_critical_days: int = 7
    owners: dict = field(default_factory=lambda: {"interfaces": "Integration team", "warranty": "Warranty team", "payments": "Finance",
                                                  "parts": "Parts team", "dms": "Dealer IT", "onboarding": "Network development"})

    def owner(self, key: str) -> str:
        return self.owners.get(key, "")


def settings_from_dict(raw: dict) -> Settings:
    s = Settings()
    for k, v in raw.items():
        if not hasattr(s, k):
            continue
        cur = getattr(s, k)
        if k == "as_of":
            v = parse_dt(v)
        elif k in ("catalogue_released", "price_released"):
            v = parse_date(v)
        elif k == "interfaces":
            v = {interface_key(i): {**{"stale_hours": 26, "critical": False}, **cfg} for i, cfg in v.items()}
        elif k == "owners":
            v = {**cur, **v}
        elif isinstance(cur, bool):
            v = bool(v)
        elif isinstance(cur, int):
            v = int(v)
        elif isinstance(cur, float):
            v = float(v)
        setattr(s, k, v)
    return s


def _status(raw: str, table: dict, default: str) -> str:
    n = _norm(raw)
    return table.get(n) or table.get((n.split() or [default])[0], default)


def load_dealers(path: Path) -> list[Dealer]:
    out = []
    for r in _rows(path, DEALER_ALIASES):
        if not r.get("dealer_id"):
            continue
        st = _norm(r.get("status", "active"))
        status = "terminated" if st.startswith(("term", "clos", "baja", "inact", "ended")) else "onboarding" if st.startswith(("onb", "new", "pend", "alta")) else "active"
        out.append(Dealer(r["dealer_id"], r.get("name") or r["dealer_id"], r.get("country", ""), r.get("city", ""),
                          r.get("kind") or "sales and service", r.get("dms", ""), r.get("dms_version", ""), status,
                          parse_date(r.get("go_live")), parse_date(r.get("end_date")), r.get("manager", "")))
    return out


def load_runs(path: Path) -> list[Run]:
    out = []
    for r in _rows(path, RUN_ALIASES):
        t = parse_dt(r.get("run_at"))
        if not r.get("dealer_id") or not t:
            continue
        out.append(Run(r["dealer_id"], interface_key(r.get("interface", "")), t, _status(r.get("status", ""), RUN_STATUS, "failed"),
                       int(num(r.get("records"))), int(num(r.get("errors")))))
    return out


def load_claims(path: Path) -> list[Claim]:
    out = []
    for r in _rows(path, CLAIM_ALIASES):
        if not r.get("claim_id"):
            continue
        out.append(Claim(r["claim_id"], r.get("dealer_id", ""), r.get("vin", ""), parse_date(r.get("repair_date")), parse_date(r.get("submitted")),
                         _status(r.get("status", ""), CLAIM_STATUS, "submitted"), parse_date(r.get("status_date")), r.get("labour_op", ""),
                         num(r.get("amount")), r.get("reason", ""), parse_date(r.get("paid_date"))))
    return out


def load_catalogue(path: Path) -> list[Catalogue]:
    return [Catalogue(r["dealer_id"], r.get("catalogue_version", ""), parse_date(r.get("catalogue_date")), r.get("price_version", ""),
                      parse_date(r.get("price_date"))) for r in _rows(path, CATALOGUE_ALIASES) if r.get("dealer_id")]


def load_onboarding(path: Path) -> dict[str, dict[str, bool]]:
    out: dict[str, dict[str, bool]] = {}
    for r in _rows(path, ONBOARDING_ALIASES):
        if r.get("dealer_id") and r.get("item"):
            out.setdefault(r["dealer_id"], {})[r["item"]] = yes(r.get("done", ""))
    return out


@dataclass
class Data:
    settings: Settings
    as_of: datetime
    dealers: list[Dealer]
    runs: list[Run] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    catalogue: list[Catalogue] = field(default_factory=list)
    onboarding: dict[str, dict[str, bool]] = field(default_factory=dict)

    def dealer(self, dealer_id: str) -> Dealer | None:
        return next((d for d in self.dealers if d.dealer_id == dealer_id), None)

    @property
    def today(self) -> date:
        return self.as_of.date()


def load(folder: Path, as_of: datetime | date | None = None) -> Data:
    folder = Path(folder)
    if not (folder / "dealers.csv").exists():
        raise FileNotFoundError(f"{folder / 'dealers.csv'} not found: the dealer register is required")
    sp = folder / "settings.json"
    s = settings_from_dict(json.loads(sp.read_text(encoding="utf-8"))) if sp.exists() else Settings()
    dealers = load_dealers(folder / "dealers.csv")
    if not dealers:
        raise ValueError("dealers.csv has no rows with a dealer id")
    opt = lambda name, fn, empty: fn(folder / name) if (folder / name).exists() else empty  # noqa: E731
    runs = opt("interface_runs.csv", load_runs, [])
    claims = opt("warranty_claims.csv", load_claims, [])
    cat = opt("catalogue_status.csv", load_catalogue, [])
    onb = opt("onboarding.csv", load_onboarding, {})
    if isinstance(as_of, date) and not isinstance(as_of, datetime):
        as_of = datetime.combine(as_of, datetime.min.time()) + timedelta(hours=8)
    when = as_of or s.as_of or (max(r.run_at for r in runs) if runs else datetime.now().replace(microsecond=0))
    return Data(s, when, dealers, runs, claims, cat, onb)
