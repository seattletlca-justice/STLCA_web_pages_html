#!/usr/bin/env python3
"""
Tests for pier_registration_gaps.py using SMALL, MADE-UP SAMPLE ROWS ONLY.
Every address here contains the word SAMPLE. None of it is real Seattle data.
Passing these tests shows the logic does what it says on these rows. It does NOT show
the code works on Kimberly's real files; it has not been run on them.

Run:  python tests/test_pier_registration_gaps.py
"""
import csv
import json
import os
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "code"))
import pier_registration_gaps as pg  # noqa: E402


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def build_sample(d):
    rr = os.path.join(d, "rrio"); os.makedirs(rr)
    sn = os.path.join(d, "snap"); os.makedirs(sn)
    # RRIO RecordList, headers as listed in the Drive Traceability Document
    write_csv(os.path.join(rr, "RRIO_SAMPLE_2021.csv"),
              ["DATE", "RECORDNUMBER", "RECORDTYPE", "PRIVATEINSPECTOR", "STATUSCURRENT", "REGISTRATIONEXPIRED", "ORIGINALADDRESS1", ""],
              [["06/01/2021", "001-9000001", "Rental Property Late Registration Violation", "", "Closed", "", "100 SAMPLE ST SEATTLE", ""],
               ["09/15/2021", "001-0000001", "Rental Property Renewal", "", "Active Registration", "", "100 SAMPLE ST", ""],
               ["02/01/2020", "001-0000003", "Rental Property Registration", "", "Active Registration", "", "300 SAMPLE PL", ""],
               ["SAMPLE FOOTER LINE", "", "", "", "", "", "", ""]])
    # 2023-style variant from the Drive log: snake_case, no record number column
    write_csv(os.path.join(rr, "RRIO_SAMPLE_2023_snake.csv"),
              ["date", "record_type", "private_inspector", "status_current", "registration_expired", "address"],
              [["03/01/2024", "Transfer Existing Registration to New Owners", "", "Completed", "", "100 SAMPLE ST"]])
    # Snapshots, headers as listed in the Drive Traceability Document
    hdr = ["REGISTRATIONNUMBER", "UNITS", "PROPERTYNAME", "REGISTEREDDATE", "EXPIRESDATE", "STATUSCURRENT",
           "ORIGINALADDRESS1", "ORIGINALZIP", "PROPERTYCONTACTNAME", "LATITUDE", "LONGITUDE"]
    write_csv(os.path.join(sn, "Rental_Property_Registration_SAMPLE_2020.csv"), hdr,
              [["001-0000001", "6", "SAMPLE APTS", "03/01/2019", "03/01/2021", "Active Registration", "100 SAMPLE ST", "", "", "", ""]])
    write_csv(os.path.join(sn, "Rental_Property_Registration_SAMPLE_2022.csv"), hdr,
              [["001-0000001", "6", "SAMPLE APTS", "09/15/2021", "09/15/2023", "Active Registration", "100 SAMPLE ST.", "", "", "", ""],
               ["001-0000002", "2", "SAMPLE DUPLEX", "05/01/2024", "05/01/2026", "Active Registration", "200  SAMPLE AVE SEATTLE", "", "", "", ""]])
    # Complaints master: only the columns the script reads, values made up
    write_csv(os.path.join(d, "complaints_SAMPLE.csv"),
              ["RECORDNUM", "RECORDTYPE", "OPENDATE", "ORIGINALADDRESS1", "DISTRICT", "CP", "VI", "CT"],
              [["S00001-20CP", "COMPLAINT", "2020 MAY 01 12:00:00 AM", "100 SAMPLE ST", "9", "TRUE", "FALSE", "FALSE"],
               ["S00002-21CP", "COMPLAINT", "2021 MAY 01 12:00:00 AM", "100 SAMPLE ST", "9", "TRUE", "FALSE", "FALSE"],
               ["S00003-VI", "NOTICE OF VIOLATION", "2024 JAN 10 12:00:00 AM", "100 SAMPLE ST", "9", "FALSE", "TRUE", "FALSE"],
               ["S00004-22CP", "COMPLAINT", "2022 JUN 01 12:00:00 AM", "400 SAMPLE WAY", "9", "TRUE", "FALSE", "FALSE"]])
    write_csv(os.path.join(d, "topics_SAMPLE.csv"), ["record_number", "topic_rent_increases_and_fees"],
              [["S00002-21CP", "yes"], ["S00001-20CP", ""]])
    write_csv(os.path.join(d, "reg03_SAMPLE.csv"), ["record_num", "address", "matched_phrase"],
              [["S00004-22CP", "400 SAMPLE WAY", "UNREGISTERED"]])
    write_csv(os.path.join(d, "evictions_SAMPLE.csv"), ["CaseID", "PropAddress", "FiledDate"],
              [["SAMPLE-E1", "100 SAMPLE ST", "2021-04-01"],
               ["SAMPLE-E2", "100 SAMPLE ST", "2020-01-01"],
               ["SAMPLE-E3", "400 SAMPLE WAY", "2022-07-01"],
               ["SAMPLE-E4", "200 SAMPLE AVE", "2025-12-01"],
               ["SAMPLE-E5", "", "2022-01-01"],
               ["SAMPLE-E6", "100 SAMPLE ST", "2018-01-01"],
               ["SAMPLE-E7", "300 SAMPLE PL", "2023-03-01"]])
    json.dump({"schedules": [{"label": "TEST ONLY made-up fees", "effective_from": "2015-01-01",
                              "property_fee": 100, "additional_unit_fee": 10, "late_fee": 25,
                              "term_days": 730, "verified": False, "source": "test"}]},
              open(os.path.join(d, "fees_TEST.json"), "w"))
    return rr, sn


