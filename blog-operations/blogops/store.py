"""SQLite durable tasks, explicit leases and atomic provider budgets."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from .config import state_dir

def today():
    return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()

class Store:
    def __init__(self, path=None):
        self.path = str(path or state_dir()/"operations.sqlite")
        with self.db() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, site TEXT NOT NULL, kind TEXT NOT NULL,
                provider TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL,
                result TEXT, error TEXT, parent TEXT, dependencies TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL, lease REAL,
                attempts INTEGER NOT NULL DEFAULT 0, dedupe TEXT UNIQUE);
              CREATE TABLE IF NOT EXISTS calls (
                id TEXT PRIMARY KEY, task_id TEXT, provider TEXT NOT NULL, day TEXT NOT NULL,
                state TEXT NOT NULL, model TEXT, duration REAL, created REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, task_id TEXT, event TEXT, details TEXT, created REAL);
              CREATE TABLE IF NOT EXISTS locks (name TEXT PRIMARY KEY, owner TEXT, expires REAL);
              CREATE INDEX IF NOT EXISTS task_state ON tasks(state,created);
              CREATE INDEX IF NOT EXISTS call_day ON calls(day,provider);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def decode(row):
        if row is None:
            return None
        result = dict(row)
        for key in ("payload", "result", "dependencies"):
            result[key] = json.loads(result[key]) if result[key] else None
        return result

    def enqueue(self, site, kind, provider, payload, *, dependencies=(), parent=None, dedupe=None):
        ident = uuid.uuid4().hex
        now = time.time()
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO tasks(id,site,kind,provider,state,payload,parent,dependencies,created,updated,dedupe) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (ident, site, kind, provider, "queued", json.dumps(payload, ensure_ascii=False), parent, json.dumps(list(dependencies)), now, now, dedupe))
            if dedupe:
                ident = db.execute("SELECT id FROM tasks WHERE dedupe=?", (dedupe,)).fetchone()[0]
        return ident

    def get(self, ident):
        with self.db() as db:
            return self.decode(db.execute("SELECT * FROM tasks WHERE id=?", (ident,)).fetchone())

    def list(self, site=None, parent=None):
        query, args = "SELECT * FROM tasks WHERE 1=1", []
        for key, value in (("site", site), ("parent", parent)):
            if value is not None:
                query += f" AND {key}=?"
                args.append(value)
        with self.db() as db:
            return [self.decode(row) for row in db.execute(query+" ORDER BY created", args)]

    def claim(self, ident, lease_seconds=4000):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM tasks WHERE id=?", (ident,)).fetchone()
            if not row or row["state"] != "queued":
                return None
            for dep in json.loads(row["dependencies"]):
                status = db.execute("SELECT state FROM tasks WHERE id=?", (dep,)).fetchone()
                if not status or status[0] != "succeeded":
                    return None
            db.execute("UPDATE tasks SET state='running',attempts=attempts+1,lease=?,updated=? WHERE id=?",
                       (time.time()+lease_seconds, time.time(), ident))
            return self.decode(db.execute("SELECT * FROM tasks WHERE id=?", (ident,)).fetchone())

    def finish(self, ident, result=None, *, error=None, state="succeeded", expected_attempt=None):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT kind,state,attempts,lease FROM tasks WHERE id=?",(ident,)).fetchone()
            if not row:return False
            if row["kind"]!="workflow" and row["attempts"]:
                if expected_attempt!=row["attempts"] or row["state"]!="running" or not row["lease"] or row["lease"]<time.time():
                    return False
            db.execute("UPDATE tasks SET state=?,result=?,error=?,lease=NULL,updated=? WHERE id=?",
                       (state, json.dumps(result, ensure_ascii=False, default=str) if result is not None else None, error, time.time(), ident))
            db.execute("INSERT INTO events(task_id,event,details,created) VALUES(?,?,?,?)", (ident, state, error, time.time()))
            return True

    def retry(self, ident):
        self.recover_expired()
        with self.db() as db:
            row=db.execute("SELECT kind FROM tasks WHERE id=?",(ident,)).fetchone()
            if row and row[0]=="workflow":
                changed=db.execute("UPDATE tasks SET state='queued',error=NULL,updated=? WHERE parent=? AND state IN ('failed','needs_attention','budget_wait')",(time.time(),ident)).rowcount
                if changed:db.execute("UPDATE tasks SET state='workflow_pending',error=NULL WHERE id=?",(ident,))
                return bool(changed)
            changed = db.execute("UPDATE tasks SET state='queued',error=NULL,updated=? WHERE id=? AND state IN ('failed','needs_attention','budget_wait')", (time.time(), ident)).rowcount
            return bool(changed)

    def recover_expired(self):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            expired=db.execute("SELECT id,parent FROM tasks WHERE state='running' AND lease<?",(time.time(),)).fetchall()
            for row in expired:
                db.execute("UPDATE tasks SET state='needs_attention',error='Worker lease expired; inspect outputs before retry',lease=NULL,updated=? WHERE id=?",(time.time(),row["id"]))
                if row["parent"]:
                    db.execute("UPDATE tasks SET state='needs_attention',error='Worker lease expired; inspect outputs before retry',updated=? WHERE id=?",(time.time(),row["parent"]))
            return len(expired)

    def reserve_call(self, provider, model, limit, task_id=None):
        return self.reserve_calls(provider,model,limit,task_id,1)[0]

    def reserve_calls(self,provider,model,limit,task_id=None,amount=1):
        if type(amount) is not int or amount<1:raise ValueError("Invalid reservation count")
        identifiers=[uuid.uuid4().hex for _ in range(amount)]
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT COUNT(*) FROM calls WHERE day=? AND provider=?", (today(),provider)).fetchone()[0]
            if count+amount > limit:
                raise BudgetExceeded(f"{provider} daily call limit reached ({limit})")
            db.executemany("INSERT INTO calls VALUES(?,?,?,?,?,?,?,?)", [(ident,task_id,provider,today(),"reserved",model,None,time.time()) for ident in identifiers])
        return identifiers

    def finish_call(self, ident, status, duration):
        with self.db() as db:
            db.execute("UPDATE calls SET state=?,duration=? WHERE id=?", (status,duration,ident))

    def usage(self):
        with self.db() as db:
            return [dict(row) for row in db.execute("SELECT provider,day,COUNT(*) AS calls,ROUND(SUM(duration),1) AS seconds FROM calls GROUP BY day,provider ORDER BY day DESC")]

    @contextmanager
    def lock(self, name, seconds=4000):
        owner = uuid.uuid4().hex
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM locks WHERE expires<?", (time.time(),))
            try:
                db.execute("INSERT INTO locks VALUES(?,?,?)", (name,owner,time.time()+seconds))
            except sqlite3.IntegrityError:
                raise RuntimeError(f"Worker already active: {name}") from None
        try:
            yield
        finally:
            with self.db() as db:
                db.execute("DELETE FROM locks WHERE name=? AND owner=?", (name,owner))

class BudgetExceeded(RuntimeError):
    pass
