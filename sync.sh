#!/bin/bash
# ── Dounselor Portfolio Sync ──────────────────────────────────────────
# 사용법:
#   ./sync.sh                          # 변경된 repo만 업데이트
#   ./sync.sh --force                  # 전체 재생성
#   ./sync.sh --dry-run                # 변경 없이 탐지만
#   ./sync.sh --obsidian ~/path/vault  # Obsidian md도 생성
# ─────────────────────────────────────────────────────────────────────

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Windows cp949 회피 — Python 출력 utf-8 강제 (sync_projects.py 의 stdout reconfigure 와 이중 안전)
export PYTHONIOENCODING=utf-8

# ※ 미리보기/확인 후 commit 하려면 "Update Portfolio.command" (scripts/portfolio_update.sh) 를 사용하세요.
#   이 스크립트는 기존과 같이 sync 후 변경이 있으면 바로 commit & push 합니다.

# GitHub Token / Anthropic Key 로드 (.env 또는 scripts/.env, 셸 값 우선, 허용된 키만)
for envfile in ".env" "scripts/.env"; do
  [ -f "$envfile" ] || continue
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"; line="${line#export }"
    case "$line" in
      GITHUB_TOKEN=*|ANTHROPIC_API_KEY=*)
        key="${line%%=*}"; val="${line#*=}"
        val="$(echo "$val" | sed -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/")"
        if [ -z "$(eval "echo \${$key:-}")" ] && [ -n "$val" ]; then export "$key=$val"; fi ;;
    esac
  done < "$envfile"
done

if [ -z "$GITHUB_TOKEN" ]; then
  echo "❌  GITHUB_TOKEN이 없습니다."
  echo "   방법 1: export GITHUB_TOKEN=ghp_xxxx && ./sync.sh"
  echo "   방법 2: 저장소 루트 .env (또는 scripts/.env) 에 GITHUB_TOKEN=ghp_xxxx 저장 후 실행"
  exit 1
fi

echo "🔄  Portfolio 동기화 시작..."
python3 scripts/sync_projects.py --obsidian ~/Workspace/MyNotes "$@"

echo ""

# 변경사항 있으면 자동 커밋/푸시
if ! git diff --quiet index.html data/projects.generated.json scripts/projects.json 2>/dev/null; then
  echo "🚀  변경 감지 → 자동 커밋 & 푸시..."
  git add index.html data/projects.generated.json scripts/projects.json
  git commit -m "sync: update projects $(date '+%Y-%m-%d')"
  git push
  echo "✅  완료! kimmydkemf.github.io 에 반영됩니다."
else
  echo "✅  변경 없음 — 푸시 생략."
fi
