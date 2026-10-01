#!/usr/bin/env python3
"""
migrate_index_cards.py — index.html 에 박혀 있던 프로젝트 카드 → JSON 데이터 레이어 (1회성 마이그레이션)
=========================================================================================
Phase 3 이전에는 프로젝트 정보가 index.html 안에만 존재했다. 이 스크립트는

  1. AUTO:START ~ AUTO:END 안의 자동 카드  → data/projects.generated.json 의 github 항목으로 seed
  2. 그 아래의 수동 카드(과거 프로젝트)      → data/projects.manual.json (사람이 편집하는 파일)
  3. (--write-index) index.html 의 AUTO 구간을 JSON 기반 카드로 다시 생성하고 수동 카드 HTML 을 제거,
     assets/js/projects.js 로더를 추가

기존 정보(기간·제목·부제·chips·소개·기능·영상·팀·수상·저장소 링크)를 그대로 옮긴다.

사용법:
  python3 scripts/migrate_index_cards.py --dry-run
  python3 scripts/migrate_index_cards.py --write-index
  python3 scripts/migrate_index_cards.py --index PATH --config PATH --manual-out PATH --generated-out PATH
"""

import argparse
import html as html_lib
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_cards import AUTO_START, AUTO_END, render_auto_section, PLACEHOLDER  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
OWNER_NAMES = ("이상호",)
SCRIPT_TAG = '<script src="assets/js/projects.js" defer></script>'
LIST_END = "</div><!-- .project-list -->"


# ── 텍스트 유틸 ───────────────────────────────────────────────────────────────
def _text(fragment: str) -> str:
    """태그 제거 + 엔티티 복원 + 공백 정리 (한 줄)"""
    s = re.sub(r"<[^>]+>", "", fragment or "")
    s = html_lib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _paragraph_lines(p_html: str) -> str:
    """<p> 내부 HTML → 줄 목록. <br> 만 줄바꿈으로 취급하고 소스 줄바꿈은 공백으로 합친다."""
    parts = re.split(r"<br\s*/?>", p_html)
    lines = [_text(part) for part in parts]
    return "\n".join(l for l in lines if l)


def slugify(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9가-힣]+", "-", s).strip("-").lower()
    return s or "project"


def parse_period(text: str) -> tuple[str, str, bool]:
    """'2020.10 – 2020.11' / '2026.05 –' / '2021.08' → (started, ended, ongoing)"""
    t = _text(text)
    m = re.match(r"^(\d{4}\.\d{2})(?:\s*[–\-]\s*(\d{4}\.\d{2}|Present)?)?$", t)
    if not m:
        return "", "", False
    started, ended = m.group(1), m.group(2) or ""
    has_dash = "–" in t or "-" in t
    ongoing = has_dash and (not ended or ended == "Present")
    if ended == "Present":
        ended = ""
    if ended == started:
        ended = ""
    return started, ended, ongoing


