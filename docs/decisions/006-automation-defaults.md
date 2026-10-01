# 자동화 기본값: Actions 는 PR, Mac 은 dry-run

날짜: 2026-10-01

## 배경

Phase 7 (GitHub Actions, launchd, repository_dispatch) 을 시작할 때 실행 시각, 반영 브랜치, Mac 자동 실행 방식이 결정되지 않았다. 사용자는 "진행해줘" 라고만 했으므로 안전한 기본값을 쓰고 모두 설정으로 바꿀 수 있게 했다.

## 결정

1. GitHub Actions: 매일 03:00 KST (`0 18 * * *`), 수동 실행, `repository_dispatch` (`portfolio-sync`).
2. 반영 기본값은 **PR** (`automation/portfolio-sync` → main). 저장소 변수 `PORTFOLIO_SYNC_MODE` 또는 수동 실행 입력으로 `push` / `dry-run` 을 고른다.
   자동 브랜치는 이 워크플로 전용이라 매 실행마다 기준 브랜치 + sync 1 commit 으로 **force push 로 덮어쓴다**. main 에는 force push 하지 않는다.
3. 저장소 설정에서 Actions 의 PR 생성이 꺼져 있으면 (현재 상태) 브랜치만 push 하고 비교 링크를 실행 요약에 남긴다.
4. 토큰: `PORTFOLIO_PAT` (본인 레포 Contents/Metadata 읽기) 를 env 로만 전달하고 마스킹한다. 없으면 실행하지 않는다. 기본 `GITHUB_TOKEN` 은 PR 생성에만 쓴다.
   push 직전에 저장소 전체를 대상으로 토큰 패턴과 실제 토큰 값을 검사한다.
5. Actions 에서도 Mac 과 같은 경로 (`portfolio_update.sh`) 를 써서 Validation · 산출물만 commit · Secret 재검사를 공유한다. sync 전에 테스트를 돌린다.
6. launchd: 설치 스크립트 기본값은 매일 03:00 **dry-run**. `--mode update` 로 바꿀 수 있다. Actions 와 Mac 이 동시에 push 하지 않도록 한 곳만 push 하기를 권장한다.
7. repository_dispatch 는 수신 트리거와 프로젝트 레포용 예시 파일까지만 만든다. 호출용 토큰은 프로젝트 레포에 따로 둔다.
8. 업데이터는 원격 추적 브랜치가 없으면 `git pull` 을 건너뛴다 (실패하지 않음).

## 영향

- 워크플로는 main 에 병합되기 전까지 schedule / dispatch 로 실행되지 않는다.
- Actions 실제 실행은 검증하지 못했다 (로컬에서 ci_sync.sh 를 bare 원격 + 가짜 gh 로 테스트). 첫 실행은 수동 실행 `dry-run` 으로 확인하기를 권장한다.

## 되돌릴 조건

- PR 검토가 번거로우면 `PORTFOLIO_SYNC_MODE=push`.
- Mac 에서만 운영하려면 workflow 의 `schedule` 을 지우고 launchd 를 `--mode update` 로 설치한다.
