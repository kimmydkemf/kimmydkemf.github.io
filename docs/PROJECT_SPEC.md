# dounselor.com 포트폴리오 개선 프로젝트 - 개발 Agent 개발 지시서

## 1. 프로젝트 목적

현재 운영 중인 `dounselor.com` 포트폴리오/블로그 사이트를 개선한다.

현재 사이트는 GitHub Repository의 README를 읽어 프로젝트 정보를 정리하고, 정적 페이지에 프로젝트 내용을 반영하는 구조를 가지고 있다.

기존 자동화 구조는 최대한 유지하되, 다음 목표를 달성하도록 개선한다.

1. GitHub 프로젝트 정보를 더 일관된 형식으로 관리
2. README 품질에 따라 포트폴리오 결과가 크게 달라지는 문제 개선
3. 현재 사용 중인 프로젝트와 종료/미사용 프로젝트를 명확히 구분
4. 실제 서비스가 존재하는 프로젝트는 Live Demo 링크 제공
5. 프로젝트 데이터를 HTML과 분리하여 유지보수성 향상
6. Mac에서 수동/자동 업데이트 가능
7. 향후 GitHub Actions를 통한 완전 자동 업데이트 가능
8. 프로젝트 Screenshot 자동 생성 기능 추가 가능
9. 기존 dounselor.com 디자인의 장점을 유지하면서 프로젝트 UX 개선

이 프로젝트의 핵심은 사이트를 완전히 새로 만드는 것이 아니라,
**현재 포트폴리오 동기화 구조를 체계적인 프로젝트 아카이브 시스템으로 발전시키는 것**이다.

---

# 2. 기존 구조 우선 분석

코드를 수정하기 전에 반드시 현재 Repository를 분석한다.

다음 항목을 우선 확인한다.

- 현재 Repository 구조
- `index.html`
- CSS
- JavaScript
- `scripts/sync_projects.py`
- `sync.sh`
- `projects.json` 또는 이에 준하는 캐시/메타데이터 파일
- GitHub README 조회 방식
- README SHA 변경 감지 방식
- 프로젝트 HTML 생성 방식
- Git Commit / Push 방식
- GitHub Pages 배포 방식

기존에 정상 동작하는 기능은 무작정 제거하거나 재작성하지 않는다.

먼저 다음 내용을 사용자에게 요약한다.

1. 현재 자동화 구조
2. 유지할 부분
3. 개선할 부분
4. 변경 시 위험요소
5. 개선 단계

그 다음 실제 구현을 진행한다.

---

# 3. 핵심 개선 방향

현재 구조가 다음과 같다면:

```text
GitHub Repository
↓
README
↓
Parser 또는 AI
↓
HTML 생성
↓
index.html 수정
↓
Git Commit
↓
Git Push
↓
GitHub Pages
```

이를 다음 구조로 개선한다.

```text
GitHub Repository
↓
portfolio.yml 우선 조회
↓
README 보조 조회
↓
Project Metadata 생성
↓
projects.generated.json
↓
Frontend Render
↓
dounselor.com
```

중요 원칙:

> README는 개발 문서이고,
> portfolio.yml은 포트폴리오 표시용 메타데이터이다.

README만으로도 동작할 수 있어야 하지만,
`portfolio.yml`이 존재하면 반드시 해당 내용을 우선 사용한다.

---

# 4. portfolio.yml 도입

각 프로젝트 Repository에 선택적으로 `portfolio.yml` 파일을 둘 수 있도록 한다.

예시:

```yaml
title: Pacer

subtitle: 건강, 술, 운동. 나를 기록하다.

status: active

started: 2026-05
ended:

category:
  - Personal
  - Health
  - AI

featured: true

live_url: https://pacer.dounselor.com

repository_url: https://github.com/example/pacer

cover:
  image: docs/cover.png

role:
  - Planning
  - Frontend
  - Backend
  - Infrastructure

tech:
  - React
  - FastAPI
  - SQLite
  - Gemini

highlights:
  - 음식 사진 AI 분석
  - 운동 및 음주 기록
  - 모바일 PWA
  - 개인 건강 데이터 시각화

summary: >
  개인의 건강, 운동, 음식, 음주 기록을 통합 관리하는
  개인용 Life Tracking 서비스.
```

