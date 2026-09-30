# fixtures — 로컬 샘플 데이터

실제 GitHub 레포(특히 private 레포)를 읽지 않고 sync 스크립트를 개발·검증하기 위한 **가상 프로젝트** 샘플이다.
모든 내용은 지어낸 것이며 실제 데이터를 넣지 않는다.

## 구조

```text
fixtures/repos/<repo-name>/
├── repo.json        GitHub repo metadata 일부 (name, full_name, html_url, language, description, updated_at)
├── README.md        README 샘플 (선택)
├── portfolio.yml    표시용 메타데이터 샘플 (선택)
└── commits.json     {"first": "ISO 날짜", "last": "ISO 날짜"} — 첫/마지막 커밋 (선택)
```

## 샘플

| 디렉터리 | 목적 |
|----------|------|
| `sample-tracker` | `status: active` + live_url + 전체 필드. README 도 있음 |
| `sample-legacy-blog` | `status: unused` + `unused_reason` + `replaced_by` — 간단 카드 확인 |
| `sample-readme-only` | portfolio.yml 없음 — 기존 README 파서 폴백 경로 확인 |
| `sample-bad-metadata` | 잘못된 status / 누락 필드 — Validation 경고 확인 |

## 사용

```bash
# 실제 index.html 을 건드리지 않고 스크래치 복사본에 렌더링
cp index.html /tmp/preview.html
cp scripts/projects.json /tmp/preview.json
python3 scripts/sync_projects.py --fixtures fixtures/repos --index /tmp/preview.html --config /tmp/preview.json
python3 -m http.server -d /tmp 8000   # http://localhost:8000/preview.html (css 는 저장소 경로 필요)

# 탐지만
python3 scripts/sync_projects.py --fixtures fixtures/repos --dry-run

```
