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

`fixtures/index.legacy.html` 은 Phase 3 마이그레이션 이전의 index.html 스냅샷이다.
`scripts/test_sync_projects.py` 가 "legacy HTML → JSON → HTML" 왕복에서 정보 손실이 없는지 검증하는 데 쓴다.

## 사용

```bash
# 실제 index.html 을 건드리지 않고 스크래치 복사본에 렌더링
cp index.html /tmp/preview.html
cp scripts/projects.json /tmp/preview.json
python3 scripts/sync_projects.py --fixtures fixtures/repos --index /tmp/preview.html --config /tmp/preview.json \
        --generated /tmp/preview.generated.json --manual data/projects.manual.json
# 미리보기는 저장소 루트에서 서버를 띄우고 preview.html 을 루트로 복사해 연다 (css/js/data 상대 경로)
# fixtures 목록에 없는 실제 레포 항목은 스크래치 JSON 에서 syncStatus=unavailable 로 표시된다 (데이터는 유지)

# 탐지만
python3 scripts/sync_projects.py --fixtures fixtures/repos --dry-run

# 단위 테스트 (네트워크 없음)
python3 scripts/test_sync_projects.py
```
