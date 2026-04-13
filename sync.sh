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

# GitHub Token 로드
if [ -z "$GITHUB_TOKEN" ]; then
  if [ -f ".env" ]; then
    export $(grep GITHUB_TOKEN .env | xargs)
  fi
fi

if [ -z "$GITHUB_TOKEN" ]; then
  echo "❌  GITHUB_TOKEN이 없습니다."
  echo "   방법 1: export GITHUB_TOKEN=ghp_xxxx && ./sync.sh"
  echo "   방법 2: scripts/.env 파일에 GITHUB_TOKEN=ghp_xxxx 저장 후 실행"
  exit 1
fi

echo "🔄  Portfolio 동기화 시작..."
python3 scripts/sync_projects.py --obsidian ~/Workspace/MyNotes "$@"

echo ""

# 변경사항 있으면 자동 커밋/푸시
if ! git diff --quiet index.html scripts/projects.json 2>/dev/null; then
  echo "🚀  변경 감지 → 자동 커밋 & 푸시..."
  git add index.html scripts/projects.json
  git commit -m "sync: update projects $(date '+%Y-%m-%d')"
  git push
  echo "✅  완료! kimmydkemf.github.io 에 반영됩니다."
else
  echo "✅  변경 없음 — 푸시 생략."
fi
