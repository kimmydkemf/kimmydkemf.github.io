#!/bin/bash
# Finder 에서 더블클릭하면 Terminal 에서 포트폴리오 업데이트 메뉴가 열린다.
# 실제 로직: scripts/portfolio_update.sh
# 처음 한 번: 우클릭 → 열기 (Gatekeeper 확인), 실행 권한이 없으면 chmod +x "Update Portfolio.command"

cd "$(dirname "$0")" || exit 1
/bin/bash scripts/portfolio_update.sh "$@"
status=$?

echo ""
if [ $status -eq 0 ]; then
  echo "끝났습니다. 로그: logs/portfolio-sync.log"
else
  echo "오류로 종료되었습니다 (code $status). 위 메시지를 확인하세요. 로그: logs/portfolio-sync.log"
fi
# 창이 바로 닫히지 않도록 대기
printf 'Enter 를 누르면 창을 닫습니다...'
read -r _
exit $status
