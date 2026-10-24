import csv
import hashlib
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from dealerhealth import cli
from dealerhealth.checks import (CRITICAL, INFO, ORDER, WARNING, catalogue_rows, claim_rows, dms_rows, interface_rows, onboarding_rows, run_all,
                                 terminated_rows)
from dealerhealth.model import Catalogue, Claim, Data, Dealer, Run, Settings, interface_key, load, load_claims, load_dealers, load_runs, num, \
    parse_dt, settings_from_dict

AS_OF = datetime(2026, 10, 25, 8, 0)


def write(path: Path, header: list[str], rows: list[list], delimiter: str = ",") -> Path:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=delimiter)
        w.writerow(header)
        w.writerows(rows)
    return path


def data(**kw) -> Data:
    s = kw.pop("settings", Settings())
    dealers = kw.pop("dealers", [Dealer("D1", "One", status="active")])
    return Data(s, AS_OF, dealers, **kw)


def runs_for(dealer: str, interface: str, days: int = 14, status: str = "ok", records: int = 20, errors: int = 0) -> list[Run]:
    return [Run(dealer, interface, datetime(2026, 10, 25, 2, 15) - timedelta(days=i), status, records, errors) for i in range(days)]


class TestLoading(unittest.TestCase):
    def test_dealer_export_with_other_column_names_and_semicolons(self):
        with tempfile.TemporaryDirectory() as t:
            p = write(Path(t) / "dealers.csv", ["Código", "Razón social", "País", "DMS", "Versión", "Estado", "Alta", "Baja"],
                      [["D1", "Uno", "ES", "DriveLedger", "7.3", "Activo", "01/03/2019", ""],
                       ["D2", "Dos", "PT", "GarageOne", "2026.1", "Baja", "01/03/2018", "30/09/2026"],
                       ["D3", "Tres", "ES", "MotorDesk", "5", "Onboarding", "30/10/2026", ""]], delimiter=";")
            ds = load_dealers(p)
        self.assertEqual([d.status for d in ds], ["active", "terminated", "onboarding"])
        self.assertEqual(ds[1].end_date, date(2026, 9, 30))
        self.assertEqual(ds[0].dms_version, "7.3")

    def test_run_log_statuses_and_interface_names(self):
        with tempfile.TemporaryDirectory() as t:
            p = write(Path(t) / "runs.csv", ["Dealer", "Job", "Started", "Result", "Rows", "Rejected"],
                      [["D1", "Warranty", "2026-10-25T02:30:00", "Success", "12", "0"], ["D1", "RO", "2026-10-25 02:15", "Timeout", "", ""],
                       ["D1", "Parts orders", "2026-10-25 02:45", "Warning", "1.200", "3"]])
            rs = load_runs(p)
        self.assertEqual([(r.interface, r.status) for r in rs], [("warranty_claims", "ok"), ("repair_orders", "failed"), ("parts_orders", "partial")])
        self.assertEqual(interface_key(""), "")
        self.assertEqual(num("1.234,50"), 1234.5)
        self.assertEqual(parse_dt("never"), None)

    def test_claim_statuses(self):
        with tempfile.TemporaryDirectory() as t:
            p = write(Path(t) / "claims.csv", ["Claim number", "Dealer", "VIN", "Repair date", "Submitted", "Estado", "Importe"],
                      [["C1", "D1", "V1", "2026-10-01", "", "Open", "100"], ["C2", "D1", "V2", "2026-10-01", "2026-10-02", "Returned", "1.000,00"],
                       ["C3", "D1", "V3", "2026-10-01", "2026-10-02", "Approved", "10"], ["C4", "D1", "V4", "2026-10-01", "2026-10-02", "Credited", "1"]])
            cs = load_claims(p)
        self.assertEqual([c.status for c in cs], ["draft", "info", "accepted", "paid"])
        self.assertEqual(cs[1].amount, 1000.0)

    def test_settings_merge_and_required_register(self):
        s = settings_from_dict({"as_of": "2026-10-25 08:00", "interfaces": {"Warranty": {"stale_hours": 12, "critical": True}},
                                "owners": {"parts": "Aftersales parts"}, "claim_submit_days": "45", "unknown": 1})
        self.assertEqual(s.as_of, AS_OF)
        self.assertEqual(s.interfaces, {"warranty_claims": {"stale_hours": 12, "critical": True}})
        self.assertEqual(s.owner("parts"), "Aftersales parts")
        self.assertEqual(s.owner("warranty"), "Warranty team")
        self.assertEqual(s.claim_submit_days, 45)
        with tempfile.TemporaryDirectory() as t, self.assertRaises(FileNotFoundError):
            load(Path(t))