---

# 5. Project Status 체계

프로젝트 상태를 명시적으로 관리한다.

최소 다음 상태를 지원한다.

```text
active
completed
paused
unused
archived
```

각 상태의 의미는 다음과 같다.

## active

현재 실제 사용 중이거나 개발 중인 프로젝트

예:

```yaml
status: active
```

UI에서는 현재 프로젝트 또는 Active Project로 표시한다.

---

## completed

개발이 완료되었고 목적을 달성한 프로젝트

더 이상 개발하지 않더라도 결과물로서 의미가 있는 프로젝트

예:

```yaml
status: completed
```

전체 프로젝트 목록에 정상적으로 표시한다.

---

## paused

개발을 일시 중단했지만 향후 다시 사용할 가능성이 있는 프로젝트

예:

```yaml
status: paused

pause_reason: >
  현재 다른 프로젝트를 우선 개발하고 있어 일시 중단.
```

필요하면 상세 내용을 표시할 수 있다.

---

## unused

개발했거나 실제로 사용했지만 현재는 더 이상 사용하지 않는 프로젝트

이 상태가 이번 개선에서 중요하다.

예:

```yaml
status: unused

started: 2026-01
ended: 2026-09

unused_reason: >
  기존 Blog 프로젝트를 Personal Archive 기반의 통합 Journal 시스템으로
  재구축하기로 결정하여 기존 서비스는 더 이상 사용하지 않음.
```

unused 프로젝트는 일반 Active Project처럼 상세 내용을 길게 표시하지 않는다.

다음 정보만 표시한다.

```text
프로젝트 제목
기간
미사용 사유
```

예:

```text
Dounselor Blog

2026.01 - 2026.09

미사용
Personal Archive의 Journal 기능으로 통합하기로 결정하여
기존 Blog 프로젝트는 더 이상 운영하지 않음.
```

Repository 링크는 선택적으로 표시할 수 있다.

기술 스택, 주요 기능, 긴 README 요약 등은 기본적으로 숨긴다.

---

## archived

과거 프로젝트로서 기록만 보존하는 프로젝트

특히 오래된 프로젝트에 사용한다.

예:

```yaml
status: archived
```

연도별 Archive 영역에 표시한다.

---

# 6. 미사용 프로젝트 표시 정책

`status: unused` 프로젝트는 다른 프로젝트와 다른 UI를 사용한다.

예:

```text
──────────────

Dounselor Blog

2026.01 - 2026.09

미사용 프로젝트

Personal Archive의 Journal 기능으로 통합됨에 따라
기존 Blog 프로젝트는 운영 종료.

──────────────
```

미사용 프로젝트 UI는 다음 원칙을 따른다.

- Screenshot 필수 아님
- 긴 README 내용 표시하지 않음
- 기술 Stack 기본 숨김
- Highlights 기본 숨김
- Live Demo 버튼 숨김
- Repository 링크는 선택
- 제목
- 기간
- 상태
- 미사용 사유
- 필요 시 대체 프로젝트 링크

를 표시한다.

---

# 7. 대체 프로젝트 관계

기존 프로젝트가 새로운 프로젝트로 대체되는 경우 이를 표현할 수 있도록 한다.

예:

```yaml
status: unused

unused_reason: >
  기존 블로그를 새로운 Personal Archive의 Journal 기능으로 통합함.

replaced_by:
  title: Personal Archive
  repository: https://github.com/example/personal-archive
  url: https://archive.dounselor.com
```

Frontend에서는 선택적으로 다음과 같이 표시한다.

```text
이 프로젝트는 Personal Archive로 통합되었습니다.

→ Personal Archive 보기
```

대체 프로젝트가 아직 공개되지 않았다면 링크는 표시하지 않는다.

---

# 8. 프로젝트 기간 처리

프로젝트 시작일/종료일을 Git Commit 날짜로 추정하는 방식은 보조 수단으로만 사용한다.

가능하면 `portfolio.yml`의 다음 값을 우선 사용한다.

```yaml
started: 2026-05
ended: 2026-09
```

active 프로젝트:

```yaml
started: 2026-05
ended:
status: active
```

표시:

```text
2026.05 - Present
```

completed 프로젝트:

