# JSON 데이터 레이어는 정적 HTML 과 JS 렌더를 동시에 생성한다

날짜: 2026-10-01

## 배경

Phase 3 (docs/tasks/PHASE_03_JSON_LAYER.md) 는 프로젝트 데이터를 HTML 에서 분리해 `data/projects.generated.json` 으로 만들고 프론트엔드가 이를 렌더링하도록 요구한다. 순수 JS fetch 렌더만 두면 `file://` 미리보기·JS 비활성·검색엔진에서 프로젝트 섹션이 비게 되는 위험(Phase 1 분석 R6)이 있다.

## 결정

1. sync 는 JSON 을 생성한 뒤 **같은 JSON 으로 index.html 의 AUTO 구간 정적 HTML 도 생성**한다 (`scripts/render_cards.py`).
2. 브라우저에서는 `assets/js/projects.js` 가 같은 JSON 을 fetch 해 **동일 마크업으로 다시 렌더**한다. fetch 실패 시 정적 카드를 유지한다. Phase 4 의 필터/섹션 구분은 이 JS 렌더 위에 얹는다.
3. 두 렌더러의 출력은 `scripts/test_sync_projects.py` 의 parity 테스트(node 로 JS 실행 → Python 출력과 공백 정규화 후 비교)로 같은지 검증한다. 마크업 변경은 항상 두 파일을 함께 수정한다.
4. index.html 에 수동으로 작성되어 있던 과거 프로젝트 6개는 `scripts/migrate_index_cards.py` 로 `data/projects.manual.json` 에 옮겼고, 정적 HTML 은 제거했다. 이제 **모든 카드가 AUTO 구간에서 JSON 으로 생성**되며 index.html 의 프로젝트 영역은 직접 편집하지 않는다. 과거 프로젝트 수정은 `projects.manual.json` 편집 → `./sync.sh`.
5. 과거 프로젝트의 `status` 는 SPEC §15 예시에 따라 `archived` 로 두었다 ("아카이브" 배지가 붙는다).
6. 변경 없는 레포는 이전 JSON 항목을 그대로 재사용한다(lastKnownData). 인증된 실행(토큰 또는 fixtures)에서 레포 목록에 없는 항목은 `syncStatus: "unavailable"` 로 표시만 하고 삭제하지 않는다. 토큰 없는 실행은 public 레포만 보이므로 unavailable 표시를 하지 않는다.
7. `scripts/projects.json` 은 변경 감지 캐시로만 남긴다. 카드 내용은 더 이상 index.html 에서 읽지 않는다.

## 이유

- SPEC §11·§12 (데이터/표현 분리) 와 §26 (삭제/비공개 대응), §15 (과거 프로젝트 점진 이전) 를 한 번에 충족한다.
- 정적 폴백 덕에 GitHub Pages 의 기존 배포 방식(Jekyll legacy, main 루트)을 바꿀 필요가 없고 SEO 가 유지된다.
- Python 과 JS 렌더러 이중화 비용은 parity 테스트로 상쇄한다.

## 영향

- index.html 의 프로젝트 영역이 JSON 기반으로 다시 생성됐다. 표시 텍스트·chips·영상·팀·수상은 그대로이고(마이그레이션 왕복 테스트로 확인), 달라진 점은 "2026.05 –" → "2026.05 – Present", "2021.08 – 2021.08" → "2021.08", Repository URL 문단 → Links 의 GitHub 버튼, 과거 프로젝트의 "아카이브" 배지, 영상 라벨의 inline style → `.video-label` 클래스.
- `sync.sh` 와 GitHub Actions workflow 는 `data/projects.generated.json` 도 함께 commit 한다.
- `fixtures/index.legacy.html` 은 마이그레이션 검증용 스냅샷이다. 필요 없어지면 삭제해도 된다.

## 되돌릴 조건

- 정적 HTML 과 JS 이중 렌더가 유지 부담이 되면, JS 렌더를 제거하고 정적 생성만 남기거나(필터는 CSS/data-attribute 로 처리) 그 반대로 정리한다. 어느 쪽이든 JSON 스키마는 유지된다.
