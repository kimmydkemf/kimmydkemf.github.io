# Phase 1 — 기존 구조 분석 결과

작성일: 2026-10-01
브랜치: `kimmydkemf/phase-01-analyze` (develop == main 상태에서 분기)
범위: 코드 수정 없음. 분석 · 검증(읽기 전용) · 문서화만 수행.

---

## 0. 분석 방법 및 수행한 검증

| 항목 | 결과 |
|------|------|
| `python3 -m py_compile scripts/sync_projects.py` | OK |
| `bash -n sync.sh` | OK |
| `index.html` `<details>` 열림/닫힘 개수 | 12 / 12 (균형) |
| `sync_projects.py --dry-run` (토큰 없음, Claude 키 제외) | 정상 종료, 파일 변경 없음 (`cmp`로 확인) |
| GitHub Pages 설정 (`gh api .../pages`, 읽기 전용) | 아래 §1.10 참조 |
| Actions 실행 이력 (`gh run list`) | `sync-projects.yml` 실행 이력 **0회** |
| Secret 패턴 검색 (`ghp_`, `sk-ant-`, `github_pat_`) | README.md의 placeholder(`***`)만 존재. 실제 값 없음 |
| `.env` 존재 여부 | 루트 · `scripts/` 모두 없음 (.gitignore에 등록됨) |

dry-run은 파일을 쓰지 않는 경로만 실행되며, Claude API 호출을 막기 위해 `ANTHROPIC_API_KEY`를 제외한 환경으로 실행했다.

---

## 1. 현재 자동화 구조

### 1.1 Repository 구조

```text
kimmydkemf.github.io/            ← GitHub Pages user site (origin: kimmydkemf/kimmydkemf.github.io)
├── index.html                   750줄. 단일 페이지. 프로젝트 카드 12개 (자동 6 + 수동 6)
├── CNAME                        "dounselor.com"
├── assets/
│   ├── css/style.css            824줄. CSS Variables 기반 다크/라이트
│   └── images/                  bc.png, prize-1~3 — index.html/CSS 어디서도 참조되지 않음 (미사용 자산)
├── scripts/
│   ├── sync_projects.py         650줄. 동기화 엔진 (GitHub API → 카드 HTML → index.html 치환)
│   └── projects.json            캐시: README SHA · 기간 · 제목 + excluded/skip_repos
├── sync.sh                      Mac/로컬 실행 래퍼. 변경 시 자동 commit + push
├── .github/workflows/sync-projects.yml   workflow_dispatch 전용 (schedule 없음)
├── projects/*.md                수동 카드 7개의 원본 md (Obsidian에서 정리한 기록). 사이트에서 참조 안 함
├── docs/                        PROJECT_SPEC, DEVELOPMENT_RULES, tasks/, decisions/ (이번에 추가된 개발 지시서)
├── README.md, HOW_TO_USE.md, AGENTS.md, CLAUDE.md
├── .claude/settings.local.json.example
└── .gitignore                   .DS_Store, **/.obsidian/, .env
```

`.nojekyll`, `_config.yml` 없음 → GitHub Pages가 **Jekyll legacy 빌드**로 처리한다. 프론트매터 없는 `.md`는 그대로 정적 파일로 복사되므로 `docs/`, `projects/`, `scripts/projects.json`, `CLAUDE.md` 등이 모두 `https://dounselor.com/...` 경로로 공개 접근 가능하다 (Secret은 없으나 내부 지시서가 노출됨).

브랜치: `main`(Pages 소스), `develop`, `kimmydkemf/phase-01-analyze`. 현재 세 브랜치의 내용은 동일하다.

### 1.2 전체 흐름

