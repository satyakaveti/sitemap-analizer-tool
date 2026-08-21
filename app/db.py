import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from app.config import TURSO_URL, TURSO_TOKEN

logger = logging.getLogger(__name__)

_local = threading.local()
USE_TURSO = bool(TURSO_URL and TURSO_TOKEN)
_schema_ready = False


def _get_conn():
    global _schema_ready
    if not hasattr(_local, "conn") or _local.conn is None:
        if USE_TURSO:
            import libsql_experimental as libsql
            _local.conn = libsql.connect(
                database=TURSO_URL,
                auth_token=TURSO_TOKEN,
            )
        else:
            import sqlite3
            db_path = Path(__file__).resolve().parent.parent / "data" / "scans.db"
            db_path.parent.mkdir(exist_ok=True)
            _local.conn = sqlite3.connect(str(db_path), check_same_thread=False)
            _local.conn.row_factory = sqlite3.Row
            _local.conn.execute("PRAGMA journal_mode=WAL")
            _local.conn.execute("PRAGMA synchronous=NORMAL")

    if not _schema_ready:
        _init_schema(_local.conn)
        _schema_ready = True

    return _local.conn


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    if hasattr(row, "keys"):
        return {col: row[col] for col in row.keys()}
    return None


def _rows_to_dicts(rows) -> list[dict]:
    return [_row_to_dict(r) for r in rows]


def _init_schema(conn):
    stmts = [
        """CREATE TABLE IF NOT EXISTS scans (
            scan_id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'QUEUED',
            phase TEXT DEFAULT '',
            current_url TEXT DEFAULT '',
            sitemaps TEXT DEFAULT '[]',
            total_urls INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            success INTEGER DEFAULT 0,
            redirects INTEGER DEFAULT 0,
            client_errors INTEGER DEFAULT 0,
            server_errors INTEGER DEFAULT 0,
            timeouts INTEGER DEFAULT 0,
            dns_errors INTEGER DEFAULT 0,
            ssl_errors INTEGER DEFAULT 0,
            other_errors INTEGER DEFAULT 0,
            seo_issues INTEGER DEFAULT 0,
            content_issues INTEGER DEFAULT 0,
            started_at TEXT,
            completed_at TEXT,
            error TEXT DEFAULT '',
            report_path TEXT DEFAULT '',
            is_cancelled INTEGER DEFAULT 0,
            scan_type TEXT DEFAULT 'FULL'
        )""",
        """CREATE TABLE IF NOT EXISTS url_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            url TEXT,
            status_code INTEGER,
            final_url TEXT,
            redirect_count INTEGER DEFAULT 0,
            redirect_chain TEXT DEFAULT '[]',
            response_time REAL DEFAULT 0,
            content_type TEXT DEFAULT '',
            content_length INTEGER DEFAULT 0,
            title TEXT DEFAULT '',
            title_length INTEGER DEFAULT 0,
            meta_description TEXT DEFAULT '',
            meta_description_length INTEGER DEFAULT 0,
            h1 TEXT DEFAULT '',
            h1_count INTEGER DEFAULT 0,
            word_count INTEGER DEFAULT 0,
            canonical TEXT DEFAULT '',
            robots TEXT DEFAULT '',
            indexable INTEGER DEFAULT 1,
            error TEXT DEFAULT '',
            issues TEXT DEFAULT '[]',
            score INTEGER DEFAULT 0,
            internal_link_count INTEGER DEFAULT 0,
            external_link_count INTEGER DEFAULT 0,
            broken_link_count INTEGER DEFAULT 0,
            image_count INTEGER DEFAULT 0,
            image_no_alt_count INTEGER DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS recent_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            url TEXT,
            status TEXT,
            time TEXT,
            size TEXT,
            title TEXT,
            words TEXT,
            issues INTEGER DEFAULT 0,
            score INTEGER DEFAULT 0
        )""",
        "CREATE INDEX IF NOT EXISTS idx_results_scan ON url_results(scan_id)",
        "CREATE INDEX IF NOT EXISTS idx_recent_scan ON recent_results(scan_id)",
    ]
    for stmt in stmts:
        try:
            conn.execute(stmt)
        except Exception as e:
            logger.warning(f"Schema statement failed: {e}")
    
    # Run Alter Table migration for existing databases
    try:
        conn.execute("ALTER TABLE scans ADD COLUMN scan_type TEXT DEFAULT 'FULL'")
    except Exception:
        pass

    conn.commit()


