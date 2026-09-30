#!/usr/bin/env python3
"""
sync_projects.py — GitHub 레포 → GitHub Pages 포트폴리오 자동 동기화
=========================================================================
동작 방식:
  1. GitHub API로 레포 목록 조회 (private 포함, GITHUB_TOKEN 필요)
  2. README 도 portfolio.yml 도 없는 레포는 스킵
  3. index.html의 기존 수동 카드와 중복 여부 감지 → 자동 스킵
  4. portfolio.yml 이 있으면 표시용 메타데이터로 우선 사용
     (status / started / ended / featured / live_url / unused_reason / replaced_by 는 여기서만)
  5. ANTHROPIC_API_KEY 있으면 Claude가 README 분석 → 포트폴리오 문장 생성
     없으면 README 직접 파싱 (폴백)
  6. index.html AUTO:START~AUTO:END 구간에 카드 삽입/업데이트

우선순위:  portfolio.yml  >  README (Claude / 파서)  >  GitHub repo metadata

사용법:
  GITHUB_TOKEN=ghp_xxx ANTHROPIC_API_KEY=sk-ant-xxx python3 scripts/sync_projects.py
  ... --dry-run            # 변경 없이 탐지만
  ... --force              # SHA 무시하고 전체 재생성
  ... --fixtures DIR       # GitHub 대신 로컬 샘플 데이터 사용 (네트워크 없음, 개발/테스트용)
  ... --index PATH         # 대상 index.html 경로 지정 (기본: 저장소 루트 index.html)
  ... --config PATH        # 대상 projects.json 경로 지정 (기본: scripts/projects.json)
"""

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import date, datetime
from html import escape as html_escape
from pathlib import Path

# PyYAML 이 있으면 사용, 없으면 내장 subset 파서로 폴백 (의존성 없는 실행 유지)
try:
    import yaml as _yaml  # type: ignore
except ImportError:  # pragma: no cover
    _yaml = None

# Windows 한국어 환경 (cp949) 에서 em-dash, 한글, 이모지 등 출력 시
# UnicodeEncodeError 로 스크립트가 죽는 문제 방지.
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# ── 설정 ──────────────────────────────────────────────────────────────────────
GITHUB_USER = "kimmydkemf"
ROOT        = Path(__file__).parent.parent
INDEX_HTML  = ROOT / "index.html"
CONFIG_FILE = Path(__file__).parent / "projects.json"
AUTO_START  = "<!-- AUTO:START"
AUTO_END    = "<!-- AUTO:END -->"

PORTFOLIO_FILE = "portfolio.yml"
VALID_STATUSES = ("active", "completed", "paused", "unused", "archived")
STATUS_LABEL = {
    "active":    "진행 중",
    "completed": "완료",
    "paused":    "일시 중단",
    "unused":    "미사용",
    "archived":  "아카이브",
}
# status 가 없는 README 전용 프로젝트: 마지막 커밋이 이 개월 수 이내면 진행 중으로 표시
ONGOING_GRACE_MONTHS = 3

# --fixtures DIR 지정 시 GitHub API 대신 로컬 샘플 디렉터리를 읽는다
FIXTURE_DIR: Path | None = None

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
def _gh_request(url: str):
    """(json, headers) 반환. 404 → (None, {}). 403 은 경고 출력 후 (None, {})."""
    token = os.environ.get("GITHUB_TOKEN", "")
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            # 권한 없음 또는 rate limit — 404 와 구분해서 원인을 남긴다
            print(f"    [WARN] GitHub API 403 (권한 없음 / rate limit): {url}", file=sys.stderr)
            return None, {}
        if e.code == 404:
            return None, {}
        raise


def _gh(url: str):
    return _gh_request(url)[0]


