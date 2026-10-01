# 프로젝트 영역을 Featured + 상태 그룹으로 나누고, status 없는 프로젝트는 기간으로 배치한다

날짜: 2026-10-01

## 배경

Phase 4 는 Featured / Current / Completed / Unused·Archived 구분과 상태 필터를 요구한다. 그런데 현재 GitHub 프로젝트 6개는 모두 portfolio.yml 이 없어 `status` 가 비어 있다. SPEC §10 은 AI·파서가 status 를 추정하지 않도록 한다.

## 결정

1. 그룹·필터용 상태(`data-display-status`)와 표시용 배지를 분리한다.
   - 배지: 명시적 `status` 가 있을 때만.
   - 그룹·필터: `status` 가 있으면 그 값, 없으면 `ongoing` (Phase 2 의 최근 3개월 커밋 규칙) 이면 `active`, 아니면 `completed`.
2. 그룹 순서: Featured → 진행 중 → 일시 중단 → 완료 → 미사용·아카이브. 그룹 안은 JSON 순서(시작월 내림차순).
3. Featured 는 `featured: true` 이고 `unused` 가 아닌 프로젝트 최대 5개. 카드 그리드로 표시하고 같은 프로젝트의 상세 카드는 그룹에도 남긴다.
4. 그룹 구조는 Python(정적 HTML)과 JS 렌더러 모두에 넣는다 (parity 테스트 대상). 필터 바는 JS 전용이며 DOM 에서 개수를 세므로 JSON fetch 가 실패해도 동작한다.
5. 필터 선택은 localStorage 에 방문자별로 저장한다 (실패해도 무시).

## 이유

- status 를 쓰지 않은 프로젝트도 그룹에 들어가야 화면이 비지 않는다. 배지를 붙이지 않음으로써 "명시적 상태"와 "추정 배치"를 구분한다.
- 정적 HTML 에도 같은 그룹 구조가 있어야 JS 없는 환경·SEO 에서 동일하게 보인다.

## 영향

- 현재 실데이터 기준: 진행 중 5 (Pacer, Portfolio, Blog, Life Manager, MyNote), 완료 1 (Business Calendar Plus), 미사용·아카이브 6 (과거 수동 프로젝트). Featured 는 `featured: true` 인 프로젝트가 아직 없어 표시되지 않는다.
- 상세 카드에 `id="proj-{slug}"` 가 생겼다.

## 되돌릴 조건

- 추정 배치가 혼란스럽다면 status 없는 프로젝트를 별도 "기타" 그룹으로 분리한다.
