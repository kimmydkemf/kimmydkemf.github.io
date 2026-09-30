# Dounselor Portfolio

**[dounselor.com](https://dounselor.com)** (GitHub Pages 호스팅, `kimmydkemf.github.io` → 커스텀 도메인 CNAME) — 개인 포트폴리오 사이트.

GitHub 레포지토리의 README를 자동으로 읽어 프로젝트 카드를 생성·업데이트하는 동기화 기능을 포함합니다.

---

## 기능

- **Apple 스타일 디자인** — 다크/라이트 모두 깔끔하고 임팩트 있는 비주얼 (라이트 배경 `#f5f5f7`, SF Pro 폴백 폰트, 부드러운 그림자·진입 페이드 애니메이션, 호버 lift)
- **다크 / 라이트 테마 전환** — nav 우측 버튼으로 전환, 선택값 localStorage 저장, 시스템 `prefers-color-scheme` 자동 감지
- **GitHub 자동 동기화** — README가 있는 레포를 감지해 포트폴리오 카드 자동 생성
- **Claude AI 카드 생성** — `ANTHROPIC_API_KEY` 설정 시 Claude가 README를 분석해 소개 문장을 다듬어 줌
- **최신순 자동 정렬** — 시작일 기준 내림차순 정렬
- **Obsidian 연동** — 동기화 시 Obsidian vault에 프로젝트 md 자동 생성

---

## 파일 구조

```
portfolio/
├── index.html                  # 포트폴리오 메인 페이지
├── assets/css/style.css        # 스타일 (다크/라이트 테마)
├── sync.sh                     # 포트폴리오 동기화 실행 스크립트
├── .env                        # 토큰 저장 (git 제외)
├── scripts/
│   ├── sync_projects.py        # GitHub API → 메타데이터 정규화 → 카드 생성 핵심 로직
│   ├── test_sync_projects.py   # 단위/통합 테스트 (네트워크 없음)
│   └── projects.json           # 레포별 README/portfolio.yml SHA·기간·상태 캐시 + 제외 목록
├── fixtures/repos/             # 개발·테스트용 가상 프로젝트 샘플 (--fixtures)
└── docs/
    ├── portfolio.template.yml  # 각 프로젝트 레포에 둘 portfolio.yml 템플릿
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

## 포트폴리오 업데이트 방법

### 새 프로젝트를 GitHub에 올린 경우

```bash
cd ~/Workspace/portfolio
./sync.sh
```

1. GitHub API로 전체 레포 조회
2. README가 있는 신규/변경 레포만 감지
3. Claude AI (또는 README 직접 파싱)로 카드 내용 생성
4. `index.html` 업데이트 → 변경사항 있으면 **자동 커밋 & 푸시**

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
        --index /tmp/preview.html --config /tmp/preview.json               # 스크래치 복사본에 렌더링
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

## 카드 직접 수정

`index.html`의 `<!-- AUTO:START -->` ~ `<!-- AUTO:END -->` 구간은 sync 스크립트가 자동 관리합니다.  
그 아래의 수동 카드(P.S, MeetingGround 등)는 직접 편집 후 커밋합니다.

```bash
# 수동 편집 후
git add index.html
git commit -m "update: 프로젝트 내용 수정"
git push
```

---

## 기술 스택

- **Frontend**: HTML · CSS (CSS Variables 기반 다크/라이트 테마, Apple-inspired) · Vanilla JS
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