# ── 로컬 fixture 소스 (--fixtures) ───────────────────────────────────────────
# fixtures/<repo>/ 안에 repo.json, README.md, portfolio.yml, commits.json 을 둔다.
def _blob_sha(text: str) -> str:
    """git blob SHA 와 같은 방식으로 계산 (fixture 변경 감지용)"""
    data = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _fixture_repos() -> list[dict]:
    repos = []
    for d in sorted(FIXTURE_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        meta = {}
        if (d / "repo.json").exists():
            meta = json.loads((d / "repo.json").read_text(encoding="utf-8"))
        meta.setdefault("name", d.name)
        meta.setdefault("full_name", f"{GITHUB_USER}/{meta['name']}")
        meta.setdefault("html_url", f"https://github.com/{meta['full_name']}")
        meta.setdefault("language", "")
        meta.setdefault("description", "")
        meta.setdefault("updated_at", "")
        repos.append(meta)
    return repos


def _fixture_file(full_name: str, filename: str) -> tuple[str, str]:
    for d in FIXTURE_DIR.iterdir():
        if not d.is_dir():
            continue
        repo_json = d / "repo.json"
        name = d.name
        if repo_json.exists():
            name = json.loads(repo_json.read_text(encoding="utf-8")).get("name", d.name)
        if name == full_name.split("/")[-1]:
            p = d / filename
            if not p.exists():
                return "", ""
            text = p.read_text(encoding="utf-8")
            return text, _blob_sha(text)
    return "", ""


def fetch_repos() -> list[dict]:
    if FIXTURE_DIR:
        return _fixture_repos()
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
    if FIXTURE_DIR:
        return _fixture_file(full_name, "README.md")
    data = _gh(f"https://api.github.com/repos/{full_name}/readme")
    if not data:
        return "", ""
    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return content, data.get("sha", "")


def fetch_portfolio_yml(full_name: str) -> tuple[str, str]:
    """레포 루트의 portfolio.yml 내용과 SHA 반환. 없으면 ('', '')"""
    if FIXTURE_DIR:
        return _fixture_file(full_name, PORTFOLIO_FILE)
    data = _gh(f"https://api.github.com/repos/{full_name}/contents/{PORTFOLIO_FILE}")
    if not data or not isinstance(data, dict) or "content" not in data:
        return "", ""
    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return content, data.get("sha", "")


def _ym_from_iso(s: str) -> str:
    return s[:7].replace("-", ".") if s else ""


def fetch_period(full_name: str) -> tuple[str, str]:
    """(첫 커밋 YYYY.MM, 마지막 커밋 YYYY.MM)

    GitHub commits API 는 정렬 방향 파라미터를 지원하지 않으므로
    per_page=1 응답의 Link 헤더 rel="last" 페이지를 다시 요청해 첫 커밋을 구한다.
    """
    if FIXTURE_DIR:
        text, _ = _fixture_file(full_name, "commits.json")
        if not text:
            return "", ""
        c = json.loads(text)
        return _ym_from_iso(c.get("first", "")), _ym_from_iso(c.get("last", ""))

    def fmt(data):
        if not data:
            return ""
        return _ym_from_iso(data[0]["commit"]["committer"]["date"])

    last_data, headers = _gh_request(
        f"https://api.github.com/repos/{full_name}/commits?per_page=1"
    )
    last = fmt(last_data)
    first = last
    link = headers.get("Link") or headers.get("link") or ""
    m = re.search(r'<([^>]+)>;\s*rel="last"', link)
    if m:
        first = fmt(_gh(m.group(1))) or last
    return first, last


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


# ── portfolio.yml 파서 ─────────────────────────────────────────────────────────
def _yaml_scalar(v: str):
    v = v.strip()
    if v == "" or v in ("~", "null"):
        return None
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_yaml_scalar(x) for x in inner.split(",")] if inner else []
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _yaml_strip_comment(line: str) -> str:
    if line.lstrip().startswith("#"):
        return ""
    m = re.search(r'\s#', line)
    if m and line.count('"') % 2 == 0 and line.count("'") % 2 == 0:
        return line[: m.start()]
    return line