# ── 카드 파서 ─────────────────────────────────────────────────────────────────
def parse_card(block: str) -> dict:
    """<details>…</details> 하나 → 필드 dict (JSON 스키마의 표시 필드만)"""
    def first(pattern, default=""):
        m = re.search(pattern, block, re.DOTALL)
        return m.group(1) if m else default

    started, ended, ongoing = parse_period(first(r'class="proj-period">(.*?)</span>'))
    title = _text(first(r'class="proj-title">(.*?)</div>'))
    subtitle = _text(first(r'class="proj-sub">(.*?)</div>'))

    tech, awards, tag_class = [], [], None
    summary_html = block.split("</summary>")[0]
    for cls, label in re.findall(r'<span class="chip([^"]*)"[^>]*>(.*?)</span>', summary_html, re.DOTALL):
        cls = cls.strip()
        label = _text(label)
        if "more" in cls.split():
            continue
        if "award" in cls:
            awards.append(re.sub(r"^🏆\s*", "", label))
        else:
            tech.append(label)
            if tag_class is None:
                tag_class = cls

    summary, highlights, highlights_title = "", [], None
    my_role, videos, team, repo_url = "", [], [], ""

    for part in re.split(r'<div class="dl-section">', block)[1:]:
        heading = _text(first_in(part, r"<h4>(.*?)</h4>"))
        if heading == "프로젝트 소개":
            p = first_in(part, r"<p>(.*?)</p>")
            summary = _paragraph_lines(p)
            if summary == PLACEHOLDER:
                summary = ""
        elif heading == "기술 스택":
            tech = [_text(t) for t in re.findall(r'<span class="chip[^"]*">(.*?)</span>', part, re.DOTALL)]
            m = re.search(r'<span class="chip([^"]*)">', part)
            tag_class = m.group(1).strip() if m else tag_class
        elif heading == "담당 역할":
            my_role = _text(first_in(part, r"<p>(.*?)</p>"))
        elif heading == "시연 영상":
            for label, url in re.findall(
                r'(?:<p[^>]*>(.*?)</p>\s*)?<div class="video-wrap">\s*<iframe src="([^"]+)"', part, re.DOTALL
            ):
                videos.append({"label": _text(label), "url": html_lib.unescape(url)})
        elif heading == "팀 구성":
            for name_html, role_html in re.findall(
                r'<div class="member-name">(.*?)</div>\s*(?:<div class="member-role">(.*?)</div>)?', part, re.DOTALL
            ):
                me = 'class="me"' in name_html
                team.append({"name": _text(name_html).replace("me", "").strip() if me else _text(name_html),
                             "role": _text(role_html), "me": me})
        elif heading == "Repository":
            repo_url = html_lib.unescape(first_in(part, r'href="([^"]+)"'))
        elif heading == "Links":
            # Live Demo(proj-link live) 가 아닌 링크가 저장소 URL
            repo_url = html_lib.unescape(first_in(part, r'<a class="proj-link" href="([^"]+)"'))
        elif "<ul>" in part:
            highlights = [_text(li) for li in re.findall(r"<li>(.*?)</li>", part, re.DOTALL)]
            if heading != "주요 기능":
                highlights_title = heading

    return {
        "title": title, "subtitle": subtitle, "summary": summary,
        "started": started, "ended": ended, "ongoing": ongoing,
        "tech": tech, "awards": awards, "tagClass": tag_class or "",
        "highlights": highlights, "highlightsTitle": highlights_title,
        "myRole": my_role, "videos": videos, "team": team, "repositoryUrl": repo_url,
    }


def first_in(text: str, pattern: str, default: str = "") -> str:
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1) if m else default


def _base_entry() -> dict:
    return {
        "slug": "", "repo": None, "source": "manual",
        "title": "", "subtitle": "", "summary": "",
        "status": None, "started": "", "ended": "", "ongoing": False, "featured": False,
        "liveUrl": "", "repositoryUrl": "", "category": [], "role": [],
        "tech": [], "highlights": [], "highlightsTitle": None, "team": [], "myRole": "",
        "unusedReason": "", "pauseReason": "", "replacedBy": None, "coverImage": "",
        "videos": [], "awards": [], "language": None, "tagClass": "",
        "indexable": True, "screenshotRefresh": False, "hasPortfolioYml": False,
        "periodFallback": "", "syncStatus": "ok", "lastSynced": None,
        "readmeSha": "", "portfolioSha": "",
    }