class TestInterfaces(unittest.TestCase):
    def verdict(self, runs, itf="repair_orders"):
        d = data(runs=runs)
        return next(r for r in interface_rows(d) if r["interface"] == itf)

    def test_healthy_feed(self):
        r = self.verdict(runs_for("D1", "repair_orders"))
        self.assertEqual(r["verdict"], "ok")
        self.assertAlmostEqual(r["hours"], 5.8, places=1)

    def test_one_failed_night_on_a_daily_feed_is_failing(self):
        rs = runs_for("D1", "repair_orders")
        rs[0] = Run("D1", "repair_orders", rs[0].run_at, "failed", 0, 0)
        r = self.verdict(rs)
        self.assertEqual(r["verdict"], "failing")
        self.assertIn("no successful run for 30 h", r["issues"][0])

    def test_rejected_records_and_silent_feeds(self):
        self.assertEqual(self.verdict(runs_for("D1", "repair_orders", status="partial", records=90, errors=10))["verdict"], "errors")
        rs = runs_for("D1", "repair_orders")
        for i in range(4):
            rs[i] = Run("D1", "repair_orders", rs[i].run_at, "ok", 0, 0)
        r = self.verdict(rs)
        self.assertEqual((r["verdict"], r["zero_days"]), ("silent", 4))
        self.assertEqual(self.verdict([])["verdict"], "no data")

    def test_only_active_dealers_are_checked(self):
        d = data(dealers=[Dealer("D1", "One"), Dealer("D2", "Two", status="onboarding")], runs=runs_for("D1", "repair_orders"))
        self.assertEqual({r["dealer"] for r in interface_rows(d)}, {"D1"})


class TestWarranty(unittest.TestCase):
    def claim(self, cid, status, repair=None, submitted=None, status_date=None, **kw):
        return Claim(cid, kw.pop("dealer", "D1"), kw.pop("vin", cid), repair, submitted, status, status_date, **kw)

    def test_queues(self):
        t = AS_OF.date()
        cs = [self.claim("late", "draft", t - timedelta(days=35), amount=500),
              self.claim("soon", "draft", t - timedelta(days=26)),
              self.claim("fresh", "draft", t - timedelta(days=5)),
              self.claim("brand", "submitted", t - timedelta(days=25), t - timedelta(days=20)),
              self.claim("recent", "submitted", t - timedelta(days=8), t - timedelta(days=6)),
              self.claim("info", "info", t - timedelta(days=30), t - timedelta(days=28), t - timedelta(days=14)),
              self.claim("unpaid", "accepted", t - timedelta(days=60), t - timedelta(days=55), t - timedelta(days=40))]
        c = claim_rows(data(claims=cs))
        self.assertEqual([(r["claim"].claim_id, r["days_left"]) for r in c["at_risk"]], [("late", -5), ("soon", 4)])
        self.assertEqual([r["claim"].claim_id for r in c["pending"]], ["brand"])
        self.assertEqual([r["claim"].claim_id for r in c["info"]], ["info"])
        self.assertEqual([r["claim"].claim_id for r in c["unpaid"]], ["unpaid"])
        f = run_all(data(claims=cs))
        self.assertEqual({x.code: x.severity for x in f if x.area == "Warranty"},
                         {"WAR-01": CRITICAL, "WAR-02": WARNING, "WAR-03": WARNING, "WAR-04": WARNING, "WAR-07": WARNING})

    def test_duplicates_ignore_rejected_and_distant_repairs(self):
        t = AS_OF.date()
        cs = [self.claim("a", "paid", t - timedelta(days=50), vin="V", labour_op="ENG-1"),
              self.claim("b", "accepted", t - timedelta(days=40), vin="V", labour_op="ENG-1"),
              self.claim("c", "rejected", t - timedelta(days=39), vin="V", labour_op="ENG-1"),
              self.claim("d", "paid", t - timedelta(days=200), vin="W", labour_op="ENG-1"),
              self.claim("e", "paid", t - timedelta(days=100), vin="W", labour_op="ENG-1")]
        dups = claim_rows(data(claims=cs))["dups"]
        self.assertEqual([(x["first"].claim_id, x["second"].claim_id, x["gap"]) for x in dups], [("a", "b", 10)])

    def test_rejection_rate_needs_enough_decisions(self):
        t = AS_OF.date() - timedelta(days=5)
        cs = [self.claim(f"x{i}", "rejected" if i < 4 else "paid", t, t, t, reason="Missing photos") for i in range(12)]
        cs += [self.claim(f"y{i}", "rejected" if i < 3 else "paid", t, t, t, dealer="D2") for i in range(5)]
        rates = {r["dealer"]: r for r in claim_rows(data(claims=cs, dealers=[Dealer("D1", "One"), Dealer("D2", "Two")]))["rates"]}
        self.assertTrue(rates["D1"]["high"])
        self.assertEqual(rates["D1"]["reasons"][0], ("Missing photos", 4))
        self.assertFalse(rates["D2"]["high"])        # 60% but only 5 decisions


