import sqlite3
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "scans.db"
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(exist_ok=True)
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
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
            is_cancelled INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS url_results (
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
            issues TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS recent_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            url TEXT,
            status TEXT,
            time TEXT,
            size TEXT,
            title TEXT,
            words TEXT,
            issues INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_results_scan ON url_results(scan_id);
        CREATE INDEX IF NOT EXISTS idx_recent_scan ON recent_results(scan_id);
    """)
    conn.commit()


def cleanup_old_scans(hours: int = 24):
    conn = _get_conn()
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    old = conn.execute("SELECT scan_id FROM scans WHERE completed_at < ? OR completed_at IS NULL", (cutoff,)).fetchall()
    for row in old:
        sid = row["scan_id"]
        conn.execute("DELETE FROM url_results WHERE scan_id = ?", (sid,))
        conn.execute("DELETE FROM recent_results WHERE scan_id = ?", (sid,))
    conn.execute("DELETE FROM scans WHERE completed_at < ? OR (completed_at IS NULL AND started_at < ?)", (cutoff, cutoff))
    conn.commit()


def create_scan(scan_id: str, sitemaps: list[str]):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO scans (scan_id, sitemaps, started_at) VALUES (?, ?, ?)",
        (scan_id, json.dumps(sitemaps), datetime.utcnow().isoformat()),
    )
    conn.commit()


def update_scan(scan_id: str, **kwargs):
    conn = _get_conn()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [scan_id]
    conn.execute(f"UPDATE scans SET {sets} WHERE scan_id = ?", vals)
    conn.commit()


def increment_scan(scan_id: str, field: str, amount: int = 1):
    conn = _get_conn()
    conn.execute(f"UPDATE scans SET {field} = {field} + ? WHERE scan_id = ?", (amount, scan_id))
    conn.commit()


def add_result(scan_id: str, r: dict):
    conn = _get_conn()
    conn.execute(
        """INSERT INTO url_results
        (scan_id, url, status_code, final_url, redirect_count, redirect_chain,
         response_time, content_type, content_length, title, title_length,
         meta_description, meta_description_length, h1, h1_count, word_count,
         canonical, robots, indexable, error, issues)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
        ),
    )
    conn.commit()


def update_recent(scan_id: str, entry: dict):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO recent_results (scan_id, url, status, time, size, title, words, issues) VALUES (?,?,?,?,?,?,?,?)",
        (scan_id, entry.get("url", ""), entry.get("status", ""),
         entry.get("time", ""), entry.get("size", ""),
         entry.get("title", ""), entry.get("words", ""),
         entry.get("issues", 0)),
    )
    conn.execute(
        """DELETE FROM recent_results WHERE scan_id = ? AND id NOT IN
        (SELECT id FROM recent_results WHERE scan_id = ? ORDER BY id DESC LIMIT 5)""",
        (scan_id, scan_id),
    )
    conn.commit()


