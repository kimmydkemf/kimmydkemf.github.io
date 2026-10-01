#!/bin/bash
# ── Dounselor Portfolio Updater ───────────────────────────────────────────────
# "Update Portfolio.command" (더블클릭) 가 이 스크립트를 실행한다. 터미널에서 직접 실행해도 된다.
#
# 흐름:  저장소 이동 → 환경 확인 → git pull --ff-only → 메뉴
#          1. Dry Run          파일 변경 없이 탐지만
#          2. Preview          임시 사본에 sync → 로컬 서버 → 브라우저 (저장소는 그대로)
#          3. Update & Push    sync → Validation → diff 확인 → (미리보기) → commit → push
#          4. Cancel
#
# 비대화형 (launchd 등, Phase 7):
#   scripts/portfolio_update.sh --mode dry-run
#   scripts/portfolio_update.sh --mode update --yes [--no-push]
#
# 옵션:
#   --mode dry-run|preview|update   메뉴 없이 바로 실행
#   --yes                           확인 질문에 모두 yes (update 모드용)
#   --no-push                       commit 까지만
#   --no-pull                       시작 시 git pull 생략
#   --force                         sync --force (SHA 무시 전체 재생성)
#   --no-screenshots                Screenshot 단계 생략
#   --refresh-screenshots           live_url 이 있는 모든 프로젝트 Screenshot 다시 캡처
#
# 환경변수 (.env 또는 셸):
#   GITHUB_TOKEN          필수 (private 레포 조회). .env 에서 읽는다
#   ANTHROPIC_API_KEY     선택 (Claude 로 README 요약)
#   OBSIDIAN_VAULT        선택 (지정 시 sync --obsidian)
#   PORTFOLIO_BRANCH      선택 (지정 시 이 브랜치에서만 update 허용)
#   PORTFOLIO_SYNC_ARGS   선택 (sync 에 추가 인자. 예: "--fixtures fixtures/repos" — 테스트용)
#   PORTFOLIO_NO_OPEN=1   Preview 에서 브라우저를 자동으로 열지 않음
#   PORTFOLIO_SCREENSHOTS=0  Screenshot 단계 생략 (--no-screenshots 와 같음)
#   PORTFOLIO_SCREENSHOT_ARGS 선택 (screenshot_projects.py 추가 인자. 예: "--max-age-days 7")
#   PORTFOLIO_LOG         로그 파일 경로 (기본: logs/portfolio-sync.log)
# ─────────────────────────────────────────────────────────────────────────────

set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO" || exit 1

export PYTHONIOENCODING=utf-8

# sync / screenshot 이 만들거나 바꾸는 파일 (이 경로들만 add 한다)
OUTPUT_FILES="index.html data/projects.generated.json data/projects.manual.json scripts/projects.json data/screenshots.json"
SHOT_DIR="assets/projects"
COMMIT_PREFIX="chore: sync portfolio projects"
LOG_FILE="${PORTFOLIO_LOG:-$REPO/logs/portfolio-sync.log}"

MODE=""
ASSUME_YES=0
DO_PUSH=1
DO_PULL=1
SYNC_FORCE=""
DO_SHOTS="${PORTFOLIO_SCREENSHOTS:-1}"
SHOT_REFRESH=""
SERVER_PID=""
TMP_DIR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --mode)    MODE="${2:-}"; shift 2 ;;
    --yes|-y)  ASSUME_YES=1; shift ;;
    --no-push) DO_PUSH=0; shift ;;
    --no-pull) DO_PULL=0; shift ;;
    --force)   SYNC_FORCE="--force"; shift ;;
    --no-screenshots)      DO_SHOTS=0; shift ;;
    --refresh-screenshots) SHOT_REFRESH="--refresh-all"; shift ;;
    -h|--help) sed -n '2,38p' "$0"; exit 0 ;;
    *) echo "알 수 없는 옵션: $1" >&2; exit 2 ;;
  esac
done