def _parse_simple_yaml(text: str) -> dict:
    """
    PyYAML 이 없을 때 쓰는 subset 파서.
    지원: key: value / 스칼라 리스트(- item, [a, b]) / 1단 중첩 매핑 / 블록 스칼라(> |) / 주석
    portfolio.template.yml 범위의 문법만 지원한다.
    """
    lines = text.splitlines()
    n = len(lines)

    def indent_of(s: str) -> int:
        return len(s) - len(s.lstrip(" "))

    def parse_block(start: int, indent: int):
        obj = None
        i = start
        while i < n:
            raw = _yaml_strip_comment(lines[i])
            if not raw.strip():
                i += 1
                continue
            ind = indent_of(raw)
            if ind < indent:
                break
            if ind > indent:
                i += 1
                continue
            s = raw.strip()
            if s.startswith("- ") or s == "-":
                if obj is None:
                    obj = []
                if not isinstance(obj, list):
                    break
                obj.append(_yaml_scalar(s[1:]))
                i += 1
                continue
            m = re.match(r'^([A-Za-z0-9_\-]+):\s*(.*)$', s)
            if not m:
                i += 1
                continue
            if obj is None:
                obj = {}
            if not isinstance(obj, dict):
                break
            key, val = m.group(1), m.group(2).strip()
            if val in (">", "|", ">-", "|-"):
                buf = []
                i += 1
                while i < n:
                    l = lines[i]
                    if l.strip() == "":
                        buf.append("")
                        i += 1
                        continue
                    if indent_of(l) <= indent:
                        break
                    buf.append(l.strip())
                    i += 1
                joiner = "\n" if val.startswith("|") else " "
                obj[key] = joiner.join(buf).strip()
                continue
            if val == "":
                j = i + 1
                while j < n and not _yaml_strip_comment(lines[j]).strip():
                    j += 1
                if j < n:
                    nxt = _yaml_strip_comment(lines[j])
                    ind2 = indent_of(nxt)
                    if ind2 > indent or (ind2 == indent and nxt.strip().startswith("- ")):
                        sub, i = parse_block(j, ind2)
                        obj[key] = sub
                        continue
                obj[key] = None
                i += 1
                continue
            obj[key] = _yaml_scalar(val)
            i += 1
        return (obj if obj is not None else {}), i

    val, _ = parse_block(0, 0)
    return val if isinstance(val, dict) else {}


def load_yaml(text: str) -> dict:
    """portfolio.yml 텍스트 → dict. 비어 있거나 매핑이 아니면 {}"""
    if not text or not text.strip():
        return {}
    if _yaml is not None:
        data = _yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    return _parse_simple_yaml(text)


# ── 메타데이터 정규화 ─────────────────────────────────────────────────────────
def _as_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).strip()


def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if isinstance(v, (list, tuple)):
        return [_as_str(x) for x in v if _as_str(x)]
    return [_as_str(v)]


def parse_ym(v) -> date | None:
    """'2026.05' / '2026-05' / '2026/5' / '2026' / date → date(연, 월, 1). 실패 시 None"""
    if isinstance(v, (date, datetime)):
        return date(v.year, v.month, 1)
    s = _as_str(v)
    m = re.match(r'^(\d{4})(?:[.\-/](\d{1,2}))?', s)
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2) or 1)
    if not 1 <= month <= 12:
        return None
    return date(year, month, 1)


def fmt_ym(d: date | None) -> str:
    return f"{d.year}.{d.month:02d}" if d else ""


def slugify(s: str) -> str:
    s = re.sub(r'[^A-Za-z0-9가-힣]+', '-', s).strip('-').lower()
    return s or "project"


def is_ongoing(status: str | None, ended: date | None, last_commit: date | None,
               today: date | None = None) -> bool:
    """
    진행 중 여부. 명시적 status 가 최우선이고, 없으면 Date 기준으로 판단한다.
      active                          → True
      completed/paused/unused/archived → False
      status 없음 + ended 명시         → False
      status 없음 + 마지막 커밋 최근    → True (ONGOING_GRACE_MONTHS 이내)
    """
    if status == "active":
        return True
    if status in ("completed", "paused", "unused", "archived"):
        return False
    if ended:
        return False
    if last_commit:
        today = today or date.today()
        months = (today.year - last_commit.year) * 12 + (today.month - last_commit.month)
        return months <= ONGOING_GRACE_MONTHS
    return False


def format_period(started: str, ended: str, ongoing: bool, fallback: str = "") -> str:
    if not started:
        return fallback or "?"
    if ongoing:
        return f"{started} – Present"
    if ended and ended != started:
        return f"{started} – {ended}"
    return started


