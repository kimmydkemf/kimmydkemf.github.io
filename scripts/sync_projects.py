#!/usr/bin/env python3
"""
sync_projects.py — GitHub 레포 → GitHub Pages 포트폴리오 자동 동기화
=========================================================================
동작 방식:
  1. GitHub API로 레포 목록 조회 (private 포함, GITHUB_TOKEN 필요)
  2. README 없는 레포는 스킵
  3. index.html의 기존 수동 카드와 중복 여부 감지 → 자동 스킵
  4. ANTHROPIC_API_KEY 있으면 Claude가 README 분석 → 포트폴리오 문장 생성
     없으면 README 직접 파싱 (폴백)
  5. index.html AUTO:START~AUTO:END 구간에 카드 삽입/업데이트

사용법:
  GITHUB_TOKEN=ghp_xxx ANTHROPIC_API_KEY=sk-ant-xxx python3 scripts/sync_projects.py
  ... --dry-run   # 변경 없이 탐지만
  ... --force     # SHA 무시하고 전체 재생성
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

# ── 설정 ──────────────────────────────────────────────────────────────────────
GITHUB_USER = "kimmydkemf"
ROOT        = Path(__file__).parent.parent
INDEX_HTML  = ROOT / "index.html"
CONFIG_FILE = Path(__file__).parent / "projects.json"
AUTO_START  = "<!-- AUTO:START"
AUTO_END    = "<!-- AUTO:END -->"

LANG_TAG = {
    "Java":       ("mobile", "Java"),
    "Kotlin":     ("mobile", "Kotlin"),
    "Dart":       ("mobile", "Flutter"),
    "Swift":      ("mobile", "Swift"),
    "Python":     ("dev",    "Python"),
    "JavaScript": ("dev",    "JavaScript"),
    "TypeScript": ("dev",    "TypeScript"),
    "Go":         ("infra",  "Go"),
    "Shell":      ("infra",  "Shell"),
    "C++":        ("mobile", "C++"),
    "C#":         ("mobile", "C#"),
    "Rust":       ("infra",  "Rust"),
}


# ── GitHub API ─────────────────────────────────────────────────────────────────
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
        if e.code in (404, 403):
            return None
        raise


def fetch_repos() -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        return _gh(
            "https://api.github.com/user/repos"
            "?per_page=100&sort=updated&affiliation=owner,collaborator"
        ) or []
    return _gh(
        f"https://api.github.com/users/{GITHUB_USER}/repos"
        "?per_page=100&sort=updated"
    ) or []


def fetch_readme(full_name: str) -> tuple[str, str]:
    """README 내용과 SHA 반환. 없으면 ('', '')"""
    data = _gh(f"https://api.github.com/repos/{full_name}/readme")
    if not data:
        return "", ""
    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return content, data.get("sha", "")


def fetch_period(full_name: str) -> tuple[str, str]:
    """(첫 커밋 YYYY.MM, 마지막 커밋 YYYY.MM)"""
    first = _gh(
        f"https://api.github.com/repos/{full_name}/commits?per_page=1&direction=asc"
    )
    last = _gh(
        f"https://api.github.com/repos/{full_name}/commits?per_page=1"
    )

    def fmt(data):
        if not data:
            return ""
        return data[0]["commit"]["committer"]["date"][:7].replace("-", ".")

    return fmt(first), fmt(last)


# ── 중복 감지 ──────────────────────────────────────────────────────────────────
def scan_existing_titles(html: str) -> set[str]:
    """index.html에서 이미 존재하는 proj-title 텍스트를 수집 (수동 카드 포함)"""
    return set(re.findall(r'class="proj-title">([^<]+)<', html))


def is_duplicate(repo_name: str, existing_titles: set[str]) -> bool:
    """
    레포 이름이 이미 존재하는 수동 카드와 중복인지 확인.
    - 대소문자 무시, 공백/언더스코어/하이픈 정규화 후 비교
    - 레포 이름이 기존 카드 제목에 포함되는 경우도 중복으로 판단
    """
    def normalize(s):
        return re.sub(r'[\s_\-]+', '', s).lower()

    name_n = normalize(repo_name)
    for title in existing_titles:
        title_n = normalize(title)
        if name_n == title_n or name_n in title_n or title_n in name_n:
            return True
    return False


# ── Claude API 콘텐츠 생성 ─────────────────────────────────────────────────────
def generate_with_claude(
    name: str, full_name: str, readme: str,
    repo: dict, start: str, end: str
) -> dict | None:
    """
    Claude API로 README를 분석해 포트폴리오 카드 데이터 생성.
    ANTHROPIC_API_KEY 없으면 None 반환.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    lang = repo.get("language") or ""
    desc = repo.get("description") or ""
    period_str = f"{start} – {end}" if start else "미상"

    prompt = f"""당신은 개발자 포트폴리오 카드를 작성하는 전문가입니다.
아래 GitHub 레포지토리 정보와 README를 분석해서 포트폴리오에 들어갈 내용을 만들어주세요.

## 레포 정보
- 이름: {name} ({full_name})
- GitHub 설명: {desc}
- 주 언어: {lang}
- 기간: {period_str}
- URL: {repo.get("html_url", "")}

## README
---
{readme[:4000]}
---

## 출력 규칙
1. proj_title: README에서 실제 프로젝트 이름 추출. 없으면 레포 이름 사용
2. subtitle: 프로젝트를 한 줄로 설명 (한국어, 40자 이내). 단순 번역 말고 핵심 가치 담기
3. intro: 프로젝트 소개 2~3문장 (한국어). "무엇을 만들었고, 왜 만들었고, 어떤 가치가 있는지" 중심
4. tech_items: 실제 사용 기술 목록 (최대 7개, 중요한 것만, 마크다운 표 행/구분선 제외)
5. features: 핵심 기능 목록 (최대 5개, 한국어)
6. team: 팀원과 역할 목록. README에 없으면 빈 배열
7. my_role: 포트폴리오 소유자(이상호/kimmydkemf)의 역할. README에 언급 없으면 빈 문자열

반드시 아래 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이):
{{
  "proj_title": "...",
  "subtitle": "...",
  "intro": "...",
  "tech_items": ["...", "..."],
  "features": ["...", "..."],
  "team": ["이름 — 역할", "..."],
  "my_role": "..."
}}"""

    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            text = result["content"][0]["text"].strip()
            # 코드블록이 있으면 제거
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group())
    except Exception as e:
        print(f"    [WARN] Claude API 오류: {e}", file=sys.stderr)
    return None


