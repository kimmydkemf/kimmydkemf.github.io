# dounselor.com Portfolio — Claude Code Memory

## 이 파일의 역할

이 파일은 매 작업에서 항상 적용할 **짧은 상시 규칙**이다.
전체 요구사항은 `docs/PROJECT_SPEC.md`에 있다.

## 먼저 읽기

작업을 시작할 때:

1. `docs/PROJECT_SPEC.md`
2. `docs/DEVELOPMENT_RULES.md`
3. 사용자가 지정한 `docs/tasks/*.md`

를 읽는다.

## 기본 역할

Claude Code는 이 프로젝트의 주 구현 도구다.

```text
현재 Repo 분석
→ 지정된 Task만 구현
→ 검증
→ git status / git diff
→ 결과 보고
```

## 보안

회사 공유 Claude 계정을 사용한다.

다음 실제 개인 데이터는 읽거나 출력하지 않는다.

```text
.env / Secret / API Key / Token / Password / Private Key
개인 사진 / 가족 사진 / 실제 일기
개인 연락처 / 주소 / 계좌정보
/Volumes/ARCHIVE 실제 데이터
~/.ssh
개인 DB Dump
```

개발은 샘플 데이터로 한다.

## Git

기본적으로 Commit/Push하지 않는다.

사용자가 해당 작업에서 명시적으로 요청한 경우에만 수행한다.

Force Push, Hard Reset, 대량 삭제, DB 삭제는 사용자 확인 없이 하지 않는다.

## 구현 원칙

- 기존 정상 기능을 우선 보존한다.
- Task 범위 밖의 대규모 리팩터링을 하지 않는다.
- 코드 수정 후 프로젝트가 제공하는 검증을 실행한다.
- 실패한 검증을 숨기지 않는다.
- 임시 workaround가 있으면 보고한다.

## 완료 보고

```text
완료한 작업
변경한 주요 파일
실행한 검증
검증 결과
남은 문제
다음 권장 작업
```

## 프로젝트 핵심

현재 사이트를 새로 갈아엎는 것이 아니라 기존 자동화 구조의 장점을 유지하면서 장기적으로 관리하기 쉬운 Project Archive로 발전시킨다.