```text
[로컬 Mac]  ./sync.sh
   ├─ .env 에서 GITHUB_TOKEN 로드 (없으면 종료)
   ├─ python3 scripts/sync_projects.py --obsidian ~/Workspace/MyNotes "$@"
   │     ├─ GitHub API: 레포 목록 (/user/repos, owner+collaborator, private 포함)
   │     ├─ scripts/projects.json 로드 (excluded / skip_repos / repos{sha,start,end,title})
   │     ├─ index.html 로드 → 기존 proj-title 수집 (수동 카드 중복 감지용)
   │     ├─ 레포마다:
   │     │     excluded/skip → 스킵
   │     │     수동 카드 제목과 중복 → 스킵 + skip_repos 자동 추가
   │     │     GET /repos/{full}/readme → 없으면 스킵
   │     │     README SHA == 저장 SHA 이고 --force 아님 → 스킵
   │     │     GET /commits (첫/마지막 커밋 → 기간)
   │     │     ANTHROPIC_API_KEY 있으면 Claude(haiku 4.5) 로 JSON 생성, 없으면 README 정규식 파서
   │     │     render_card() → <details> HTML 문자열
   │     │     index.html 의 <!-- AUTO:{repo} --> ~ <!-- /AUTO:{repo} --> 치환 또는 AUTO:END 앞에 삽입
   │     ├─ AUTO 구간 카드를 start 내림차순 재정렬
   │     ├─ index.html, projects.json 저장
   │     └─ (옵션) Obsidian vault/개발/{title}.md 생성
   └─ git diff --quiet index.html scripts/projects.json → 변경 있으면
         git add → git commit "sync: update projects YYYY-MM-DD" → git push (현재 브랜치)

[GitHub]  main 에 push
   └─ pages-build-deployment (Jekyll legacy) → https://dounselor.com (CNAME)

[GitHub Actions]  sync-projects.yml (수동 dispatch 전용, 실행 이력 0회)
   └─ secrets.GITHUB_TOKEN 으로 동일 스크립트 실행 → github-actions[bot] commit → push
```

### 1.3 index.html

- 단일 페이지: NAV → HERO → About → Skills → **Projects** → Contact → Floating Claude Badge → footer → inline `<script>`.
- Projects 섹션 (`index.html:118` 부근)은 `.project-list` 안에 `<details>` 아코디언 카드가 나열된다.
- `<!-- AUTO:START -->`(122행) ~ `<!-- AUTO:END -->`(317행) 구간이 자동 관리 영역이며, 카드마다 `<!-- AUTO:{repo} -->` / `<!-- /AUTO:{repo} -->` 마커로 감싸져 있다.
- 자동 카드 6개: health-tracker(Pacer), kimmydkemf.github.io, dounselor-blog, life-manager, MyNote, bcplus_legacy.
- 수동 카드 6개 (AUTO:END 아래, 정적): P.S — Private Secretary, MeetingGround, BC+, Butterfly, 천로역정, HGU 졸업 Project. 수동 카드는 YouTube iframe, 팀 구성(member-grid), 수상 chip(`chip award`) 등 자동 카드에 없는 요소를 가진다.
- 외부 리소스: `assets/css/style.css` 1개, YouTube embed 8개, GitHub 링크, mailto. 외부 JS 없음.
- 카드 데이터가 HTML에 직접 박혀 있어 **데이터와 표현이 분리되지 않았다** (SPEC §11·§12가 바꾸려는 지점).

### 1.4 CSS / JavaScript

- `assets/css/style.css`: `:root`(다크 기본) + `[data-theme="light"]` 오버라이드. 색·그림자·태그 색이 전부 CSS Variables. 섹션 순서: LIGHT vars → BASE → NAV → HERO → SECTION → ABOUT → SKILLS → PROJECTS(336~) → DETAIL(407~) → CONTACT → FLOAT BADGE → FOOTER → RESPONSIVE(720px, 400px) → reduced-motion → 라이트 전용 임팩트 레이어(599~).
- 프로젝트 카드 관련 클래스: `.project-list`, `details`, `summary`, `.proj-period`, `.proj-main`, `.proj-title`, `.proj-sub`, `.proj-chips`, `.chip{.dev,.infra,.mobile,.ai,.award}`, `.arrow`, `.detail`, `.dl-section`, `.video-wrap`, `.member-grid/.member-card/.member-name/.member-role`, `.me`.
- JavaScript는 `index.html:717~748` 인라인 IIFE 하나. 역할: 테마 토글 (`localStorage.theme`, `prefers-color-scheme` 감지, `<html data-theme>` 설정). 프로젝트 렌더링 관련 JS는 **전혀 없음**. `float-badge`는 인라인 `onclick`.
- 스크립트가 `</body>` 직전에 있어 라이트 모드 사용자는 첫 페인트에서 다크 → 라이트로 바뀌는 깜빡임(FOUC)이 생길 수 있다 (기존 동작, 이번 범위 밖).

### 1.5 scripts/sync_projects.py

