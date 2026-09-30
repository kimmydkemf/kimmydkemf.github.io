# Tasks

이 폴더의 파일은 **작업 하나당 하나의 Worktree**를 만들기 위한 지시서입니다.

권장 순서:

1. `PHASE_01_ANALYZE.md`
2. `PHASE_02_METADATA.md`
3. `PHASE_03_JSON_LAYER.md`
4. `PHASE_04_UI.md`
5. `PHASE_05_MAC_UPDATER.md`
6. `PHASE_06_SCREENSHOT.md`
7. `PHASE_07_AUTOMATION.md`

## 사용법

Orca에서 새 Worktree를 만든 다음 Claude Code에게:

```text
CLAUDE.md,
docs/PROJECT_SPEC.md,
docs/DEVELOPMENT_RULES.md,
현재 Task 파일

을 읽고 이번 Task만 구현해.
검증 후 git diff를 요약하고 commit/push는 하지 마.
```

라고 지시합니다.

한 Task가 Merge된 뒤 다음 Task로 넘어가는 것을 기본으로 합니다.
