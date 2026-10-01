# 공통 프로젝트 개발 규칙

## 역할

### ChatGPT
- 아이디어 구체화
- 요구사항 정의
- 아키텍처 설계
- UI/UX 방향
- 데이터 구조
- Phase/Task 분리
- Claude/Codex용 작업지시서 작성
- 구현 결과 리뷰

### Claude Code
- 주 구현 도구
- 현재 Repository 분석
- 코드 작성/수정
- Build / Test / Docker
- 오류 재현 및 수정
- 작은 단위 리팩터링
- `git status`, `git diff` 확인

### Codex
- 기본 주 개발 도구로 사용하지 않음
- Claude Code가 반복적으로 실패한 문제
- 중요한 코드의 두 번째 리뷰
- 보안/데이터 손실 위험 검토
- 대안 구현 비교
- 제한된 Task 구현

---

# 개인 데이터 보호 규칙

Claude Code는 **소스코드 중심으로만 사용한다.**

다음 실제 개인 정보는 Claude Code가 읽거나 처리하지 않도록 한다.

```text
개인 사진
가족/지인 사진
실제 Journal/일기
청첩장 실데이터
전화번호
주소
계좌번호
실제 사용자 데이터
.env
API Key
Token
Password
Private Key
GitHub PAT
SSH Key
Database Dump
개인 외장 HDD의 실제 미디어
```

기능 개발에는 다음과 같은 샘플 데이터를 사용한다.

```text
demo/
fixtures/
sample-data/
```

---

# 접근 범위

Agent는 기본적으로 현재 Repository 내부만 작업한다.

임의로 다음 영역을 탐색하지 않는다.

```text
상위 디렉터리
~/Documents
~/Desktop
~/Pictures
~/.ssh
/Volumes/ARCHIVE
다른 Repository
```

필요한 외부 파일이 있으면 사용자가 명시적으로 제공한다.

---

# 개발 방식

```text
요구사항 확인
→ Repository 분석
→ 작은 Task 구현
→ Type/Lint
→ Build/Test
→ Runtime 확인
→ git diff 확인
→ 작업 결과 보고
```

한 번에 프로젝트 전체를 갈아엎지 않는다.

기존에 정상 동작하는 기능은 이유 없이 다시 작성하지 않는다.

작업 범위와 관계없는 대규모 리팩터링은 하지 않는다.

---

# Git 규칙

Claude Code의 기본 작업 범위:

```text
코드 수정
검증
git status
git diff
결과 설명
```

다음은 사용자가 그 Task에서 명시적으로 요청한 경우에만 한다.

```text
git add
git commit
git push
배포
main merge
```

다음은 사용자 확인 없이 하지 않는다.

```text
git push --force
git reset --hard
공개된 commit amend
branch 삭제
DB 삭제
대량 파일 삭제
운영환경 변경
공유 인프라 변경
```

Secret, 개인 미디어, DB 데이터는 Git에 올리지 않는다.

---

# 검증

가능한 검증을 직접 수행한다.

예:

```text
Type Check
Lint
Unit Test
Integration Test
Build
Docker Build
Docker Compose
Browser / Runtime Test
```

테스트 통과를 위해 기존 테스트를 삭제하거나 약화하지 않는다.

---

# 오류 처리

```text
오류 재현
→ 로그/코드 확인
→ 원인 설명
→ 최소 수정
→ 재검증
```

해결하지 못한 오류는 숨기지 않는다.

환경/인증/네트워크 문제라면 현재 완료 상태와 막힌 이유를 명확히 남긴다.

---

# 작업 완료 보고

각 Task 완료 후 아래 내용을 짧게 보고한다.

```text
1. 완료한 작업
2. 변경한 주요 파일
3. 실행한 검증
4. 검증 결과
5. 남은 문제
6. 다음 권장 작업
```

Commit을 실제로 수행한 경우에만:

```text
Commit Hash
Commit Message
Branch
```

도 추가한다.



# dounselor.com 추가 규칙

- 기존 공개 사이트가 정상 운영 중이라는 전제로 수정한다.
- 기존 Project 기록과 Git History를 임의 삭제하지 않는다.
- 자동 Sync 변경은 `--dry-run` 또는 이에 준하는 검증 수단을 우선 사용한다.
- GitHub Token/API Key는 코드나 생성 JSON에 포함하지 않는다.
- 자동 Commit/Push 기능은 실제 변경 여부와 Secret 포함 여부를 확인한 뒤 동작해야 한다.
