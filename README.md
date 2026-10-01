# Dounselor Portfolio

**[dounselor.com](https://dounselor.com)** (GitHub Pages 호스팅, `kimmydkemf.github.io` → 커스텀 도메인 CNAME) — 개인 포트폴리오 사이트.

GitHub 레포지토리의 README를 자동으로 읽어 프로젝트 카드를 생성·업데이트하는 동기화 기능을 포함합니다.

---

## 기능

- **Apple 스타일 디자인** — 다크/라이트 모두 깔끔하고 임팩트 있는 비주얼 (라이트 배경 `#f5f5f7`, SF Pro 폴백 폰트, 부드러운 그림자·진입 페이드 애니메이션, 호버 lift)
- **다크 / 라이트 테마 전환** — nav 우측 버튼으로 전환, 선택값 localStorage 저장, 시스템 `prefers-color-scheme` 자동 감지
- **GitHub 자동 동기화** — README / portfolio.yml 이 있는 레포를 감지해 `data/projects.generated.json` 생성 → 포트폴리오 카드 자동 생성 (정적 HTML + JS 렌더)
- **Claude AI 카드 생성** — `ANTHROPIC_API_KEY` 설정 시 Claude가 README를 분석해 소개 문장을 다듬어 줌
- **최신순 자동 정렬** — 시작일 기준 내림차순 정렬
- **Obsidian 연동** — 동기화 시 Obsidian vault에 프로젝트 md 자동 생성

---

## 파일 구조

```
portfolio/
├── index.html                  # 메인 페이지. 프로젝트 영역(AUTO 구간)은 sync 가 JSON 에서 생성
├── assets/
│   ├── css/style.css           # 스타일 (다크/라이트 테마)
│   └── js/projects.js          # projects.generated.json 을 브라우저에서 렌더 (정적 카드와 동일 마크업)
├── data/
│   ├── projects.generated.json # sync 결과 — 전체 프로젝트 데이터 (직접 편집 X)
│   ├── projects.manual.json    # 레포 없는 과거 프로젝트 — 사람이 편집
│   └── screenshots.json        # Screenshot manifest (url · 파일 · 캡처 시각)
├── Update Portfolio.command    # Mac 더블클릭 업데이터 (→ scripts/portfolio_update.sh)
├── sync.sh                     # 기존 일괄 동기화 스크립트 (확인 없이 commit & push)
├── .env                        # 토큰 저장 (git 제외)
├── scripts/
│   ├── sync_projects.py        # GitHub API → 메타데이터 정규화 → JSON 생성 → 정적 HTML 재생성
│   ├── render_cards.py         # JSON → 정적 카드 HTML (projects.js 와 1:1)
│   ├── migrate_index_cards.py  # (1회성) 예전 index.html 카드 → JSON 마이그레이션
│   ├── portfolio_update.sh     # Dry Run / Preview / Update & Push 업데이터
│   ├── validate_site.py        # commit 전 검증 (JSON · HTML · CNAME · Secret · 크기)
│   ├── screenshot_projects.py  # live_url Screenshot (Playwright / Chrome CLI)
│   ├── ci_sync.sh              # GitHub Actions 동기화 (pr / push / dry-run)
│   ├── install_launchd.sh      # Mac launchd 자동 실행 설치/해제
│   ├── test_automation.py      # ci_sync · launchd · workflow 테스트
│   ├── test_screenshot_projects.py
│   ├── test_sync_projects.py   # 단위/통합/parity 테스트 (네트워크 없음)
│   ├── test_portfolio_update.py# 업데이터 통합 테스트 (임시 저장소 + bare 원격)
│   └── projects.json           # 변경 감지 캐시 (README/portfolio.yml SHA, 커밋 월) + 제외 목록
├── fixtures/                   # 개발·테스트용 가상 프로젝트 샘플 (--fixtures), legacy index 스냅샷
└── docs/
    ├── portfolio.template.yml  # 각 프로젝트 레포에 둘 portfolio.yml 템플릿
    ├── PROJECT_DATA_SCHEMA.md  # projects.generated.json 스키마
    ├── PROJECT_SPEC.md         # 개선 프로젝트 요구사항
    └── tasks/, analysis/, decisions/
```

---

## 초기 설정

### 1. 토큰 준비

| 토큰 | 필수 여부 | 용도 |
|------|-----------|------|
| `GITHUB_TOKEN` | **필수** | private 레포 포함 전체 레포 조회 |
| `ANTHROPIC_API_KEY` | 선택 | Claude AI로 README 분석 → 자연스러운 소개 문장 생성 |

- **GitHub Token** 발급: [github.com → Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens) (repo 권한 필요)
- **Anthropic API Key** 발급: [console.anthropic.com](https://console.anthropic.com)

### 2. `.env` 파일 생성

프로젝트 루트에 `.env` 파일을 만들고 토큰을 저장합니다.

```bash
# portfolio/.env
GITHUB_TOKEN=github_pat_xxxxxxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx   # 선택
```

> `.env`는 `.gitignore`에 추가해 커밋되지 않도록 주의하세요.

---

## 프로젝트 상태 바꾸기

프로젝트가 어디에 있느냐에 따라 고치는 곳이 다릅니다.

| 프로젝트 | 고치는 곳 |
|----------|-----------|
| 본인(`kimmydkemf`) 소유 레포 — Pacer, Life Manager, Dounselor Blog 등 | 그 레포 루트의 `portfolio.yml` |
| 다른 사람 소유 레포 · 레포 없는 과거 프로젝트 — Business Calendar Plus, P.S 등 | 이 저장소의 `data/projects.manual.json` 의 `"status"` |

### 본인 레포: `portfolio.yml` 추가

1. 해당 프로젝트 레포의 **최상단(루트)** 에 `portfolio.yml` 파일을 만듭니다.
   [`docs/portfolio.template.yml`](docs/portfolio.template.yml) 을 복사해도 되고, 아래처럼 필요한 줄만 써도 됩니다.
2. 기본 브랜치(보통 `main`)에 commit & push 합니다.
3. 다음 자동 실행 때 반영됩니다 (아래 "반영 시점").

지켜야 할 것:

- 파일 이름은 정확히 **`portfolio.yml`**. `portfolio.template.yml` 같은 이름 그대로면 읽지 않습니다.
- **루트**에 있어야 하고, **기본 브랜치**에 push 되어 있어야 합니다. 다른 브랜치에만 있으면 읽지 않습니다.
- 토큰(`PORTFOLIO_PAT`)을 "Only select repositories" 로 만들었다면 그 레포가 선택 목록에 있어야 합니다.
- 템플릿의 `summary` 줄에는 `프로젝트 소개 2~3문장.` 이라는 예시 문장이 있습니다. 그대로 두면 이 문장이 README 소개 대신 카드에 나오므로 **실제 소개로 바꾸거나 지우세요.**
  나머지 빈 칸은 비워 두면 README 내용으로 채워집니다.

상태만 바꿀 때 (최소):

```yaml
title: Pacer
status: active
started: 2026-05
```

더 이상 쓰지 않는 프로젝트:

```yaml
title: Dounselor Blog
status: unused
started: 2026-05
ended: 2026-10
unused_reason: >
  Personal Archive 의 Journal 기능으로 통합해 운영을 종료함.
replaced_by:              # 선택 — 대체 프로젝트
  title: Personal Archive
  url: https://archive.dounselor.com
```

### 다른 사람 레포 · 과거 프로젝트: `data/projects.manual.json`

이 저장소의 `data/projects.manual.json` 에서 해당 항목의 `"status"` 값만 바꿉니다. 다른 내용은 그대로 둡니다.

```json
"status": "archived",
```

`null` 은 "배지 없음" 입니다. 바꾼 뒤 Mac 업데이터나 Actions 를 실행하면 반영됩니다.

### 반영 시점

- **자동**: 매일 03:00 KST 에 GitHub Actions 가 변경을 감지해 PR 을 만듭니다. PR 을 확인하고 병합하면 사이트에 반영됩니다.
- **바로**: GitHub → Actions → Sync GitHub Projects → Run workflow, 또는 Mac 에서 `Update Portfolio.command`.

### 상태별로 화면이 바뀌는 방식

| status | 배지 | 들어가는 그룹 | 기간 표시 | 카드 내용 |
|--------|------|--------------|----------|----------|
| `active` | 진행 중 | 진행 중 | `2026.05 – Present` | 전체 (소개 · 기능 · 기술 · Live Demo · GitHub) |
| `completed` | 완료 | 완료 | `2025.11 – 2026.03` | 전체 |
| `paused` | 일시 중단 | 일시 중단 | 시작 – 종료 | 전체 + "일시 중단 사유" (`pause_reason`) |
| `unused` | 미사용 | 미사용 · 아카이브 | 시작 – 종료 | **간단 카드**: 제목 · 기간 · 미사용 사유 · 대체 프로젝트 · Repository 만. 기술 · 기능 · 소개 · Live Demo · Screenshot 숨김 |
| `archived` | 아카이브 | 미사용 · 아카이브 | 시작 – 종료 | 전체 |
| 없음 (`null`) | 없음 | 마지막 커밋 3개월 이내면 진행 중, 아니면 완료 | 커밋 날짜 기준 | 전체 |

함께 바뀌는 것:

- 상단 **필터 버튼**의 개수가 바뀌고, 처음 생긴 상태는 버튼이 새로 나타납니다.
- **Featured**: `featured: true` 이고 `unused` 가 아닌 프로젝트가 맨 위 카드로 올라갑니다 (최대 5개). `unused` 로 바꾸면 Featured 에서 빠집니다.
- **Live Demo · Screenshot**: `live_url` 이 있으면 Live Demo 버튼과 Screenshot 이 생깁니다 (`unused` 는 둘 다 숨김).
  로그인 후 개인 데이터가 보이는 서비스라면 `screenshot: false` 를 함께 넣으세요.
- 상태 값에 **오타**가 있으면 sync 가 경고하고, Update & Push 의 Validation 이 commit 을 막습니다.

---

## 포트폴리오 업데이트 방법

### Mac — `Update Portfolio.command` (권장)

Finder 에서 저장소 루트의 **`Update Portfolio.command`** 를 더블클릭하면 Terminal 에 메뉴가 열립니다.

```text
── Dounselor Portfolio Updater ──
▶ 환경 확인        git · Python 3.10+ · 브랜치 · .env 토큰 확인
▶ git pull --ff-only
무엇을 할까요?
  1) Dry Run        — 변경 없이 탐지만
  2) Preview        — 임시 사본에 sync → 로컬 서버 → 브라우저 (저장소 변경 없음)
  3) Update & Push  — sync → Validation → 변경 파일 확인 → (미리보기) → commit → push
  4) Cancel
```

- **처음 한 번**: 우클릭 → 열기 (Gatekeeper 확인). 실행 권한이 없다면 `chmod +x "Update Portfolio.command"`.
- **Preview** 는 임시 디렉터리에서 sync 하고 추가/변경/제거된 프로젝트를 요약한 뒤 브라우저로 엽니다. 저장소 파일은 바뀌지 않습니다.
- **Update & Push** 는 매 단계마다 확인을 받습니다. 변경이 없으면 commit 하지 않고, commit 을 거절하면 sync 결과를 되돌릴 수 있습니다.
- commit 전 **Validation** (`scripts/validate_site.py`): JSON 스키마, index.html 정적 카드 == JSON, `CNAME == dounselor.com`, Secret 패턴, 파일 크기. 실패하면 commit 하지 않습니다.
- commit 대상은 sync 산출물 4개뿐입니다: `index.html`, `data/projects.generated.json`, `data/projects.manual.json`, `scripts/projects.json`. 다른 로컬 변경은 섞이지 않습니다.
- push 대상은 **현재 브랜치**입니다. GitHub Pages 는 `main` 을 배포하므로 다른 브랜치에서 실행하면 사이트에는 main 병합 후 반영됩니다. `.env` 에 `PORTFOLIO_BRANCH=main` 을 넣으면 그 브랜치에서만 Update 가 허용됩니다.
- 실패해도 창이 바로 닫히지 않습니다. 실행 기록은 `logs/portfolio-sync.log` (git 제외).

터미널에서 직접 / 비대화형 (launchd 등):

```bash
scripts/portfolio_update.sh                              # 메뉴
scripts/portfolio_update.sh --mode dry-run
scripts/portfolio_update.sh --mode preview
scripts/portfolio_update.sh --mode update                # 확인 질문 있음 (tty 가 아니면 모두 'no')
scripts/portfolio_update.sh --mode update --yes          # 확인 없이 commit & push
scripts/portfolio_update.sh --mode update --yes --no-push
scripts/portfolio_update.sh --force ...                  # sync --force (SHA 무시 전체 재생성)
```

Screenshot 단계는 sync 다음에 자동으로 실행됩니다 (아래 "Screenshot" 참고). 끄려면 `--no-screenshots`, 전부 다시 찍으려면 `--refresh-screenshots`.

`.env` 에서 읽는 값 (허용된 키만, 값은 출력하지 않음): `GITHUB_TOKEN` (필수), `ANTHROPIC_API_KEY`, `OBSIDIAN_VAULT` (지정 시 Obsidian md 생성), `PORTFOLIO_BRANCH`. 예시는 [`.env.example`](.env.example).

### `./sync.sh` (기존 방식)

확인 없이 sync 후 변경이 있으면 바로 commit & push 합니다.

```bash
cd ~/Workspace/portfolio
./sync.sh
```

1. GitHub API로 전체 레포 조회
2. README / portfolio.yml 이 바뀐 신규/변경 레포만 감지 (나머지는 이전 JSON 항목 재사용)
3. portfolio.yml 우선, 부족한 내용은 Claude AI (또는 README 직접 파싱)로 보완
4. `data/projects.generated.json` 생성 (+ `data/projects.manual.json` 의 과거 프로젝트 병합)
5. 같은 JSON 으로 `index.html` AUTO 구간 정적 카드 재생성 → 변경사항 있으면 **자동 커밋 & 푸시**

GitHub Pages 반영까지 약 1~2분 소요됩니다.

### 옵션

```bash
./sync.sh                    # 변경된 레포만 처리 (기본)
./sync.sh --force            # 전체 레포 강제 재생성
./sync.sh --dry-run          # 실제 변경 없이 감지만
```

개발·테스트용 (GitHub 접근 없음):

```bash
python3 scripts/sync_projects.py --fixtures fixtures/repos --dry-run      # 샘플로 탐지만
python3 scripts/sync_projects.py --fixtures fixtures/repos \
        --index /tmp/preview.html --config /tmp/preview.json \
        --generated /tmp/preview.generated.json --manual data/projects.manual.json   # 스크래치 복사본에 렌더링
python3 scripts/test_sync_projects.py                                      # 테스트 (node 있으면 JS parity 포함)
python3 scripts/test_portfolio_update.py                                   # 업데이터 테스트 (임시 저장소, push 없음)
python3 scripts/test_screenshot_projects.py                                # Screenshot 테스트 (로컬 서버만)
python3 scripts/test_automation.py                                         # Actions · launchd 테스트 (push 없음)
python3 scripts/validate_site.py --scan-repo                               # 저장소 전체 Secret 검사
```

---

## 자동 업데이트

### GitHub Actions (Mac 이 꺼져 있어도 동작)

`.github/workflows/sync-projects.yml` — **매일 03:00 KST** · 수동 실행 · 프로젝트 레포 호출(`repository_dispatch`).

```text
checkout → 테스트 → scripts/ci_sync.sh
            └ portfolio_update.sh --mode update --yes --no-push   (sync → Screenshot → Validation → commit)
            └ Secret 검사 (패턴 + 실제 토큰 값 비교) → 반영
반영 방식 (SYNC_MODE):
  pr      (기본) automation/portfolio-sync 브랜치에 push → main 으로 가는 PR 생성/갱신 → 확인 후 병합
  push    main 에 바로 push (Pages 즉시 반영)
  dry-run 결과만 확인
```

**처음 설정**

1. Fine-grained PAT 발급 — GitHub → Settings → Developer settings → Fine-grained tokens
   - Resource owner: `kimmydkemf`, Repository access: 포트폴리오에 올릴 **본인 레포** (또는 All repositories)
   - Permissions: **Contents: Read-only**, **Metadata: Read-only** (그 외 권한 불필요)
   - 다른 사람 소유 레포는 읽지 않으므로 권한이 필요 없습니다 (`data/projects.manual.json` 에서 관리).
2. 이 레포 Settings → Secrets and variables → Actions → **Secrets**
   - `PORTFOLIO_PAT` = 위 토큰 (필수)
   - `ANTHROPIC_API_KEY` (선택, Claude 요약)
3. PR 모드를 쓰려면 Settings → Actions → General → Workflow permissions →
   **"Allow GitHub Actions to create and approve pull requests"** 체크. 끄면 브랜치만 push 하고 실행 요약에 비교 링크를 남깁니다.
4. (선택) **Variables**: `PORTFOLIO_SYNC_MODE` = `pr` | `push` | `dry-run`, `PORTFOLIO_SCREENSHOTS` = `0` (끄기)
5. 이 워크플로 파일이 **main 에 병합된 뒤부터** schedule / repository_dispatch 가 동작합니다 (GitHub 규칙).
   수동 실행: Actions → Sync GitHub Projects → Run workflow.

**시간대**: cron 은 UTC 기준입니다. `0 18 * * *` = 매일 18:00 UTC = 다음날 03:00 KST. GitHub 사정에 따라 수 분~수십 분 늦게 시작할 수 있습니다.
바꾸려면 원하는 KST 시각에서 9시간을 뺀 값을 넣으세요 (예: 07:30 KST → `30 22 * * *`).

**토큰 처리**: PAT 는 `env` 로만 전달하고 `run` 스크립트에 직접 넣지 않습니다. 로그에서는 마스킹하고, 기본 `GITHUB_TOKEN` 은 PR 생성에만 씁니다.
push 직전에 `validate_site.py --scan-repo` 가 모든 파일에서 토큰 패턴과 **실제 토큰 값**을 찾아, 발견되면 push 하지 않습니다.

### Mac launchd (Mac 에서 정해진 시각에 자동 실행)

```bash
scripts/install_launchd.sh install                    # 매일 03:00, dry-run (기록만 — 권장 기본값)
scripts/install_launchd.sh install --mode update      # 매일 03:00, 확인 없이 sync → commit → push
scripts/install_launchd.sh install --hour 7 --minute 30 --at-login
scripts/install_launchd.sh status                     # 등록 여부 · 최근 실행
scripts/install_launchd.sh run                        # 지금 한 번 실행
scripts/install_launchd.sh uninstall                  # 해제 (plist 삭제)
```

- 설치 위치: `~/Library/LaunchAgents/com.dounselor.portfolio-sync.plist`. 로그: `logs/launchd.log`, `logs/portfolio-sync.log`.
- Mac 이 잠자기 중이면 깨어난 뒤 한 번 실행됩니다. 토큰은 저장소 `.env` 에서 읽습니다.
- `--mode update` 는 **현재 체크아웃된 브랜치**에 push 합니다. git 인증은 Terminal 과 같습니다 (암호 있는 SSH 키는 `ssh-add --apple-use-keychain` 로 키체인에 저장).
- GitHub Actions 와 함께 쓸 때는 **한 곳에서만 push** 하도록 권장합니다 (예: Actions = pr/push, Mac = dry-run).

### 프로젝트 레포에서 즉시 갱신 (repository_dispatch, 선택)

프로젝트 레포의 README / portfolio.yml 이 바뀌면 포트폴리오 sync 를 바로 실행하도록 할 수 있습니다.
예시: [`docs/examples/notify-portfolio.yml`](docs/examples/notify-portfolio.yml) 을 프로젝트 레포의 `.github/workflows/` 에 복사하고,
그 레포에 `PORTFOLIO_DISPATCH_TOKEN` (이 포트폴리오 레포만 대상, Contents: Read and write 인 Fine-grained PAT) 을 등록합니다.
읽기용 `PORTFOLIO_PAT` 과는 권한이 달라 별도 토큰을 씁니다.

---

## Screenshot

`live_url` 이 있는 프로젝트는 실제 서비스 화면을 캡처해 Featured 커버와 상세 카드의 "화면" 섹션에 보여줍니다.

```text
live_url → (HTTP 200 확인) → Playwright → assets/projects/{slug}/desktop.webp (1440×900)
                                         → assets/projects/{slug}/mobile.webp  (390×844 @2x)
         → data/screenshots.json (manifest) → projects.generated.json "screenshots" → index.html
```

- **언제 다시 찍나**: 새 프로젝트, `live_url` 변경, 파일 없음, 30일 경과, `--refresh SLUG` / `--refresh-all`, portfolio.yml `screenshot_refresh: true`. 그 외에는 기존 파일을 그대로 씁니다.
- **실패해도 계속**: 접속 실패·HTTP 오류·엔진 없음은 경고만 남기고 기존 Screenshot 을 유지합니다. 오류 페이지를 캡처해 저장하지 않도록 캡처 전에 응답 코드를 확인합니다.
- **대상 제외**: `status: unused`, 또는 portfolio.yml `screenshot: false`.
  ⚠ Screenshot 은 공개 사이트에 올라갑니다. 로그인 후 개인 데이터가 보이는 화면이라면 `screenshot: false` 로 두세요.
- **설치 (선택)**: `python3 -m pip install --user -r requirements-screenshot.txt`. 브라우저는 설치된 Chrome 을 씁니다.
  Playwright 가 없으면 Chrome CLI 로 Desktop 만 찍습니다 (모바일은 Playwright 필요).

```bash
python3 scripts/screenshot_projects.py --dry-run          # 무엇을 찍을지
python3 scripts/screenshot_projects.py                    # 필요한 것만 캡처
python3 scripts/screenshot_projects.py --refresh pacer    # 특정 프로젝트 다시
python3 scripts/screenshot_projects.py --max-age-days 7
```

---

## portfolio.yml — 프로젝트 표시용 메타데이터

각 프로젝트 레포 루트에 `portfolio.yml`을 두면 README보다 우선 적용됩니다.
README는 개발 문서, `portfolio.yml`은 포트폴리오 표시용 메타데이터입니다.
없으면 기존처럼 README(Claude 또는 파서)로 카드를 만듭니다.

```text
우선순위:  portfolio.yml  >  README (Claude / 파서)  >  GitHub repo metadata
```

템플릿: [`docs/portfolio.template.yml`](docs/portfolio.template.yml)

```yaml
title: Pacer
subtitle: 건강, 술, 운동. 나를 기록하다.
status: active            # active | completed | paused | unused | archived
started: 2026-05
ended:                    # active 는 비워둠
featured: true
live_url: https://pacer.dounselor.com
tech: [React, FastAPI, SQLite]
highlights:
  - 음식 사진 AI 분석
  - 운동 및 음주 기록
summary: >
  개인의 건강·운동·음식·음주 기록을 통합 관리하는 Life Tracking 서비스.
```

### status

| 값 | 의미 | 표시 |
|----|------|------|
| `active` | 현재 사용·개발 중 | 배지 "진행 중", 기간 `YYYY.MM – Present` |
| `completed` | 완료, 목적 달성 | 배지 "완료" (`ended` 권장) |
| `paused` | 일시 중단 | 배지 "일시 중단", `pause_reason` 표시 |
| `unused` | 더 이상 사용하지 않음 | **간단 카드**: 제목·기간·미사용 사유·대체 프로젝트만. 기술/기능/Live Demo 숨김 |
| `archived` | 과거 기록 보존 | 배지 "아카이브" |

`status`·`started`·`ended`·`featured`·`live_url`·`unused_reason`·`replaced_by`는
`portfolio.yml`에서만 읽습니다. Claude나 README 파서가 추정하지 않습니다.

`status`가 없는 README 전용 프로젝트는 커밋 날짜로 기간을 추정하며, 마지막 커밋이 3개월 이내면 진행 중으로 표시합니다.

바꾸는 방법과 화면 변화는 위 ["프로젝트 상태 바꾸기"](#프로젝트-상태-바꾸기) 참고.

### 미사용(unused) 프로젝트 예

```yaml
title: Dounselor Blog
status: unused
started: 2026-01
ended: 2026-09
unused_reason: >
  Personal Archive의 Journal 기능으로 통합하기로 결정하여
  기존 독립형 블로그 운영을 종료함.
replaced_by:
  title: Personal Archive
  url: https://archive.dounselor.com   # 공개 전이면 비워둠
```

### Validation

sync 시 다음을 검사하고 경고를 출력합니다 (중단하지 않음).
`title`/`status` 누락, 지원되지 않는 `status`, `unused`인데 `unused_reason` 없음,
`completed`인데 `ended` 없음, `active`인데 `ended` 있음, 날짜 형식(`YYYY-MM`) 오류, `live_url`이 http(s)가 아님.

### 변경 감지

README SHA와 `portfolio.yml` SHA를 `scripts/projects.json`에 저장하고, 둘 중 하나라도 바뀌면 카드를 갱신합니다.

---

## projects.json 관리

`scripts/projects.json`은 sync 결과를 캐시하고 제외·스킵 목록을 관리합니다.

```json
{
  "excluded": [
    "레포이름"          // 포트폴리오에 표시하지 않을 레포
  ],
  "skip_repos": [
    "레포이름"          // 자동 감지는 하되 카드 생성은 건너뛸 레포
  ],
  "repos": {
    "레포이름": {
      "sha": "...",            // README SHA (변경 감지용)
      "portfolioSha": "...",   // portfolio.yml SHA (없으면 "")
      "start": "2026.04",      // 표시용 시작월 (portfolio.yml started 우선)
      "end": "2026.09",        // 표시용 종료월 (진행 중이면 "")
      "commitStart": "2026.04",// 첫 커밋 월 (보조)
      "commitEnd": "2026.09",  // 마지막 커밋 월 (보조)
      "status": "active",      // portfolio.yml status (없으면 null)
      "title": "표시할 제목"
    }
  }
}
```

**특정 레포를 제외하고 싶을 때:**

```json
"excluded": ["MyNote", "SharePaper", "제외할레포"]
```

수정 후 `./sync.sh` 실행하면 반영됩니다.

---

## 프로젝트 데이터 레이어

프로젝트 정보의 원본은 `data/projects.generated.json` 입니다. 스키마는 [`docs/PROJECT_DATA_SCHEMA.md`](docs/PROJECT_DATA_SCHEMA.md) 참고.

```text
GitHub (README + portfolio.yml) ─┐
                                 ├─ sync_projects.py ─→ data/projects.generated.json
data/projects.manual.json ───────┘                          ├─→ render_cards.py → index.html AUTO 구간 (정적, JS 없이도 표시)
                                                            └─→ assets/js/projects.js → 브라우저 렌더
```

- `index.html` 의 `<!-- AUTO:START -->` ~ `<!-- AUTO:END -->` 구간은 **모든 카드**를 sync 가 생성합니다. 직접 편집하지 마세요.
- 프로젝트 영역은 **Featured → 진행 중 → 일시 중단 → 완료 → 미사용·아카이브** 순서로 나뉘고, 상단에 상태 필터가 붙습니다.
  Featured 에 올리려면 해당 레포 `portfolio.yml` 에 `featured: true` (또는 manual JSON 의 `"featured": true`). 최대 5개.
  `live_url` 이 있으면 카드에 **Live Demo** 버튼이 생깁니다. 자세한 규칙은 스키마 문서의 "프로젝트 영역 구조" 참고.
- **과거 프로젝트(레포 없음)** 는 `data/projects.manual.json` 을 편집한 뒤 `./sync.sh` 를 실행하면 반영됩니다.
- **다른 사람 소유 레포는 읽지 않습니다.** sync 는 본인(`kimmydkemf`) 소유 레포만 조회합니다.
  팀 프로젝트처럼 다른 사람 레포에 있는 프로젝트는 `data/projects.manual.json` 에 내용을 그대로 두고 (`"repo": "레포이름"` 지정),
  **`status` 만 직접 고치면 됩니다** — `"active"` · `"completed"` · `"paused"` · `"unused"` · `"archived"` 또는 `null` (배지 없음, 기간 기준 그룹).
  예: Business Calendar Plus (`ghals5737/bcplus_legacy`). 잘못된 값은 sync 에서 경고가 나고 Update 의 Validation 에서 commit 이 막힙니다.
- GitHub 프로젝트의 표시 내용은 해당 레포의 `portfolio.yml` 로 조정합니다.
- 레포가 삭제되거나 private 으로 바뀌어 목록에서 사라지면 항목은 `syncStatus: "unavailable"` 로 유지됩니다. 지우려면 `scripts/projects.json` 의 `excluded` 에 추가하세요.

```bash
# projects.manual.json 편집 후
./sync.sh            # JSON + index.html 재생성 → 변경 있으면 커밋 & 푸시
```

---

## 기술 스택

- **Frontend**: HTML · CSS (CSS Variables 기반 다크/라이트 테마, Apple-inspired) · Vanilla JS (JSON 렌더러)
- **Sync**: Python 3 (표준 라이브러리, PyYAML 선택) · GitHub REST API · Anthropic Claude API
- **Hosting**: GitHub Pages

---

## 도메인 / 인프라

- **메인 도메인**: `dounselor.com` (apex)
- **GitHub Pages**: 정적 호스팅 — `kimmydkemf.github.io`, CNAME 파일로 커스텀 도메인 연결
- **DNS / SSL**: Cloudflare (free 플랜)
- **관련 서브도메인**:
  - `pacer.dounselor.com` — Pacer (개인 PWA, 자체 호스트)
  - `life.dounselor.com` — Life Manager (개인 PWA, 자체 호스트)

### GitHub Pages 커스텀 도메인 설정

1. 레포 Settings → Pages → **Custom domain** 에 `dounselor.com` 입력
2. Enforce HTTPS 체크
3. Cloudflare DNS:
   - **A 레코드** `@` → GitHub Pages IP 4개:
     ```
     185.199.108.153
     185.199.109.153
     185.199.110.153
     185.199.111.153
     ```
   - **CNAME** `www` → `kimmydkemf.github.io`
4. Cloudflare proxied → DNS only 로 설정 (GitHub Pages 자체 SSL 사용 위해)

---

## 디자인 노트

- **라이트 모드** — Anthropic / Substack 스타일 따뜻한 크림 톤 (`#faf6ed` 배경 + 오프화이트 카드 + 깊은 블루 액센트). 종이 매거진 같은 인상.
- **다크 모드** — 거의 검정 (`#07090f`) 배경에 네온 블루·퍼플 그라데이션 hero. 심플한 톤 유지.
- **라이트 전용 임팩트 레이어** — 큰 섹션 번호 인디케이터 (`01·02·03·04`, CSS counter), Hero 그라데이션 블롭 + 28초 드리프트 애니메이션, About/Project 카드 상단 stripe 슬라이드.
- **공통** — hero 진입 fadeUp stagger, 카드 호버 lift, sticky nav backdrop blur, `prefers-reduced-motion` 대응.
- 모든 색상은 CSS Variables 로 분리 → 두 테마에서 동일 룩 유지.