def normalize_metadata(name: str, repo: dict, yml: dict | None, content: dict,
                       commit_start: str, commit_end: str,
                       today: date | None = None) -> dict:
    """
    portfolio.yml(yml)  >  README 기반 content(Claude/파서)  >  repo metadata
    순으로 병합해 표시용 메타데이터를 만든다.

    status / started / ended / featured / live_url / unused_reason / pause_reason /
    replaced_by 는 portfolio.yml 에서만 읽는다 (AI·파서가 추정하지 않음).

    반환 dict 는 render_card 가 쓰는 새 키와 함께 기존 키
    (proj_title, subtitle, intro, tech_items, features, team, my_role) 도 유지한다.
    """
    yml = yml or {}
    content = content or {}
    has_yml = bool(yml)

    title      = _as_str(yml.get("title")) or _as_str(content.get("proj_title")) or name
    subtitle   = _as_str(yml.get("subtitle")) or _as_str(content.get("subtitle")) \
                 or _as_str(repo.get("description"))
    summary    = _as_str(yml.get("summary")) or _as_str(content.get("intro"))
    tech       = _as_list(yml.get("tech")) or list(content.get("tech_items") or [])
    highlights = _as_list(yml.get("highlights")) or list(content.get("features") or [])
    team       = _as_list(yml.get("team")) or list(content.get("team") or [])
    role       = _as_list(yml.get("role"))
    my_role    = " · ".join(role) if role else _as_str(content.get("my_role"))

    status_raw = _as_str(yml.get("status")).lower()
    status     = status_raw if status_raw in VALID_STATUSES else None

    started_d      = parse_ym(yml.get("started")) or parse_ym(commit_start)
    ended_explicit = parse_ym(yml.get("ended"))
    last_commit    = parse_ym(commit_end)
    ongoing        = is_ongoing(status, ended_explicit, last_commit, today)
    ended_d        = None if ongoing else (ended_explicit or last_commit)

    replaced = yml.get("replaced_by")
    replaced_by = None
    if isinstance(replaced, dict):
        rb = {k: _as_str(replaced.get(k)) for k in ("title", "repository", "url")}
        if any(rb.values()):
            replaced_by = rb

    cover = yml.get("cover")
    cover_image = _as_str(cover.get("image")) if isinstance(cover, dict) else _as_str(cover)
    live_url = _as_str(yml.get("live_url"))

    return {
        # 식별
        "slug":            _as_str(yml.get("slug")) or slugify(name),
        "repo":            name,
        "has_portfolio_yml": has_yml,
        # 표시
        "title":           title,
        "subtitle":        subtitle,
        "summary":         summary,
        "status":          status,
        "status_raw":      status_raw,
        "started":         fmt_ym(started_d),
        "ended":           fmt_ym(ended_d),
        "ongoing":         ongoing,
        "featured":        bool(yml.get("featured")),
        # http(s) URL 만 표시. 형식이 틀리면 비우고 validate_metadata 가 경고한다
        "live_url":        live_url if re.match(r'^https?://', live_url) else "",
        "repository_url":  _as_str(yml.get("repository_url")) or _as_str(repo.get("html_url")),
        "category":        _as_list(yml.get("category")),
        "role":            role,
        "tech":            tech,
        "highlights":      highlights,
        "team":            team,
        "my_role":         my_role,
        "unused_reason":   _as_str(yml.get("unused_reason")),
        "pause_reason":    _as_str(yml.get("pause_reason")),
        "replaced_by":     replaced_by,
        "cover_image":     cover_image,
        "indexable":       yml.get("indexable") is not False,
        "screenshot_refresh": bool(yml.get("screenshot_refresh")),
        # 기존 호환 키
        "proj_title":      title,
        "intro":           summary,
        "tech_items":      tech,
        "features":        highlights,
    }