_db_lock = threading.Lock()


def execute_sql(sql: str, params: tuple = (), commit: bool = False):
    global _schema_ready
    
    with _db_lock:
        for attempt in range(2):
            try:
                conn = _get_conn()
                cur = conn.execute(sql, params)
                if commit:
                    conn.commit()
                return cur
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"Database execute failed: {e}. Resetting connection and retrying...")
                    if hasattr(_local, "conn") and _local.conn is not None:
                        try:
                            _local.conn.close()
                        except Exception:
                            pass
                        _local.conn = None
                    _schema_ready = False
                else:
                    logger.error(f"Database execute failed on retry: {e}")
                    raise e


def init_db():
    _get_conn()


def cleanup_old_scans(hours: int = 24):
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    cur = execute_sql(
        "SELECT scan_id FROM scans WHERE (completed_at < ?) OR (completed_at IS NULL AND started_at < ?)",
        (cutoff, cutoff),
    )
    old = cur.fetchall()
    for row in old:
        sid = row[0] if isinstance(row, tuple) else row["scan_id"]
        execute_sql("DELETE FROM url_results WHERE scan_id = ?", (sid,))
        execute_sql("DELETE FROM recent_results WHERE scan_id = ?", (sid,))
    execute_sql(
        "DELETE FROM scans WHERE (completed_at < ?) OR (completed_at IS NULL AND started_at < ?)",
        (cutoff, cutoff),
        commit=True
    )


def create_scan(scan_id: str, sitemaps: list[str], scan_type: str = "FULL"):
    execute_sql(
        "INSERT INTO scans (scan_id, sitemaps, started_at, scan_type) VALUES (?, ?, ?, ?)",
        (scan_id, json.dumps(sitemaps), datetime.utcnow().isoformat(), scan_type),
        commit=True
    )


def update_scan(scan_id: str, **kwargs):
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [scan_id]
    execute_sql(f"UPDATE scans SET {sets} WHERE scan_id = ?", tuple(vals), commit=True)


def increment_scan(scan_id: str, field: str, amount: int = 1):
    execute_sql(f"UPDATE scans SET {field} = {field} + ? WHERE scan_id = ?", (amount, scan_id), commit=True)


