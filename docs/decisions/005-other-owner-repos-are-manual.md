# 다른 사람 소유 레포는 읽지 않고 manual 데이터로 고정한다

날짜: 2026-10-01

## 배경

sync 는 `/user/repos?affiliation=owner,collaborator` 로 collaborator 레포까지 읽었다. 그 결과 다른 사람 소유 private 레포(`ghals5737/bcplus_legacy`)가 포트폴리오에 들어와 있었다.
Phase 7 의 GitHub Actions 는 Fine-grained PAT 를 쓸 예정인데, Fine-grained PAT 는 다른 사람 소유 레포에 접근할 수 없다. 사용자는 이런 레포를 굳이 읽지 말고 지금 내용을 그대로 쓰되, 상태만 직접 고치기를 원했다.

## 결정

1. sync 는 본인(`GITHUB_USER`) 소유 레포만 조회한다 (`affiliation=owner`, owner 재확인).
2. 다른 사람 소유 레포의 프로젝트는 `data/projects.manual.json` 에 둔다. `"repo"` 를 지정하면 sync 가 그 레포를 GitHub 에서 조회하지 않는다.
3. `bcplus_legacy` 항목을 기존 내용 그대로 manual 로 옮겼다. `status` 는 기존처럼 `null` 이라 화면은 바뀌지 않는다. 사용자는 `status` 만 고치면 된다.
4. manual 의 `status` 오타는 sync 가 경고하고, Update 의 Validation 이 commit 을 막는다.

## 영향

- Phase 7 Actions 는 Fine-grained PAT (본인 레포 Contents/Metadata 읽기) 만으로 충분하다.
- `scripts/projects.json` 캐시에서 `bcplus_legacy` 를 지웠다.
- 카드의 `data-source` 가 `github` 에서 `manual` 로 바뀐 것 외에 화면 변화는 없다.

## 되돌릴 조건

- 다른 사람 소유 레포도 자동 동기화가 필요해지면 Classic PAT 또는 GitHub App 을 쓰고, manual 항목에서 `repo` 를 지운다.