def validate_metadata(meta: dict, yml: dict | None, name: str) -> list[str]:
    """portfolio.yml 값 검증. 경고 문자열 목록 반환 (오류로 중단하지 않음)."""
    yml = yml or {}
    warns: list[str] = []
    if not meta.get("has_portfolio_yml"):
        return warns
    if not _as_str(yml.get("title")):
        warns.append("title 누락 — README/레포 이름으로 대체")
    if not meta["status_raw"]:
        warns.append("status 누락 — active/completed/paused/unused/archived 중 하나를 권장")
    elif meta["status"] is None:
        warns.append(f"지원되지 않는 status '{meta['status_raw']}' — 기본 표시로 처리")
    st = meta["status"]
    if st == "unused" and not meta["unused_reason"]:
        warns.append("status=unused 인데 unused_reason 없음")
    if st == "completed" and not parse_ym(yml.get("ended")):
        warns.append("status=completed 인데 ended 없음 — 마지막 커밋 월로 대체")
    if st == "active" and parse_ym(yml.get("ended")):
        warns.append("status=active 인데 ended 가 지정됨 — active 는 ended 를 비워둔다 (무시함)")
    if "started" in yml and yml.get("started") is not None and not parse_ym(yml.get("started")):
        warns.append(f"started 형식 인식 불가 '{_as_str(yml.get('started'))}' — YYYY-MM 권장")
    if "ended" in yml and yml.get("ended") is not None and not parse_ym(yml.get("ended")):
        warns.append(f"ended 형식 인식 불가 '{_as_str(yml.get('ended'))}' — YYYY-MM 권장")
    if not parse_ym(yml.get("started")):
        warns.append("started 없음 — 첫 커밋 월로 추정")
    live = _as_str(yml.get("live_url"))
    if live and not re.match(r'^https?://', live):
        warns.append(f"live_url 이 http(s) URL 이 아님 — 표시하지 않음: '{live}'")
    return warns


# ── HTML 카드 렌더링 ───────────────────────────────────────────────────────────
def _li(items: list[str]) -> str:
    return "\n".join(f"              <li>{html_escape(i)}</li>" for i in items)


def _links_html(meta: dict) -> str:
    """Live Demo / GitHub 링크 섹션. unused 는 Live Demo 를 숨긴다."""
    links = ""
    live = meta.get("live_url", "")
    repo_url = meta.get("repository_url", "")
    if live and meta.get("status") != "unused":
        links += (f'\n              <a class="proj-link live" href="{html_escape(live, quote=True)}"'
                  f' target="_blank" rel="noopener">Live Demo</a>')
    if repo_url:
        links += (f'\n              <a class="proj-link" href="{html_escape(repo_url, quote=True)}"'
                  f' target="_blank" rel="noopener">GitHub</a>')
    if not links:
        return ""
    return f"""
          <div class="dl-section">
            <h4>Links</h4>
            <div class="proj-links">{links}
            </div>
          </div>"""


def _badge_html(status: str | None) -> str:
    if not status:
        return ""
    return (f'\n            <span class="status-badge status-{status}">'
            f'{STATUS_LABEL[status]}</span>')


def _render_unused_card(name: str, meta: dict, period_str: str) -> str:
    """
    unused 프로젝트: 제목 · 기간 · 상태 · 미사용 사유 · (선택) 대체 프로젝트 · (선택) Repository 만 표시.
    기술 스택 / 주요 기능 / 긴 소개 / Live Demo 는 표시하지 않는다.
    """
    E = html_escape
    reason = meta.get("unused_reason") or ""
    reason_html = "<br>\n              ".join(E(l) for l in reason.splitlines() if l.strip())
    sub = E(meta.get("subtitle") or (reason.splitlines()[0] if reason.strip() else ""))

    replaced_html = ""
    rb = meta.get("replaced_by")
    if rb and rb.get("title"):
        link = rb.get("url") or rb.get("repository")
        if link:
            replaced_html = f"""
          <div class="dl-section">
            <h4>대체 프로젝트</h4>
            <p>이 프로젝트는 {E(rb["title"])}(으)로 통합되었습니다.<br>
              <a href="{E(link, quote=True)}" target="_blank" rel="noopener">→ {E(rb["title"])} 보기</a></p>
          </div>"""
        else:
            replaced_html = f"""
          <div class="dl-section">
            <h4>대체 프로젝트</h4>
            <p>이 프로젝트는 {E(rb["title"])}(으)로 통합되었습니다.</p>
          </div>"""

    repo_url = meta.get("repository_url", "")
    repo_html = ""
    if repo_url:
        repo_html = f"""
          <div class="dl-section">
            <h4>Repository</h4>
            <p><a href="{E(repo_url, quote=True)}" target="_blank" rel="noopener">{E(repo_url)}</a></p>
          </div>"""

    reason_section = ""
    if reason_html:
        reason_section = f"""
          <div class="dl-section">
            <h4>미사용 사유</h4>
            <p>{reason_html}</p>
          </div>"""

    return f"""
      <!-- AUTO:{name} -->
      <details class="proj-unused" data-status="unused" data-slug="{E(meta["slug"], quote=True)}">
        <summary>
          <span class="proj-period">{E(period_str)}</span>
          <div class="proj-main">
            <div class="proj-title">{E(meta["title"])}</div>{_badge_html("unused")}
            <div class="proj-sub">{sub}</div>
          </div>
          <span class="arrow">▶</span>
        </summary>
        <div class="detail">{reason_section}{replaced_html}{repo_html}
        </div>
      </details>
      <!-- /AUTO:{name} -->"""


