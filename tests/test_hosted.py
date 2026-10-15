import tempfile, unittest, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sonaweft_web.ledger import Ledger
from sonaweft_web.errors import DomainError
from sonaweft_web.config import quote


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Ledger(self.tmp.name + "/db.sqlite")
        self.owner = str(uuid.uuid4())
        self.db.credit(self.owner, "fixture", 50000)
        self.upload = self.db.upload(
            self.owner, str(uuid.uuid4()), "fixture.wav", 120, 100
        )["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def job(self, request=None, **kw):
        return self.db.confirm(
            self.owner,
            self.upload,
            request or str(uuid.uuid4()),
            kw.get("review", "none"),
            kw.get("trial", False),
            "fixture-ip",
            kw.get("expected", quote(120)["units"]),
        )

    def test_reservation_settles_once_and_survives_reopen(self):
        jid = self.job()["id"]
        self.assertTrue(self.db.start(jid))
        self.db.finish(jid, True)
        self.assertFalse(self.db.finish(jid, True))
        a = Ledger(self.tmp.name + "/db.sqlite").account(self.owner)
        self.assertEqual(a["spent"], 1800)
        self.assertEqual(a["reserved"], 0)
        self.assertEqual(a["available"], 48200)
        self.assertEqual(self.db.operations()["invalid_balances"], 0)

    def test_failed_review_returns_entire_quote_no_partial_customer_charge(self):
        j = self.job(review="standard", expected=2900)
        self.db.start(j["id"])
        self.db.finish(j["id"], False)
        a = self.db.account(self.owner)
        self.assertEqual((a["spent"], a["available"], a["reserved"]), (0, 50000, 0))

    def test_parallel_duplicate_confirmation_reserves_once(self):
        request = str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=8) as p:
            jobs = list(p.map(lambda _: self.job(request), range(8)))
        self.assertEqual(len({j["id"] for j in jobs}), 1)
        self.assertEqual(sum(j["new"] for j in jobs), 1)
        self.assertEqual(self.db.account(self.owner)["reserved"], 1800)

    def test_refund_cancels_queued_work_and_never_regrants(self):
        j = self.job()
        self.db.credit(self.owner, "fixture", 50000, revoked=50000)
        self.assertEqual(self.db.internal(j["id"])["status"], "canceled")
        self.db.credit(self.owner, "fixture", 50000, revoked=0)
        self.assertEqual(self.db.account(self.owner)["available"], 0)
        self.assertEqual(self.db.operations()["invalid_balances"], 0)

    def test_refund_of_running_work_leaves_debt_but_balances_stay_sound(self):
        j = self.job()
        self.db.start(j["id"])
        self.db.credit(self.owner, "fixture", 50000, revoked=50000)
        self.db.finish(j["id"], True)
        self.assertEqual(self.db.account(self.owner)["available"], -1800)
        self.assertEqual(self.db.operations()["invalid_balances"], 0)
        with self.assertRaises(DomainError):
            self.job()

    def test_owner_quote_trial_pause_and_stale_correction_guards(self):
        self.assertIsNone(self.db.upload_get(str(uuid.uuid4()), self.upload))
        with self.assertRaises(DomainError):
            self.job(expected=1)
        trial = self.job(trial=True, expected=0)
        self.assertEqual(trial["seconds"], 30)
        with self.assertRaises(DomainError):
            self.job(trial=True, expected=0)
        self.db.cancel(self.owner, trial["id"])
        self.db.control(paused=True)
        with self.assertRaises(DomainError):
            self.job()
        self.db.control(paused=False)
        j = self.job()
        self.db.start(j["id"])
        self.db.finish(j["id"], True)
        self.db.edit(self.owner, j["id"], 0, {"s000000": "Correction"})
        with self.assertRaises(DomainError):
            self.db.edit(self.owner, j["id"], 0, {"s000000": "Stale"})

    def test_snapshot_strips_media_metadata_and_preserves_money(self):
        blob = self.db.snapshot()
        self.assertNotIn(b"fixture.wav", blob)
        p = Path(self.tmp.name) / "clone.sqlite"
        p.write_bytes(blob)
        self.assertEqual(Ledger(p).account(self.owner)["available"], 50000)
