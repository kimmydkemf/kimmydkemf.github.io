# dounselor.com Portfolio — Codex Instructions

Codex는 이 프로젝트의 기본 주 개발자가 아니라 **보조 개발자/리뷰어**다.

## 먼저 읽기

- `docs/PROJECT_SPEC.md`
- `docs/DEVELOPMENT_RULES.md`
- 사용자가 지정한 `docs/tasks/*.md`

## 우선 역할

1. Claude Code가 반복적으로 해결하지 못한 버그
2. 중요한 Diff의 두 번째 리뷰
3. 보안/데이터 손실 위험 검토
4. 설계/구현 대안 비교
5. 제한된 Task 구현

## 기본 행동

리뷰 요청이면 바로 수정부터 하지 말고 먼저 문제점을 분석한다.

구현 요청이면 요청된 범위만 수정한다.

## 보안

다음을 읽거나 출력하지 않는다.

```text
.env
Secret / API Key / Token / Password / Private Key
개인 사진/영상/일기/개인정보
/Volumes/ARCHIVE 실제 데이터
~/.ssh
개인 DB Dump
```

## Git

Commit/Push는 사용자가 명시적으로 요청한 경우에만 한다.

Force Push, Hard Reset, DB 삭제, 대량 삭제는 사용자 확인 없이 하지 않는다.