def get_status(scan_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()
    if not row:
        return None

    d = dict(row)
    d["sitemaps"] = json.loads(d["sitemaps"])
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

    recent = conn.execute(
        "SELECT url, status, time, size, title, words, issues FROM recent_results WHERE scan_id = ? ORDER BY id DESC",
        (scan_id,),
    ).fetchall()
    d["recent_results"] = [dict(r) for r in recent]

    return d


def get_results(scan_id: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM url_results WHERE scan_id = ?", (scan_id,)).fetchall()
    results = []
    for row in rows:
        d = dict(row)
        d["issues"] = json.loads(d["issues"])
        d["redirect_chain"] = json.loads(d["redirect_chain"])
        d["indexable"] = bool(d["indexable"])
        results.append(d)
    return results


def get_error_summary(scan_id: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("""
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
    """, (scan_id,)).fetchall()

    summaries = []
    for row in rows:
        urls = row["urls"].split("||") if row["urls"] else []
        summaries.append({
            "error_type": row["error_type"],
            "count": row["count"],
            "sample_urls": urls[:5],
        })
    return summaries


def get_seo_summary(scan_id: str) -> list[dict]:
    conn = _get_conn()
    summaries = []

    for label, condition in [
        ("Missing title", "title = '' OR title IS NULL"),
        ("Missing meta description", "meta_description = '' OR meta_description IS NULL"),
        ("Missing H1", "h1 = '' OR h1 IS NULL"),
        ("Multiple H1 tags", "h1_count > 1"),
        ("Missing canonical", "canonical = '' OR canonical IS NULL"),
        ("Noindex directive", "robots LIKE '%noindex%'"),
    ]:
        count = conn.execute(
            f"SELECT COUNT(*) as c FROM url_results WHERE scan_id = ? AND {condition}", (scan_id,)
        ).fetchone()["c"]
        if count > 0:
            summaries.append({"issue": label, "count": count})

    return summaries


def get_content_summary(scan_id: str) -> list[dict]:
    conn = _get_conn()
    summaries = []

    for label, condition in [
        ("Very thin content (<50 words)", "word_count < 50 AND word_count > 0"),
        ("Thin content (<100 words)", "word_count >= 50 AND word_count < 100"),
        ("Possible soft 404", "issues LIKE '%soft 404%'"),
        ("Possible application error", "issues LIKE '%application error%'"),
    ]:
        count = conn.execute(
            f"SELECT COUNT(*) as c FROM url_results WHERE scan_id = ? AND {condition}", (scan_id,)
        ).fetchone()["c"]
        if count > 0:
            summaries.append({"issue": label, "count": count})

    return summaries


def count_by_status(scan_id: str) -> dict:
    conn = _get_conn()
    rows = conn.execute("""
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
    """, (scan_id,)).fetchall()
    return {row["category"]: row["count"] for row in rows}


def get_all_issues_grouped(scan_id: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT issues, url FROM url_results WHERE scan_id = ?", (scan_id,)).fetchall()

    issue_map: dict[str, dict] = {}
    for row in rows:
        issues = json.loads(row["issues"]) if row["issues"] else []
        url = row["url"]
        for issue in issues:
            issue = issue.strip()
            if not issue:
                continue
            if issue not in issue_map:
                issue_map[issue] = {"issue": issue, "count": 0, "sample_urls": []}
            issue_map[issue]["count"] += 1
            if len(issue_map[issue]["sample_urls"]) < 5:
                issue_map[issue]["sample_urls"].append(url)

    result = sorted(issue_map.values(), key=lambda x: x["count"], reverse=True)
    return result


def get_url_detail(scan_id: str, url: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM url_results WHERE scan_id = ? AND url = ?",
        (scan_id, url),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["issues"] = json.loads(d["issues"]) if d["issues"] else []
    d["redirect_chain"] = json.loads(d["redirect_chain"]) if d["redirect_chain"] else []
    d["indexable"] = bool(d["indexable"])
    return d


def get_url_detail_by_id(scan_id: str, result_id: int) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM url_results WHERE scan_id = ? AND id = ?",
        (scan_id, result_id),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["issues"] = json.loads(d["issues"]) if d["issues"] else []
    d["redirect_chain"] = json.loads(d["redirect_chain"]) if d["redirect_chain"] else []
    d["indexable"] = bool(d["indexable"])
    return d


def get_paginated_results(scan_id: str, offset: int = 0, limit: int = 50,
                          search: str = "", status_filter: str = "",
                          issue_filter: str = "") -> tuple[list[dict], int]:
    conn = _get_conn()

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

    total = conn.execute(
        f"SELECT COUNT(*) as c FROM url_results WHERE {where_str}", params
    ).fetchone()["c"]

    rows = conn.execute(
        f"SELECT * FROM url_results WHERE {where_str} ORDER BY id LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    results = []
    for row in rows:
        d = dict(row)
        d["issues"] = json.loads(d["issues"]) if d["issues"] else []
        d["redirect_chain"] = json.loads(d["redirect_chain"]) if d["redirect_chain"] else []
        d["indexable"] = bool(d["indexable"])
        results.append(d)

    return results, total
