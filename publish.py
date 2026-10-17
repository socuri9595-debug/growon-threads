#!/usr/bin/env python3
"""Publish scheduled Threads posts.

Reads posts/YYYY-MM-DD.json (KST date). Each entry:
  {"time": "10:17", "app": "...", "text": "..."}   (preferred)
  {"hour": 10, ...}                                 (legacy; means HH:00)
Publishes every post whose time <= now (KST) and that is not yet recorded in
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
REPO = Path(__file__).resolve().parent
# ACCOUNT="" → 저장소 루트(growon). ACCOUNT="salkka" → accounts/salkka/ 아래 posts/state, 토큰은 THREADS_TOKEN_SALKKA
ACCOUNT = os.environ.get("ACCOUNT", "").strip()
ROOT = REPO / "accounts" / ACCOUNT if ACCOUNT else REPO


def api(method: str, path: str, params: dict) -> dict:
    params = {**params, "access_token": TOKEN}
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(f"{API}{path}?{data.decode()}")
    else:
        req = urllib.request.Request(f"{API}{path}", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def recent_texts(limit: int = 25) -> set[str]:
    """최근 올린 글 본문(공백 정규화). 중복 발행 방지용."""
    try:
        data = api("GET", "/me/threads", {"fields": "id,text,timestamp", "limit": limit})
    except Exception:  # noqa: BLE001
        return set()
    return {" ".join((p.get("text") or "").split()) for p in data.get("data", [])}


def publish_text(text: str) -> str:
    if " ".join(text.split()) in recent_texts():
        raise RuntimeError("DUPLICATE: same text already posted recently")
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
    minute = int(os.environ.get("POST_MINUTE") or (now.minute if not os.environ.get("POST_HOUR") else 59))
    now_min = hour * 60 + minute

    def when(p):
        t = p.get("time")
        if t:
            h, m = t.split(":")
            return int(h) * 60 + int(m)
        return int(p["hour"]) * 60

    def key_of(p):
        return p.get("time") or f"{int(p['hour']):02d}:00"

    posts_file = ROOT / "posts" / f"{date}.json"
    state_file = ROOT / "state" / f"{date}.json"
    if not posts_file.exists():
        print(f"no posts file for {date}; nothing to do")
        return 0

    posts = json.loads(posts_file.read_text(encoding="utf-8"))
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}

    due = [p for p in posts if when(p) <= now_min and key_of(p) not in state]
    if not due:
        print(f"{date} {hour:02d}:{minute:02d} KST — nothing due")
        return 0

    failures = 0
    for p in sorted(due, key=when):
        key = key_of(p)
        label = f"{date} {key} [{p.get('app', '')}]"
        if DRY_RUN:
            print(f"DRY RUN {label}\n{p['text']}\n")
            state[key] = {"dry_run": True, "at": now.isoformat()}
            continue
        try:
            post_id = publish_text(p["text"])
            state[key] = {"post_id": post_id, "at": datetime.now(KST).isoformat()}
            print(f"posted {label} -> {post_id}")
        except RuntimeError as e:
            if str(e).startswith("DUPLICATE"):
                state[key] = {"skipped": "duplicate", "at": datetime.now(KST).isoformat()}
                print(f"skipped {label}: already posted")
            else:
                failures += 1
                print(f"FAILED {label}: {e}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"FAILED {label}: {e}", file=sys.stderr)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(3)

    return 1 if failures else 0


if __name__ == "__main__":
    TOKEN = os.environ.get(f"THREADS_TOKEN_{ACCOUNT.upper()}" if ACCOUNT else "THREADS_TOKEN", "")
    DRY_RUN = os.environ.get("DRY_RUN") == "1"
    if not TOKEN and not DRY_RUN:
        print(f"[{ACCOUNT or 'growon'}] token not set yet; skipping")
        sys.exit(0)
    if os.environ.get("CHECK") == "1":
        me = api("GET", "/me", {"fields": "id,username,threads_profile_picture_url"})
        msg = f"token OK — @{me.get('username')} (id {me.get('id')}) at {datetime.now(KST).isoformat()}"
        print(msg)
        (ROOT / "state" / "last_check.txt").write_text(msg + "\n", encoding="utf-8")
        sys.exit(0)
    if os.environ.get("TEST_POST"):
        pid = publish_text(os.environ["TEST_POST"])
        print(f"test post published -> {pid}")
        sys.exit(0)
    sys.exit(main())