class TestPartsAndNetwork(unittest.TestCase):
    def settings(self):
        return settings_from_dict({"catalogue_version": "2026.10", "catalogue_released": "2026-10-01", "catalogue_versions": ["2026.10", "2026.09", "2026.08"],
                                   "price_version": "P10", "price_released": "2026-10-15", "supported_dms": {"DL": ["7.3"]},
                                   "dms_end_of_support": {"DL 7.3": "2026-12-31"}})

    def test_catalogue_and_price_file(self):
        dl = [Dealer(f"D{i}", f"N{i}") for i in range(1, 6)]
        cat = [Catalogue("D1", "2026.10", None, "P10"), Catalogue("D2", "2026.09", None, "P10"), Catalogue("D3", "2026.08", None, "P10"),
               Catalogue("D4", "2026.10", None, "P09")]
        rows = {r["dealer"]: r for r in catalogue_rows(data(settings=self.settings(), dealers=dl, catalogue=cat))}
        self.assertEqual([rows[f"D{i}"]["verdict"] for i in range(1, 6)], ["ok", "behind", "critical", "critical", "unknown"])
        f = {x.code: x.severity for x in run_all(data(settings=self.settings(), dealers=dl, catalogue=cat))}
        self.assertEqual((f["PRT-01"], f["PRT-02"], f["PRT-03"], f["PRT-04"]), (CRITICAL, CRITICAL, WARNING, INFO))

    def test_dms_onboarding_and_terminated(self):
        dl = [Dealer("D1", "One", dms="DL", dms_version="7.1"), Dealer("D2", "Two", dms="DL", dms_version="7.3"),
              Dealer("D3", "New", status="onboarding", go_live=date(2026, 10, 29)), Dealer("D4", "Later", status="onboarding", go_live=date(2026, 12, 20)),
              Dealer("D5", "Gone", status="terminated", end_date=date(2026, 9, 30)), Dealer("D6", "Clean", status="terminated", end_date=date(2026, 9, 30))]
        d = data(settings=self.settings(), dealers=dl, runs=runs_for("D5", "stock", days=3), onboarding={"D3": {"DMS certified": True}})
        self.assertEqual([r["verdict"] for r in dms_rows(d)][:2], ["unsupported", "end of support"])
        self.assertEqual([r["verdict"] for r in onboarding_rows(d)], ["critical", "in progress"])
        self.assertEqual([(r["dealer"], r["runs"]) for r in terminated_rows(d)], [("D5", 3)])
        codes = [(x.code, x.severity) for x in run_all(d)]
        self.assertIn(("NET-04", CRITICAL), codes)
        self.assertIn(("NET-03", CRITICAL), codes)
        self.assertEqual(sum(c == "NET-03" for c, _ in codes), 1)


class TestDemo(unittest.TestCase):
    def test_demo_end_to_end_is_deterministic(self):
        hashes = []
        with tempfile.TemporaryDirectory() as t:
            for k in range(2):
                out = Path(t) / f"out{k}"
                rc = cli.main(["demo", "--data", str(Path(t) / f"data{k}"), "--out", str(out)])
                self.assertEqual(rc, 0)
                self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(cli.OUTPUTS))
                hashes.append({n: hashlib.sha1((out / n).read_bytes()).hexdigest() for n in cli.OUTPUTS})
            self.assertEqual(hashes[0], hashes[1])
            d = load(Path(t) / "data0")
            f = run_all(d)
        self.assertEqual([x.severity for x in f], sorted((x.severity for x in f), key=ORDER.get))
        codes = {x.code for x in f}
        for c in ("INT-01", "INT-02", "INT-03", "WAR-01", "WAR-03", "WAR-05", "WAR-06", "WAR-07", "PRT-01", "PRT-02", "NET-01", "NET-03", "NET-04"):
            self.assertIn(c, codes)
        self.assertEqual(d.settings.brand, "VanArsdel Motors Iberia")
        self.assertEqual(sum(x.status == "active" for x in d.dealers), 48)

    def test_review_reports_a_missing_register(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o")]), 2)


if __name__ == "__main__":
    unittest.main()
