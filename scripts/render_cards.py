#!/usr/bin/env python3
"""
render_cards.py — projects.generated.json 의 프로젝트 항목 → 정적 HTML 카드
=========================================================================
sync_projects.py 가 JSON 을 만든 뒤, JS 가 없는 환경(및 SEO)을 위해
index.html 의 AUTO:START ~ AUTO:END 구간에 넣을 정적 HTML 을 이 모듈로 생성한다.

assets/js/projects.js 는 같은 JSON 을 브라우저에서 동일한 마크업으로 렌더링한다.
두 렌더러의 출력은 scripts/test_sync_projects.py 의 parity 테스트로 비교된다.
마크업을 바꿀 때는 두 파일을 함께 수정한다.
"""

import re
from html import escape as html_escape

AUTO_START = "<!-- AUTO:START"
AUTO_END   = "<!-- AUTO:END -->"
AUTO_START_LINE = ("<!-- AUTO:START — 아래 카드는 sync_projects.py 가 data/projects.generated.json 에서 "
                   "자동 생성합니다. 직접 편집하지 마세요 -->")

STATUS_LABEL = {
    "active":    "진행 중",
    "completed": "완료",
    "paused":    "일시 중단",
    "unused":    "미사용",
    "archived":  "아카이브",
}

PLACEHOLDER = "내용을 입력하세요."


def E(s) -> str:
    return html_escape("" if s is None else str(s))


def format_period(started: str, ended: str, ongoing: bool, fallback: str = "") -> str:
    if not started:
        return fallback or "?"
    if ongoing:
        return f"{started} – Present"
    if ended and ended != started:
        return f"{started} – {ended}"
    return started


def _li(items) -> str:
    return "\n".join(f"              <li>{E(i)}</li>" for i in items)


def _badge(status) -> str:
    if not status or status not in STATUS_LABEL:
        return ""
    return f'\n            <span class="status-badge status-{status}">{STATUS_LABEL[status]}</span>'


def _multiline(text: str) -> str:
    """줄바꿈 → <br>. 모든 줄 이스케이프."""
    return "<br>\n              ".join(E(line) for line in (text or "").splitlines() if line.strip())


def _section(title: str, body: str) -> str:
    return f"""
          <div class="dl-section">
            <h4>{E(title)}</h4>{body}
          </div>"""


def _links(p: dict) -> str:
    links = ""
    live = p.get("liveUrl") or ""
    repo_url = p.get("repositoryUrl") or ""
    if live and p.get("status") != "unused":
        links += (f'\n              <a class="proj-link live" href="{E(live)}"'
                  f' target="_blank" rel="noopener">Live Demo</a>')
    if repo_url:
        links += (f'\n              <a class="proj-link" href="{E(repo_url)}"'
                  f' target="_blank" rel="noopener">GitHub</a>')
    if not links:
        return ""
    return _section("Links", f"""
            <div class="proj-links">{links}
            </div>""")


def _videos(p: dict) -> str:
    videos = [v for v in (p.get("videos") or []) if v.get("url")]
    if not videos:
        return ""
    body = ""
    for v in videos:
        if v.get("label"):
            body += f'\n            <p class="video-label">{E(v["label"])}</p>'
        body += f"""
            <div class="video-wrap">
              <iframe src="{E(v["url"])}" allowfullscreen></iframe>
            </div>"""
    return _section("시연 영상", body)


def _team(p: dict) -> str:
    team = p.get("team") or []
    if not team:
        return ""
    members = ""
    for m in team:
        me_tag = '<span class="me">me</span>' if m.get("me") else ""
        role_html = f'\n                <div class="member-role">{E(m["role"])}</div>' if m.get("role") else ""
        members += f"""
              <div class="member-card">
                <div class="member-name">{E(m.get("name"))}{me_tag}</div>{role_html}
              </div>"""
    return _section("팀 구성", f"""
            <div class="member-grid">{members}
            </div>""")


def _chips(p: dict) -> str:
    cls = ("chip " + p["tagClass"]).strip() if p.get("tagClass") else "chip"
    out = ""
    for t in (p.get("tech") or [])[:7]:
        out += f'\n              <span class="{cls}">{E(t)}</span>'
    for a in p.get("awards") or []:
        out += f'\n              <span class="chip award">🏆 {E(a)}</span>'
    return out


def _attrs(p: dict) -> str:
    attrs = ""
    if p.get("status") == "unused":
        attrs += ' class="proj-unused"'
    attrs += f' data-slug="{E(p.get("slug"))}" data-source="{E(p.get("source") or "github")}"'
    if p.get("status"):
        attrs += f' data-status="{E(p["status"])}"'
    if p.get("featured"):
        attrs += ' data-featured="true"'
    return attrs


