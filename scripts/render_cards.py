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

# 프로젝트 영역 그룹 (표시 순서). status 가 없는 프로젝트는 ongoing 여부로 current / completed 에 배치
GROUPS = (
    ("current",   "진행 중",           "Current"),
    ("paused",    "일시 중단",         "Paused"),
    ("completed", "완료",              "Completed"),
    ("archive",   "미사용 · 아카이브", "Unused · Archived"),
)
GROUP_OF = {"active": "current", "paused": "paused", "completed": "completed",
            "unused": "archive", "archived": "archive"}
FEATURED_MAX = 5
CHIP_LIMIT = 5          # 접힌 카드에 보이는 기술 태그 수 (나머지는 +N, 펼치면 "기술 스택")


def display_status(p: dict) -> str:
    """필터·그룹용 상태. 명시적 status 가 우선, 없으면 ongoing → active, 아니면 completed.
    배지는 명시적 status 가 있을 때만 붙는다 (AI/파서가 status 를 정하지 않는다는 원칙 유지)."""
    st = p.get("status")
    if st in STATUS_LABEL:
        return st
    return "active" if p.get("ongoing") else "completed"


def card_id(p: dict) -> str:
    return "proj-" + str(p.get("slug") or "")


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


def _shots(p: dict) -> str:
    """상세 카드의 화면 (Screenshot). unused 는 표시하지 않음"""
    shots = p.get("screenshots") or {}
    desktop, mobile = _usable_src(shots.get("desktop")), _usable_src(shots.get("mobile"))
    if not desktop or p.get("status") == "unused":
        return ""
    title = E(p.get("title"))
    body = (f'\n              <img class="shot-desktop" src="{E(desktop)}" alt="{title} 데스크톱 화면"'
            f' loading="lazy" width="1440" height="900">')
    if mobile:
        body += (f'\n              <img class="shot-mobile" src="{E(mobile)}" alt="{title} 모바일 화면"'
                 f' loading="lazy" width="390" height="844">')
    return _section("화면", f"""
            <div class="shot-row">{body}
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


def _chip_cls(p: dict) -> str:
    return ("chip " + p["tagClass"]).strip() if p.get("tagClass") else "chip"


def _is_archived_view(p: dict) -> bool:
    """미사용·아카이브 그룹 카드는 접힌 상태에서 기술 태그를 숨긴다 (기록 중심 최소 표현)"""
    return display_status(p) in ("archived", "unused")


def _chips(p: dict) -> str:
    cls = _chip_cls(p)
    tech = p.get("tech") or []
    out = ""
    if not _is_archived_view(p):
        for t in tech[:CHIP_LIMIT]:
            out += f'\n              <span class="{cls}">{E(t)}</span>'
        if len(tech) > CHIP_LIMIT:
            out += f'\n              <span class="chip more" title="펼치면 전체 기술 스택">+{len(tech) - CHIP_LIMIT}</span>'
    for a in p.get("awards") or []:
        out += f'\n              <span class="chip award">🏆 {E(a)}</span>'
    return out


def _tech_section(p: dict) -> str:
    """접힌 카드에서 다 보이지 않은 기술은 펼친 화면에 전체 목록으로"""
    tech = p.get("tech") or []
    if not tech or (len(tech) <= CHIP_LIMIT and not _is_archived_view(p)):
        return ""
    cls = _chip_cls(p)
    chips = "".join(f'\n              <span class="{cls}">{E(t)}</span>' for t in tech)
    return _section("기술 스택", f"""
            <div class="proj-chips">{chips}
            </div>""")


def _attrs(p: dict) -> str:
    attrs = ""
    if p.get("status") == "unused":
        attrs += ' class="proj-unused"'
    attrs += f' id="{E(card_id(p))}"'
    attrs += f' data-slug="{E(p.get("slug"))}" data-source="{E(p.get("source") or "github")}"'
    if p.get("status"):
        attrs += f' data-status="{E(p["status"])}"'
    attrs += f' data-display-status="{display_status(p)}"'
    if p.get("featured"):
        attrs += ' data-featured="true"'
    return attrs


def _live_pill(p: dict) -> str:
    """접힌 카드에서도 보이는 Live Demo 링크 (unused 제외)"""
    live = p.get("liveUrl") or ""
    if not live or p.get("status") == "unused":
        return ""
    return (f'\n            <a class="proj-live" href="{E(live)}" target="_blank" rel="noopener">'
            f'Live Demo ↗</a>')


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
    body += _tech_section(p)
    body += _shots(p)
    body += _videos(p)
    body += _links(p)
    body += _team(p)

    return f"""
      <details{_attrs(p)}>
        <summary>
          <span class="proj-period">{E(_period_str(p))}</span>
          <div class="proj-main">
            <div class="proj-title">{E(p.get("title"))}</div>{_badge(p.get("status"))}{_live_pill(p)}
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


# ── Featured / 그룹 섹션 ──────────────────────────────────────────────────────
def _usable_src(src) -> str:
    src = src or ""
    return src if src.startswith(("https://", "http://", "assets/")) else ""


def _cover_src(p: dict) -> str:
    """Featured 커버: portfolio.yml cover.image (사이트에서 바로 쓸 수 있는 경로일 때) > Desktop Screenshot"""
    return _usable_src(p.get("coverImage")) or _usable_src((p.get("screenshots") or {}).get("desktop"))


def render_featured_card(p: dict) -> str:
    title = p.get("title") or ""
    cover = _cover_src(p)
    if cover:
        cover_html = (f'\n          <div class="feat-cover"><img src="{E(cover)}" alt="{E(title)} 미리보기"'
                      f' loading="lazy"></div>')
    else:
        initial = title[0] if title else "?"
        cover_html = f'\n          <div class="feat-cover feat-cover-empty" aria-hidden="true"><span>{E(initial)}</span></div>'

    cls = ("chip " + p["tagClass"]).strip() if p.get("tagClass") else "chip"
    chips = "".join(f'\n              <span class="{cls}">{E(t)}</span>' for t in (p.get("tech") or [])[:4])

    links = ""
    if p.get("liveUrl") and p.get("status") != "unused":
        links += (f'\n              <a class="proj-link live" href="{E(p["liveUrl"])}"'
                  f' target="_blank" rel="noopener">Live Demo</a>')
    if p.get("repositoryUrl"):
        links += (f'\n              <a class="proj-link" href="{E(p["repositoryUrl"])}"'
                  f' target="_blank" rel="noopener">GitHub</a>')
    links += f'\n              <a class="proj-link more" href="#{E(card_id(p))}">자세히</a>'

    return f"""
        <article class="feat-card" data-slug="{E(p.get("slug"))}" data-display-status="{display_status(p)}">{cover_html}
          <div class="feat-body">
            <div class="feat-meta">
              <span class="proj-period">{E(_period_str(p))}</span>{_badge(p.get("status"))}
            </div>
            <h4 class="feat-title">{E(title)}</h4>
            <p class="feat-sub">{E(p.get("subtitle"))}</p>
            <div class="proj-chips">{chips}
            </div>
            <div class="proj-links">{links}
            </div>
          </div>
        </article>"""


def featured_projects(projects: list[dict]) -> list[dict]:
    return [p for p in projects if p.get("featured") and p.get("status") != "unused"][:FEATURED_MAX]


def render_sections(projects: list[dict], with_markers: bool = True) -> str:
    """Featured + 상태 그룹. with_markers=True 면 카드를 AUTO 마커로 감싼다 (정적 index.html 용)"""
    out = ""
    featured = featured_projects(projects)
    if featured:
        cards = "".join(render_featured_card(p) for p in featured)
        out += f"""
      <div class="proj-featured">
        <h3 class="proj-group-title">Featured</h3>
        <div class="feat-grid">{cards}
        </div>
      </div>"""
    for key, ko, en in GROUPS:
        items = [p for p in projects if GROUP_OF[display_status(p)] == key]
        if not items:
            continue
        cards = "".join((render_card_block(p) if with_markers else render_card(p)) for p in items)
        out += f"""
      <div class="proj-group" data-group="{key}">
        <h3 class="proj-group-title">{ko}<span class="proj-group-en">{en}</span><span class="proj-group-count">{len(items)}</span></h3>
        <div class="proj-group-list">{cards}
        </div>
      </div>"""
    return out


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
    return head + render_sections(projects) + "\n      " + html[end_idx:]


def normalize_html(s: str) -> str:
    """parity/fidelity 비교용: 주석 제거, 태그 사이 공백 정규화"""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r">\s+<", "><", s)
    s = re.sub(r"\s+>", ">", s)
    s = re.sub(r">\s+", ">", s)
    s = re.sub(r"\s+<", "<", s)
    return s.strip()
