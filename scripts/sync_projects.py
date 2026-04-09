#!/usr/bin/env python3
"""
sync_projects.py — 로컬 실행 전용
=========================================
새 repo 또는 README 변경 감지 시:
  1. README 파싱 → 포트폴리오 카드 생성/업데이트 (index.html)
  2. --obsidian <vault_path> 지정 시 Obsidian md 생성/업데이트

사용법:
  GITHUB_TOKEN=ghp_xxxx python3 scripts/sync_projects.py
  GITHUB_TOKEN=ghp_xxxx python3 scripts/sync_projects.py --obsidian ~/Workspace/MyNotes
  GITHUB_TOKEN=ghp_xxxx python3 scripts/sync_projects.py --force   # SHA 무시하고 전체 재생성
  GITHUB_TOKEN=ghp_xxxx python3 scripts/sync_projects.py --dry-run # 변경 없이 탐지만
"""

import argparse
import base64
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ── 설정 ──────────────────────────────────────────────────────────────
GITHUB_USER  = "kimmydkemf"
ROOT         = Path(__file__).parent.parent
INDEX_HTML   = ROOT / "index.html"
CONFIG_FILE  = Path(__file__).parent / "projects.json"
AUTO_END     = "<!-- AUTO:END -->"

LANG_TAG = {
    "Java": ("mobile", "Java"), "Kotlin": ("mobile", "Kotlin"),
    "Dart": ("mobile", "Flutter"), "Swift": ("mobile", "Swift"),
    "Python": ("dev", "Python"), "JavaScript": ("dev", "JavaScript"),
    "TypeScript": ("dev", "TypeScript"), "Go": ("infra", "Go"),
    "Shell": ("infra", "Shell"), "C++": ("mobile", "C++"),
    "C#": ("mobile", "C#"), "Rust": ("infra", "Rust"),
}

# README에서 섹션을 찾을 때 사용하는 키워드 매핑
SECTION_MAP = {
    "intro":    ["소개", "overview", "about", "introduction", "프로젝트 소개", "프로젝트소개"],
    "features": ["기능", "feature", "주요 기능", "주요기능", "기능 소개", "핵심 기능"],
    "tech":     ["기술", "tech", "stack", "사용 기술", "기술스택", "기술 스택", "개발 환경", "environment"],
    "team":     ["팀", "team", "member", "구성", "팀원", "팀 구성"],
}


# ── GitHub API ────────────────────────────────────────────────────────
def _gh(url: str):
    token = os.environ.get("GITHUB_TOKEN", "")
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def fetch_repos() -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        # 토큰 있을 때: 인증된 엔드포인트로 private + collaborator 레포 포함 전체 조회
        return _gh("https://api.github.com/user/repos?per_page=100&sort=updated&affiliation=owner,collaborator") or []
    return _gh(f"https://api.github.com/users/{GITHUB_USER}/repos?per_page=100&sort=updated") or []


def fetch_readme(full_name: str) -> tuple[str, str]:
    """(content, sha) 반환. README 없으면 ('', '')"""
    data = _gh(f"https://api.github.com/repos/{full_name}/readme")
    if not data:
        return "", ""
    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return content, data.get("sha", "")


def fetch_period(full_name: str) -> tuple[str, str]:
    """(첫 커밋 날짜 YYYY.MM, 마지막 커밋 날짜 YYYY.MM) 반환"""
    # 첫 커밋 — 마지막 페이지 1개
    first_url = (
        f"https://api.github.com/repos/{full_name}"
        f"/commits?per_page=1&direction=asc"
    )
    last_url = (
        f"https://api.github.com/repos/{full_name}"
        f"/commits?per_page=1"
    )
    first_data = _gh(first_url)
    last_data  = _gh(last_url)

    def fmt(commit_list):
        if not commit_list:
            return ""
        dt = commit_list[0]["commit"]["committer"]["date"][:7]  # YYYY-MM
        return dt.replace("-", ".")

    return fmt(first_data), fmt(last_data)