# ── 출력 / 로그 ────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
  C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'; C_BLU=$'\033[36m'; C_B=$'\033[1m'; C_0=$'\033[0m'
else
  C_RED=""; C_GRN=""; C_YEL=""; C_BLU=""; C_B=""; C_0=""
fi
step() { echo ""; echo "${C_B}${C_BLU}▶ $*${C_0}"; }
ok()   { echo "${C_GRN}✔ $*${C_0}"; }
warn() { echo "${C_YEL}⚠ $*${C_0}"; }
fail() { echo "${C_RED}✖ $*${C_0}" >&2; log "FAIL $*"; cleanup; exit 1; }

existing_outputs() {  # 실제로 존재하거나 git 이 추적 중인 산출물 경로만 (git add 오류 방지)
  local f out=""
  for f in $OUTPUT_FILES $SHOT_DIR; do
    if [ -e "$f" ] || git ls-files --error-unmatch -- "$f" >/dev/null 2>&1; then out="$out $f"; fi
  done
  echo "$out"
}

log() {
  mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || return 0
  printf '%s [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "${MODE:-menu}" "$*" >> "$LOG_FILE" 2>/dev/null || true
}

cleanup() {
  if [ -n "$SERVER_PID" ]; then kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; SERVER_PID=""; fi
  if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then rm -rf "$TMP_DIR"; TMP_DIR=""; fi
}
trap cleanup EXIT
trap 'echo ""; warn "중단됨"; cleanup; exit 130' INT TERM

confirm() {  # confirm "질문"  → 0 = yes
  if [ "$ASSUME_YES" = "1" ]; then echo "$1 [y/N] y (자동)"; return 0; fi
  if [ ! -t 0 ] && [ -z "${PORTFOLIO_ALLOW_PIPED_INPUT:-}" ]; then echo "$1 [y/N] n (비대화형)"; return 1; fi
  local ans
  printf '%s [y/N] ' "$1"
  read -r ans || ans=""
  case "$ans" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

# ── .env 로드 (허용된 키만, 값은 출력하지 않음) ─────────────────────────────────
load_env() {
  local f line key val
  for f in "$REPO/.env" "$REPO/scripts/.env"; do
    [ -f "$f" ] || continue
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line%$'\r'}"
      case "$line" in ''|\#*) continue ;; esac
      line="${line#export }"
      key="${line%%=*}"; val="${line#*=}"
      key="$(echo "$key" | tr -d ' ')"
      val="${val%%#*}"                                   # 뒤 주석
      val="$(echo "$val" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/")"
      case "$key" in
        GITHUB_TOKEN|ANTHROPIC_API_KEY|OBSIDIAN_VAULT|PORTFOLIO_BRANCH)
          # 셸에 이미 있으면 셸 값 우선
          if [ -z "$(eval "echo \${$key:-}")" ] && [ -n "$val" ]; then export "$key=$val"; fi ;;
      esac
    done < "$f"
  done
}

# ── 환경 확인 ──────────────────────────────────────────────────────────────────
check_env() {
  step "환경 확인"
  command -v git >/dev/null 2>&1 || fail "git 이 없습니다. Xcode Command Line Tools 를 설치하세요: xcode-select --install"
  PY="$(command -v python3 || true)"
  [ -n "$PY" ] || fail "python3 이 없습니다."
  "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
    || fail "Python 3.10 이상이 필요합니다 (현재: $("$PY" --version 2>&1))"
  ok "$("$PY" --version 2>&1) · $(git --version)"
  "$PY" -c 'import yaml' 2>/dev/null && ok "PyYAML 있음" || warn "PyYAML 없음 — 내장 파서 사용 (정상 동작)"

  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "$REPO 가 git 저장소가 아닙니다."
  BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  [ "$BRANCH" != "HEAD" ] || fail "detached HEAD 상태입니다. 브랜치를 체크아웃하세요."
  ok "저장소: $REPO"
  ok "브랜치: ${C_B}$BRANCH${C_0}  (push 대상: origin/$BRANCH)"
  [ "$BRANCH" = "main" ] || warn "GitHub Pages 는 main 을 배포합니다. $BRANCH 에 push 하면 사이트에는 main 병합 후 반영됩니다."

  load_env
  if [ -n "${GITHUB_TOKEN:-}" ]; then ok "GITHUB_TOKEN 설정됨"
  elif [ -n "${PORTFOLIO_SYNC_ARGS:-}" ] && echo "$PORTFOLIO_SYNC_ARGS" | grep -q -- '--fixtures'; then warn "GITHUB_TOKEN 없음 — fixtures 모드"
  else fail "GITHUB_TOKEN 이 없습니다. 저장소 루트 .env 에 GITHUB_TOKEN=... 을 저장하세요 (.env 는 git 에 올라가지 않음)."
  fi
  [ -n "${ANTHROPIC_API_KEY:-}" ] && ok "ANTHROPIC_API_KEY 설정됨 (Claude 요약)" || warn "ANTHROPIC_API_KEY 없음 — README 직접 파싱"
}

git_pull() {
  [ "$DO_PULL" = "1" ] || { warn "git pull 생략 (--no-pull)"; return 0; }
  step "git pull --ff-only"
  if [ -n "$(git status --porcelain -- $OUTPUT_FILES $SHOT_DIR)" ]; then
    warn "sync 산출물에 커밋되지 않은 변경이 있습니다:"
    git status --short -- $OUTPUT_FILES $SHOT_DIR
    fail "먼저 커밋하거나 되돌린 뒤 다시 실행하세요 (git restore / git clean 으로 정리)."
  fi
  if ! git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
    warn "$BRANCH 에 원격 추적 브랜치가 없어 pull 을 건너뜁니다 (git branch -u origin/<브랜치> 로 연결 가능)."
    return 0
  fi
  git pull --ff-only 2>&1 || fail "git pull 실패 — 로컬 커밋과 원격이 갈라졌거나 네트워크 문제입니다. 터미널에서 git status 를 확인하세요."
  ok "최신 상태"
}

sync_args() {
  local a="$SYNC_FORCE"
  [ -n "${OBSIDIAN_VAULT:-}" ] && a="$a --obsidian $OBSIDIAN_VAULT"
  [ -n "${PORTFOLIO_SYNC_ARGS:-}" ] && a="$a $PORTFOLIO_SYNC_ARGS"
  echo "$a"
}

run_sync() {  # run_sync [추가 인자...]  — 출력은 화면 + 로그 요약
  local out rc
  out="$(mktemp -t portfolio-sync.XXXXXX)"
  # shellcheck disable=SC2046
  "$PY" scripts/sync_projects.py $(sync_args) "$@" 2>&1 | tee "$out"
  rc=${PIPESTATUS[0]}
  log "sync rc=$rc $(grep -E '^Checked:' "$out" | tail -1)"
  rm -f "$out"
  return "$rc"
}

run_screenshots() {  # run_screenshots [추가 인자...] — 실패해도 계속 (경고만)
  if [ "$DO_SHOTS" = "0" ]; then warn "Screenshot 생략"; return 0; fi
  step "Screenshot (live_url 있는 프로젝트, 필요한 것만)"
  # shellcheck disable=SC2086
  "$PY" scripts/screenshot_projects.py $SHOT_REFRESH ${PORTFOLIO_SCREENSHOT_ARGS:-} "$@" 2>&1
  local rc=$?
  log "screenshots rc=$rc"
  [ $rc -eq 0 ] || warn "Screenshot 단계 오류 — 기존 Screenshot 을 유지하고 계속합니다."
  return 0
}

# ── 1. Dry Run ────────────────────────────────────────────────────────────────
do_dry_run() {
  step "Dry Run — 파일을 변경하지 않습니다"
  run_sync --dry-run
  local rc=$?
  [ $rc -eq 0 ] || warn "일부 프로젝트 처리 실패 (위 [ERROR] 참고)"
  [ "$DO_SHOTS" = "0" ] || { step "Screenshot 계획 (캡처하지 않음)"; "$PY" scripts/screenshot_projects.py --dry-run $SHOT_REFRESH ${PORTFOLIO_SCREENSHOT_ARGS:-} 2>&1; }
  echo ""
  ok "No files were changed or committed."
}

# ── 2. Preview (임시 사본) ────────────────────────────────────────────────────
free_port() { "$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'; }

serve_and_open() {  # serve_and_open DIR 설명
  local dir="$1" what="$2" port url
  port="$(free_port)"
  "$PY" -m http.server "$port" --bind 127.0.0.1 --directory "$dir" >/dev/null 2>&1 &
  SERVER_PID=$!
  url="http://127.0.0.1:$port/"
  local i=0
  while [ $i -lt 30 ]; do
    curl -fsS -o /dev/null "$url" 2>/dev/null && break
    sleep 0.2; i=$((i + 1))
  done
  if curl -fsS -o /dev/null "${url}data/projects.generated.json" 2>/dev/null; then
    ok "미리보기 서버: $url  ($what)"
  else
    warn "미리보기 서버 응답 확인 실패: $url"
  fi
  if [ -z "${PORTFOLIO_NO_OPEN:-}" ] && command -v open >/dev/null 2>&1; then open "$url#projects"; fi
  if [ "$ASSUME_YES" = "1" ] || { [ ! -t 0 ] && [ -z "${PORTFOLIO_ALLOW_PIPED_INPUT:-}" ]; }; then
    echo "(비대화형 — 미리보기 서버를 바로 종료합니다)"
  else
    printf '확인이 끝나면 Enter 를 누르세요 (서버 종료) '
    read -r _ || true
  fi
  kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; SERVER_PID=""
}

do_preview() {
  step "Preview — 임시 사본에 sync 합니다 (저장소 파일은 그대로)"
  TMP_DIR="$(mktemp -d -t portfolio-preview.XXXXXX)"
  mkdir -p "$TMP_DIR/data" "$TMP_DIR/scripts"
  cp index.html CNAME "$TMP_DIR/"
  cp -R assets "$TMP_DIR/"
  cp data/projects.generated.json data/projects.manual.json "$TMP_DIR/data/"
  [ -f data/screenshots.json ] && cp data/screenshots.json "$TMP_DIR/data/"
  cp scripts/projects.json "$TMP_DIR/scripts/"
  run_sync --index "$TMP_DIR/index.html" --config "$TMP_DIR/scripts/projects.json" \
           --generated "$TMP_DIR/data/projects.generated.json" --manual "$TMP_DIR/data/projects.manual.json"
  [ $? -eq 0 ] || warn "일부 프로젝트 처리 실패 (위 [ERROR] 참고)"
  run_screenshots --root "$TMP_DIR"
  step "Validation (미리보기 사본)"
  "$PY" scripts/validate_site.py --root "$TMP_DIR" --files index.html data/projects.generated.json \
    || warn "미리보기 사본이 Validation 을 통과하지 못했습니다. 이 상태로 Update 하면 commit 이 막힙니다."
  step "변경 요약 (현재 사이트 대비)"
  diff -q data/projects.generated.json "$TMP_DIR/data/projects.generated.json" >/dev/null \
    && ok "프로젝트 데이터 변경 없음" \
    || "$PY" - "$REPO/data/projects.generated.json" "$TMP_DIR/data/projects.generated.json" <<'PYEOF'
import json, sys
a = {p["slug"]: p for p in json.load(open(sys.argv[1], encoding="utf-8"))["projects"]}
b = {p["slug"]: p for p in json.load(open(sys.argv[2], encoding="utf-8"))["projects"]}
ign = {"lastSynced"}
added   = sorted(set(b) - set(a))
removed = sorted(set(a) - set(b))
changed = sorted(s for s in set(a) & set(b)
                 if {k: v for k, v in a[s].items() if k not in ign} != {k: v for k, v in b[s].items() if k not in ign})
print(f"  추가 {len(added)} · 변경 {len(changed)} · 제거 {len(removed)} · 유지 {len(set(a) & set(b)) - len(changed)}")
for s in added:   print(f"    + {b[s].get('title')}")
for s in changed:
    keys = sorted(k for k in set(a[s]) | set(b[s]) if k not in ign and a[s].get(k) != b[s].get(k))
    print(f"    ~ {b[s].get('title')}  ({', '.join(keys)})")
for s in removed: print(f"    - {a[s].get('title')}")
PYEOF
  serve_and_open "$TMP_DIR" "sync 결과 미리보기"
  cleanup
  ok "Preview 종료 — 저장소 파일은 변경되지 않았습니다."
}

# ── 3. Update & Push ──────────────────────────────────────────────────────────
restore_outputs() {
  local f
  for f in $OUTPUT_FILES $SHOT_DIR; do
    git ls-files --error-unmatch -- "$f" >/dev/null 2>&1 && git checkout -- "$f" 2>/dev/null
  done
  git clean -fdq -- $OUTPUT_FILES $SHOT_DIR 2>/dev/null   # sync/screenshot 이 새로 만든 파일만
}

do_update() {
  if [ -n "${PORTFOLIO_BRANCH:-}" ] && [ "$BRANCH" != "$PORTFOLIO_BRANCH" ]; then
    fail "PORTFOLIO_BRANCH=$PORTFOLIO_BRANCH 인데 현재 브랜치는 $BRANCH 입니다."
  fi
  if ! git diff --cached --quiet; then
    fail "이미 staged 된 변경이 있습니다. 섞이지 않도록 먼저 정리하세요 (git status)."
  fi

  step "Sync"
  run_sync
  local rc=$?
  [ $rc -eq 0 ] || warn "일부 프로젝트 처리 실패 — 실패한 프로젝트는 기존 데이터를 유지합니다."
  run_screenshots

  local changed
  changed="$(git status --porcelain -- $OUTPUT_FILES $SHOT_DIR)"
  if [ -z "$changed" ]; then
    ok "변경 없음 — commit 하지 않습니다."
    log "update: no changes"
    return 0
  fi

  step "Validation"
  local check_files
  check_files="$OUTPUT_FILES $(git ls-files -mo --exclude-standard -- $SHOT_DIR | tr '\n' ' ')"
  # shellcheck disable=SC2086
  if ! "$PY" scripts/validate_site.py --files $check_files; then
    warn "Validation 실패 — commit 하지 않습니다."
    if confirm "sync 로 바뀐 파일을 원래대로 되돌릴까요?"; then restore_outputs; ok "되돌렸습니다."; fi
    fail "Validation 실패"
  fi

  step "변경 파일"
  git status --short -uall -- $OUTPUT_FILES $SHOT_DIR
  git --no-pager diff --stat -- $OUTPUT_FILES $SHOT_DIR

  if [ "$ASSUME_YES" != "1" ] && confirm "브라우저에서 변경 결과를 미리 볼까요?"; then
    serve_and_open "$REPO" "저장소 작업본"
  fi

  if ! confirm "이 변경을 commit 할까요?"; then
    if confirm "sync 로 바뀐 파일을 원래대로 되돌릴까요?"; then restore_outputs; ok "되돌렸습니다."
    else warn "변경을 작업 트리에 남겨둡니다 (commit 안 함)."; fi
    log "update: commit declined"
    return 0
  fi

  step "Commit"
  # shellcheck disable=SC2046
  git add -A -- $(existing_outputs)
  local staged
  staged="$(git diff --cached --name-only)"
  echo "$staged" | sed 's/^/  /'
  # staged 목록이 산출물 파일로만 구성됐는지 확인
  local f
  for f in $staged; do
    case " $OUTPUT_FILES " in
      *" $f "*) ;;
      *) case "$f" in "$SHOT_DIR"/*) ;; *) git reset -q; fail "예상하지 못한 파일이 staged 됨: $f" ;; esac ;;
    esac
  done
  # staged diff 에 Secret 이 없는지 한 번 더
  if git diff --cached -U0 | grep -E '^\+' | "$PY" -c '
import sys; sys.path.insert(0, "scripts")
from validate_site import scan_secrets
hits = scan_secrets(sys.stdin.read())
print(", ".join(hits)); sys.exit(1 if hits else 0)'; then :; else
    git reset -q; fail "staged diff 에 Secret 패턴이 있습니다. commit 을 중단합니다."
  fi
  git commit -q -m "$COMMIT_PREFIX ($(date '+%Y-%m-%d'))" || fail "git commit 실패"
  ok "commit $(git log --oneline -1)"
  log "update: committed $(git rev-parse --short HEAD)"

  if [ "$DO_PUSH" != "1" ]; then warn "push 생략 (--no-push)"; return 0; fi
  if ! confirm "origin/$BRANCH 에 push 할까요?"; then
    warn "push 하지 않았습니다. 나중에: git push origin $BRANCH"
    return 0
  fi
  step "Push"
  git push origin "HEAD:$BRANCH" 2>&1 || fail "git push 실패 — commit 은 로컬에 남아 있습니다. 네트워크/권한 확인 후 git push 하세요."
  ok "push 완료 → origin/$BRANCH"
  log "update: pushed $(git rev-parse --short HEAD) to $BRANCH"
  [ "$BRANCH" = "main" ] && ok "GitHub Pages 반영까지 1~2분 정도 걸립니다: https://dounselor.com"
  return 0
}

# ── 메뉴 ──────────────────────────────────────────────────────────────────────
menu() {
  echo ""
  echo "${C_B}무엇을 할까요?${C_0}"
  echo "  1) Dry Run        — 변경 없이 탐지만"
  echo "  2) Preview        — 임시 사본으로 미리보기 (저장소 변경 없음)"
  echo "  3) Update & Push  — sync → 확인 → commit → push"
  echo "  4) Cancel"
  printf '선택 [1-4]: '
  local c
  read -r c || c="4"
  case "$c" in
    1) MODE="dry-run" ;;
    2) MODE="preview" ;;
    3) MODE="update" ;;
    *) MODE="cancel" ;;
  esac
}

echo "${C_B}── Dounselor Portfolio Updater ──${C_0}"
log "start"
check_env
git_pull

[ -n "$MODE" ] || menu
case "$MODE" in
  dry-run) do_dry_run ;;
  preview) do_preview ;;
  update)  do_update ;;
  cancel)  ok "취소했습니다." ;;
  *) fail "알 수 없는 모드: $MODE (dry-run | preview | update)" ;;
esac
log "done"
exit 0