def render_card(name: str, repo: dict, meta: dict) -> str:
    """정규화된 메타데이터(normalize_metadata 결과) → <details> 카드 HTML. 모든 텍스트는 이스케이프한다."""
    E = html_escape
    lang = repo.get("language") or ""
    tag_cls, tag_lbl = LANG_TAG.get(lang, ("dev", lang or "Code"))

    period_str = format_period(
        meta["started"], meta["ended"], meta["ongoing"],
        fallback=(repo.get("updated_at") or "")[:7].replace("-", "."),
    )
    status = meta.get("status")

    if status == "unused":
        return _render_unused_card(name, meta, period_str)

    # 기술 chips
    chip_html = ""
    for item in (meta["tech"] or [tag_lbl])[:7]:
        chip_html += f'\n              <span class="chip {tag_cls}">{E(item)}</span>'

    # 소개 (줄바꿈 → <br>)
    intro_html = "<br>\n              ".join(
        E(line) for line in meta["summary"].splitlines() if line.strip()
    ) or "내용을 입력하세요."

    # 기능 섹션
    feature_html = ""
    if meta["highlights"]:
        feature_html = f"""
          <div class="dl-section">
            <h4>주요 기능</h4>
            <ul>
{_li(meta["highlights"])}
            </ul>
          </div>"""

    # 일시 중단 사유
    paused_html = ""
    if status == "paused" and meta.get("pause_reason"):
        paused_html = f"""
          <div class="dl-section">
            <h4>일시 중단 사유</h4>
            <p>{E(meta["pause_reason"])}</p>
          </div>"""

    # 팀 섹션
    team_html = ""
    if meta["team"]:
        members = ""
        for item in meta["team"]:
            # "이름 — 역할" 형식 파싱
            if "—" in item or "-" in item:
                parts = re.split(r'\s*[—\-]\s*', item, maxsplit=1)
                member_name = parts[0].strip()
                member_role = parts[1].strip() if len(parts) > 1 else ""
                me_tag = '<span class="me">me</span>' if "이상호" in member_name else ""
                members += f"""
              <div class="member-card">
                <div class="member-name">{E(member_name)}{me_tag}</div>
                <div class="member-role">{E(member_role)}</div>
              </div>"""
            else:
                members += f"""
              <div class="member-card">
                <div class="member-name">{E(item)}</div>
              </div>"""
        team_html = f"""
          <div class="dl-section">
            <h4>팀 구성</h4>
            <div class="member-grid">{members}
            </div>
          </div>"""

    # 내 역할 섹션
    role_html = ""
    if meta.get("my_role"):
        role_html = f"""
          <div class="dl-section">
            <h4>담당 역할</h4>
            <p>{E(meta["my_role"])}</p>
          </div>"""

    data_attrs = f' data-status="{status}"' if status else ""
    data_attrs += f' data-slug="{E(meta["slug"], quote=True)}"'
    if meta.get("featured"):
        data_attrs += ' data-featured="true"'

    return f"""
      <!-- AUTO:{name} -->
      <details{data_attrs}>
        <summary>
          <span class="proj-period">{E(period_str)}</span>
          <div class="proj-main">
            <div class="proj-title">{E(meta["title"])}</div>{_badge_html(status)}
            <div class="proj-sub">{E(meta["subtitle"])}</div>
            <div class="proj-chips">{chip_html}
            </div>
          </div>
          <span class="arrow">▶</span>
        </summary>
        <div class="detail">
          <div class="dl-section">
            <h4>프로젝트 소개</h4>
            <p>{intro_html}</p>
          </div>{feature_html}{paused_html}{role_html}{_links_html(meta)}{team_html}
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
    global FIXTURE_DIR, INDEX_HTML, CONFIG_FILE

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true", help="파일 수정 없이 탐지만")
    parser.add_argument("--force",    action="store_true", help="SHA 무시하고 전체 재생성")
    parser.add_argument("--obsidian", metavar="VAULT", help="Obsidian vault 경로 (md 파일 생성)")
    parser.add_argument("--fixtures", metavar="DIR",
                        help="GitHub API 대신 로컬 샘플 디렉터리 사용 (개발/테스트용)")
    parser.add_argument("--index",    metavar="PATH", help="대상 index.html 경로 (기본: 루트 index.html)")
    parser.add_argument("--config",   metavar="PATH", help="대상 projects.json 경로 (기본: scripts/projects.json)")
    args = parser.parse_args()

    if args.fixtures:
        FIXTURE_DIR = Path(args.fixtures).expanduser().resolve()
        if not FIXTURE_DIR.is_dir():
            print(f"[ERROR] fixtures 디렉터리가 없습니다: {FIXTURE_DIR}", file=sys.stderr)
            sys.exit(1)
    if args.index:
        INDEX_HTML = Path(args.index).expanduser().resolve()
    if args.config:
        CONFIG_FILE = Path(args.config).expanduser().resolve()

    using_claude = bool(os.environ.get("ANTHROPIC_API_KEY", ""))
    mode_str = "Claude AI 분석" if using_claude else "README 직접 파싱 (ANTHROPIC_API_KEY 없음)"
    print(f"모드: {mode_str}")
    if FIXTURE_DIR:
        print(f"소스: 로컬 fixtures ({FIXTURE_DIR})")
    else:
        print(f"GitHub repos 조회 중 ({GITHUB_USER})…")
    print()

    cfg      = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}
    excluded = set(cfg.get("excluded", []))
    skip     = set(cfg.get("skip_repos", []))
    repo_cfg = cfg.get("repos", {})

    repos = fetch_repos()
    html  = INDEX_HTML.read_text(encoding="utf-8")

    # 현재 index.html에 이미 존재하는 수동 카드 제목 수집
    existing_titles = scan_existing_titles(html)
    print(f"기존 수동 카드 {len(existing_titles)}개 감지: {', '.join(sorted(existing_titles))}\n")

    changed = False
    stats = {"checked": 0, "updated": 0, "skipped": 0, "failed": 0}
    all_warnings: list[str] = []
    failures: list[str] = []

    for repo in repos:
        name      = repo["name"]
        full_name = repo.get("full_name", f"{GITHUB_USER}/{name}")

        # 제외 목록
        if name in excluded:
            continue

        # 수동 skip 목록
        if name in skip:
            print(f"  [{name}] skip_repos 목록 — 스킵")
            stats["skipped"] += 1
            continue

        stats["checked"] += 1

        # proj-title 기준 중복 체크 (AUTO 블록 내의 카드는 제외)
        auto_titles = set(re.findall(
            r'<!-- AUTO:[\w\-\.]+ -->.*?class="proj-title">([^<]+)<',
            html, re.DOTALL
        ))
        manual_only_titles = existing_titles - auto_titles

        if is_duplicate(name, manual_only_titles):
            print(f"  [{name}] 수동 카드 중복 감지 — 스킵 (skip_repos에 추가 권장)")
            skip.add(name)
            stats["skipped"] += 1
            continue

        # 레포 하나의 오류가 전체 Sync 를 멈추지 않도록 감싼다
        try:
            # README + portfolio.yml 조회
            readme_text, readme_sha = fetch_readme(full_name)
            pf_text, pf_sha = fetch_portfolio_yml(full_name)
            if not readme_text and not pf_text:
                print(f"  [{name}] README / portfolio.yml 없음 — 스킵")
                stats["skipped"] += 1
                continue

            # 변경 감지 (README SHA 또는 portfolio.yml SHA 중 하나라도 바뀌면 갱신)
            saved       = repo_cfg.get(name, {})
            is_new      = name not in repo_cfg
            sha_changed = (readme_sha != saved.get("sha", "")
                           or pf_sha != saved.get("portfolioSha", ""))

            # 플레이스홀더 내용 감지 (해당 카드가 비어있으면 강제 재생성)
            has_placeholder = False
            if card_exists(html, name):
                m = re.search(
                    rf'<!-- AUTO:{re.escape(name)} -->.*?<!-- /AUTO:{re.escape(name)} -->',
                    html, re.DOTALL,
                )
                has_placeholder = bool(m and "내용을 입력하세요." in m.group())

            if not is_new and not sha_changed and not args.force and not has_placeholder:
                print(f"  [{name}] 변경 없음 — 스킵")
                stats["skipped"] += 1
                continue
            if has_placeholder:
                print(f"  [{name}] 빈 카드 감지 — 내용 재생성")

            action = "신규" if is_new else "업데이트"
            print(f"  [{name}] {action} 처리 중…{' (portfolio.yml)' if pf_text else ''}")

            # portfolio.yml 파싱
            yml: dict = {}
            if pf_text:
                try:
                    yml = load_yaml(pf_text)
                except Exception as e:
                    print(f"    [WARN] portfolio.yml 파싱 실패 — README 로 대체: {e}", file=sys.stderr)
                    all_warnings.append(f"{name}: portfolio.yml 파싱 실패 ({e})")
                    yml = {}

            # 기간 (커밋 날짜 — portfolio.yml 값이 없을 때의 보조 수단)
            commit_start, commit_end = fetch_period(full_name)
            if not commit_start:
                commit_start = saved.get("commitStart", saved.get("start", ""))
            if not commit_end:
                commit_end = saved.get("commitEnd", saved.get("end", ""))

            # README 기반 콘텐츠 (portfolio.yml 이 summary/highlights/tech 를 모두 주면 Claude 호출 생략)
            content = None
            yml_complete = bool(yml.get("summary") and yml.get("highlights") and yml.get("tech"))
            if readme_text and not yml_complete:
                content = generate_with_claude(name, full_name, readme_text, repo, commit_start, commit_end)
            if content:
                print(f"    → Claude 분석 완료")
            else:
                content = _parse_readme_fallback(readme_text, repo)
                if readme_text and not yml_complete:
                    print(f"    → README 파싱 (폴백)")

            meta = normalize_metadata(name, repo, yml, content, commit_start, commit_end)

            for w in validate_metadata(meta, yml, name):
                print(f"    [WARN] {w}")
                all_warnings.append(f"{name}: {w}")

            print(f"    제목: {meta['title']}")
            if meta["status"]:
                print(f"    상태: {meta['status']} ({STATUS_LABEL[meta['status']]})")
            print(f"    기간: {format_period(meta['started'], meta['ended'], meta['ongoing'])}")
            print(f"    기술: {meta['tech']}")
            print(f"    기능: {meta['highlights'][:3]}")

            if not args.dry_run:
                card = render_card(name, repo, meta)
                if card_exists(html, name):
                    html = update_card(html, name, card)
                else:
                    html = insert_card(html, card)

                repo_cfg[name] = {
                    "sha":          readme_sha,
                    "portfolioSha": pf_sha,
                    "start":        meta["started"],
                    "end":          meta["ended"],
                    "commitStart":  commit_start,
                    "commitEnd":    commit_end,
                    "status":       meta["status"],
                    "title":        meta["title"],
                }
                changed = True
                print(f"    → 카드 {'삽입' if is_new else '교체'} 완료")
            stats["updated"] += 1

        except Exception as e:
            stats["failed"] += 1
            failures.append(f"{name}: {e}")
            print(f"    [ERROR] {name} 처리 실패 — 기존 데이터 유지: {e}", file=sys.stderr)

        print()

    if changed and not args.dry_run:
        html = reorder_auto_section(html, repo_cfg)
        INDEX_HTML.write_text(html, encoding="utf-8")
        cfg["repos"]      = repo_cfg
        cfg["excluded"]   = sorted(excluded)
        cfg["skip_repos"] = sorted(skip)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("index.html 및 projects.json 저장 완료.")
        print("git add index.html scripts/projects.json && git commit -m 'sync projects' && git push")

        # Obsidian md 생성
        if args.obsidian:
            _write_obsidian(args.obsidian, repo_cfg)

    elif not changed and not args.dry_run:
        print("업데이트할 내용 없음.")

    # 요약
    print()
    print(f"Checked: {stats['checked']}  Updated: {stats['updated']}  "
          f"Skipped: {stats['skipped']}  Failed: {stats['failed']}  Warnings: {len(all_warnings)}")
    if args.dry_run:
        print("Dry run — 파일을 수정하지 않았습니다.")
    for w in all_warnings:
        print(f"  [WARN] {w}")
    for f in failures:
        print(f"  [ERROR] {f}")
    if failures:
        sys.exit(2)


if __name__ == "__main__":
    main()
