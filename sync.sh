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
echo "✅  완료! GitHub에 반영하려면:"
echo "   git add -A && git commit -m 'sync: update projects' && git push"
