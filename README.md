# Dounselor Portfolio

**kimmydkemf.github.io** — GitHub Pages 기반 개인 포트폴리오 사이트.

GitHub 레포지토리의 README를 자동으로 읽어 프로젝트 카드를 생성·업데이트하는 동기화 기능을 포함합니다.

---

## 기능

- **다크 / 라이트 테마 전환** — nav 우측 버튼으로 전환, 선택값 localStorage 저장
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
└── scripts/
    ├── sync_projects.py        # GitHub API → 카드 생성 핵심 로직
    └── projects.json           # 레포별 SHA·기간·제목 캐시 + 제외 목록
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
      "sha": "...",    // README SHA (변경 감지용)
      "start": "2026.04",
      "end": "2026.04",
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

- **Frontend**: HTML · CSS (CSS Variables 기반 다크/라이트 테마) · Vanilla JS
- **Sync**: Python 3 · GitHub REST API · Anthropic Claude API
- **Hosting**: GitHub Pages