주요 함수와 역할 (행 번호는 현재 파일 기준):

| 함수 | 행 | 역할 |
|------|----|------|
| `_gh()` | 64 | GitHub REST 호출. `urllib` 사용, 의존성 없음. **404·403 모두 `None` 반환** |
| `fetch_repos()` | 79 | 토큰 있으면 `/user/repos?affiliation=owner,collaborator`, 없으면 `/users/kimmydkemf/repos`. `per_page=100`, 페이지네이션 없음 |
| `fetch_readme()` | 92 | `/repos/{full}/readme` → base64 decode, `sha` 반환 |
| `fetch_period()` | 101 | `/commits?per_page=1&direction=asc` + `/commits?per_page=1` → 첫/마지막 커밋 월 |
| `scan_existing_titles()` / `is_duplicate()` | 119/124 | `class="proj-title">` 텍스트를 수집, 정규화 후 부분 문자열 포함이면 중복 |
| `generate_with_claude()` | 142 | `claude-haiku-4-5-20251001`, README 앞 4000자, JSON 응답 파싱. 프롬프트에 소유자 이름 하드코딩 |
| `_parse_readme_fallback()` | 232 | h1/h2/h3 섹션 분할 → 키워드(소개/기능/기술/팀)로 섹션 매칭 → 불릿·표 파싱 |
| `render_card()` | 347 | `<details>` 카드 HTML 문자열 생성 (f-string) |
| `insert_card()` / `update_card()` / `card_exists()` | 445~462 | 마커 기반 삽입/정규식 치환 |
| `reorder_auto_section()` | 467 | AUTO 구간 카드를 `projects.json`의 `start` 문자열 내림차순 정렬 |
| `_write_obsidian()` | 493 | vault/개발/{title}.md 생성 (없을 때만) |
| `main()` | 515 | 위 흐름 조합. `--dry-run`, `--force`, `--obsidian` |

옵션 동작:
- `--dry-run`: 콘텐츠 생성까지 수행하고 파일은 쓰지 않음 (검증 완료). Claude 키가 있으면 dry-run에서도 API 호출은 일어난다.
- `--force`: SHA 무시하고 전체 재생성.
- 플레이스홀더(`"내용을 입력하세요."`) 감지 시 강제 재생성.

### 1.6 sync.sh

- `set -e`. 루트 `.env`에서 `GITHUB_TOKEN`만 export (`ANTHROPIC_API_KEY`는 `.env`에서 읽지 않음 → README 안내와 불일치. 셸에 미리 export 된 경우만 Claude 모드 동작).
- Obsidian 경로 `~/Workspace/MyNotes` **하드코딩** 후 `"$@"` 전달.
- 변경 판단: `git diff --quiet index.html scripts/projects.json` → 변경 시 `git add`(두 파일만) → `git commit -m "sync: update projects $(date)"` → `git push` (현재 체크아웃 브랜치로). `git pull` 선행 없음, Secret 검사 없음, diff 미리보기 없음.
- 오류 메시지에 `scripts/.env`라고 안내하지만 실제로는 루트 `.env`만 읽는다.

### 1.7 projects.json (캐시/메타데이터)

```json
{ "excluded": [...], "skip_repos": [...],
  "repos": { "<repo>": { "sha": "<README blob sha>", "start": "YYYY.MM", "end": "YYYY.MM", "title": "..." } } }
```

- 키는 **repo 이름** (full_name 아님). `ghals5737/bcplus_legacy` 처럼 다른 소유자의 collaborator 레포도 repo 이름만으로 저장된다.
- `excluded`(SharePaper, VirtualityForSafety)는 조용히 스킵, `skip_repos`(MeetingGround)는 로그를 남기며 스킵. 효과는 동일.
- 스크립트가 실행 중 중복 감지한 레포를 `skip_repos`에 **자동 추가**하고 저장한다 → 설정 파일이 실행마다 바뀔 수 있음.
- 현재 6개 레포 **모두 start == end** (예: `2026.05`/`2026.05`, `2021.08`/`2021.08`) — §3.1 버그 참조.
- 카드 본문(소개·기술·기능)은 저장하지 않는다. 진짜 데이터는 `index.html` 안에만 있다.

### 1.8 GitHub README 조회 방식 · SHA 변경 감지

