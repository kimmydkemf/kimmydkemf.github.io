# sync PR 은 자동으로 병합한다 (pr-auto)

날짜: 2026-10-08

## 배경

Phase 7 (decision 006) 에서는 자동 sync 결과를 PR 로 만들고 병합은 사람이 하도록 했다. 일주일 동안 PR #9 가 열린 채로 매일 갱신만 되었고, 사용자는 병합도 자동으로 되기를 원했다. 같은 날 LineManager 레포는 사이트에 올리지 않기로 해 `excluded` 에 넣었다.

## 결정

1. `SYNC_MODE=pr-auto` 를 추가하고 기본값으로 한다. PR 을 만들거나 갱신한 뒤 mergeable 상태를 확인하고 바로 merge commit 으로 병합한다. 병합 후 자동 브랜치는 지운다.
2. 충돌(`CONFLICTING`)이거나 병합 호출이 실패하면 PR 을 열어 두고 실행 요약에 이유와 링크를 남긴다. 실행 자체는 성공으로 끝낸다.
3. 기존 `pr`(병합은 사람이), `push`, `dry-run` 모드는 그대로 둔다. 저장소 변수 `PORTFOLIO_SYNC_MODE` 로 바꿀 수 있다.
4. 공개하지 않을 레포는 `scripts/projects.json` 의 `excluded` 로 관리한다 (LineManager 추가).

## 영향

- 매일 03:00 KST 실행 뒤 몇 분 안에 사이트가 갱신된다. 기록은 PR 과 merge commit 으로 남는다.
- 자동 병합은 GitHub Actions 토큰으로 이뤄진다. main 에 보호 규칙을 추가하면 상태 검사 통과가 필요하다.
- Secret 검사와 Validation 은 push 전에 그대로 수행된다.

## 되돌릴 조건

- 잘못된 내용이 자동으로 올라가는 일이 생기면 `PORTFOLIO_SYNC_MODE=pr` 로 돌려 사람이 병합한다.