def add_result(scan_id: str, r: dict):
    execute_sql(
        """INSERT INTO url_results
        (scan_id, url, status_code, final_url, redirect_count, redirect_chain,
         response_time, content_type, content_length, title, title_length,
         meta_description, meta_description_length, h1, h1_count, word_count,
         canonical, robots, indexable, error, issues, score,
         internal_link_count, external_link_count, broken_link_count,
         image_count, image_no_alt_count)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            scan_id, r.get("url"), r.get("status_code"), r.get("final_url"),
            r.get("redirect_count", 0), json.dumps(r.get("redirect_chain", [])),
            r.get("response_time", 0), r.get("content_type", ""),
            r.get("content_length", 0), r.get("title", ""),
            r.get("title_length", 0), r.get("meta_description", ""),
            r.get("meta_description_length", 0), r.get("h1", ""),
            r.get("h1_count", 0), r.get("word_count", 0),
            r.get("canonical", ""), r.get("robots", ""),
            1 if r.get("indexable", True) else 0,
            r.get("error", ""), json.dumps(r.get("issues", [])),
            r.get("score", 0),
            r.get("internal_link_count", 0),
            r.get("external_link_count", 0),
            r.get("broken_link_count", 0),
            r.get("image_count", 0),
            r.get("image_no_alt_count", 0),
        ),
        commit=True
    )


def update_recent(scan_id: str, entry: dict):
    execute_sql(
        "INSERT INTO recent_results (scan_id, url, status, time, size, title, words, issues, score) VALUES (?,?,?,?,?,?,?,?,?)",
        (scan_id, entry.get("url", ""), entry.get("status", ""),
         entry.get("time", ""), entry.get("size", ""),
         entry.get("title", ""), entry.get("words", ""),
         entry.get("issues", 0), entry.get("score", 0)),
    )
    execute_sql(
        """DELETE FROM recent_results WHERE scan_id = ? AND id NOT IN
        (SELECT id FROM recent_results WHERE scan_id = ? ORDER BY id DESC LIMIT 5)""",
        (scan_id, scan_id),
        commit=True
    )


def _fetch(sql: str, params: tuple = ()) -> list[dict]:
    cur = execute_sql(sql, tuple(params))
    rows = cur.fetchall()

    if not rows:
        return []
    
    first = rows[0]
    if hasattr(first, "keys"):
        return [{col: r[col] for col in r.keys()} for r in rows]
    elif cur.description:
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, r)) for r in rows]
    return rows



def _fetch_one(sql: str, params: tuple = ()) -> Optional[dict]:
    rows = _fetch(sql, params)
    return rows[0] if rows else None


def get_status(scan_id: str) -> Optional[dict]:
    d = _fetch_one("SELECT * FROM scans WHERE scan_id = ?", (scan_id,))
    if not d:
        return None

    d["sitemaps"] = json.loads(d["sitemaps"]) if isinstance(d["sitemaps"], str) else d["sitemaps"]
    d["total"] = d["total_urls"]
    d["percentage"] = round((d["completed"] / d["total_urls"] * 100), 2) if d["total_urls"] > 0 else 0

    elapsed = 0.0
    if d["started_at"]:
        start = datetime.fromisoformat(d["started_at"])
        end = datetime.fromisoformat(d["completed_at"]) if d["completed_at"] else datetime.utcnow()
        elapsed = (end - start).total_seconds()
    d["elapsed"] = round(elapsed, 1)

    d["eta"] = None
    if d["completed"] > 0 and d["total_urls"] > 0 and d["status"] == "RUNNING":
        rate = d["completed"] / elapsed if elapsed > 0 else 0
        remaining = d["total_urls"] - d["completed"]
        d["eta"] = round(remaining / rate, 1) if rate > 0 else None

    recent = _fetch(
        "SELECT url, status, time, size, title, words, issues FROM recent_results WHERE scan_id = ? ORDER BY id DESC",
        (scan_id,),
    )
    d["recent_results"] = recent

    return d


def get_results(scan_id: str) -> list[dict]:
    rows = _fetch("SELECT * FROM url_results WHERE scan_id = ?", (scan_id,))
    for d in rows:
        d["issues"] = json.loads(d["issues"]) if isinstance(d["issues"], str) else d.get("issues", [])
        d["redirect_chain"] = json.loads(d["redirect_chain"]) if isinstance(d["redirect_chain"], str) else d.get("redirect_chain", [])
        d["indexable"] = bool(d["indexable"])
    return rows


def get_error_summary(scan_id: str) -> list[dict]:
    rows = _fetch("""
        SELECT
            CASE
                WHEN error != '' THEN error
                WHEN status_code >= 500 THEN 'HTTP ' || status_code || ' Server Error'
                WHEN status_code >= 400 THEN 'HTTP ' || status_code || ' Client Error'
                ELSE NULL
            END as error_type,
            COUNT(*) as count,
            GROUP_CONCAT(url, '||') as urls
        FROM url_results
        WHERE scan_id = ?
          AND (error != '' OR status_code >= 400)
        GROUP BY error_type
        ORDER BY count DESC
    """, (scan_id,))

    summaries = []
    for rd in rows:
        urls = rd["urls"].split("||") if rd.get("urls") else []
        summaries.append({
            "error_type": rd["error_type"],
            "count": rd["count"],
            "sample_urls": urls[:5],
        })
    return summaries


def get_seo_summary(scan_id: str) -> list[dict]:
    summaries = []
    seo_codes = [
        ("TITLE_MISSING", "Missing title"),
        ("TITLE_SHORT", "Title too short"),
        ("TITLE_LONG", "Title too long"),
        ("TITLE_VERY_LONG", "Title very long"),
        ("META_DESC_MISSING", "Missing meta description"),
        ("META_DESC_SHORT", "Meta desc too short"),
        ("META_DESC_LONG", "Meta desc too long"),
        ("META_DESC_VERY_LONG", "Meta desc very long"),
        ("H1_MISSING", "Missing H1"),
        ("H1_MULTIPLE", "Multiple H1 tags"),
        ("H1_EMPTY", "Empty H1"),
        ("CANONICAL_MISSING", "Missing canonical"),
        ("CANONICAL_CROSS_DOMAIN", "Canonical cross-domain"),
        ("ROBOTS_NOINDEX", "Noindex directive"),
        ("ROBOTS_NOFOLLOW", "Nofollow directive"),
        ("VIEWPORT_MISSING", "Missing viewport"),
        ("OG_MISSING", "Missing OG tags"),
        ("OG_PARTIAL", "Partial OG tags"),
    ]
    for code, label in seo_codes:
        rows = _fetch(
            "SELECT COUNT(*) as c FROM url_results WHERE scan_id = ? AND issues LIKE ?",
            (scan_id, f'%"{code}"%'),
        )
        count = rows[0]["c"] if rows else 0
        if count > 0:
            summaries.append({"issue": label, "count": count})
    return summaries


def get_content_summary(scan_id: str) -> list[dict]:
    summaries = []
    content_codes = [
        ("CONTENT_VERY_THIN", "Very thin content (<50 words)"),
        ("CONTENT_THIN", "Thin content (<100 words)"),
        ("CONTENT_WRONG_TYPE", "Wrong content type"),
        ("SOFT_404", "Possible soft 404"),
        ("APP_ERROR_PAGE", "Possible application error"),
    ]
    for code, label in content_codes:
        if code == "SOFT_404":
            pattern = '%"SOFT_404%'
        else:
            pattern = f'%"{code}"%'
        rows = _fetch(
            "SELECT COUNT(*) as c FROM url_results WHERE scan_id = ? AND issues LIKE ?",
            (scan_id, pattern),
        )
        count = rows[0]["c"] if rows else 0
        if count > 0:
            summaries.append({"issue": label, "count": count})
    return summaries


def count_by_status(scan_id: str) -> dict:
    rows = _fetch("""
        SELECT
            CASE
                WHEN status_code IS NULL AND error != '' THEN 'error'
                WHEN status_code BETWEEN 200 AND 299 THEN '2xx'
                WHEN status_code BETWEEN 300 AND 399 THEN '3xx'
                WHEN status_code BETWEEN 400 AND 499 THEN '4xx'
                WHEN status_code BETWEEN 500 AND 599 THEN '5xx'
                ELSE 'other'
            END as category,
            COUNT(*) as count
        FROM url_results WHERE scan_id = ?
        GROUP BY category
    """, (scan_id,))
    return {r["category"]: r["count"] for r in rows}


def get_all_issues_grouped(scan_id: str) -> list[dict]:
    rows = _fetch("SELECT issues, url FROM url_results WHERE scan_id = ?", (scan_id,))

    issue_map: dict[str, dict] = {}
    for rd in rows:
        issues = json.loads(rd["issues"]) if isinstance(rd["issues"], str) else rd.get("issues", [])
        url = rd["url"]
        for issue in issues:
            if isinstance(issue, dict):
                code = issue.get("code", "UNKNOWN")
                msg = issue.get("message", code)
                priority = issue.get("priority", "info")
                key = code
            else:
                code = str(issue)
                msg = code
                priority = "info"
                key = code

            if not key:
                continue
            if key not in issue_map:
                issue_map[key] = {"issue": msg, "code": code, "priority": priority, "count": 0, "sample_urls": []}
            issue_map[key]["count"] += 1
            if len(issue_map[key]["sample_urls"]) < 5:
                issue_map[key]["sample_urls"].append(url)

    return sorted(issue_map.values(), key=lambda x: x["count"], reverse=True)


def get_url_detail(scan_id: str, url: str) -> Optional[dict]:
    rows = _fetch("SELECT * FROM url_results WHERE scan_id = ? AND url = ?", (scan_id, url))
    if not rows:
        return None
    d = rows[0]
    d["issues"] = json.loads(d["issues"]) if isinstance(d["issues"], str) else d.get("issues", [])
    d["redirect_chain"] = json.loads(d["redirect_chain"]) if isinstance(d["redirect_chain"], str) else d.get("redirect_chain", [])
    d["indexable"] = bool(d["indexable"])
    return d


def get_url_detail_by_id(scan_id: str, result_id: int) -> Optional[dict]:
    rows = _fetch("SELECT * FROM url_results WHERE scan_id = ? AND id = ?", (scan_id, result_id))
    if not rows:
        return None
    d = rows[0]
    d["issues"] = json.loads(d["issues"]) if isinstance(d["issues"], str) else d.get("issues", [])
    d["redirect_chain"] = json.loads(d["redirect_chain"]) if isinstance(d["redirect_chain"], str) else d.get("redirect_chain", [])
    d["indexable"] = bool(d["indexable"])
    return d


def get_paginated_results(scan_id: str, offset: int = 0, limit: int = 50,
                          search: str = "", status_filter: str = "",
                          issue_filter: str = "") -> tuple[list[dict], int]:

    where = ["scan_id = ?"]
    params: list = [scan_id]

    if search:
        where.append("url LIKE ?")
        params.append(f"%{search}%")

    if status_filter == "error":
        where.append("status_code IS NULL AND error != ''")
    elif status_filter == "4xx":
        where.append("status_code BETWEEN 400 AND 499")
    elif status_filter == "5xx":
        where.append("status_code BETWEEN 500 AND 599")
    elif status_filter == "2xx":
        where.append("status_code BETWEEN 200 AND 299")
    elif status_filter == "3xx":
        where.append("status_code BETWEEN 300 AND 399")

    if issue_filter:
        where.append("issues LIKE ?")
        params.append(f"%{issue_filter}%")

    where_str = " AND ".join(where)

    total_rows = _fetch(f"SELECT COUNT(*) as c FROM url_results WHERE {where_str}", tuple(params))
    total = total_rows[0]["c"] if total_rows else 0

    rows = _fetch(
        f"SELECT * FROM url_results WHERE {where_str} ORDER BY id LIMIT ? OFFSET ?",
        tuple(params + [limit, offset]),
    )

    for d in rows:
        d["issues"] = json.loads(d["issues"]) if isinstance(d["issues"], str) else d.get("issues", [])
        d["redirect_chain"] = json.loads(d["redirect_chain"]) if isinstance(d["redirect_chain"], str) else d.get("redirect_chain", [])
        d["indexable"] = bool(d["indexable"])

    return rows, total


def get_recent_scans(limit: int = 10) -> list[dict]:
    rows = _fetch(
        "SELECT scan_id, status, sitemaps, total_urls, completed, success, redirects, "
        "client_errors, server_errors, seo_issues, content_issues, started_at, completed_at, error "
        "FROM scans ORDER BY started_at DESC LIMIT ?",
        (limit,),
    )
    for d in rows:
        d["sitemaps"] = json.loads(d["sitemaps"]) if isinstance(d["sitemaps"], str) else d.get("sitemaps", [])
    return rows