- 조회: `GET /repos/{owner}/{repo}/readme` (GitHub이 README 파일명 대소문자/확장자를 알아서 해석). Accept `application/vnd.github+json`, Bearer 토큰. 실패(404/403) 시 `("", "")`.
- 변경 감지: 응답의 `sha`(blob SHA)를 `projects.json.repos[name].sha`와 비교. 다르면 갱신, 같으면 스킵. `--force`로 우회. 이 구조는 SPEC §25가 유지하라고 명시한 부분이며 정상 동작한다.
- 한계: README 외의 신호(레포 description 변경, 언어 변경, 커밋 추가 → 종료월 변경)는 감지하지 않는다. `portfolio.yml` SHA 관리는 아직 없다.

### 1.9 프로젝트 HTML 생성 방식

- Python f-string으로 `<details>…</details>` 전체를 만들고 `index.html`을 문자열 치환한다.
- **HTML 이스케이프 없음**: README/Claude 출력의 `<`, `&`, `"`가 그대로 삽입된다. 현재 카드에도 마크다운 잔여물(`> *"기록은 곧 나를 만든다."*`)이 그대로 보인다.
- 카드 순서는 AUTO 구간 내에서만 `start` 문자열 정렬. 수동 카드 6개는 항상 AUTO 구간 아래 고정.
- 기술 chip 클래스는 레포 주 언어 → `LANG_TAG` 매핑(dev/mobile/infra)으로 카드 단위 결정. chip 내용은 README 파싱 결과.

### 1.10 Git commit / push · GitHub Pages 배포 · CNAME

- **로컬**: `sync.sh`가 `index.html`, `scripts/projects.json` 두 파일만 add → commit → 현재 브랜치 push. 로컬 히스토리를 보면 실제 운영은 이 경로로 이뤄졌다 (`sync: update projects 2026-05-23` 등).
- **Actions**: `sync-projects.yml`은 `workflow_dispatch`만 있고 `schedule` 없음. `permissions: contents: write`, `github-actions[bot]`으로 commit/push. **실행 이력 0회**.
- **Pages 설정 (API 확인)**: `build_type: legacy`, source `main` / `/`, `cname: dounselor.com`, `https_enforced: true`, status `built`. 즉 **main 브랜치 루트에 push되면 Jekyll 빌드 후 배포**. 5월 23일 이력에 연속 push로 인한 빌드 cancel → success 패턴이 보인다 (정상).
- **CNAME**: 루트 `CNAME` 한 줄 `dounselor.com`. Pages 설정의 custom domain과 이 파일이 일치해야 하며, 파일이 사라지거나 내용이 바뀐 commit이 main에 올라가면 커스텀 도메인 연결이 해제된다.
- DNS/SSL은 Cloudflare(DNS only 모드) → GitHub Pages IP 4개 A 레코드 + `www` CNAME (README 문서 기준, 이번 분석에서 DNS는 조회하지 않음).

### 1.11 레포 가시성 (Actions 실행 가능성에 직접 영향)

| 레포 | 소유자 | 공개 여부 |
|------|--------|-----------|
| dounselor-blog | kimmydkemf | public |
| kimmydkemf.github.io | kimmydkemf | public |
| PloblemSolving | kimmydkemf | public (README 없음 → 스킵됨) |
| health-tracker (Pacer) | kimmydkemf | **private** |
| life-manager | kimmydkemf | **private** |
| MyNote | kimmydkemf | **private** |
| bcplus_legacy | ghals5737 (collaborator) | **private** |

토큰 없는 dry-run에서는 public 3개만 조회됐다. Actions의 기본 `secrets.GITHUB_TOKEN`은 **해당 레포 하나에만 권한이 있어** `/user/repos`가 403 → `_gh`가 `None` → 빈 목록 → "업데이트할 내용 없음"으로 조용히 끝날 가능성이 매우 높다. 현재 workflow는 그대로 실행하면 사실상 아무 일도 하지 않는다 (SPEC §23이 이미 예고한 문제).

---

## 2. 유지해야 할 부분