```yaml
started: 2025-11
ended: 2026-03
status: completed
```

표시:

```text
2025.11 - 2026.03
```

날짜를 문자열 비교만으로 판단하지 않는다.

Date 객체 또는 명시적 상태값을 사용한다.

---

# 9. README 사용 정책

다음 우선순위를 적용한다.

```text
1. portfolio.yml
2. README.md
3. GitHub Repository metadata
4. AI/Parser 보완
```

README는 다음 용도로 활용한다.

- 프로젝트 설명 보완
- 주요 기능 추출
- 기술 스택 추출
- 설치/사용 방법 추출
- Screenshot 경로 후보 탐색

하지만 README 내용 전체를 포트폴리오에 그대로 노출하지 않는다.

영문 README라 하더라도 사이트 표시 언어에 맞게 정리한다.

---

# 10. AI 사용 원칙

AI가 사용 가능한 경우 README를 기반으로 다음을 생성할 수 있다.

```text
subtitle
summary
highlights
category 후보
tech 후보
```

하지만 다음 값은 AI가 임의로 추정하지 않는다.

```text
status
started
ended
featured
live_url
unused_reason
replaced_by
```

이 값들은 `portfolio.yml` 또는 명시적인 설정값을 우선한다.

AI가 프로젝트 상태나 운영 여부를 임의로 판단하지 않도록 한다.

---

# 11. projects.generated.json

Python에서 HTML을 직접 생성하여 `index.html`을 수정하는 방식에서 점진적으로 벗어난다.

프로젝트 정보를 다음 파일로 생성한다.

```text
data/projects.generated.json
```

예:

```json
{
  "generatedAt": "2026-09-30T14:00:00+09:00",
  "projects": [
    {
      "title": "Pacer",
      "subtitle": "건강, 술, 운동. 나를 기록하다.",
      "status": "active",
      "started": "2026-05",
      "ended": null,
      "featured": true,
      "liveUrl": "https://pacer.dounselor.com",
      "repositoryUrl": "https://github.com/example/pacer",
      "tech": [
        "React",
        "FastAPI",
        "Gemini"
      ],
      "highlights": [
        "음식 사진 AI 분석",
        "운동 및 음주 기록"
      ]
    },
    {
      "title": "Dounselor Blog",
      "status": "unused",
      "started": "2026-01",
      "ended": "2026-09",
      "unusedReason": "Personal Archive Journal 기능으로 통합하여 기존 블로그 운영 종료."
    }
  ]
}
```

Frontend JavaScript는 이 JSON을 읽어 UI를 생성한다.

---

# 12. 데이터와 Presentation 분리

다음 구조를 목표로 한다.

```text
GitHub
↓
Sync Engine
↓
projects.generated.json
↓
Frontend Renderer
↓
HTML
```

Sync Script가 직접 복잡한 HTML 문자열을 만들지 않도록 한다.

다만 기존 구조를 한 번에 제거하면 위험한 경우 단계적으로 전환한다.

---

# 13. Featured Projects

현재 사용 중이거나 중요한 프로젝트 중 일부를 Featured로 표시한다.

`portfolio.yml`

```yaml
featured: true
```

Featured 영역에서는 다음 내용을 보여준다.

```text
Cover / Screenshot
Title
Subtitle
Status
Tech
Live Demo
GitHub
```

예:

```text
PROJECTS

Featured

┌─────────────────────────┐
│        Screenshot       │
│                         │
│ PACER                   │
│ 건강, 술, 운동.          │
│                         │
│ React · FastAPI · AI    │
│                         │
│ Live Demo     GitHub    │
└─────────────────────────┘
```

Featured는 너무 많지 않게 한다.

권장 최대:

```text
3 ~ 5 projects
```

---

# 14. 전체 프로젝트 구조

전체 프로젝트 영역을 다음과 같이 구성한다.

```text
PROJECTS

Featured Projects

Current Projects

Completed Projects

Unused / Archived Projects
```

또는 연도 기반으로:

```text
2026

Active
Completed
Unused

2025

Completed
Archived
```

필터를 지원할 수 있다.

예:

```text
[All] [Active] [Completed] [Unused] [Archived]
```

---

# 15. 기존 과거 프로젝트