# ── README 폴백 파서 ──────────────────────────────────────────────────────────
SECTION_KEYWORDS = {
    "intro":    ["소개", "overview", "about", "introduction", "프로젝트 소개"],
    "features": ["기능", "feature", "주요 기능", "핵심 기능"],
    "tech":     ["기술", "tech", "stack", "사용 기술", "기술스택", "개발 환경", "environment"],
    "team":     ["팀", "team", "member", "팀원", "팀 구성"],
}


def _parse_readme_fallback(readme: str, repo: dict) -> dict:
    """Claude 없을 때 README를 직접 파싱해 카드 데이터 반환"""
    result = {
        "proj_title": repo["name"],
        "subtitle":   repo.get("description") or "",
        "intro":      "",
        "tech_items": [],
        "features":   [],
        "team":       [],
        "my_role":    "",
    }

    if not readme:
        return result

    lines = readme.splitlines()
    sections: dict[str, list[str]] = {"__top__": []}
    current = "__top__"
    h1_found = False

    for line in lines:
        hm = re.match(r'^(#{1,3})\s+(.+)$', line)
        if hm:
            level, title = len(hm.group(1)), hm.group(2).strip()
            if level == 1 and not h1_found:
                # 첫 h1은 제목으로 처리하고 그 아래 내용은 __top__에 계속 수집
                result["proj_title"] = title
                h1_found = True
                current = "__top__"
            else:
                current = title
                sections[current] = []
        else:
            sections.setdefault(current, []).append(line)

    def get_section(key: str) -> list[str]:
        for title, sec_lines in sections.items():
            if any(kw in title.lower() for kw in SECTION_KEYWORDS.get(key, [])):
                return sec_lines
        return []

    def clean(text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'`(.+?)`', r'\1', text)
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
        return text.strip()

    def bullets(raw: list[str]) -> list[str]:
        items = []
        for l in raw:
            m = re.match(r'^\s*[-*+]\s+(.+)', l)
            if m:
                items.append(clean(m.group(1)))
        return items

    def paragraphs(raw: list[str], max_p: int = 3) -> list[str]:
        out = []
        for l in raw:
            l = clean(l)
            if l and not l.startswith(('#', '!', '|', '-|', '|-')) and not re.match(r'^-{3,}$', l):
                out.append(l)
            if len(out) >= max_p:
                break
        return out

    # 소개
    intro_sec = get_section("intro")
    intro_lines = paragraphs(intro_sec) if intro_sec else paragraphs(sections.get("__top__", []))
    result["intro"] = "\n".join(intro_lines)
    if not result["subtitle"] and intro_lines:
        result["subtitle"] = intro_lines[0][:60]

    # 기능
    result["features"] = bullets(get_section("features"))[:5]

    # 기술
    tech_sec = get_section("tech")
    tech = bullets(tech_sec)
    # 마크다운 표 형식 파싱 (| 구분 | 기술 | → 오른쪽 컬럼 값 추출)
    if not tech:
        for l in tech_sec:
            if re.match(r'^\s*\|', l) and '---' not in l:
                cols = [c.strip() for c in l.strip('| ').split('|')]
                # 헤더행 제외, 값 컬럼 (마지막 또는 두번째)에서 추출
                if len(cols) >= 2:
                    val = cols[-1].strip()
                    val = clean(val)
                    if val and val not in ('기술', 'Tech', 'Stack', '기술 스택'):
                        # 쉼표나 슬래시로 여러 기술이 하나의 셀에 있을 수 있음
                        for part in re.split(r'[,/·]', val):
                            part = part.strip().strip('`')
                            if part and len(part) < 40:
                                tech.append(part)
    if not tech:
        for l in tech_sec:
            l = l.strip()
            if l and not l.startswith('#') and '|' not in l and '---' not in l:
                for part in re.split(r'[,/·|]', l):
                    part = part.strip().strip('`').strip()
                    if part and len(part) < 40 and part not in ('', '-'):
                        tech.append(part)
    result["tech_items"] = tech[:7]

    # 팀
    result["team"] = bullets(get_section("team"))

    return result


