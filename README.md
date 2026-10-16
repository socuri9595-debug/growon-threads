# growon-threads

@growon_growth Threads 자동 발행.

- `posts/YYYY-MM-DD.json` — 그날 올릴 글 9개 (10시~18시, 1시간 간격). 매일 아침 자동 생성.
- `publish.py` — GitHub Actions가 매시간 실행. 아직 안 올라간 글 중 시간이 된 것을 Threads API로 발행.
- `state/` — 발행 기록 (중복 방지).
- `WRITING.md` — 글 작성 규칙. `APPS.md` — 앱 정보.

## 설정
Settings → Secrets and variables → Actions → **New repository secret**
- `THREADS_TOKEN` : Threads 장기 액세스 토큰 (60일마다 재발급)