1. **README SHA 기반 변경 감지** (`fetch_readme` + `projects.json.repos[].sha`). SPEC §25가 명시적으로 유지 요구. 여기에 `portfolioSha`를 추가하는 방식으로 확장.
2. **`projects.json`의 excluded / skip_repos 개념**. 표시 제외 정책을 코드 밖에서 관리하는 구조는 그대로 두고, 새 메타데이터 시스템과 병행.
3. **의존성 없는 Python 표준 라이브러리 구성** (`urllib`, `json`, `re`). Actions·Mac 어디서나 즉시 실행 가능. `portfolio.yml` 파싱을 위해 PyYAML을 추가하더라도 (로컬에 6.0.3 있음) 그 외 의존성은 최소로.
4. **Claude 생성 + README 정규식 파서 폴백 2단 구조**. 키가 없어도 동작해야 한다는 원칙(SPEC §9·§46)과 일치. 단 AI가 status/기간/live_url을 추정하지 않도록 프롬프트 범위를 조정해야 함(SPEC §10).
5. **`--dry-run` / `--force` 옵션과 "변경 있을 때만 commit" 정책** (sync.sh, workflow 모두). SPEC §39·§41.
6. **디자인 시스템**: CSS Variables · 다크/라이트 토글 · `<details>` 아코디언 · chip/tag 색상 체계 · 라이트 임팩트 레이어 · reduced-motion 대응. SPEC §29 "디자인 정체성 유지".
7. **수동 카드 6개와 `projects/*.md` 기록**. 삭제 금지 (SPEC §15). Phase 2~4에서 `status: archived` 메타데이터로 점진 이전하는 원천 자료.
8. **`CNAME`, `main` 브랜치 루트 배포, 기존 Git 히스토리**. 배포 경로는 바꾸지 않는다.
9. **AUTO 마커 구조** (`AUTO:START/END`, `AUTO:{repo}`): Phase 3에서 JSON 렌더러로 넘어가기 전까지 기존 sync 경로가 계속 동작해야 하므로 유지. 최종적으로 마커 구간이 JS 마운트 포인트로 대체되는 것이 자연스러움.

---

## 3. 개선이 필요한 부분

### 3.1 확인된 동작 결함 (기능 버그)

| # | 위치 | 내용 | 근거 |
|---|------|------|------|
| B1 | `sync_projects.py:104` | `/commits?direction=asc`는 GitHub API가 지원하지 않는 파라미터 → 첫 커밋이 아닌 **최신 커밋**이 반환됨 → start == end | projects.json 6개 레포 전부 start == end |
| B2 | `sync_projects.py:354` | `end >= "2026"` 문자열 비교로 진행 중 판단 → **올해 안에 끝난 모든 프로젝트가 "2026.05 –"(진행 중)로 표시** | index.html 자동 카드 5개가 모두 `2026.05 –`. SPEC §8 "문자열 비교로 판단하지 않는다" |
| B3 | `render_card()` 전체 | HTML 이스케이프 없음. README의 `<`/`&`/마크다운 잔여물이 그대로 삽입 → 마크업 깨짐·스크립트 삽입 가능성 | MyNote 카드에 `> *"…"*` 그대로 노출 |
| B4 | `sync_projects.py:303` | 폴백 subtitle을 `[:60]`으로 잘라 문장이 중간에 끊김 | Dounselor Portfolio 카드 `"… → 커스텀 "`, Blog 카드 `"… 폰에서도 "` |
| B5 | `_parse_readme_fallback` 기술 파싱 | `**Frontend**: A · B · C` 형태 불릿 한 줄이 chip 하나가 됨 | Portfolio/Blog/Life Manager 카드의 문장형 chip |
| B6 | `sync_projects.py:584` | 플레이스홀더 감지가 `html` 전체를 검사 → 어느 카드든 플레이스홀더가 있으면 모든 기존 카드가 재생성됨 | 코드 로직 |
| B7 | `sync_projects.py:569` | 중복 감지된 레포를 `skip_repos`에 자동 추가·저장 → 오탐 시 사용자가 모르는 채로 영구 제외됨 (5월 23일 fix 커밋이 바로 이 오탐 사례) | 커밋 `f6174eb` 메시지 |
| B8 | `sync_projects.py:556` | `manual_titles` 계산 후 미사용 (dead code) | 코드 |
| B9 | `sync_projects.py:74` | 403(rate limit·권한 없음)을 404와 동일하게 `None` 처리 → 원인 없이 "README 없음"/"레포 없음"으로 보임 | 코드. Actions 토큰 문제를 감지 못 하는 원인 |
| B10 | `sync.sh:19-27` | `.env`를 루트에서만 읽으면서 안내 메시지는 `scripts/.env`. `ANTHROPIC_API_KEY`는 `.env`에서 읽지 않음 | README와 불일치 |
| B11 | `fetch_repos()` | `per_page=100` 단일 호출. 레포 100개 초과 시 누락 | 현재는 영향 없음 |