# ── HTML 카드 렌더링 ───────────────────────────────────────────────────────────
def _li(items: list[str]) -> str:
    return "\n".join(f"              <li>{i}</li>" for i in items)


def render_card(name: str, repo: dict, data: dict, start: str, end: str) -> str:
    lang = repo.get("language") or ""
    tag_cls, tag_lbl = LANG_TAG.get(lang, ("dev", lang or "Code"))
    url = repo.get("html_url", "")

    # 기간
    if start and end:
        ongoing = end >= datetime.now().strftime("%Y.%m")[:4]
        period_str = f"{start} –" if ongoing else f"{start} – {end}"
    else:
        period_str = repo.get("updated_at", "")[:7].replace("-", ".") or "?"

    # 기술 chips
    chip_html = ""
    for item in (data["tech_items"] or [tag_lbl])[:7]:
        chip_html += f'\n              <span class="chip {tag_cls}">{item}</span>'

    # 소개 (줄바꿈 → <br>)
    intro_html = "<br>\n              ".join(
        line for line in data["intro"].splitlines() if line.strip()
    ) or "내용을 입력하세요."

    # 기능 섹션
    feature_html = ""
    if data["features"]:
        feature_html = f"""
          <div class="dl-section">
            <h4>주요 기능</h4>
            <ul>
{_li(data["features"])}
            </ul>
          </div>"""

    # 팀 섹션
    team_html = ""
    if data["team"]:
        members = ""
        for item in data["team"]:
            # "이름 — 역할" 형식 파싱
            if "—" in item or "-" in item:
                parts = re.split(r'\s*[—\-]\s*', item, 1)
                member_name = parts[0].strip()
                member_role = parts[1].strip() if len(parts) > 1 else ""
                me_tag = '<span class="me">me</span>' if "이상호" in member_name else ""
                members += f"""
              <div class="member-card">
                <div class="member-name">{member_name}{me_tag}</div>
                <div class="member-role">{member_role}</div>
              </div>"""
            else:
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

    # 내 역할 섹션
    role_html = ""
    if data.get("my_role"):
        role_html = f"""
          <div class="dl-section">
            <h4>담당 역할</h4>
            <p>{data["my_role"]}</p>
          </div>"""

    return f"""
      <!-- AUTO:{name} -->
      <details>
        <summary>
          <span class="proj-period">{period_str}</span>
          <div class="proj-main">
            <div class="proj-title">{data["proj_title"]}</div>
            <div class="proj-sub">{data["subtitle"]}</div>
            <div class="proj-chips">{chip_html}
            </div>
          </div>
          <span class="arrow">▶</span>
        </summary>
        <div class="detail">
          <div class="dl-section">
            <h4>프로젝트 소개</h4>
            <p>{intro_html}</p>
          </div>{feature_html}{role_html}
          <div class="dl-section">
            <h4>Repository</h4>
            <p><a href="{url}" target="_blank">{url}</a></p>
          </div>{team_html}
        </div>
      </details>
      <!-- /AUTO:{name} -->"""


