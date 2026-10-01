#!/bin/bash
# ── macOS launchd 로 포트폴리오 업데이터 자동 실행 ───────────────────────────
# ~/Library/LaunchAgents/com.dounselor.portfolio-sync.plist 를 만들고 등록한다.
#
#   scripts/install_launchd.sh install                     # 매일 03:00, dry-run (기록만, 변경 없음)
#   scripts/install_launchd.sh install --mode update       # 매일 03:00, sync → commit → push (확인 없이)
#   scripts/install_launchd.sh install --hour 7 --minute 30 --at-login
#   scripts/install_launchd.sh status                      # 등록 여부 · 마지막 실행 로그
#   scripts/install_launchd.sh run                         # 지금 한 번 실행 (등록된 설정으로)
#   scripts/install_launchd.sh uninstall                   # 해제 + plist 삭제
#   scripts/install_launchd.sh print [옵션]                # 등록하지 않고 plist 내용만 출력
#
# 메모:
#   - Mac 이 잠자기 중이면 그 시각 실행은 건너뛰고, 깨어난 뒤 한 번 실행된다 (launchd 동작).
#   - update 모드는 현재 체크아웃된 브랜치에 push 한다. GitHub Actions 도 켜 두었다면 둘 중 하나만
#     push 하도록 하는 것을 권장 (Mac 은 dry-run, Actions 가 반영).
#   - push 는 Terminal 과 같은 git 인증(SSH 키 / credential helper)을 쓴다. 암호가 걸린 SSH 키는
#     launchd 에서 입력할 수 없으니 키체인에 저장해 두어야 한다 (ssh-add --apple-use-keychain).
#   - 로그: logs/launchd.log (stdout/stderr), logs/portfolio-sync.log (요약)
# ─────────────────────────────────────────────────────────────────────────────
set -u

LABEL="com.dounselor.portfolio-sync"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS_DIR="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"     # 테스트에서 바꿀 수 있음
PLIST="$AGENTS_DIR/$LABEL.plist"
DOMAIN="gui/$(id -u)"

CMD="${1:-}"; [ $# -gt 0 ] && shift
MODE="dry-run"; HOUR=3; MINUTE=0; AT_LOGIN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --mode)     MODE="${2:-}"; shift 2 ;;
    --hour)     HOUR="${2:-}"; shift 2 ;;
    --minute)   MINUTE="${2:-}"; shift 2 ;;
    --at-login) AT_LOGIN=1; shift ;;
    *) echo "알 수 없는 옵션: $1" >&2; exit 2 ;;
  esac
done

case "$MODE" in dry-run|update) ;; *) echo "--mode 는 dry-run 또는 update" >&2; exit 2 ;; esac
case "$HOUR" in ''|*[!0-9]*) echo "--hour 는 0-23" >&2; exit 2 ;; esac
case "$MINUTE" in ''|*[!0-9]*) echo "--minute 는 0-59" >&2; exit 2 ;; esac
[ "$HOUR" -le 23 ] && [ "$MINUTE" -le 59 ] || { echo "시각 범위 오류" >&2; exit 2; }

xml_escape() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }

render_plist() {
  local repo args path extra=""
  repo="$(xml_escape "$REPO")"
  args="    <string>/bin/bash</string>
    <string>$repo/scripts/portfolio_update.sh</string>
    <string>--mode</string>
    <string>$MODE</string>"
  [ "$MODE" = "update" ] && args="$args
    <string>--yes</string>"
  # launchd 는 PATH 가 최소한이라 Homebrew python3 (3.10+) 를 찾도록 경로를 넣는다
  path="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
  [ "$AT_LOGIN" = "1" ] && extra="
  <key>RunAtLoad</key>
  <true/>"
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
$args
  </array>
  <key>WorkingDirectory</key>
  <string>$repo</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>$HOUR</integer>
    <key>Minute</key>
    <integer>$MINUTE</integer>
  </dict>$extra
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>$path</string>
    <key>LANG</key>
    <string>ko_KR.UTF-8</string>
    <key>PORTFOLIO_NO_OPEN</key>
    <string>1</string>
  </dict>
  <key>StandardOutPath</key>
  <string>$repo/logs/launchd.log</string>
  <key>StandardErrorPath</key>
  <string>$repo/logs/launchd.log</string>
  <key>ProcessType</key>
  <string>Background</string>
</dict>
</plist>
EOF
}

do_launchctl() {  # 테스트에서는 PORTFOLIO_LAUNCHD_NO_LOAD=1 로 실제 등록을 막는다
  if [ -n "${PORTFOLIO_LAUNCHD_NO_LOAD:-}" ]; then echo "(launchctl $* — 생략)"; return 0; fi
  launchctl "$@"
}

case "$CMD" in
  print)
    render_plist ;;
  install)
    mkdir -p "$AGENTS_DIR" "$REPO/logs"
    tmp="$(mktemp -t portfolio-plist.XXXXXX)"
    render_plist > "$tmp"
    plutil -lint "$tmp" >/dev/null || { echo "plist 검증 실패" >&2; rm -f "$tmp"; exit 1; }
    if [ -f "$PLIST" ]; then do_launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true; fi
    mv "$tmp" "$PLIST"
    chmod 644 "$PLIST"
    do_launchctl bootstrap "$DOMAIN" "$PLIST" || { echo "launchctl bootstrap 실패" >&2; exit 1; }
    printf '등록 완료: %s\n  매일 %02d:%02d · 모드 %s%s\n  로그: %s/logs/launchd.log\n' \
      "$PLIST" "$HOUR" "$MINUTE" "$MODE" "$([ "$AT_LOGIN" = 1 ] && echo ' · 로그인 시에도 실행')" "$REPO"
    if [ "$MODE" = "update" ]; then
      echo "  ⚠ update 모드: 확인 없이 commit & push 합니다 (현재 브랜치: $(git -C "$REPO" rev-parse --abbrev-ref HEAD))."
    fi
    ;;
  uninstall)
    if [ -f "$PLIST" ]; then
      do_launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true
      rm -f "$PLIST"
      echo "해제 완료: $PLIST 삭제"
    else
      echo "등록되어 있지 않습니다 ($PLIST 없음)"
    fi ;;
  status)
    if [ -f "$PLIST" ]; then
      echo "plist: $PLIST"
      /usr/libexec/PlistBuddy -c "Print :ProgramArguments" "$PLIST" 2>/dev/null | sed 's/^/  /'
      if [ -z "${PORTFOLIO_LAUNCHD_NO_LOAD:-}" ]; then
        launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E 'state =|last exit code' | sed 's/^[[:space:]]*/  /' \
          || echo "  (launchd 에 로드되어 있지 않음)"
      fi
    else
      echo "등록되어 있지 않습니다."
    fi
    if [ -f "$REPO/logs/portfolio-sync.log" ]; then echo "최근 실행:"; tail -5 "$REPO/logs/portfolio-sync.log" | sed 's/^/  /'; fi ;;
  run)
    [ -f "$PLIST" ] || { echo "먼저 install 하세요." >&2; exit 1; }
    do_launchctl kickstart -k "$DOMAIN/$LABEL" && echo "실행 요청함 — 로그: $REPO/logs/launchd.log" ;;
  *)
    sed -n '2,22p' "$0"; exit 2 ;;
esac