# ── README 파서 ───────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    return text.lower().strip()


def parse_readme(readme: str, repo: dict) -> dict:
    """
    README를 파싱하여 포트폴리오에 쓸 데이터 dict 반환.
    keys: description, intro_lines, tech_items, feature_items, team_items
    """
    result = {
        "description": repo.get("description") or "",
        "intro_lines": [],
        "tech_items":  [],
        "feature_items": [],
        "team_items":  [],
    }

    if not readme:
        return result

    lines = readme.splitlines()

    # 섹션 분류: {섹션명: [줄 목록]}
    sections: dict[str, list[str]] = {"__top__": []}
    current = "__top__"

    for line in lines:
        hm = re.match(r'^#{1,3}\s+(.+)$', line)
        if hm:
            current = hm.group(1).strip()
            sections[current] = []
        else:
            sections.setdefault(current, []).append(line)

    def get_section(key: str) -> list[str]:
        """키워드에 해당하는 섹션의 줄 목록 반환"""
        keywords = SECTION_MAP.get(key, [])
        for sec_title, sec_lines in sections.items():
            if any(kw in _normalize(sec_title) for kw in keywords):
                return sec_lines
        return []

    def extract_bullets(raw_lines: list[str]) -> list[str]:
        items = []
        for l in raw_lines:
            m = re.match(r'^\s*[-*+]\s+(.+)', l)
            if m:
                # 마크다운 인라인 제거 (bold, code, link)
                text = re.sub(r'\*\*(.+?)\*\*', r'\1', m.group(1))
                text = re.sub(r'`(.+?)`', r'\1', text)
                text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
                items.append(text.strip())
        return items

    def extract_paragraphs(raw_lines: list[str], max_lines=3) -> list[str]:
        paras = []
        for l in raw_lines:
            l = l.strip()
            if not l or l.startswith('#') or l.startswith('!') or l.startswith('|'):
                continue
            # 마크다운 인라인 제거
            l = re.sub(r'\*\*(.+?)\*\*', r'\1', l)
            l = re.sub(r'`(.+?)`', r'\1', l)
            l = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', l)
            l = re.sub(r'!\[.*?\]\(.*?\)', '', l).strip()
            if l:
                paras.append(l)
            if len(paras) >= max_lines:
                break
        return paras

    # 소개: 전용 섹션 → 없으면 최상단 첫 단락
    intro_sec = get_section("intro")
    if intro_sec:
        result["intro_lines"] = extract_paragraphs(intro_sec)
    else:
        top_lines = sections.get("__top__", [])
        # h1 타이틀 이후 첫 단락
        result["intro_lines"] = extract_paragraphs(top_lines)

    # description fallback: intro 첫 줄
    if not result["description"] and result["intro_lines"]:
        result["description"] = result["intro_lines"][0][:80]

    # 기능
    result["feature_items"] = extract_bullets(get_section("features"))

    # 기술스택
    tech_sec = get_section("tech")
    result["tech_items"] = extract_bullets(tech_sec)
    # 텍스트 형태 (콤마/슬래시)도 처리
    if not result["tech_items"]:
        for l in tech_sec:
            l = l.strip()
            if l and not l.startswith('#'):
                parts = re.split(r'[,/·|]', l)
                for p in parts:
                    p = p.strip().strip('`').strip()
                    if p and len(p) < 40:
                        result["tech_items"].append(p)

    # 팀
    result["team_items"] = extract_bullets(get_section("team"))

    return result


# ── HTML 카드 생성 ────────────────────────────────────────────────────
def _li(items: list[str]) -> str:
    return "\n".join(f"              <li>{i}</li>" for i in items) if items else ""