기존 사이트에 수동으로 작성되어 있는 과거 프로젝트를 무작정 삭제하지 않는다.

필요하면 점진적으로 Metadata 구조로 이전한다.

예:

```yaml
title: MeetingGround
status: archived
started: 2019
ended: 2020
```

과거 프로젝트는 상세 자동화 대상에서 제외할 수 있다.

---

# 16. Live Demo 버튼

`live_url`이 있는 경우 프로젝트 카드에 다음 버튼을 표시한다.

```text
Live Demo
GitHub
```

`live_url`이 없으면 Live Demo를 표시하지 않는다.

`status: unused`인 경우 기본적으로 Live Demo를 표시하지 않는다.

---

# 17. Screenshot 자동화

향후 또는 가능하면 이번 프로젝트에서 Playwright를 사용해 Screenshot 기능을 추가한다.

`live_url`이 있는 프로젝트는 다음 과정을 수행할 수 있다.

```text
Live URL
↓
Playwright
↓
Desktop Screenshot
↓
Mobile Screenshot
↓
assets/projects/{slug}/
```

예:

```text
assets/projects/pacer/desktop.webp
assets/projects/pacer/mobile.webp
```

Screenshot 생성 실패가 전체 Sync 실패로 이어지지 않도록 한다.

기존 Screenshot이 존재하면 유지한다.

---

# 18. Screenshot 업데이트 정책

매 Sync마다 Screenshot을 다시 생성하지 않는다.

다음 경우에만 갱신한다.

- 새 프로젝트
- live_url 변경
- 명시적 refresh 요청
- 일정 기간 경과
- `screenshot_refresh: true`

예:

```yaml
screenshot_refresh: true
```

---

# 19. Mac 실행 프로그램

Mac에서 터미널 명령어를 직접 입력하지 않고 업데이트할 수 있도록 실행 파일을 제공한다.

예:

```text
Update Portfolio.command
```

실행 흐름:

```text
Double Click
↓
Repository 이동
↓
git pull
↓
Python 환경 확인
↓
Portfolio Sync 실행
↓
JSON 생성
↓
필요 시 Screenshot
↓
Preview / Validation
↓
git status
↓
Commit
↓
Push
```

실패 시 Terminal 창이 바로 닫히지 않고 오류를 확인할 수 있어야 한다.

---

# 20. Mac 자동 업데이트

macOS `launchd`를 이용한 자동 실행 예제를 제공한다.

예:

```text
매일 오전 03:00
```

또는

```text
Mac 로그인 시
```

자동화 파일 예:

```text
~/Library/LaunchAgents/com.dounselor.portfolio-sync.plist
```

README에 설정 및 해제 방법을 작성한다.

---

# 21. GitHub Actions 자동 업데이트

향후 Mac이 꺼져 있어도 자동 업데이트할 수 있도록 GitHub Actions Workflow를 추가할 수 있다.

기본 Workflow:

```text
schedule
workflow_dispatch
```

예:

```yaml
on:
  schedule:
    - cron: "0 18 * * *"
  workflow_dispatch:
```

시간대 차이를 README에 설명한다.

---

# 22. repository_dispatch 확장

각 프로젝트 Repository에서 README 또는 `portfolio.yml`이 변경되면 포트폴리오 Repository의 Workflow를 호출하는 구조로 확장 가능하도록 한다.

예:

```text
Project Repository Push
↓
repository_dispatch
↓
Portfolio Repository
↓
Sync
↓
Commit
↓
GitHub Pages Update
```

초기 구현에서 반드시 적용할 필요는 없지만 문서화한다.

---

# 23. Private Repository 처리

Private Repository를 읽어야 하는 경우 기본 `GITHUB_TOKEN`만으로 충분하지 않을 수 있으므로 별도 인증 구조를 고려한다.

권장:

```text
Fine-grained Personal Access Token
```

또는 장기적으로:

```text
GitHub App
```

Token을 코드에 하드코딩하지 않는다.

GitHub Actions Secret 또는 `.env`를 사용한다.

---

# 24. GitHub Token 보호

다음 값은 Git에 Commit하지 않는다.

```text
GITHUB_TOKEN
GITHUB_PAT
CLAUDE_API_KEY
OPENAI_API_KEY
PRIVATE_KEY
```

`.env.example`만 Repository에 포함한다.

