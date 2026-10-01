# 프로젝트 데이터 스키마 (`data/projects.generated.json`)

Phase 3 부터 프로젝트 정보의 원본은 HTML 이 아니라 JSON 이다.

```text
GitHub (README + portfolio.yml)  ─┐
                                  ├─ scripts/sync_projects.py ─→ data/projects.generated.json
data/projects.manual.json (수동) ─┘                                      │
                                                                         ├─→ scripts/render_cards.py → index.html AUTO 구간 (정적, JS 없이도 표시 / SEO)
                                                                         └─→ assets/js/projects.js   → 브라우저에서 동일 마크업으로 재렌더 (Phase 4 필터의 기반)
```

## 파일

| 파일 | 역할 | 편집 |
|------|------|------|
| `data/projects.generated.json` | sync 결과. 전체 프로젝트 목록 (github + manual) | **직접 편집하지 않음** (sync 가 덮어씀) |
| `data/projects.manual.json` | 레포가 없거나 자동화 대상이 아닌 과거 프로젝트 | 사람이 편집 → `./sync.sh` 로 반영 |
| `data/screenshots.json` | Screenshot manifest: `{slug: {url, desktop, mobile, capturedAt, engine, lastError?}}` | 직접 편집하지 않음 (`scripts/screenshot_projects.py`) |
| `scripts/projects.json` | 변경 감지 캐시 (README/portfolio.yml SHA, 커밋 월, 제외 목록) | `excluded` / `skip_repos` 만 편집 |

