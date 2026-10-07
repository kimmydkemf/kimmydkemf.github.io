#!/bin/bash
# ── CI 용 포트폴리오 동기화 (GitHub Actions 에서 실행) ────────────────────────
# .github/workflows/sync-projects.yml 이 호출한다. 로컬에서도 테스트할 수 있다 (scripts/test_ci_sync.py).
#
# 동작:
#   1. 토큰 확인 (PORTFOLIO_PAT → GITHUB_TOKEN 으로 전달. 값은 출력하지 않음)
#   2. scripts/portfolio_update.sh --mode update --yes --no-push --no-pull
#        sync → Screenshot → Validation → 산출물만 commit (변경 없으면 commit 없음)
#   3. 반영
#        SYNC_MODE=pr-auto (기본) 자동 브랜치(SYNC_BRANCH) 에 push → PR 생성/갱신 → 바로 병합 (기록은 PR 로 남고 사이트는 즉시 반영)
#                          병합이 안 되면(충돌 · 권한) PR 을 열어 두고 요약에 남긴다
#        SYNC_MODE=pr      PR 생성/갱신만 하고 병합은 사람이 한다
#                          PR 생성이 막혀 있으면 브랜치만 push 하고 비교 링크를 남긴다
#        SYNC_MODE=push    기본 브랜치에 바로 push (PR 없음)
#        SYNC_MODE=dry-run dry-run 결과만 출력
#
# 환경변수:
#   PORTFOLIO_PAT     필수 — 본인 레포 읽기용 Fine-grained PAT (Actions secret)
#   SYNC_MODE         pr-auto | pr | push | dry-run   (기본 pr-auto)
#   SYNC_BRANCH       PR 모드 자동 브랜치           (기본 automation/portfolio-sync)
#   BASE_BRANCH       반영 대상                     (기본: 현재 체크아웃 브랜치)
#   SYNC_FORCE=true   sync --force
#   SYNC_SCREENSHOTS  0 이면 Screenshot 생략
#   GITHUB_STEP_SUMMARY  (Actions 가 제공) 실행 요약 파일
#   GITHUB_REPOSITORY / GITHUB_SERVER_URL  (Actions 가 제공) 링크 생성용
# ─────────────────────────────────────────────────────────────────────────────
set -u
set -o pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1

SYNC_MODE="${SYNC_MODE:-pr-auto}"
SYNC_BRANCH="${SYNC_BRANCH:-automation/portfolio-sync}"
BASE_BRANCH="${BASE_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/null}"
REPO_SLUG="${GITHUB_REPOSITORY:-}"
SERVER="${GITHUB_SERVER_URL:-https://github.com}"

CI_LOG="$(mktemp -t portfolio-ci.XXXXXX)"
trap 'rm -f "$CI_LOG"' EXIT

summary() { echo "$*" >> "$SUMMARY"; echo "$*"; }
die() { summary "❌ $*"; exit 1; }

case "$SYNC_MODE" in pr-auto|pr|push|dry-run) ;; *) die "SYNC_MODE 는 pr-auto | pr | push | dry-run 중 하나여야 합니다 (현재: $SYNC_MODE)";; esac
AUTOMERGE=0; [ "$SYNC_MODE" = "pr-auto" ] && AUTOMERGE=1

# ── 1. 토큰 ──────────────────────────────────────────────────────────────────
if [ -z "${PORTFOLIO_PAT:-}" ]; then
  die "PORTFOLIO_PAT secret 이 없습니다. Settings → Secrets and variables → Actions 에 Fine-grained PAT 를 등록하세요 (README 'GitHub Actions' 참고). 기본 GITHUB_TOKEN 으로는 private 레포를 읽을 수 없어 실행하지 않습니다."
fi
if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::add-mask::$PORTFOLIO_PAT"; fi
export GITHUB_TOKEN="$PORTFOLIO_PAT"     # sync_projects.py 가 읽는 이름 (이 프로세스 안에서만)
unset PORTFOLIO_PAT

git config user.name  >/dev/null 2>&1 || git config user.name  "github-actions[bot]"
git config user.email >/dev/null 2>&1 || git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

ARGS="--yes --no-pull"
[ "${SYNC_FORCE:-}" = "true" ] && ARGS="$ARGS --force"
[ "${SYNC_SCREENSHOTS:-1}" = "0" ] && ARGS="$ARGS --no-screenshots"

summary "## Portfolio sync"
summary ""
summary "- 모드: \`$SYNC_MODE\` · 기준 브랜치: \`$BASE_BRANCH\`"

# ── dry-run ─────────────────────────────────────────────────────────────────
if [ "$SYNC_MODE" = "dry-run" ]; then
  # shellcheck disable=SC2086
  bash scripts/portfolio_update.sh --mode dry-run $ARGS | tee "$CI_LOG"
  rc=${PIPESTATUS[0]}
  summary "- 결과: $(grep -E '^Checked:' "$CI_LOG" | tail -1)"
  summary "- dry-run — 파일 변경 / commit 없음"
  exit "$rc"
fi

# ── 2. sync + commit (push 는 아래에서) ──────────────────────────────────────
BEFORE="$(git rev-parse HEAD)"
if [ "$SYNC_MODE" = "pr" ] || [ "$SYNC_MODE" = "pr-auto" ]; then
  git checkout -q -B "$SYNC_BRANCH" || die "브랜치 생성 실패: $SYNC_BRANCH"