### 3.2 구조적 한계 (SPEC 목표 대비)

1. **데이터가 HTML 안에만 존재**. `projects.json`은 sha/기간/제목만 보관하므로 카드 본문을 재사용·재렌더링할 수 없다. → Phase 3 `data/projects.generated.json` 필요.
2. **상태(status) 개념 없음**. active/completed/unused/archived 구분 불가. 종료 판단이 커밋 날짜 추정 + 문자열 비교(B2)에만 의존. → Phase 2.
3. **live_url · featured · category · cover 정보 없음**. 카드에 Live Demo 버튼 불가. → Phase 2·4.
4. **README 품질에 결과가 좌우됨** (B4·B5가 그 증상). `portfolio.yml` 우선 조회로 해결. → Phase 2.
5. **수동 카드는 자동화 밖**. 6개 수동 카드가 별도 HTML로 고정되어 정렬·필터에 참여하지 못한다. → Phase 2~4에서 `projects/*.md` 기반 archived 메타데이터로 이전.
6. **Sync 스크립트가 HTML 디자인을 알고 있음** (`render_card`가 CSS 클래스명을 소유). 디자인 변경마다 Python도 수정해야 한다. → Phase 3 렌더러 분리.
7. **Actions 경로가 실질적으로 동작하지 않음** (§1.11). 기본 토큰으로는 private·collaborator 레포 4개를 읽을 수 없다. → Phase 7에서 Fine-grained PAT Secret 도입.
8. **push 안전장치 부재**: `git pull` 없음, staged diff 검토 없음, Secret 검사 없음, 로그 파일 없음. → Phase 5·7 (SPEC §42·§43).
9. **하드코딩**: Obsidian 경로(sync.sh), GitHub 사용자명·소유자 실명(스크립트·프롬프트), Claude 모델 ID.
10. **레포 삭제/비공개 전환 대응 없음**. 카드는 남지만(의도치 않게 안전) `syncStatus: unavailable` 같은 표식이 없다 (SPEC §26).
11. **Jekyll legacy 빌드**: `.nojekyll`이 없어 매 push마다 Jekyll이 돌며 `docs/`·`projects/`·`CLAUDE.md` 등이 그대로 공개된다. 정적 HTML만 쓰는 사이트라 `.nojekyll` 추가가 빌드 속도와 예측 가능성에 유리하지만, 배포 경로 변경이므로 사용자 결정 필요.
12. **미사용 자산**: `assets/images/bc.png`, `prize-1~3` 미참조. 삭제 대상은 아니며(수상 이미지, Phase 4 UI에서 활용 후보), 기록만 남김.

---

## 4. 변경 시 위험요소