def rows(db, sql):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    out = [dict(r) for r in c.execute(sql)]
    c.close()
    return out


class SampleRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="pier_sample_")
        rr, sn = build_sample(cls.tmp)
        cls.out = os.path.join(cls.tmp, "out")
        d = cls.tmp
        cls.rc = pg.main(["--rrio-dir", rr, "--snapshot-dir", sn, "--rrio-glob", "RRIO_*.csv",
                          "--snapshot-glob", "Rental_*.csv",
                          "--complaints", os.path.join(d, "complaints_SAMPLE.csv"),
                          "--topics", os.path.join(d, "topics_SAMPLE.csv"),
                          "--reg03", os.path.join(d, "reg03_SAMPLE.csv"),
                          "--evictions", os.path.join(d, "evictions_SAMPLE.csv"),
                          "--evictions-address-col", "PropAddress", "--evictions-date-col", "FiledDate",
                          "--evictions-id-col", "CaseID",
                          "--fee-schedule", os.path.join(d, "fees_TEST.json"), "--out-dir", cls.out])
        cls.db = os.path.join(cls.out, "pier_registration_gaps_DRAFT.sqlite")

    def test_run_ok(self):
        self.assertEqual(self.rc, 0)

    def test_address_normalization(self):
        self.assertEqual(pg.normalize_address("200  sample ave Seattle"), "200 SAMPLE AVE")
        self.assertEqual(pg.normalize_address("100 SAMPLE ST."), "100 SAMPLE ST")

    def test_gaps_at_100(self):
        g = rows(self.db, "SELECT * FROM rrio_registration_gaps WHERE normalized_address='100 SAMPLE ST' ORDER BY gap_start")
        self.assertEqual(len(g), 2)
        self.assertEqual((g[0]["gap_start"], g[0]["gap_end"], g[0]["gap_days"]), ("2021-03-01", "2021-09-15", "198"))
        self.assertEqual(g[0]["late_registration_violation_count"], "1")
        self.assertEqual(g[1]["gap_start"], "2023-09-15")
        self.assertEqual(g[1]["gap_status"], "still open as of 2025-11-20")
        self.assertEqual(g[1]["gap_days"], "797")
        self.assertEqual(g[1]["transfer_events_in_gap"], "1")  # sale inside the gap is kept and shown

    def test_expiring_after_data_end_is_not_lapsed(self):
        g = rows(self.db, "SELECT * FROM rrio_gaps_all WHERE normalized_address='200 SAMPLE AVE'")
        self.assertEqual(g, [])
        p = rows(self.db, "SELECT end_status FROM rrio_registration_periods WHERE normalized_address='200 SAMPLE AVE'")
        self.assertEqual(p[0]["end_status"], "expires after data end - unknown")

    def test_unknown_end_is_not_a_gap_by_default(self):
        self.assertEqual(rows(self.db, "SELECT * FROM rrio_gaps_all WHERE normalized_address='300 SAMPLE PL'"), [])
        u = rows(self.db, "SELECT * FROM rrio_coverage_unknown WHERE normalized_address='300 SAMPLE PL'")
        self.assertEqual(len(u), 1)

    def test_candidates(self):
        c = rows(self.db, "SELECT * FROM unregistered_candidates WHERE normalized_address='400 SAMPLE WAY'")
        self.assertEqual(len(c), 1)
        self.assertIn("reg03_complaint_says_unregistered", c[0]["evidence_kinds"])
        self.assertIn("lt_record_no_rrio_match", c[0]["evidence_kinds"])
        self.assertEqual(c[0]["has_any_rrio_registration_on_file"], "0")

    def test_complaints_during_gaps(self):
        c = rows(self.db, "SELECT record_num, is_rent_increase, is_violation FROM complaints_during_gaps ORDER BY record_num")
        self.assertEqual([r["record_num"] for r in c], ["S00002-21CP", "S00003-VI"])
        self.assertEqual(c[0]["is_rent_increase"], "1")
        self.assertEqual(c[1]["is_violation"], "1")

    def test_evictions(self):
        e = {r["filing_id"]: r["rrio_status_on_filing_date"]
             for r in rows(self.db, "SELECT * FROM evictions_without_registration")}
        self.assertEqual(e, {"SAMPLE-E1": "in_gap", "SAMPLE-E2": "covered", "SAMPLE-E3": "never_registered_on_file",
                             "SAMPLE-E4": "undetermined", "SAMPLE-E5": "could_not_match",
                             "SAMPLE-E6": "before_first_registration", "SAMPLE-E7": "undetermined"})

    def test_money_is_calculation(self):
        m = rows(self.db, "SELECT * FROM rrio_money_estimate ORDER BY gap_start")
        self.assertEqual(len(m), 2)
        self.assertEqual(m[0]["terms_spanned"], 1)
        self.assertAlmostEqual(m[0]["registration_fee_calc"], 150.0)   # 100 + 10 x (6 - 1)
        self.assertAlmostEqual(m[0]["late_fees_schedule_would_apply"], 25.0)
        self.assertEqual(m[1]["terms_spanned"], 2)
        self.assertAlmostEqual(m[1]["registration_fee_calc"], 300.0)
        self.assertIn("CALCULATION ONLY", m[0]["label"])

    def test_estimated_term_is_labeled(self):
        out = os.path.join(self.tmp, "out_est")
        rr, sn = os.path.join(self.tmp, "rrio"), os.path.join(self.tmp, "snap")
        rc = pg.main(["--rrio-dir", rr, "--snapshot-dir", sn, "--rrio-glob", "RRIO_*.csv",
                      "--snapshot-glob", "Rental_*.csv", "--assumed-term-years", "2", "--out-dir", out])
        self.assertEqual(rc, 0)
        db = os.path.join(out, "pier_registration_gaps_DRAFT.sqlite")
        p = rows(db, "SELECT * FROM rrio_registration_periods WHERE normalized_address='300 SAMPLE PL'")
        self.assertTrue(p[0]["end_date_basis"].startswith("ESTIMATED"))
        g = rows(db, "SELECT * FROM rrio_gaps_all WHERE normalized_address='300 SAMPLE PL'")
        self.assertEqual(g[0]["gap_start"], "2022-02-01")