---

# 25. README SHA 변경 감지

현재 README SHA를 저장하여 변경 여부를 판단하는 구조가 있다면 유지한다.

예:

```text
README SHA 변경 없음
→ Skip

README SHA 변경
→ Update
```

추가로 `portfolio.yml` SHA도 관리한다.

예:

```json
{
  "repo": "pacer",
  "readmeSha": "...",
  "portfolioSha": "..."
}
```

둘 중 하나라도 변경되면 프로젝트 Metadata를 갱신한다.

---

# 26. 프로젝트 삭제/비공개 대응

기존 프로젝트 Repository가 삭제되거나 Private으로 변경되어 읽을 수 없는 경우 프로젝트 기록을 즉시 삭제하지 않는다.

다음과 같이 상태를 유지한다.

```text
lastKnownData
syncStatus: unavailable
```

관리자가 확인 후 삭제하도록 한다.

포트폴리오 역사 기록을 자동으로 잃지 않도록 한다.

---

# 27. Metadata Validation

`portfolio.yml`을 읽을 때 Validation을 수행한다.

예:

필수:

```text
title
status
```

조건부 필수:

```text
status == unused
→ unused_reason 권장 또는 필수

status == completed
→ ended 권장

status == active
→ ended 비워둠
```

지원되지 않는 status 값은 Warning을 출력한다.

---

# 28. Project Slug

프로젝트마다 안정적인 slug를 사용한다.

예:

```yaml
slug: pacer
```

없으면 Repository Name 또는 Title을 기반으로 생성한다.

Slug는 URL, Screenshot Path, DOM ID 등에 사용한다.

---

# 29. UI 디자인 원칙

현재 dounselor.com의 전체 디자인 정체성을 크게 훼손하지 않는다.

하지만 프로젝트 영역은 더 명확한 정보 계층을 갖도록 개선한다.

핵심:

```text
현재 중요한 프로젝트
↓
크고 시각적으로 표현

일반 프로젝트
↓
간결하게

미사용 / 종료 프로젝트
↓
기록 중심으로 최소 표현
```

---

# 30. 미사용 프로젝트 디자인

미사용 프로젝트는 시각적으로 너무 부정적으로 표현하지 않는다.

예:

```text
Unused
Archived
Retired
```

등의 차분한 Badge를 사용할 수 있다.

다만 사이트 기본 언어가 한국어 중심이라면:

```text
미사용
운영 종료
아카이브
```

등 자연스러운 표현을 사용한다.

---

# 31. 프로젝트 예시 - Blog

향후 현재 Blog 프로젝트가 Personal Archive로 대체되는 경우 다음 Metadata를 사용할 수 있다.

```yaml
title: Dounselor Blog

slug: dounselor-blog

status: unused

started: 2026-01
ended: 2026-10

unused_reason: >
  기존 독립형 Blog 서비스 대신 Personal Archive 내부의 Journal 기능으로
  기록 시스템을 통합하기로 결정하여 기존 프로젝트는 운영을 종료함.

replaced_by:
  title: Personal Archive
  url: https://archive.dounselor.com

featured: false
```

화면에서는 다음 정도만 보여준다.

```text
Dounselor Blog

2026.01 - 2026.10

운영 종료

Personal Archive의 Journal 기능으로 통합하여
기존 독립형 블로그 운영을 종료함.

→ Personal Archive
```

---

# 32. 프로젝트 예시 - 중간에 포기한 프로젝트

개발을 시작했지만 실제 사용하지 않은 경우:

```yaml
title: Sample Automation Tool

status: unused

started: 2025-11
ended: 2025-12

unused_reason: >
  초기 프로토타입까지 구현했으나 실제 사용 흐름에서 효용이 낮아
  정식 서비스로 발전시키지 않음.
```

화면:

```text
Sample Automation Tool

2025.11 - 2025.12

미사용

프로토타입까지 구현했으나 실제 활용성이 낮아
정식 서비스로 확장하지 않음.
```

이러한 프로젝트도 삭제하지 않고 기록으로 남긴다.

---

# 33. 프로젝트를 실패 여부로 평가하지 않는다

unused / archived는 실패를 의미하지 않는다.