def render_card(name: str, repo: dict, parsed: dict,
                start: str, end: str) -> str:
    lang     = repo.get("language") or ""
    tag_cls, tag_lbl = LANG_TAG.get(lang, ("dev", lang or "Code"))
    desc     = parsed["description"] or "설명을 입력하세요."
    url      = repo.get("html_url", "")

    # 기간 표시
    if start and end:
        ongoing = (end >= datetime.now().strftime("%Y.%m")[:5])
        period_str = f"{start} –" if ongoing else f"{start} – {end}"
    else:
        period_str = repo.get("updated_at", "")[:7].replace("-", ".") or "?"

    # 기술 chip들
    tech_chips = ""
    for item in parsed["tech_items"][:6]:  # 최대 6개
        tech_chips += f'\n              <span class="chip {tag_cls}">{item}</span>'
    if not tech_chips:
        tech_chips = f'\n              <span class="chip {tag_cls}">{tag_lbl}</span>'

    # 소개 단락
    intro_html = ""
    if parsed["intro_lines"]:
        intro_html = "<br>\n              ".join(parsed["intro_lines"])
    else:
        intro_html = "내용을 입력하세요."

    # 기능 목록
    feature_html = ""
    if parsed["feature_items"]:
        feature_html = f"""
          <div class="dl-section">
            <h4>주요 기능</h4>
            <ul>
{_li(parsed["feature_items"])}
            </ul>
          </div>"""

    # 팀 구성
    team_html = ""
    if parsed["team_items"]:
        members = ""
        for item in parsed["team_items"]:
            members += f"""
              <div class="member-card">
                <div class="member-name">{item}</div>
              </div>"""
        team_html = f"""
          <div class="dl-section">
            <h4>팀 구성</h4>
            <div class="member-grid">{members}
            </div>
          </div>"""

    return f"""
      <!-- AUTO:{name} -->
      <details>
        <summary>
          <span class="proj-period">{period_str}</span>
          <div class="proj-main">
            <div class="proj-title">{name}</div>
            <div class="proj-sub">{desc}</div>
            <div class="proj-chips">{tech_chips}
            </div>
          </div>
          <span class="arrow">▶</span>
        </summary>
        <div class="detail">
          <div class="dl-section">
            <h4>프로젝트 소개</h4>
            <p>{intro_html}</p>
          </div>{feature_html}
          <div class="dl-section">
            <h4>Repository</h4>
            <p><a href="{url}" target="_blank">{url}</a></p>
          </div>{team_html}
        </div>
      </details>
      <!-- /AUTO:{name} -->"""


# ── Obsidian md 생성 ──────────────────────────────────────────────────
def render_md(name: str, repo: dict, parsed: dict,
              start: str, end: str) -> str:
    desc    = parsed["description"] or ""
    url     = repo.get("html_url", "")
    lang    = repo.get("language") or ""
    today   = datetime.now().strftime("%Y-%m-%d")

    period  = f"{start} – {end}" if (start and end) else start or today[:7]

    tech_list  = "\n".join(f"- {i}" for i in parsed["tech_items"]) or "- 미입력"
    feat_list  = "\n".join(f"- {i}" for i in parsed["feature_items"]) or "- 미입력"
    team_list  = "\n".join(f"- {i}" for i in parsed["team_items"]) or "- 미입력"
    intro_text = "\n".join(parsed["intro_lines"]) or "내용을 입력하세요."

    return f"""# {name}

> {desc}

## 기본 정보

- **기간**: {period}
- **언어**: {lang}
- **GitHub**: {url}
- **메모 생성**: {today}

## 프로젝트 소개

{intro_text}

## 기술 스택

{tech_list}

## 주요 기능

{feat_list}

## 팀 구성

{team_list}
"""


# ── index.html 조작 ───────────────────────────────────────────────────
def insert_card(html: str, card: str) -> str:
    """AUTO:END 마커 직전에 카드 삽입"""
    if AUTO_END not in html:
        print(f"[ERROR] index.html에 '{AUTO_END}' 마커가 없습니다.", file=sys.stderr)
        sys.exit(1)
    return html.replace(AUTO_END, card + "\n      " + AUTO_END)