class HeaderRules(unittest.TestCase):
    def test_unknown_header_stops(self):
        d = tempfile.mkdtemp(prefix="pier_hdr_")
        write_csv(os.path.join(d, "RRIO_SAMPLE_bad.csv"), ["DATE", "RECORDTYPE", "ORIGINALADDRESS1", "MYSTERY_COLUMN"],
                  [["01/01/2021", "Rental Property Registration", "1 SAMPLE ST", "x"]])
        rc = pg.main(["--rrio-dir", d, "--rrio-glob", "RRIO_*.csv", "--out-dir", os.path.join(d, "o")])
        self.assertEqual(rc, 2)
        self.assertIn("MYSTERY_COLUMN", open(os.path.join(d, "o", "RUN_LOG.txt")).read())

    def test_unnamed_column_with_values_stops(self):
        d = tempfile.mkdtemp(prefix="pier_hdr2_")
        write_csv(os.path.join(d, "RRIO_SAMPLE_bad2.csv"), ["DATE", "RECORDTYPE", "ORIGINALADDRESS1", ""],
                  [["01/01/2021", "Rental Property Registration", "1 SAMPLE ST", "has a value"]])
        rc = pg.main(["--rrio-dir", d, "--rrio-glob", "RRIO_*.csv", "--out-dir", os.path.join(d, "o")])
        self.assertEqual(rc, 2)

    def test_bad_bytes_stop_without_fallback(self):
        d = tempfile.mkdtemp(prefix="pier_enc_")
        open(os.path.join(d, "RRIO_SAMPLE_enc.csv"), "wb").write(
            b"DATE,RECORDTYPE,ORIGINALADDRESS1\n01/01/2021,Rental Property Registration,1 SAMPLE CAF\xc3 ST\n")
        rc = pg.main(["--rrio-dir", d, "--rrio-glob", "RRIO_*.csv", "--out-dir", os.path.join(d, "o")])
        self.assertEqual(rc, 2)

    def test_refuses_pier_db(self):
        d = tempfile.mkdtemp(prefix="pier_db_")
        with self.assertRaises(SystemExit):
            pg.main(["--out-dir", d, "--sqlite", os.path.join(d, "stlca_property_intelligence.sqlite")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
