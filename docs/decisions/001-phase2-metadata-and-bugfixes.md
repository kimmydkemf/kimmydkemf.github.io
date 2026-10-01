# Phase 2 에서 portfolio.yml 도입과 함께 기간·진행 중·이스케이프 버그를 수정한다

날짜: 2026-10-01

## 배경

Phase 1 분석(`docs/analysis/PHASE_01_ANALYSIS.md` §3.1)에서 기존 sync 스크립트의 결함 세 가지가 확인됐다.

- B1: 커밋 API에 지원되지 않는 `direction=asc` 를 사용해 첫 커밋 대신 최신 커밋을 받아 모든 레포의 시작월 == 종료월
- B2: 종료월을 연도 문자열과 비교해 올해 끝난 프로젝트가 모두 "진행 중"으로 표시
- B3: 카드 HTML 생성 시 이스케이프 없음

Phase 2 의 status 체계와 기간 표시는 이 세 가지 위에 쌓이므로 별도 hotfix 로 분리하면 같은 코드를 두 번 만지게 된다.

## 결정

1. Phase 2 구현에 B1·B2·B3 수정을 포함한다.
2. 기간 판단은 `date` 객체 기준으로 한다. 명시적 `status` 가 최우선이고, `status` 가 없는 README 전용 프로젝트는 **마지막 커밋이 3개월 이내(`ONGOING_GRACE_MONTHS`)면 진행 중**으로 표시한다.
3. `status / started / ended / featured / live_url / unused_reason / pause_reason / replaced_by` 는 portfolio.yml 에서만 읽는다. Claude·README 파서는 이 값을 채우지 않는다.
4. portfolio.yml 파싱은 PyYAML 이 있으면 사용하고, 없으면 내장 subset 파서로 폴백해 의존성 없는 실행을 유지한다. subset 파서는 `docs/portfolio.template.yml` 범위의 문법만 지원한다.
5. 개발·검증은 `fixtures/repos/` 의 가상 샘플과 `--fixtures / --index / --config` 옵션으로만 수행한다. 실제 private 레포를 읽는 sync 는 사용자가 직접 실행한다.
6. `projects.json` 항목에 `portfolioSha`, `commitStart`, `commitEnd`, `status` 를 추가한다. 기존 키(`sha`, `start`, `end`, `title`)는 유지한다.

## 이유

- SPEC §8 (Date 기준 판단), §10 (AI 가 status 를 추정하지 않음), §25 (README SHA 감지 유지 + portfolio.yml SHA 추가), §46 (README 만으로도 동작) 과 일치한다.
- 개인 데이터 보호 규칙상 실제 개인 데이터를 세션에서 읽지 않기 위해 fixture 기반 검증이 필요하다.

## 영향

- 기존 자동 카드 6개는 README SHA 가 바뀌지 않는 한 재생성되지 않는다. 다음 `--force` 또는 README 변경 시 새 형식(이스케이프, `– Present`, Links 섹션)으로 바뀐다. 이때 실제 첫 커밋 월이 반영되어 기간 표시가 달라진다.
- 기존 카드의 "Repository" 섹션은 재생성 시 "Links" 섹션(GitHub 버튼, live_url 있으면 Live Demo)으로 대체된다.
- `reorder_auto_section` 은 `projects.json.repos[].start` 로 정렬하며, 이 값은 이제 portfolio.yml `started` 가 있으면 그것을 따른다.

## 되돌릴 조건

- 3개월 휴리스틱이 실제 프로젝트에서 부적절하다고 판단되면 상수를 조정하거나, README 전용 프로젝트는 항상 "start – end" 로만 표시하도록 바꾼다.
- Phase 3 에서 HTML 생성이 프론트엔드 렌더러로 이동하면 `render_card` 의 이스케이프·배지 로직은 템플릿/JS 로 옮겨진다.