def update_card(html: str, name: str, card: str) -> str:
    """기존 AUTO:{name} … /AUTO:{name} 블록을 교체"""
    pattern = re.compile(
        rf'\n\s*<!-- AUTO:{re.escape(name)} -->.*?<!-- /AUTO:{re.escape(name)} -->',
        re.DOTALL
    )
    if pattern.search(html):
        return pattern.sub(card, html)
    # 마커가 없으면 신규 삽입
    return insert_card(html, card)


def card_exists(html: str, name: str) -> bool:
    return f"<!-- AUTO:{name} -->" in html


# ── 메인 ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--obsidian", metavar="PATH",
                        help="Obsidian vault 경로 (md 생성/업데이트)")
    parser.add_argument("--dry-run", action="store_true",
                        help="파일 수정 없이 탐지 결과만 출력")
    parser.add_argument("--force", action="store_true",
                        help="README SHA 무시하고 전체 재생성")
    args = parser.parse_args()

    cfg      = json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
    excluded = set(cfg.get("excluded", []))
    repo_cfg = cfg.get("repos", {})   # {"repo_name": {"sha": "...", "start": "...", "end": "..."}}

    print(f"GitHub repos 조회 중 ({GITHUB_USER})…")
    repos = fetch_repos()
    html  = INDEX_HTML.read_text(encoding="utf-8")

    changed = False

    for repo in repos:
        name = repo["name"]
        if name in excluded:
            continue

        full_name = repo.get("full_name", f"{GITHUB_USER}/{name}")

        # README 가져오기
        readme_text, readme_sha = fetch_readme(full_name)
        saved_sha = repo_cfg.get(name, {}).get("sha", "")

        is_new    = name not in repo_cfg
        is_changed = (not args.force) and (readme_sha != saved_sha) and not is_new

        if not is_new and not is_changed and not args.force:
            print(f"  [{name}] 변경 없음 — 스킵")
            continue

        action = "신규" if is_new else "업데이트"
        print(f"  [{name}] {action} 처리 중…")

        # 기간 계산
        saved_start = repo_cfg.get(name, {}).get("start", "")
        saved_end   = repo_cfg.get(name, {}).get("end", "")
        start, end  = fetch_period(full_name)
        if not start:
            start = saved_start
        if not end:
            end = saved_end

        # README 파싱
        parsed = parse_readme(readme_text, repo)

        # 카드 생성
        card = render_card(name, repo, parsed, start, end)

        if not args.dry_run:
            if is_new:
                html = insert_card(html, card)
            else:
                html = update_card(html, name, card)

            # Obsidian md
            if args.obsidian:
                vault = Path(args.obsidian).expanduser()
                md_dir = vault / "20-projects" / name
                md_dir.mkdir(parents=True, exist_ok=True)
                md_path = md_dir / f"{name}.md"
                md_path.write_text(render_md(name, repo, parsed, start, end),
                                   encoding="utf-8")
                print(f"    → Obsidian md: {md_path}")

            # config 업데이트
            repo_cfg[name] = {"sha": readme_sha, "start": start, "end": end}
            changed = True
            print(f"    → 카드 {'삽입' if is_new else '교체'} 완료  (기간: {start} – {end})")
        else:
            print(f"    [dry-run] 카드 생성 예정 (기간: {start} – {end})")
            print(f"    기술: {parsed['tech_items']}")
            print(f"    기능: {parsed['feature_items'][:3]}")

    if changed and not args.dry_run:
        INDEX_HTML.write_text(html, encoding="utf-8")
        cfg["repos"]    = repo_cfg
        cfg["excluded"] = sorted(excluded)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
        print("\nindex.html 및 projects.json 저장 완료.")
        print("이제 'git add -A && git commit -m \"sync projects\" && git push' 하면 반영됩니다.")
    elif not changed:
        print("\n업데이트할 내용 없음.")


if __name__ == "__main__":
    main()