def parse_index(html: str, repo_cfg: dict | None = None) -> tuple[list[dict], list[dict]]:
    """index.html → (github 항목 목록, manual 항목 목록)"""
    repo_cfg = repo_cfg or {}
    s = html.find(AUTO_START)
    e = html.find(AUTO_END)
    if s == -1 or e == -1:
        raise ValueError("AUTO:START / AUTO:END 마커가 없습니다.")
    auto_region = html[s:e]
    manual_region = html[e:html.find(LIST_END) if LIST_END in html else len(html)]

    github = []
    for name, block in re.findall(r"<!-- AUTO:([\w\-\.]+) -->(.*?)<!-- /AUTO:\1 -->", auto_region, re.DOTALL):
        entry = _base_entry()
        entry.update(parse_card(block))
        entry.update({
            "slug": slugify(name), "repo": name, "source": "github",
            "syncStatus": "migrated",
            "readmeSha": repo_cfg.get(name, {}).get("sha", ""),
            "portfolioSha": repo_cfg.get(name, {}).get("portfolioSha", ""),
        })
        github.append(entry)

    manual = []
    for label, block in re.findall(r"<!-- ([^>\n]+?) -->\s*<details>(.*?)</details>", manual_region, re.DOTALL):
        if label.startswith("/AUTO:") or label.startswith("AUTO:"):
            continue
        entry = _base_entry()
        entry.update(parse_card(block))
        entry.update({"slug": slugify(label), "source": "manual", "status": "archived"})
        manual.append(entry)

    return github, manual


# ── index.html 재작성 ─────────────────────────────────────────────────────────
def rewrite_index(html: str, projects: list[dict]) -> str:
    """AUTO 구간을 JSON 기반 카드로 교체, 수동 카드 HTML 제거, JS 로더 추가"""
    out = render_auto_section(html, projects)
    e = out.find(AUTO_END) + len(AUTO_END)
    le = out.find(LIST_END)
    if le != -1:
        out = out[:e] + "\n\n    " + out[le:]
    if SCRIPT_TAG not in out:
        out = out.replace('<link rel="stylesheet" href="assets/css/style.css">',
                          '<link rel="stylesheet" href="assets/css/style.css">\n  ' + SCRIPT_TAG, 1)
    return out


def sort_projects(projects: list[dict]) -> list[dict]:
    return sorted(projects, key=lambda p: p.get("started") or "0000.00", reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=str(ROOT / "index.html"))
    ap.add_argument("--config", default=str(ROOT / "scripts" / "projects.json"))
    ap.add_argument("--manual-out", default=str(ROOT / "data" / "projects.manual.json"))
    ap.add_argument("--generated-out", default=str(ROOT / "data" / "projects.generated.json"))
    ap.add_argument("--write-index", action="store_true", help="index.html 도 JSON 기반으로 재작성")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    index_path = Path(args.index)
    html = index_path.read_text(encoding="utf-8")
    cfg_path = Path(args.config)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}

    github, manual = parse_index(html, cfg.get("repos", {}))
    print(f"자동 카드 {len(github)}개, 수동 카드 {len(manual)}개 파싱")
    for p in github + manual:
        print(f"  [{p['source']}] {p['title']}  ({p['started']} – {p['ended'] or ('Present' if p['ongoing'] else '')})"
              f"  tech={len(p['tech'])} highlights={len(p['highlights'])} videos={len(p['videos'])} team={len(p['team'])}")

    if args.dry_run:
        print("\nDry run — 파일을 쓰지 않았습니다.")
        return

    manual_path = Path(args.manual_out)
    gen_path = Path(args.generated_out)
    if manual_path.exists():
        print(f"[ERROR] {manual_path} 가 이미 있습니다. 덮어쓰지 않습니다.", file=sys.stderr)
        sys.exit(1)
    manual_path.parent.mkdir(parents=True, exist_ok=True)
    gen_path.parent.mkdir(parents=True, exist_ok=True)

    manual_path.write_text(json.dumps({"projects": manual}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    projects = sort_projects(github + manual)
    gen_path.write_text(json.dumps({
        "schemaVersion": 1,
        "generatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "projects": projects,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n{manual_path} 저장 ({len(manual)}개)")
    print(f"{gen_path} 저장 ({len(projects)}개)")

    if args.write_index:
        index_path.write_text(rewrite_index(html, projects), encoding="utf-8")
        print(f"{index_path} 재작성 (AUTO 구간 재생성, 수동 카드 HTML 제거, JS 로더 추가)")


if __name__ == "__main__":
    main()