프로젝트를 삭제하는 대신 다음과 같은 이유를 기록하여 개발 히스토리를 남긴다.

예:

```text
다른 시스템으로 통합
활용성 부족
중복 기능 존재
기술적 실험 종료
업무 우선순위 변경
더 나은 대안으로 전환
서비스 목적 달성
```

이를 통해 Portfolio가 단순 결과물 전시가 아니라 개발 여정을 보여줄 수 있도록 한다.

---

# 34. 검색 및 필터

프로젝트가 많아지면 다음 Filter를 지원할 수 있도록 한다.

```text
All
Active
Completed
Paused
Unused
Archived
```

추가로 Category Filter:

```text
Web
AI
Infrastructure
Automation
Mobile
Personal
```

초기 MVP에서는 Status Filter만 구현해도 된다.

---

# 35. SEO

Project Metadata에 다음 정보를 활용한다.

```text
title
subtitle
summary
```

Public 프로젝트에 대해서만 SEO Metadata를 제공한다.

Unused 프로젝트도 검색엔진에 노출할지 여부를 옵션화할 수 있다.

예:

```yaml
indexable: false
```

---

# 36. 프로젝트 상세페이지 확장

현재는 메인 페이지 내 프로젝트 Accordion 구조를 유지해도 된다.

다만 장기적으로 다음 구조로 확장 가능하도록 데이터 모델을 설계한다.

```text
/projects
/projects/pacer
/projects/personal-archive
```

이번 개선에서 상세 페이지가 필수는 아니다.

---

# 37. Sync Script 역할

Sync Script는 다음 역할에 집중한다.

```text
Repository 목록 조회
↓
portfolio.yml 조회
↓
README 조회
↓
변경 감지
↓
Metadata 정규화
↓
Validation
↓
projects.generated.json 생성
```

HTML 디자인 로직은 최대한 Frontend로 이동한다.

---

# 38. Error Handling

각 프로젝트 Sync 오류가 전체 Sync 실패로 이어지지 않도록 한다.

예:

```text
Pacer → 성공
Life Manager → 성공
Blog → README 오류
Archive → 성공
```

이 경우 Blog만 기존 데이터를 유지하고 나머지는 갱신할 수 있어야 한다.

최종적으로 오류 목록을 출력한다.

---

# 39. Dry Run

실제 파일을 수정하거나 Push하지 않고 결과를 확인할 수 있도록 한다.

예:

```bash
python scripts/sync_projects.py --dry-run
```

Dry Run 결과:

```text
3 projects changed
1 project unchanged
1 warning

No files were committed.
```

---

# 40. Preview Mode

가능하면 Sync 후 브라우저에서 로컬 Preview를 확인할 수 있도록 한다.

예:

```text
python -m http.server
```

또는 기존 프로젝트 구조에 적합한 간단한 Preview 방식 사용.

Mac 실행 파일에서 다음 옵션을 제공할 수 있다.

```text
1. Preview only
2. Update and Push
3. Cancel
```

초기 버전에서는 CLI 선택 방식도 가능하다.

---

# 41. 자동 Commit

Sync 결과 실제 변경사항이 있을 때만 Commit한다.

예:

```text
chore: sync portfolio projects
```

변경이 없으면 Commit하지 않는다.

---

# 42. Push 안전 규칙

Push 전에 다음을 확인한다.

```text
git status
git diff --cached
```

Secret이나 불필요한 대용량 파일이 포함되지 않았는지 확인한다.

기본적으로 현재 정상 운영 중인 Branch 전략을 따른다.

---

# 43. Log

Sync 실행 결과를 로그로 남길 수 있도록 한다.

예:

```text
logs/portfolio-sync.log
```

단 로그 파일이 Git에 Commit되지 않도록 한다.

기록 예:

```text
2026-09-30 03:00
Checked: 12
Updated: 3
Skipped: 8
Failed: 1
```

---

# 44. README 문서화

사이트 Repository README에 다음을 자세히 작성한다.

```text
전체 구조
Project Sync 방식
portfolio.yml 작성법
Project Status 정의
unused 프로젝트 작성법
Mac 수동 업데이트
Mac 자동 업데이트
GitHub Actions
Token 설정
Screenshot 기능
Dry Run
Troubleshooting
```

---

# 45. portfolio.yml Template 제공

