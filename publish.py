#!/usr/bin/env python3
"""Publish scheduled Threads posts.

Reads posts/YYYY-MM-DD.json (KST date). Each entry: {"hour": 10, "app": "...", "text": "..."}.
Publishes every post whose hour <= current KST hour and that is not yet recorded in
state/YYYY-MM-DD.json. Safe to run repeatedly (idempotent).

Env:
  THREADS_TOKEN  long-lived Threads user access token
  DRY_RUN=1      print instead of posting
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
API = "https://graph.threads.net/v1.0"
ROOT = Path(__file__).resolve().parent


def api(method: str, path: str, params: dict) -> dict:
    params = {**params, "access_token": TOKEN}
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(f"{API}{path}?{data.decode()}")
    else:
        req = urllib.request.Request(f"{API}{path}", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def publish_text(text: str) -> str:
    container = api("POST", "/me/threads", {"media_type": "TEXT", "text": text})
    cid = container["id"]
    # wait until the container is ready
    for _ in range(12):
        status = api("GET", f"/{cid}", {"fields": "status,error_message"})
        st = status.get("status")
        if st == "FINISHED":
            break
        if st == "ERROR":
            raise RuntimeError(f"container error: {status.get('error_message')}")
        time.sleep(5)
    result = api("POST", "/me/threads_publish", {"creation_id": cid})
    return result["id"]


def main() -> int:
    now = datetime.now(KST)
    date = os.environ.get("POST_DATE") or now.strftime("%Y-%m-%d")
    hour = int(os.environ.get("POST_HOUR") or now.hour)

    posts_file = ROOT / "posts" / f"{date}.json"
    state_file = ROOT / "state" / f"{date}.json"
    if not posts_file.exists():
        print(f"no posts file for {date}; nothing to do")
        return 0

    posts = json.loads(posts_file.read_text(encoding="utf-8"))
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}

    due = [p for p in posts if int(p["hour"]) <= hour and str(p["hour"]) not in state]
    if not due:
        print(f"{date} {hour:02d}:xx KST — nothing due")
        return 0

    failures = 0
    for p in sorted(due, key=lambda x: int(x["hour"])):
        key = str(p["hour"])
        label = f"{date} {int(p['hour']):02d}:00 [{p.get('app', '')}]"
        if DRY_RUN:
            print(f"DRY RUN {label}\n{p['text']}\n")
            state[key] = {"dry_run": True, "at": now.isoformat()}
            continue
        try:
            post_id = publish_text(p["text"])
            state[key] = {"post_id": post_id, "at": datetime.now(KST).isoformat()}
            print(f"posted {label} -> {post_id}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"FAILED {label}: {e}", file=sys.stderr)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(3)

    return 1 if failures else 0


if __name__ == "__main__":
    TOKEN = os.environ.get("THREADS_TOKEN", "")
    DRY_RUN = os.environ.get("DRY_RUN") == "1"
    if not TOKEN and not DRY_RUN:
        print("THREADS_TOKEN missing", file=sys.stderr)
        sys.exit(2)
    if os.environ.get("CHECK") == "1":
        me = api("GET", "/me", {"fields": "id,username,threads_profile_picture_url"})
        print(f"token OK — @{me.get('username')} (id {me.get('id')})")
        sys.exit(0)
    if os.environ.get("TEST_POST"):
        pid = publish_text(os.environ["TEST_POST"])
        print(f"test post published -> {pid}")
        sys.exit(0)
    sys.exit(main())
