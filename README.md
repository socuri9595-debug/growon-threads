# growon-threads

@growon_growth Threads 자동 발행.

- `posts/YYYY-MM-DD.json` — 그날 올릴 글 9개 (10시~18시, 1시간 간격). 매일 아침 자동 생성.
- `publish.py` — GitHub Actions가 매시간 실행. 아직 안 올라간 글 중 시간이 된 것을 Threads API로 발행.
- `state/` — 발행 기록 (중복 방지).
- `WRITING.md` — 글 작성 규칙. `APPS.md` — 앱 정보.

## 설정
Settings → Secrets and variables → Actions → **New repository secret**
- `THREADS_TOKEN` : Threads 장기 액세스 토큰 (60일마다 재발급)

## 계정 보호 원칙
- 하루 발행 수는 `plan.json`의 `ramp`로 천천히 늘림: 첫 2주 3개 → 4개 → 5개. `hard_cap`(6) 절대 초과 안 함.
- 글 종류를 섞음(A 공감→만든 이유 / B 장면만, 앱 이름 없음 / C 만드는 사람 이야기). "앱스토어_" 꼬리와 "그래서 만들었어요"는 하루 최대 2개.
- 발행 시간은 아침·점심·저녁 자연스러운 시간대에 불규칙하게.
- 사용자가 직접: 매일 몇 분 다른 글에 좋아요·답글, 팔로우. 답글 달리면 답하기.

## 반응 기반 조정
- `insights.py` (매일 07:50 KST) — 최근 7일 글의 조회·좋아요·답글·리포스트를 `metrics/`에 기록. `THREADS_TOKEN`에 `threads_manage_insights` 권한 필요.
- `plan.json` `weights` — 앱별 비중. 매주 금요일 Claude가 `metrics/summary.json`을 보고 반응 좋은 앱은 한 단계 올리고, 없는 앱은 한 단계 내림(0.5 ~ 3). 하루 총 개수는 바꾸지 않음.