# ── index.html 조작 ────────────────────────────────────────────────────────────
def insert_card(html: str, card: str) -> str:
    if AUTO_END not in html:
        print(f"[ERROR] index.html에 '{AUTO_END}' 마커가 없습니다.", file=sys.stderr)
        sys.exit(1)
    return html.replace(AUTO_END, card + "\n      " + AUTO_END)


def update_card(html: str, name: str, card: str) -> str:
    pattern = re.compile(
        rf'\n\s*<!-- AUTO:{re.escape(name)} -->.*?<!-- /AUTO:{re.escape(name)} -->',
        re.DOTALL,
    )
    if pattern.search(html):
        return pattern.sub(card, html)
    return insert_card(html, card)


def card_exists(html: str, name: str) -> bool:
    return f"<!-- AUTO:{name} -->" in html


# ── 자동 카드 정렬 ────────────────────────────────────────────────────────────
def reorder_auto_section(html: str, repo_cfg: dict) -> str:
    """AUTO:START ~ AUTO:END 사이 카드를 시작일 내림차순으로 재정렬"""
    start_idx = html.find(AUTO_START)
    end_idx   = html.find(AUTO_END)
    if start_idx == -1 or end_idx == -1:
        return html
    start_line_end = html.index('\n', start_idx) + 1
    between = html[start_line_end:end_idx]
    card_pattern = re.compile(
        r'(\s*<!-- AUTO:([A-Za-z0-9_\-\.]+) -->.*?<!-- /AUTO:\2 -->)',
        re.DOTALL
    )
    cards = card_pattern.findall(between)
    if len(cards) <= 1:
        return html
    def sort_key(card_tuple):
        name  = card_tuple[1]
        return repo_cfg.get(name, {}).get("start", "0000.00")
    sorted_cards = sorted(cards, key=sort_key, reverse=True)
    if cards == sorted_cards:
        return html
    sorted_content = ''.join(c[0] for c in sorted_cards) + '\n      '
    return html[:start_line_end] + sorted_content + html[end_idx:]


