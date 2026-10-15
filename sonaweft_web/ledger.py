"""One serialized SQLite writer; money is integer 1/10,000 USD service allowance."""

import json, sqlite3, time, uuid
from contextlib import closing, contextmanager
from .errors import DomainError
from .payments import PaymentLedger
from .config import quote


class Ledger(PaymentLedger):
    def __init__(self, path):
        self.path = str(path)
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS accounts(owner TEXT PRIMARY KEY,available INTEGER NOT NULL DEFAULT 0,reserved INTEGER NOT NULL DEFAULT 0,spent INTEGER NOT NULL DEFAULT 0,recovery TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS purchases(order_id TEXT PRIMARY KEY,owner TEXT NOT NULL,granted INTEGER NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,verified INTEGER NOT NULL DEFAULT 0,checked REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY,owner TEXT NOT NULL,request TEXT NOT NULL,filename TEXT NOT NULL,duration REAL NOT NULL,bytes INTEGER NOT NULL,created REAL NOT NULL,expires REAL NOT NULL,UNIQUE(owner,request));
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,owner TEXT NOT NULL,upload TEXT NOT NULL,request TEXT NOT NULL,review TEXT NOT NULL,trial INTEGER NOT NULL,seconds REAL NOT NULL,units INTEGER NOT NULL,status TEXT NOT NULL,stage TEXT NOT NULL,created REAL NOT NULL,deadline REAL,expires REAL NOT NULL,error TEXT,revision INTEGER NOT NULL DEFAULT 0,corrections TEXT NOT NULL DEFAULT '{}',UNIQUE(owner,request));
            CREATE TABLE IF NOT EXISTS admission(day TEXT NOT NULL,month TEXT NOT NULL,envelope INTEGER NOT NULL,trial INTEGER NOT NULL,owner TEXT NOT NULL,identity TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS rate(bucket TEXT NOT NULL,identity TEXT NOT NULL,minute INTEGER NOT NULL,count INTEGER NOT NULL,PRIMARY KEY(bucket,identity,minute));
            CREATE TABLE IF NOT EXISTS control(id INTEGER PRIMARY KEY CHECK(id=1),paused INTEGER NOT NULL DEFAULT 0,day_units INTEGER NOT NULL DEFAULT 10000,month_units INTEGER NOT NULL DEFAULT 20000);
            INSERT OR IGNORE INTO control(id) VALUES (1);
            CREATE TABLE IF NOT EXISTS metrics(day TEXT NOT NULL,kind TEXT NOT NULL,count INTEGER NOT NULL,PRIMARY KEY(day,kind));
            """)
            self.setup_payments(db)

    @contextmanager
    def db(self):
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.row_factory = sqlite3.Row
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def account(self, owner):
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO accounts(owner) VALUES (?)", (owner,))
            a = dict(
                db.execute(
                    "SELECT available,reserved,spent,recovery FROM accounts WHERE owner=?",
                    (owner,),
                ).fetchone()
            )
            a["has_recovery"] = bool(a.pop("recovery"))
            return a

    def set_recovery(self, owner, key):
        self.account(owner)
        with self.db() as db:
            db.execute("UPDATE accounts SET recovery=? WHERE owner=?", (key, owner))

    def recover(self, key):
        with self.db() as db:
            r = db.execute(
                "SELECT owner FROM accounts WHERE recovery=?", (key,)
            ).fetchone()
            return r[0] if r else None

    def credit(self, owner, order_id, units, revoked=0, verified=False):
        if (
            type(units) is not int
            or units not in (50000, 100000)
            or type(revoked) is not int
            or not 0 <= revoked <= units
        ):
            raise DomainError("Invalid processing allowance.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT * FROM purchases WHERE order_id=?", (order_id,)
            ).fetchone()
            if prior:
                if prior["owner"] != owner or prior["granted"] != units:
                    raise DomainError(
                        "Purchase ownership/amount differs from its original grant."
                    )
                effective = max(revoked, prior["revoked"])
                delta = effective - prior["revoked"]
                db.execute(
                    "UPDATE purchases SET revoked=?,checked=?,verified=MAX(verified,?) WHERE order_id=?",
                    (effective, time.time(), int(verified), order_id),
                )
                db.execute(
                    "UPDATE accounts SET available=available-? WHERE owner=?",
                    (delta, owner),
                )
            else:
                db.execute("INSERT OR IGNORE INTO accounts(owner) VALUES (?)", (owner,))
                db.execute(
                    "INSERT INTO purchases VALUES (?,?,?,?,?,?)",
                    (order_id, owner, units, revoked, int(verified), time.time()),
                )
                db.execute(
                    "UPDATE accounts SET available=available+? WHERE owner=?",
                    (units - revoked, owner),
                )
            if (
                db.execute(
                    "SELECT available FROM accounts WHERE owner=?", (owner,)
                ).fetchone()[0]
                < 0
            ):
                rows = db.execute(
                    "SELECT * FROM jobs WHERE owner=? AND status='queued'", (owner,)
                ).fetchall()
                for row in rows:
                    self._release(
                        db, row, "canceled", "Refund exceeded remaining credit."
                    )
        return owner

    def purchase_list(self, owner=None):
        with self.db() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM purchases" + (" WHERE owner=?" if owner else ""),
                    (owner,) if owner else (),
                )
            ]

    def upload(self, owner, request, filename, duration, size, retention=172800):
        if not 0 < duration <= 3600 or not 0 < size <= 64 * 1024 * 1024:
            raise DomainError("Media exceeds the supported limit.")
        with self.db() as db:
            prior = db.execute(
                "SELECT * FROM uploads WHERE owner=? AND request=?", (owner, request)
            ).fetchone()
            if prior:
                return dict(prior)
            if (
                db.execute(
                    "SELECT COUNT(*) FROM uploads WHERE owner=? AND expires>?",
                    (owner, time.time()),
                ).fetchone()[0]
                >= 5
            ):
                raise DomainError("Keep at most five uploaded files. Delete one first.")
            retained = db.execute(
                "SELECT COALESCE(SUM(bytes),0) FROM uploads WHERE expires>?",
                (time.time(),),
            ).fetchone()[0]
            if retained + size > 512 * 1024 * 1024:
                raise DomainError(
                    "Upload storage allowance reached; retry after expired media is cleared."
                )
            uid = str(uuid.uuid4())
            now = time.time()
            db.execute(
                "INSERT INTO uploads VALUES (?,?,?,?,?,?,?,?)",
                (
                    uid,
                    owner,
                    request,
                    filename[:180],
                    duration,
                    size,
                    now,
                    now + retention,
                ),
            )
            return dict(
                db.execute("SELECT * FROM uploads WHERE id=?", (uid,)).fetchone()
            )

    def upload_get(self, owner, upload):
        with self.db() as db:
            r = db.execute(
                "SELECT * FROM uploads WHERE id=? AND owner=? AND expires>?",
                (upload, owner, time.time()),
            ).fetchone()
            return dict(r) if r else None

    def confirm(self, owner, upload, request, review, trial, identity, expected):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT * FROM jobs WHERE owner=? AND request=?", (owner, request)
            ).fetchone()
            if prior:
                if (
                    prior["upload"] != upload
                    or prior["review"] != review
                    or bool(prior["trial"]) != trial
                ):
                    raise DomainError("This request already belongs to another quote.")
                return {**dict(prior), "new": False}
            control = db.execute("SELECT * FROM control").fetchone()
            if control["paused"]:
                raise DomainError("Processing is paused. No credit was reserved.")
            media = db.execute(
                "SELECT * FROM uploads WHERE id=? AND owner=? AND expires>?",
                (upload, owner, time.time()),
            ).fetchone()
            if not media:
                raise DomainError("Upload not found or expired.")
            if review not in ("none", "standard", "advanced") or (
                trial and review != "none"
            ):
                raise DomainError("The free sample supports transcription only.")
            seconds = min(30, media["duration"]) if trial else media["duration"]
            units = 0 if trial else quote(seconds, review)["units"]
            if type(expected) is not int or expected != units:
                raise DomainError("Quote changed. Review it before confirming.")
            if (
                db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE owner=? AND status IN ('queued','running')",
                    (owner,),
                ).fetchone()[0]
                >= 2
            ):
                raise DomainError("At most two active jobs per workspace.")
            day = time.strftime("%Y-%m-%d", time.gmtime())
            month = day[:7]
            if trial:
                used = db.execute(
                    "SELECT COUNT(*) FROM admission WHERE trial=1 AND (owner=? OR identity=?)",
                    (owner, identity),
                ).fetchone()[0]
                daily = db.execute(
                    "SELECT COUNT(*) FROM admission WHERE trial=1 AND day=?", (day,)
                ).fetchone()[0]
                monthly = db.execute(
                    "SELECT COUNT(*) FROM admission WHERE trial=1 AND month=?", (month,)
                ).fetchone()[0]
                if used or daily >= 3 or monthly >= 20:
                    raise DomainError(
                        "The bounded sample allowance is used. Hear the completed example above or use the local CLI without hosted sample limits."
                    )
            envelope = (
                2000
                + int(seconds / 60) * 100
                + ({"none": 0, "standard": 500, "advanced": 1500}[review])
            )
            daily = db.execute(
                "SELECT COALESCE(SUM(envelope),0) FROM admission WHERE day=?", (day,)
            ).fetchone()[0]
            monthly = db.execute(
                "SELECT COALESCE(SUM(envelope),0) FROM admission WHERE month=?",
                (month,),
            ).fetchone()[0]
            if (
                daily + envelope > control["day_units"]
                or monthly + envelope > control["month_units"]
            ):
                raise DomainError(
                    "Owner processing safety allowance reached. No credit was reserved."
                )
            db.execute("INSERT OR IGNORE INTO accounts(owner) VALUES (?)", (owner,))
            if (
                units
                and db.execute(
                    "UPDATE accounts SET available=available-?,reserved=reserved+? WHERE owner=? AND available>=?",
                    (units, units, owner, units),
                ).rowcount
                != 1
            ):
                raise DomainError("Not enough processing credit. No job was started.")
            jid = str(uuid.uuid4())
            now = time.time()
            db.execute(
                "INSERT INTO jobs(id,owner,upload,request,review,trial,seconds,units,status,stage,created,expires) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    jid,
                    owner,
                    upload,
                    request,
                    review,
                    int(trial),
                    seconds,
                    units,
                    "queued",
                    "queued",
                    now,
                    media["expires"],
                ),
            )
            db.execute(
                "INSERT INTO admission VALUES (?,?,?,?,?,?)",
                (day, month, envelope, int(trial), owner, identity),
            )
            return {
                **dict(db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()),
                "new": True,
            }

    def start(self, job):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            r = db.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone()
            if not r or r["status"] != "queued":
                return False
            if (
                db.execute("SELECT paused FROM control").fetchone()[0]
                or db.execute(
                    "SELECT available FROM accounts WHERE owner=?", (r["owner"],)
                ).fetchone()[0]
                < 0
            ):
                self._release(
                    db, r, "canceled", "Processing was paused or credit was refunded."
                )
                return False
            db.execute(
                "UPDATE jobs SET status='running',stage='decoding',deadline=? WHERE id=?",
                (time.time() + 1200, job),
            )
            return True

    def stage(self, job, stage):
        if stage not in ("transcribing", "reviewing", "exporting"):
            raise DomainError("Invalid stage.")
        with self.db() as db:
            db.execute(
                "UPDATE jobs SET stage=? WHERE id=? AND status='running'", (stage, job)
            )

    def finish(self, job, success, error=""):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            r = db.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone()
            if not r or r["status"] != "running":
                return False
            if success:
                db.execute(
                    "UPDATE accounts SET reserved=reserved-?,spent=spent+? WHERE owner=?",
                    (r["units"], r["units"], r["owner"]),
                )
                db.execute(
                    "UPDATE jobs SET status='done',stage='ready',deadline=NULL,error=NULL WHERE id=?",
                    (job,),
                )
            else:
                self._release(
                    db,
                    r,
                    "error",
                    error
                    or "Processing failed; reserved credit was returned. Retry explicitly to use retained checkpoints.",
                )
            return True

    def _release(self, db, row, status, error):
        db.execute(
            "UPDATE accounts SET reserved=reserved-?,available=available+? WHERE owner=?",
            (row["units"], row["units"], row["owner"]),
        )
        db.execute(
            "UPDATE jobs SET status=?,stage=?,error=?,deadline=NULL WHERE id=?",
            (status, status, error[:240], row["id"]),
        )

    def get(self, owner, job):
        r = self.internal(job)
        return r if r and r["owner"] == owner and r["expires"] > time.time() else None

    def internal(self, job):
        with self.db() as db:
            r = db.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone()
            return dict(r) if r else None

    def list(self, owner):
        with self.db() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT j.*,u.filename FROM jobs j JOIN uploads u ON u.id=j.upload WHERE j.owner=? AND j.expires>? ORDER BY j.created DESC LIMIT 20",
                    (owner, time.time()),
                )
            ]

    def cancel(self, owner, job):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            r = db.execute(
                "SELECT * FROM jobs WHERE id=? AND owner=?", (job, owner)
            ).fetchone()
            if not r or r["status"] != "queued":
                raise DomainError(
                    "Only queued work can be cancelled; running work is bounded and settles once."
                )
            self._release(db, r, "canceled", "Cancelled before execution.")
            return True

    def edit(self, owner, job, revision, corrections):
        if (
            not isinstance(corrections, dict)
            or len(corrections) > 20000
            or any(
                not isinstance(k, str) or not isinstance(v, str) or len(v) > 10000
                for k, v in corrections.items()
            )
        ):
            raise DomainError("Invalid corrections.")
        with self.db() as db:
            if (
                db.execute(
                    "UPDATE jobs SET corrections=?,revision=revision+1 WHERE id=? AND owner=? AND revision=? AND status='done' AND expires>?",
                    (json.dumps(corrections), job, owner, revision, time.time()),
                ).rowcount
                != 1
            ):
                raise DomainError(
                    "Corrections changed elsewhere or the result expired. Refresh before saving."
                )
        return revision + 1

    def event(self, kind):
        if kind not in (
            "payment_error",
            "reconcile_error",
            "job_error",
            "upload",
            "download",
            "visit",
        ):
            return
        with self.db() as db:
            db.execute(
                "INSERT INTO metrics VALUES (?,?,1) ON CONFLICT(day,kind) DO UPDATE SET count=count+1",
                (time.strftime("%Y-%m-%d", time.gmtime()), kind),
            )

    def admit_request(self, bucket, identity):
        minute = int(time.time() // 60)
        limits = {
            "session": 60,
            "upload": 5,
            "job": 10,
            "payment": 12,
            "read": 120,
            "research": 5,
        }
        if bucket not in limits:
            raise DomainError("Invalid rate limit.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM rate WHERE minute<?", (minute - 2,))
            db.execute(
                "INSERT INTO rate VALUES (?,?,?,1) ON CONFLICT(bucket,identity,minute) DO UPDATE SET count=count+1",
                (bucket, identity, minute),
            )
            personal = db.execute(
                "SELECT count FROM rate WHERE bucket=? AND identity=? AND minute=?",
                (bucket, identity, minute),
            ).fetchone()[0]
            total = db.execute(
                "SELECT SUM(count) FROM rate WHERE bucket=? AND minute=?",
                (bucket, minute),
            ).fetchone()[0]
            if personal > limits[bucket] or total > limits[bucket] * 10:
                raise DomainError("Too many requests. Try again in one minute.")

    def cleanup(self):
        self.stale()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            expired = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM uploads WHERE expires<? AND NOT EXISTS(SELECT 1 FROM jobs WHERE upload=uploads.id AND status='running')",
                    (time.time(),),
                )
            ]
            if expired:
                for uid in expired:
                    db.execute("DELETE FROM jobs WHERE upload=?", (uid,))
                    db.execute("DELETE FROM uploads WHERE id=?", (uid,))
            return expired

    def stale(self):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for row in db.execute(
                "SELECT * FROM jobs WHERE (status='running' AND deadline<?) OR (status='queued' AND created<?)",
                (time.time(), time.time() - 1200),
            ).fetchall():
                self._release(
                    db,
                    row,
                    "error",
                    "Worker deadline exceeded; hold released. Retry explicitly.",
                )

    def control(self, paused=None, day_units=None, month_units=None):
        for value in (day_units, month_units):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= 100000000
            ):
                raise DomainError(
                    "Admission caps must be positive integer credit units."
                )
        with self.db() as db:
            if paused is not None:
                db.execute("UPDATE control SET paused=? WHERE id=1", (int(paused),))
            if day_units is not None:
                db.execute("UPDATE control SET day_units=? WHERE id=1", (day_units,))
            if month_units is not None:
                db.execute(
                    "UPDATE control SET month_units=? WHERE id=1", (month_units,)
                )
            return dict(db.execute("SELECT * FROM control").fetchone())

    def operations(self):
        with self.db() as db:
            invalid = db.execute(
                "SELECT COUNT(*) FROM accounts a WHERE reserved<0 OR spent<0 OR available+reserved+spent!=COALESCE((SELECT SUM(granted-revoked) FROM purchases WHERE owner=a.owner),0)"
            ).fetchone()[0]
            return {
                "invalid_balances": invalid,
                "commercial_purchases": db.execute(
                    "SELECT COUNT(*) FROM purchases WHERE verified=1"
                ).fetchone()[0],
                "pending_jobs": db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')"
                ).fetchone()[0],
                "pending_payments": db.execute(
                    "SELECT COUNT(*) FROM payment_events WHERE completed IS NULL"
                ).fetchone()[0],
                "admission_units": db.execute(
                    "SELECT COALESCE(SUM(envelope),0) FROM admission"
                ).fetchone()[0],
                "control": dict(db.execute("SELECT * FROM control").fetchone()),
                "metrics": [dict(r) for r in db.execute("SELECT * FROM metrics")],
            }

    def snapshot(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            target = d + "/financial.sqlite"
            with self.db() as source, closing(sqlite3.connect(target)) as copy:
                source.backup(copy)
                copy.execute("DELETE FROM jobs")
                copy.execute("DELETE FROM uploads")
                copy.execute("DELETE FROM rate")
                copy.commit()
                copy.execute("VACUUM")
            from pathlib import Path

            return Path(target).read_bytes()