def _period_str(p: dict) -> str:
    return format_period(p.get("started") or "", p.get("ended") or "", bool(p.get("ongoing")),
                         fallback=p.get("periodFallback") or "")


def _render_unused(p: dict) -> str:
    reason = p.get("unusedReason") or ""
    sub = p.get("subtitle") or (reason.splitlines()[0] if reason.strip() else "")

    body = ""
    if reason.strip():
        body += _section("미사용 사유", f"\n            <p>{_multiline(reason)}</p>")
    rb = p.get("replacedBy") or {}
    if rb.get("title"):
        link = rb.get("url") or rb.get("repository") or ""
        if link:
            body += _section("대체 프로젝트", f"""
            <p>이 프로젝트는 {E(rb["title"])}(으)로 통합되었습니다.<br>
              <a href="{E(link)}" target="_blank" rel="noopener">→ {E(rb["title"])} 보기</a></p>""")
        else:
            body += _section("대체 프로젝트", f"\n            <p>이 프로젝트는 {E(rb['title'])}(으)로 통합되었습니다.</p>")
    repo_url = p.get("repositoryUrl") or ""
    if repo_url:
        body += _section("Repository", f'\n            <p><a href="{E(repo_url)}" target="_blank" rel="noopener">{E(repo_url)}</a></p>')

    return f"""
      <details{_attrs(p)}>
        <summary>
          <span class="proj-period">{E(_period_str(p))}</span>
          <div class="proj-main">
            <div class="proj-title">{E(p.get("title"))}</div>{_badge("unused")}
            <div class="proj-sub">{E(sub)}</div>
          </div>
          <span class="arrow">▶</span>
        </summary>
        <div class="detail">{body}
        </div>
      </details>"""


def render_card(p: dict) -> str:
    """프로젝트 항목(dict, projects.generated.json 스키마) → <details> 카드 HTML"""
    if p.get("status") == "unused":
        return _render_unused(p)

    intro = _multiline(p.get("summary") or "") or PLACEHOLDER
    body = _section("프로젝트 소개", f"\n            <p>{intro}</p>")
    if p.get("highlights"):
        body += _section(p.get("highlightsTitle") or "주요 기능", f"""
            <ul>
{_li(p["highlights"])}
            </ul>""")
    if p.get("status") == "paused" and p.get("pauseReason"):
        body += _section("일시 중단 사유", f"\n            <p>{_multiline(p['pauseReason'])}</p>")
    if p.get("myRole"):
        body += _section("담당 역할", f"\n            <p>{E(p['myRole'])}</p>")
    body += _videos(p)
    body += _links(p)
    body += _team(p)

    return f"""
      <details{_attrs(p)}>
        <summary>
          <span class="proj-period">{E(_period_str(p))}</span>
          <div class="proj-main">
            <div class="proj-title">{E(p.get("title"))}</div>{_badge(p.get("status"))}
            <div class="proj-sub">{E(p.get("subtitle"))}</div>
            <div class="proj-chips">{_chips(p)}
            </div>
          </div>
          <span class="arrow">▶</span>
        </summary>
        <div class="detail">{body}
        </div>
      </details>"""


def render_card_block(p: dict) -> str:
    """정적 index.html 용: AUTO 마커로 감싼 카드"""
    key = p.get("repo") or p.get("slug")
    return f"\n      <!-- AUTO:{key} -->{render_card(p)}\n      <!-- /AUTO:{key} -->"


def render_project_list(projects: list[dict]) -> str:
    return "".join(render_card_block(p) for p in projects)


def render_auto_section(html: str, projects: list[dict]) -> str:
    """index.html 의 AUTO:START ~ AUTO:END 구간 전체를 JSON 기반 카드로 교체"""
    start_idx = html.find(AUTO_START)
    end_idx   = html.find(AUTO_END)
    if start_idx == -1 or end_idx == -1:
        raise ValueError("index.html 에 AUTO:START / AUTO:END 마커가 없습니다.")
    start_line_end = html.index("\n", start_idx)
    # START 마커 줄 자체를 최신 문구로 갱신
    line_begin = html.rfind("\n", 0, start_idx) + 1
    indent = html[line_begin:start_idx]
    head = html[:line_begin] + indent + AUTO_START_LINE
    return head + render_project_list(projects) + "\n      " + html[end_idx:]


def normalize_html(s: str) -> str:
    """parity/fidelity 비교용: 주석 제거, 태그 사이 공백 정규화"""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r">\s+<", "><", s)
    s = re.sub(r"\s+>", ">", s)
    s = re.sub(r">\s+", ">", s)
    s = re.sub(r"\s+<", "<", s)
    return s.strip()