| # | 위험 | 영향 | 완화 방안 |
|---|------|------|-----------|
| R1 | `CNAME` 파일 삭제·변경, 또는 Pages source 변경 | dounselor.com 즉시 다운. Cloudflare DNS는 그대로여도 GitHub 쪽 도메인 연결 해제 | CNAME은 어떤 Phase에서도 건드리지 않음. Pages source(main, `/`)와 legacy 빌드 유지. Actions 배포 방식으로 전환하지 않음 |
| R2 | `docs/` 폴더 존재 | GitHub Pages는 `/docs`를 소스로 선택할 수 있는 옵션이 있어, 누군가 설정을 바꾸면 지시서가 사이트가 됨 | Pages 설정 변경 금지. 현재는 `/` 루트라 영향 없음 |
| R3 | `index.html`의 AUTO 마커·`proj-title` 클래스 변경 | 기존 sync 스크립트가 마커를 못 찾으면 `sys.exit(1)`, 중복 감지가 깨지면 카드 중복 삽입 또는 오탐 스킵(B7) | Phase 3 전까지 마커 구조 유지. 새 렌더러 도입 시 기존 sync가 `data/`만 쓰도록 먼저 전환한 뒤 마커 제거 |
| R4 | 수동 카드 6개 정보 손실 | 시연 영상 8개·팀 구성·수상 기록은 HTML에만 완전한 형태로 존재 (`projects/*.md`는 일부 필드만) | 메타데이터 이전 시 HTML → YAML/JSON 변환 결과를 카드 단위로 diff 검증 |
| R5 | 자동 카드 재생성 시 내용 후퇴 | `--force` 또는 SHA 변경 시 Claude 없는 환경에서는 폴백 파서 결과로 덮어써져 품질이 떨어질 수 있음 | 데이터 레이어 도입 후에는 마지막 정상 데이터를 보존(`lastKnownData`). 재생성 전 `--dry-run` |
| R6 | 프론트엔드 JSON fetch 전환 | `file://`로 열면 fetch 실패 → 빈 프로젝트 섹션. 구형 브라우저·JS 비활성 시 내용 없음. SEO도 JS 렌더 의존 | 로컬 미리보기는 `python -m http.server`. Phase 3에서 빌드 타임 정적 HTML 삽입(SSG) vs 런타임 fetch 중 결정. **권장: sync가 JSON과 함께 정적 HTML 조각도 생성해 index.html에 삽입**하면 JS 없이도 표시되고 SEO 유지 |
| R7 | 자동 commit/push 확대 (Mac Updater, launchd, Actions schedule) | 잘못된 렌더 결과가 검토 없이 운영 사이트로 나감. 두 경로(Mac·Actions)가 동시에 push하면 충돌 | Preview/diff 확인 우선(Phase 5 원칙). Actions는 처음엔 `--dry-run` 또는 PR 생성 방식. push 전 `git pull --rebase` |
| R8 | Secret 노출 | `.env`를 실수로 add, 생성 JSON에 토큰 포함, Actions 로그에 출력 | `.gitignore` 유지, `git add`는 명시 파일만, 생성 JSON 스키마에 URL/문자열만 허용, push 전 Secret 패턴 grep |
| R9 | Actions 토큰 권한 | Fine-grained PAT를 Secret에 넣으면 private 레포 README가 Actions 로그에 찍힐 수 있음 | 로그에 README 본문 출력 금지 (현재도 제목·기술만 출력) |
| R10 | Jekyll 처리 | `portfolio.template.yml`, `data/*.json` 등 새 파일은 정적 복사되므로 문제 없지만, 프론트매터(`---`)로 시작하는 `.md`를 두면 Jekyll이 변환을 시도 | 새 md 파일은 프론트매터 없이 작성하거나 `.nojekyll` 도입 여부를 결정 |
| R11 | `projects.json` 키 충돌 | repo 이름 키라서 다른 소유자의 같은 이름 레포와 충돌 가능 | Phase 2에서 slug 도입, 내부 키는 `owner/repo` 또는 slug |
| R12 | 개인 데이터 보호 | 실제 개인 데이터 접근 금지. README 중 개인 정보가 있는 private 레포(MyNote 등)의 내용이 세션에 노출될 수 있음 | 개발·테스트는 `fixtures/` 샘플 README·portfolio.yml로 수행. 실제 sync 실행은 사용자가 직접 |

---

## 5. 이후 구현 권장 순서

docs/tasks의 Phase 순서(2→7)를 그대로 따르되, 각 Phase에 아래 선행 조건·주의점을 반영한다.

### Phase 2 — Metadata (portfolio.yml / status)
- **먼저 B1·B2·B3 수정**을 이 Phase에 포함 권장. 기간·종료 판단은 status 체계의 기반이고, 이스케이프는 새 렌더 경로에서도 필요하다.
- `fetch_portfolio_yml(full_name)`: `GET /repos/{full}/contents/portfolio.yml` (404 허용). SHA를 `projects.json`에 `portfolioSha`로 저장.
- 정규화 스키마 하나로 통일: portfolio.yml → README/Claude → repo metadata 순으로 채우고, status/started/ended/featured/live_url은 yml 외 출처에서 채우지 않음(SPEC §10).
- Validation: title/status 필수, 미지원 status warning, unused → unused_reason 권장.
- 수동 카드 6개 + `projects/*.md`를 `data/manual/*.yml`(또는 `data/archive.yml`)로 옮길 수 있게 **로컬 메타데이터 소스**도 허용 (레포 없는 과거 프로젝트용).
- 샘플: `fixtures/portfolio.sample.yml`, `docs/portfolio.template.yml`.
- 기존 render_card 경로는 그대로 두고, 새 필드가 있으면 기간 표기(`Present`)·status badge만 추가하는 최소 변경으로 "기존 README 프로젝트 깨지지 않음" 조건 충족.

