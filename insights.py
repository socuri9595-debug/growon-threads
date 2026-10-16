#!/usr/bin/env python3
"""Collect Threads insights for posts published in the last N days.

Reads state/YYYY-MM-DD.json files (post ids), fetches per-post metrics, and writes
  metrics/posts.json    — one record per post (date, time, app, post_id, views, likes, replies, reposts, quotes, fetched_at)
  metrics/summary.json  — per-app averages over the last 7 days, ranked by score
Requires THREADS_TOKEN with threads_manage_insights.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
API = "https://graph.threads.net/v1.0"
ROOT = Path(__file__).resolve().parent
TOKEN = os.environ.get("THREADS_TOKEN", "")
DAYS = int(os.environ.get("INSIGHTS_DAYS", "7"))
METRICS = ["views", "likes", "replies", "reposts", "quotes"]


def api(path: str, params: dict) -> dict:
    q = urllib.parse.urlencode({**params, "access_token": TOKEN})
    with urllib.request.urlopen(f"{API}{path}?{q}", timeout=60) as r:
        return json.loads(r.read().decode())


def post_insights(post_id: str) -> dict:
    data = api(f"/{post_id}/insights", {"metric": ",".join(METRICS)})
    out = {}
    for item in data.get("data", []):
        name = item.get("name")
        vals = item.get("values") or []
        out[name] = (vals[0].get("value") if vals else item.get("total_value", {}).get("value")) or 0
    return out


def main() -> int:
    if not TOKEN:
        print("THREADS_TOKEN missing", file=sys.stderr)
        return 2
    today = datetime.now(KST).date()
    start = today - timedelta(days=DAYS)

    posts_by_key = {}
    for f in sorted((ROOT / "posts").glob("*.json")):
        date = f.stem
        try:
            d = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < start:
            continue
        for p in json.loads(f.read_text(encoding="utf-8")):
            key = p.get("time") or f"{int(p['hour']):02d}:00"
            posts_by_key[(date, key)] = p.get("app", "")

    records = []
    errors = 0
    for f in sorted((ROOT / "state").glob("*.json")):
        date = f.stem
        try:
            d = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < start:
            continue
        for key, info in json.loads(f.read_text(encoding="utf-8")).items():
            pid = info.get("post_id")
            if not pid:
                continue
            rec = {"date": date, "time": key, "app": posts_by_key.get((date, key), ""), "post_id": pid}
            try:
                rec.update(post_insights(pid))
                rec["fetched_at"] = datetime.now(KST).isoformat()
            except urllib.error.HTTPError as e:
                errors += 1
                body = e.read().decode(errors="replace")[:300]
                rec["error"] = f"HTTP {e.code}: {body}"
                print(f"insights failed for {date} {key}: {rec['error']}", file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                errors += 1
                rec["error"] = str(e)
            records.append(rec)

    (ROOT / "metrics").mkdir(exist_ok=True)
    (ROOT / "metrics" / "posts.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    # per-app summary (only records with metrics)
    by_app = {}
    for r in records:
        if "views" not in r:
            continue
        a = by_app.setdefault(r["app"], {"posts": 0, **{m: 0 for m in METRICS}})
        a["posts"] += 1
        for m in METRICS:
            a[m] += int(r.get(m) or 0)
    summary = []
    for app, a in by_app.items():
        n = a["posts"] or 1
        avg = {m: round(a[m] / n, 1) for m in METRICS}
        # engagement-weighted score per post: replies and reposts count more than likes; views as a light base
        score = round(avg["views"] * 0.01 + avg["likes"] * 1 + avg["replies"] * 3 + avg["reposts"] * 2 + avg["quotes"] * 2, 2)
        summary.append({"app": app, "posts": a["posts"], "avg": avg, "score": score})
    summary.sort(key=lambda s: s["score"], reverse=True)
    (ROOT / "metrics" / "summary.json").write_text(
        json.dumps({"window_days": DAYS, "generated_at": datetime.now(KST).isoformat(), "apps": summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{len(records)} posts, {errors} errors")
    for s in summary:
        print(f"  {s['app']:<12} n={s['posts']} views={s['avg']['views']} likes={s['avg']['likes']} replies={s['avg']['replies']} score={s['score']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