Repository에 다음 파일을 제공한다.

```text
docs/portfolio.template.yml
```

예:

```yaml
title:
slug:

subtitle:

status: active

started:
ended:

category: []

featured: false

live_url:
repository_url:

summary:

tech: []

highlights: []

unused_reason:

replaced_by:
  title:
  url:

cover:
  image:

screenshot_refresh: false

indexable: true
```

---

# 46. Migration 지원

현재 기존 프로젝트 정보를 한번에 모두 수정하도록 강제하지 않는다.

다음 방식으로 동작한다.

```text
portfolio.yml 있음
→ 새 Metadata 시스템

portfolio.yml 없음
→ 기존 README Parser 방식
```

따라서 기존 프로젝트가 깨지지 않고 점진적으로 전환 가능해야 한다.

---

# 47. 구현 단계

## Phase 1 - 분석

- 기존 코드 분석
- 기존 Sync Workflow 확인
- 기존 HTML 생성 방식 확인
- 위험요소 정리

## Phase 2 - Metadata

- portfolio.yml Parser
- Status 체계
- Validation
- unused 프로젝트 지원

## Phase 3 - JSON 분리

- projects.generated.json
- Frontend Renderer
- 기존 HTML 자동 생성 의존 축소

## Phase 4 - UI 개선

- Featured
- Active
- Completed
- Unused/Archived
- Live Demo
- Status Filter

## Phase 5 - Mac Updater

- `.command`
- Dry Run
- Preview
- Update & Push

## Phase 6 - Screenshot

- Playwright
- Desktop
- Mobile

## Phase 7 - Automation

- launchd
- GitHub Actions
- repository_dispatch 확장 준비

---

# 48. 각 Phase 검증

각 Phase 완료 후 반드시 다음을 확인한다.

```text
기존 사이트 정상 동작
README 기반 기존 프로젝트 정상 표시
portfolio.yml 프로젝트 정상 표시
unused 프로젝트 간단 표시
Active 프로젝트 상세 표시
JSON 생성 정상
브라우저 Console Error 없음
Mobile Layout 정상
Git Diff 검토
```

---

# 49. Git 원칙

기존 Git History를 보존한다.

무리한 Rewrite를 하지 않는다.

각 Phase별 Commit을 생성한다.

예:

```text
feat: add portfolio metadata schema

feat: add project lifecycle statuses

feat: add generated project data layer

feat: improve project portfolio interface

feat: add mac portfolio updater

feat: add project screenshot automation

ci: add portfolio sync workflow
```

사용자의 명시적인 요청 없이 Force Push하지 않는다.

---

# 50. 최종 목표

최종적으로 다음 개발 경험을 제공한다.

프로젝트 Repository에서:

```text
README 작성
+
portfolio.yml 작성
```

그러면:

```text
GitHub Push
↓
변경 감지
↓
Portfolio Metadata 생성
↓
dounselor.com 프로젝트 갱신
```

그리고 프로젝트가 더 이상 사용되지 않는다면:

```yaml
status: unused

ended: 2026-10

unused_reason: >
  Personal Archive Journal 기능으로 통합하여 기존 서비스를 종료함.
```

만 수정하면:

```text
Dounselor Blog
2026.01 - 2026.10
운영 종료
Personal Archive로 통합
```

형태로 자동 전환된다.

---

# 51. 가장 중요한 철학

이 Portfolio는 "현재 사용 중인 완성된 프로젝트만 보여주는 전시장"이 아니다.

현재 사용하는 프로젝트,
완료된 프로젝트,
중단된 프로젝트,
대체된 프로젝트,
실험 후 사용하지 않은 프로젝트까지

**개발 과정 전체를 기록하는 개인 Project Archive**로 발전시키는 것을 목표로 한다.

따라서 프로젝트가 더 이상 사용되지 않는다고 해서 기록을 삭제하지 않는다.

대신:

```text
무엇을 만들었는지
언제 만들었는지
왜 더 이상 사용하지 않는지
무엇으로 대체되었는지
```

를 간결하게 남긴다.

특히 `unused` 프로젝트는 긴 설명 대신:

```text
Title
Period
Unused Reason
Replacement (optional)
```

만 보여주는 것을 기본 원칙으로 한다.

---