### Phase 3 — JSON Data Layer
- sync가 `data/projects.generated.json`을 생성 (generatedAt, projects[] with slug/status/period/urls/tech/highlights/summary/team/videos/awards/syncStatus).
- **권장 렌더 방식**: JS 런타임 렌더 + 정적 폴백을 동시에. 즉 sync가 JSON을 쓰고, 동일 JSON으로 `AUTO:START~END` 구간의 정적 HTML도 생성(템플릿 파일 `templates/card.html`로 분리). JS가 있으면 JSON으로 다시 그려 필터를 붙이고, 없어도 정적 HTML이 보인다. R6 완화.
- 수동 카드 6개도 JSON에 포함 → 처음으로 전체 정렬 가능. 이 시점에 `index.html`의 수동 카드 HTML은 유지하고 diff로 동일성 확인 후 다음 Phase에서 제거.
- `projects.json`은 sync 상태 캐시로 축소(sha/portfolioSha/lastSynced/syncStatus). 표시 데이터는 generated.json.

### Phase 4 — UI
- Featured / Current / Completed / Unused·Archived 섹션 + status 필터. CSS Variables·chip 체계 재사용, 새 클래스만 추가.
- unused 카드는 제목·기간·사유·replaced_by만 (SPEC §6).
- live_url 있으면 Live Demo 버튼. `prize-*` 이미지를 수상 표시에 활용 검토.
- 검증: 브라우저 콘솔 에러 0, 720px·400px 레이아웃, 라이트/다크 모두.

### Phase 5 — Mac Updater
- `Update Portfolio.command`: `git pull --rebase` → python 확인 → `--dry-run` 결과 표시 → 메뉴(Preview / Update & Push / Cancel) → `python -m http.server` 미리보기 → staged diff·Secret grep 후 commit/push. 실패 시 `read` 로 창 유지.
- `sync.sh`의 하드코딩(Obsidian 경로, `.env` 위치 불일치 B10) 정리는 이 Phase에서.
- 로그 `logs/portfolio-sync.log` + `.gitignore` 추가.

### Phase 6 — Screenshot
- Playwright는 선택 의존성. 실패해도 sync 계속. `assets/projects/{slug}/desktop.webp|mobile.webp`. 갱신 조건은 SPEC §18.
- 이미지 커밋 크기 주의 (webp, 해상도 제한).

### Phase 7 — Automation
- Actions: `secrets.PORTFOLIO_PAT`(Fine-grained, 대상 레포 read + 이 레포 contents write)로 교체. B9 수정으로 403을 명시적으로 보고. 처음엔 `schedule` + `--dry-run` 요약만, 안정화 후 자동 commit.
- launchd plist 예제 + README.
- `repository_dispatch` 수신 준비(문서화만).
- Secret이 생성 JSON·로그에 없는지 검증 스크립트.

### Phase 간 공통
- 각 Phase 시작 시 `--dry-run`, 종료 시 `git diff` 검토, 브라우저 확인.
- `CNAME`, Pages 설정, main 브랜치 배포 경로는 끝까지 불변.
- 개인 데이터 보호 규칙상 실제 private README를 세션에 불러오는 sync 실행은 사용자가 직접 수행하고, Claude Code는 fixtures로 개발·검증.

---

## 6. 결정이 필요한 사항 (사용자 확인)

1. **`.nojekyll` 추가 여부** — 빌드 단순화 이점 vs 배포 경로 변경. 추가하더라도 현재 정적 사이트에는 기능 영향 없음.
2. **Phase 3 렌더 방식** — 순수 JS fetch 렌더 vs "JSON + 정적 HTML 동시 생성"(권장).
3. **B1·B2·B3 버그 수정 시점** — Phase 2에 포함(권장) vs 별도 hotfix.
4. **`docs/`·`CLAUDE.md`·`AGENTS.md`가 dounselor.com에서 공개 접근 가능한 상태 유지 여부** — Secret은 없으나 내부 지시서다. 신경 쓰인다면 별도 브랜치/폴더 정책이 필요하다.
5. **Actions용 Fine-grained PAT 발급** — Phase 7 전제 조건. 사용자가 직접 발급·Secret 등록.