## 최상위

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-10-01T15:00:00+09:00",
  "projects": [ { ... } ]
}
```

`projects` 는 `started` 내림차순으로 정렬된다 (같은 달은 github → manual, 입력 순서 유지).

## 프로젝트 항목

| 필드 | 타입 | 설명 |
|------|------|------|
| `slug` | string | 안정적인 식별자. portfolio.yml `slug` > repo 이름 기반 생성. DOM `data-slug`, Screenshot 경로(Phase 6)에 사용 |
| `repo` | string \| null | GitHub repo 이름. manual 항목에 지정하면 sync 가 그 레포를 GitHub 에서 조회하지 않는다 (다른 사람 소유 레포 등) |
| `source` | `"github"` \| `"manual"` | 출처 |
| `title`, `subtitle`, `summary` | string | 표시 텍스트. `summary` 는 줄바꿈(`\n`)이 `<br>` 로 렌더됨 |
| `status` | `active` \| `completed` \| `paused` \| `unused` \| `archived` \| null | portfolio.yml 에서만 옴. null 이면 배지 없음 (README 전용 프로젝트) |
| `started`, `ended` | `"YYYY.MM"` \| `""` | 표시용 기간. 진행 중이면 `ended` 는 `""` |
| `ongoing` | bool | `started – Present` 로 표시할지 |
| `featured` | bool | Featured 영역 (Phase 4) |
| `liveUrl` | string | http(s) URL 만. `unused` 는 렌더 시 숨김 |
| `repositoryUrl` | string | GitHub 링크. 비어 있으면 Links 섹션 없음 |
| `category`, `role` | string[] | portfolio.yml 값 그대로 |
| `tech` | string[] | chips (최대 7개 렌더). 비어 있으면 sync 가 언어 라벨 하나를 넣음 |
| `highlights` | string[] | "주요 기능" 목록 |
| `highlightsTitle` | string \| null | 목록 제목을 바꿀 때 (예: 과거 카드의 "핵심 구현") |
| `team` | `[{name, role, me}]` | `me: true` 면 "me" 표시 |
| `myRole` | string | "담당 역할" 문단 |
| `unusedReason`, `pauseReason` | string | status 별 사유 |
| `replacedBy` | `{title, repository, url}` \| null | 대체 프로젝트. `url`/`repository` 없으면 링크 없이 문장만 |
| `coverImage` | string | portfolio.yml `cover.image` (Phase 6) |
| `videos` | `[{label, url}]` | YouTube embed URL. `label` 은 선택 |
| `awards` | string[] | 🏆 chip 으로 렌더 |
| `language` | string \| null | GitHub 주 언어 |
| `tagClass` | `"dev"` \| `"infra"` \| `"mobile"` \| `""` | chip 색상 클래스 (언어 기반). manual 은 `""` |
| `indexable` | bool | SEO 노출 여부 (Phase 4 이후) |
| `screenshotRefresh` | bool | portfolio.yml `screenshot_refresh`. true 면 매 실행마다 다시 캡처 |
| `screenshotEnabled` | bool | portfolio.yml `screenshot` (기본 true). false 면 캡처 대상에서 제외 |
| `screenshots` | `{desktop, mobile?}` \| 없음 | `assets/projects/{slug}/…` 경로. 파일이 실제로 있을 때만 붙는다 (`data/screenshots.json` 기준) |
| `hasPortfolioYml` | bool | portfolio.yml 존재 여부 |
| `periodFallback` | string | 기간을 알 수 없을 때 표시할 값 (repo `updated_at` 월) |
| `syncStatus` | `"ok"` \| `"migrated"` \| `"unavailable"` | `unavailable` = 레포 목록에서 사라짐(삭제/비공개). 데이터는 유지되고 표시도 그대로. 관리자가 확인 후 `excluded` 에 넣으면 제거됨 |
| `lastSynced` | `"YYYY-MM-DD"` \| null | 마지막으로 내용을 다시 만든 날 |
| `readmeSha`, `portfolioSha` | string | 변경 감지 참고용 (실제 판단은 `scripts/projects.json`) |

## 렌더링 규칙 (Python 과 JS 공통)

- `status == "unused"` → 제목·기간·배지·사유·대체 프로젝트·Repository 만. chips/기능/소개/Live Demo 없음.
- 그 외 → 접힌 카드: `.card-top`([배지] · 기간) · 제목 · 부제 · `.card-foot`(태그 최대 4개 + `+N` · GitHub/Live 링크).
  펼치면: 소개 · [기능] · [일시 중단 사유] · [담당 역할] · [기술 스택 — 태그가 4개를 넘거나 지난 프로젝트일 때] · [화면] · [시연 영상 `.video-row`] · [Links] · [팀 구성].
- 모든 텍스트는 HTML 이스케이프된다.
- `<details [class="proj-unused"] id="proj-{slug}" data-slug data-source [data-status] data-display-status [data-featured]>`
- 지난 프로젝트 그룹에는 시작 연도가 바뀔 때마다 `<div class="tl-year">YYYY</div>` 가 끼어든다 (연도 타임라인).
- `render_stats()` / `renderStats()` 는 표지의 `<!-- STATS:START -->` 구간에 들어가는 연도별 막대(`.year-bars`), 큰 숫자 4개(`.stat-grid > .stat`), 한 줄 메타(`.stat-meta`: 기록 시작 연도 · 마지막 동기화)를 만든다.
- 카드 머리글자 아이콘 `.mark.hue-N`: N 은 slug 문자 코드 합 % 6 + 1 (Python `hue_index` / JS `hueIndex` 동일). 글자는 제목의 첫 영숫자·한글.

### 프로젝트 영역 구조 (Phase 4)

```text
[필터 바]  전체 · 진행 중 · 완료 · 일시 중단 · 미사용 · 과거   ← JS 가 DOM 에서 개수를 세어 붙임 (있는 상태만)
Featured   featured: true 이고 unused 가 아닌 프로젝트, 최대 5개 (카드 그리드)
진행 중    Current
일시 중단  Paused
완료       Completed
지난 프로젝트 (미사용 · 과거) — 기본 접힘, 연도 타임라인
```

- 그룹과 필터는 `data-display-status` 기준이다. 명시적 `status` 가 있으면 그 값, 없으면 `ongoing` 이면 `active`, 아니면 `completed`.
- 상태 배지는 명시적 `status` 가 있을 때만 붙는다. status 없는 README 전용 프로젝트는 배지 없이 기간 기준 그룹에만 들어간다.
- Featured 카드 커버: `coverImage` (`http(s)://` 또는 `assets/` 로 시작할 때) > `screenshots.desktop` > 제목 첫 글자 placeholder.
- 상세 카드에는 `screenshots` 가 있으면 "화면" 섹션 (Desktop + Mobile) 이 붙는다. `unused` 는 표시하지 않는다.
- Featured 의 "자세히" 는 `#proj-{slug}` 링크다. JS 가 해시를 보고 해당 카드를 열고, 필터로 숨겨져 있으면 "전체"로 되돌린다.
- 선택한 필터는 브라우저 localStorage(`projectFilter`) 에 저장된다 (방문자별 편의 기능, 없어도 동작).

## 수동 프로젝트 추가 예 (`data/projects.manual.json`)

```json
{
  "projects": [
    {
      "slug": "old-project",
      "source": "manual",
      "title": "Old Project",
      "subtitle": "한 줄 설명",
      "summary": "소개 문장.",
      "status": "archived",
      "started": "2019.03",
      "ended": "2019.07",
      "tech": ["Unity", "AR"],
      "awards": ["OO 공모전"],
      "highlights": ["핵심 구현 1"],
      "highlightsTitle": "핵심 구현",
      "videos": [{"label": "", "url": "https://www.youtube.com/embed/xxxx"}],
      "team": [{"name": "이상호", "role": "Unity", "me": true}]
    }
  ]
}
```

다른 사람 소유 레포의 프로젝트는 `"repo"` 를 지정해 둔다. sync 는 그 레포를 읽지 않고 이 항목을 그대로 쓴다.
보통은 `status` 만 고친다.

```json
{ "slug": "bcplus-legacy", "repo": "bcplus_legacy", "source": "manual", "title": "Business Calendar Plus",
  "status": null, "started": "2021.08", "repositoryUrl": "https://github.com/ghals5737/bcplus_legacy", "...": "..." }
```

나머지 필드는 생략 가능하다 (sync 가 기본값을 채우지는 않지만 렌더러는 없는 필드를 빈 값으로 취급한다).