fi
# shellcheck disable=SC2086
bash scripts/portfolio_update.sh --mode update --no-push $ARGS | tee "$CI_LOG"
rc=${PIPESTATUS[0]}
[ "$rc" -eq 0 ] || die "portfolio_update.sh 실패 (code $rc) — 위 로그 확인. 아무것도 push 하지 않았습니다."
summary "- 결과: $(grep -E '^Checked:' "$CI_LOG" | tail -1)"

AFTER="$(git rev-parse HEAD)"
if [ "$BEFORE" = "$AFTER" ]; then
  summary "- ✅ 변경 없음 — commit / push 하지 않음"
  exit 0
fi
summary "- commit: \`$(git log --oneline -1)\`"
summary ""
summary '```'
git --no-pager diff --stat "$BEFORE" "$AFTER" | tail -15 >> "$SUMMARY"
git --no-pager diff --stat "$BEFORE" "$AFTER" | tail -15
summary '```'

# ── 3. 반영 전 Secret 검사 — 패턴 + 실제 토큰 값이 어떤 파일에도 없는지 ─────
if ! python3 scripts/validate_site.py --scan-repo; then
  die "Secret 검사 실패 — push 하지 않았습니다."
fi
summary "- 🔒 Secret 검사 통과"

# ── 4. 반영 ──────────────────────────────────────────────────────────────────
if [ "$SYNC_MODE" = "push" ]; then
  git push origin "HEAD:$BASE_BRANCH" || die "push 실패 — 다른 commit 이 먼저 들어왔을 수 있습니다. 다음 실행에서 다시 시도됩니다."
  summary "- 🚀 \`$BASE_BRANCH\` 에 push 완료"
  exit 0
fi

# PR 모드: 자동 브랜치는 이 워크플로 전용이라 매번 기준 브랜치 + 최신 sync 1 commit 으로 덮어쓴다
git push --force origin "HEAD:refs/heads/$SYNC_BRANCH" || die "자동 브랜치 push 실패: $SYNC_BRANCH"
summary "- 자동 브랜치 \`$SYNC_BRANCH\` 갱신"

TITLE="chore: sync portfolio projects ($(date '+%Y-%m-%d'))"
BODY="GitHub Actions 가 자동 생성한 포트폴리오 동기화 PR 입니다.

- 실행 요약 / Validation 결과: Actions 실행 로그 참고
- 병합하면 GitHub Pages 에 반영됩니다.
- 이 브랜치(\`$SYNC_BRANCH\`) 는 다음 실행 때 덮어써집니다. 직접 수정하지 마세요.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"

if ! command -v gh >/dev/null 2>&1; then
  summary "- ⚠ gh CLI 없음 — PR 을 만들지 못했습니다. 직접 PR 을 여세요: $SERVER/$REPO_SLUG/compare/$BASE_BRANCH...$SYNC_BRANCH"
  exit 0
fi
pr_url=""
existing="$(gh pr list --head "$SYNC_BRANCH" --base "$BASE_BRANCH" --state open --json url --jq '.[0].url' 2>/dev/null || true)"
if [ -n "$existing" ]; then
  gh pr edit "$existing" --title "$TITLE" >/dev/null 2>&1 || true
  summary "- 🔁 기존 PR 갱신: $existing"
  pr_url="$existing"
elif url="$(gh pr create --head "$SYNC_BRANCH" --base "$BASE_BRANCH" --title "$TITLE" --body "$BODY" 2>&1)"; then
  summary "- 📝 PR 생성: $url"
  pr_url="$url"
else
  summary "- ⚠ PR 을 만들지 못했습니다 ($(echo "$url" | tail -1))."
  summary "  저장소 Settings → Actions → General → 'Allow GitHub Actions to create and approve pull requests' 를 켜거나,"
  summary "  직접 PR 을 여세요: $SERVER/$REPO_SLUG/compare/$BASE_BRANCH...$SYNC_BRANCH"
  exit 0
fi

# ── 5. 자동 병합 (pr-auto) ───────────────────────────────────────────────────
[ "$AUTOMERGE" = "1" ] || exit 0
# PR 이 병합 가능 상태가 될 때까지 잠깐 기다린다 (GitHub 이 mergeable 을 계산하는 데 몇 초 걸림)
for i in 1 2 3 4 5 6 7 8 9 10; do
  state="$(gh pr view "$pr_url" --json mergeable --jq .mergeable 2>/dev/null || echo UNKNOWN)"
  [ "$state" != "UNKNOWN" ] && break
  sleep 3
done
if [ "$state" = "CONFLICTING" ]; then
  summary "- ⚠ 기준 브랜치와 충돌해 자동 병합하지 못했습니다. PR 에서 확인하세요: $pr_url"
  exit 0
fi
if gh pr merge "$pr_url" --merge --subject "$TITLE" >/dev/null 2>&1; then
  summary "- ✅ 자동 병합 완료 → \`$BASE_BRANCH\` (Pages 가 곧 배포합니다)"
  gh api -X DELETE "repos/$REPO_SLUG/git/refs/heads/$SYNC_BRANCH" >/dev/null 2>&1 || true
else
  summary "- ⚠ 자동 병합 실패 — PR 은 열려 있습니다: $pr_url"
  summary "  저장소 Settings → Actions → General → 'Allow GitHub Actions to create and approve pull requests' 가 켜져 있어야 하고, main 에 보호 규칙이 있으면 상태 검사를 통과해야 합니다."
fi
exit 0
