#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────────────────────
# run_sync.sh  —  GitHub Pages 프로젝트 자동 동기화 실행 스크립트
#
# 토큰은 scripts/.env 파일에 보관 (.gitignore 처리됨):
#   GITHUB_TOKEN=ghp_xxxx
#   ANTHROPIC_API_KEY=sk-ant-xxxx
# ───────────────────────────────────────────────────────────────────────────────

set -e

# .env 로드
ENV_FILE="$(dirname "$0")/.env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

# 필수 토큰 확인
if [[ -z "$GITHUB_TOKEN" ]]; then
  echo "[ERROR] GITHUB_TOKEN이 설정되지 않았습니다."
  echo "  scripts/.env 파일에 GITHUB_TOKEN=ghp_xxxx 를 추가하세요."
  exit 1
fi

if [[ -z "$ANTHROPIC_API_KEY" ]]; then
  echo "[INFO] ANTHROPIC_API_KEY 없음 → README 직접 파싱 모드로 실행"
  echo "       더 좋은 결과를 원하면 scripts/.env에 ANTHROPIC_API_KEY=sk-ant-xxx 추가"
  echo ""
fi

# 작업 디렉토리
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "========================================"
echo "  GitHub Pages 프로젝트 동기화"
echo "========================================"
echo ""

# 옵션 전달
GITHUB_TOKEN="$GITHUB_TOKEN" \
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
python3 scripts/sync_projects.py "$@"

# 변경 후 푸시 여부 확인 (dry-run이 아닌 경우)
if [[ "$*" != *"--dry-run"* ]]; then
  echo ""
  if git diff --quiet index.html scripts/projects.json 2>/dev/null; then
    echo "변경된 파일 없음."
  else
    echo "변경사항을 GitHub에 푸시하시겠습니까? (y/N)"
    read -r PUSH
    if [[ "$PUSH" =~ ^[Yy]$ ]]; then
      git add index.html scripts/projects.json
      git commit -m "sync: auto-update projects from GitHub repos"
      git push
      echo "푸시 완료."
    else
      echo "푸시 건너뜀."
    fi
  fi
fi