# ── Obsidian md 생성 ──────────────────────────────────────────────────────────
def _write_obsidian(vault_path: str, repo_cfg: dict):
    """각 프로젝트를 Obsidian vault의 개발/ 디렉토리에 md로 저장"""
    vault = Path(vault_path).expanduser()
    out_dir = vault / "개발"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, cfg in repo_cfg.items():
        title = cfg.get("title", name)
        start = cfg.get("start", "")
        end   = cfg.get("end", "")
        period = f"{start} – {end}" if start else ""
        md_path = out_dir / f"{title}.md"
        if not md_path.exists():
            md_path.write_text(
                f"# {title}\n\n"
                f"- GitHub: [{name}](https://github.com/kimmydkemf/{name})\n"
                f"- 기간: {period}\n",
                encoding="utf-8"
            )
            print(f"  Obsidian: {md_path} 생성")


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true", help="파일 수정 없이 탐지만")
    parser.add_argument("--force",    action="store_true", help="SHA 무시하고 전체 재생성")
    parser.add_argument("--obsidian", metavar="VAULT", help="Obsidian vault 경로 (md 파일 생성)")
    args = parser.parse_args()

    using_claude = bool(os.environ.get("ANTHROPIC_API_KEY", ""))
    mode_str = "Claude AI 분석" if using_claude else "README 직접 파싱 (ANTHROPIC_API_KEY 없음)"
    print(f"모드: {mode_str}")
    print(f"GitHub repos 조회 중 ({GITHUB_USER})…\n")

    cfg      = json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
    excluded = set(cfg.get("excluded", []))
    skip     = set(cfg.get("skip_repos", []))
    repo_cfg = cfg.get("repos", {})

    repos = fetch_repos()
    html  = INDEX_HTML.read_text(encoding="utf-8")

    # 현재 index.html에 이미 존재하는 수동 카드 제목 수집
    existing_titles = scan_existing_titles(html)
    print(f"기존 수동 카드 {len(existing_titles)}개 감지: {', '.join(sorted(existing_titles))}\n")

    changed = False

    for repo in repos:
        name      = repo["name"]
        full_name = repo.get("full_name", f"{GITHUB_USER}/{name}")

        # 제외 목록
        if name in excluded:
            continue

        # 수동 skip 목록
        if name in skip:
            print(f"  [{name}] skip_repos 목록 — 스킵")
            continue

        # 기존 수동 카드와 중복 감지
        # AUTO 카드 마커는 제외하고 수동 카드 기준으로만 비교
        manual_titles = {t for t in existing_titles if f"<!-- AUTO:" not in html or
                         not re.search(rf'<!-- AUTO:[^>]+ -->[^<]*{re.escape(t)}', html)}

        # proj-title 기준 중복 체크 (AUTO 블록 내의 카드는 제외)
        auto_titles = set(re.findall(
            r'<!-- AUTO:\w+ -->.*?class="proj-title">([^<]+)<',
            html, re.DOTALL
        ))
        manual_only_titles = existing_titles - auto_titles

        if is_duplicate(name, manual_only_titles):
            print(f"  [{name}] 수동 카드 중복 감지 — 스킵 (skip_repos에 추가 권장)")
            skip.add(name)
            continue

        # README 필수
        readme_text, readme_sha = fetch_readme(full_name)
        if not readme_text:
            print(f"  [{name}] README 없음 — 스킵")
            continue

        # 변경 감지
        saved_sha = repo_cfg.get(name, {}).get("sha", "")
        is_new     = name not in repo_cfg
        sha_changed = readme_sha != saved_sha

        # 플레이스홀더 내용 감지 (카드가 비어있으면 강제 재생성)
        has_placeholder = card_exists(html, name) and "내용을 입력하세요." in html

        if not is_new and not sha_changed and not args.force and not has_placeholder:
            print(f"  [{name}] 변경 없음 — 스킵")
            continue
        if has_placeholder:
            print(f"  [{name}] 빈 카드 감지 — 내용 재생성")

        action = "신규" if is_new else "업데이트"
        print(f"  [{name}] {action} 처리 중…")

        # 기간
        saved_start = repo_cfg.get(name, {}).get("start", "")
        saved_end   = repo_cfg.get(name, {}).get("end", "")
        start, end  = fetch_period(full_name)
        if not start:
            start = saved_start
        if not end:
            end = saved_end

        # 콘텐츠 생성
        data = generate_with_claude(name, full_name, readme_text, repo, start, end)
        if data:
            print(f"    → Claude 분석 완료")
        else:
            data = _parse_readme_fallback(readme_text, repo)
            print(f"    → README 파싱 (폴백)")

        print(f"    제목: {data['proj_title']}")
        print(f"    기술: {data['tech_items']}")
        print(f"    기능: {data['features'][:3]}")

        if not args.dry_run:
            card = render_card(name, repo, data, start, end)
            if card_exists(html, name):
                html = update_card(html, name, card)
            else:
                html = insert_card(html, card)

            repo_cfg[name] = {
                "sha":   readme_sha,
                "start": start,
                "end":   end,
                "title": data["proj_title"],
            }
            changed = True
            print(f"    → 카드 {'삽입' if is_new else '교체'} 완료 (기간: {start} – {end})")

        print()

    if changed and not args.dry_run:
        html = reorder_auto_section(html, repo_cfg)
        INDEX_HTML.write_text(html, encoding="utf-8")
        cfg["repos"]      = repo_cfg
        cfg["excluded"]   = sorted(excluded)
        cfg["skip_repos"] = sorted(skip)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
        print("index.html 및 projects.json 저장 완료.")
        print("git add index.html scripts/projects.json && git commit -m 'sync projects' && git push")

        # Obsidian md 생성
        if args.obsidian:
            _write_obsidian(args.obsidian, repo_cfg)

    elif not changed:
        print("업데이트할 내용 없음.")


if __name__ == "__main__":
    main()
