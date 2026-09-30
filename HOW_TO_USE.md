# dounselor.com Portfolio — 실제 사용법

## 1. 이 폴더를 실제 Repository에 복사

최소 다음을 Repository 루트에 둡니다.

```text
CLAUDE.md
AGENTS.md
docs/
.claude/settings.local.json.example
```

## 2. 처음에는 Task 하나만 고르기

`docs/tasks/README.md`를 보고 다음에 할 Task를 하나 선택합니다.

## 3. Orca에서 Worktree 생성

예:

```text
task 이름: phase-01-analyze
start from: develop
agent: Claude Code
```

## 4. Claude에게 아래처럼 말하기

```text
CLAUDE.md를 읽고,
docs/PROJECT_SPEC.md,
docs/DEVELOPMENT_RULES.md,
docs/tasks/PHASE_01_ANALYZE.md
를 읽어줘.

이번 Task 범위만 구현해.
완료 후 가능한 검증을 수행하고 git diff를 요약해줘.
commit/push는 하지 마.
```

## 5. 끝나면 Orca Diff 확인

바로 Merge하지 말고 변경된 파일을 확인합니다.

## 6. 문제가 있을 때

먼저 같은 Claude Worktree에서 수정 요청합니다.

그래도 해결되지 않거나 중요한 변경이면 Codex용 별도 Worktree를 만들어 리뷰합니다.

## 7. Merge 후 다음 Task

현재 Worktree를 정리하고 다음 Task용 새 Worktree를 만듭니다.
