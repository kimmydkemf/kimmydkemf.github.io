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
  6. data/projects.generated.json 생성 (github 프로젝트 + data/projects.manual.json 의 과거 프로젝트)
  7. 같은 JSON 으로 index.html AUTO:START~AUTO:END 구간의 정적 카드 재생성 (render_cards.py)
     브라우저에서는 assets/js/projects.js 가 같은 JSON 을 다시 렌더링한다.

우선순위:  portfolio.yml  >  README (Claude / 파서)  >  GitHub repo metadata
변경 없는 레포는 이전 JSON 항목을 그대로 재사용하고, 목록에서 사라진 레포는
syncStatus: unavailable 로 표시만 하고 삭제하지 않는다.

사용법:
  GITHUB_TOKEN=ghp_xxx ANTHROPIC_API_KEY=sk-ant-xxx python3 scripts/sync_projects.py
  ... --dry-run            # 변경 없이 탐지만
  ... --force              # SHA 무시하고 전체 재생성
  ... --fixtures DIR       # GitHub 대신 로컬 샘플 데이터 사용 (네트워크 없음, 개발/테스트용)
  ... --index PATH         # 대상 index.html 경로 지정 (기본: 저장소 루트 index.html)
  ... --config PATH        # 대상 projects.json 경로 지정 (기본: scripts/projects.json)
  ... --generated PATH     # 대상 projects.generated.json 경로 (기본: data/projects.generated.json)
  ... --manual PATH        # 수동 프로젝트 JSON 경로 (기본: data/projects.manual.json)
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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_cards import (  # noqa: E402
    STATUS_LABEL, PLACEHOLDER, format_period, render_auto_section,
)
from screenshot_projects import attach_screenshots  # noqa: E402

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
GENERATED_JSON = ROOT / "data" / "projects.generated.json"
MANUAL_JSON    = ROOT / "data" / "projects.manual.json"
SCHEMA_VERSION = 1
KST = timezone(timedelta(hours=9))

PORTFOLIO_FILE = "portfolio.yml"
VALID_STATUSES = ("active", "completed", "paused", "unused", "archived")
# 팀 구성에서 "me" 표시를 붙일 이름
OWNER_NAMES = ("이상호",)
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


def _owner_of(repo: dict) -> str:
    owner = (repo.get("owner") or {}).get("login") if isinstance(repo.get("owner"), dict) else None
    return owner or (repo.get("full_name") or "").split("/")[0]


def fetch_repos() -> list[dict]:
    """본인(GITHUB_USER) 소유 레포만 반환한다.
    다른 사람 소유 레포(collaborator 등)는 읽지 않는다 — 필요하면 data/projects.manual.json 에 직접 기록."""
    if FIXTURE_DIR:
        return _fixture_repos()
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        repos = _gh(
            "https://api.github.com/user/repos"
            "?per_page=100&sort=updated&affiliation=owner"
        ) or []
    else:
        repos = _gh(
            f"https://api.github.com/users/{GITHUB_USER}/repos"
            "?per_page=100&sort=updated&type=owner"
        ) or []
    owned = [r for r in repos if _owner_of(r).lower() == GITHUB_USER.lower()]
    if len(owned) != len(repos):
        print(f"  다른 사람 소유 레포 {len(repos) - len(owned)}개는 조회하지 않음")
    return owned


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
        result["subtitle"] = smart_truncate(intro_lines[0], SUBTITLE_MAX)

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
    """따옴표 밖의 ' #' 부터 주석으로 잘라낸다 (따옴표 안의 # 은 내용)"""
    if line.lstrip().startswith("#"):
        return ""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and i > 0 and line[i - 1] in (" ", "\t"):
            return line[:i]
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
    tech_from_yml = bool(_as_list(yml.get("tech")))
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
        "tech_from_yml":   tech_from_yml,
        "highlights":      highlights,
        "team":            team,
        "my_role":         my_role,
        "unused_reason":   _as_str(yml.get("unused_reason")),
        "pause_reason":    _as_str(yml.get("pause_reason")),
        "replaced_by":     replaced_by,
        "cover_image":     cover_image,
        "indexable":       yml.get("indexable") is not False,
        "screenshot_refresh": bool(yml.get("screenshot_refresh")),
        "screenshot_enabled": yml.get("screenshot") is not False,
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


# ── 태그 · 부제 정리 ──────────────────────────────────────────────────────────
SUBTITLE_MAX = 80
TECH_STORE_MAX = 10
# README 에서 흔히 쓰는 표기 → 짧은 이름 (소문자 비교). 값이 "" 이면 버린다.
TECH_ALIASES = {
    "better-sqlite3": "SQLite", "sqlite": "SQLite", "next-pwa": "PWA",
    "next.js api routes": "Next.js", "node-telegram-bot-api": "Telegram Bot",
    "cloudflared": "Cloudflare Tunnel", "cloudflare named tunnel": "Cloudflare Tunnel",
    "named tunnel": "Cloudflare Tunnel",
    "jose": "JWT", "jsonwebtoken": "JWT", "google gemini": "Gemini",
    "anthropic claude api": "Claude API", "anthropic claude": "Claude",
    "pc": "", "in-memory pub/sub": "",
}
_HANGUL_WORD = re.compile(r"(?:^|\s)[가-힣]+(?=\s|$)")
_VERSION_TAIL = re.compile(r"\s+v?\d+(?:\.\d+)*[a-z]?$", re.I)


def smart_truncate(text: str, limit: int) -> str:
    """단어 경계에서 자르고 … 를 붙인다 (문장 중간 잘림 방지)"""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,·-—(") + "…"


def normalize_tech(items: list[str], max_items: int = TECH_STORE_MAX) -> list[str]:
    """README 기술 목록 한 줄("Frontend: Next.js 14 (App Router) · React 18") → 기술 이름 하나씩.
    분류 이름 · 괄호 설명 · 끝의 버전 · 한글 수식어를 떼고, 같은 이름은 한 번만."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in items or []:
        text = str(raw).strip()
        m = re.match(r"^[^:：]{1,24}[:：]\s*(.+)$", text)
        if m and not re.match(r"^https?$", text.split(":")[0], re.I):
            text = m.group(1)
        text = re.sub(r"\([^)]*\)|（[^）]*）", " ", text)                 # 괄호 설명
        for part in re.split(r"\s*[·,，]\s*|\s+\+\s+|\s+&\s+", text):
            part = re.sub(r"\s+", " ", part).strip(" -—`*")
            part = _HANGUL_WORD.sub(" ", part).strip()                     # "로컬 Ollama" → "Ollama"
            if not part:
                continue
            key = part.lower()
            if key in TECH_ALIASES:
                part = TECH_ALIASES[key]
            else:
                part = _VERSION_TAIL.sub("", part).strip()                  # "React 18" → "React"
                for alias, name in TECH_ALIASES.items():
                    if name and part.lower().startswith(alias + " "):        # "Google Gemini 2.5 Flash"
                        part = name
                        break
                if part.lower() in TECH_ALIASES:
                    part = TECH_ALIASES[part.lower()]
            if not part or len(part) > 30 or part.lower() in seen:
                continue
            seen.add(part.lower())
            out.append(part)
            if len(out) >= max_items:
                return out
    return out


def repair_subtitle(subtitle: str, summary: str) -> str:
    """예전 파서가 60자에서 자른 부제(요약 첫 줄의 앞부분)를 단어 경계 기준으로 다시 만든다"""
    sub = (subtitle or "").strip()
    first = next((l.strip() for l in (summary or "").splitlines() if l.strip()), "")
    if sub and first and first != sub and first.startswith(sub):
        return smart_truncate(first, SUBTITLE_MAX)
    return subtitle


# ── JSON 데이터 레이어 ────────────────────────────────────────────────────────
def parse_team_item(item: str) -> dict:
    """'이름 — 역할' → {name, role, me}"""
    item = _as_str(item)
    name, role = item, ""
    if "—" in item or "-" in item:
        parts = re.split(r'\s*[—\-]\s*', item, maxsplit=1)
        name = parts[0].strip()
        role = parts[1].strip() if len(parts) > 1 else ""
    return {"name": name, "role": role, "me": any(n in name for n in OWNER_NAMES)}


def to_project_entry(meta: dict, repo: dict, readme_sha: str = "", pf_sha: str = "",
                     sync_status: str = "ok", last_synced: str | None = None) -> dict:
    """normalize_metadata 결과 → projects.generated.json 의 프로젝트 항목 (camelCase)"""
    lang = repo.get("language") or ""
    tag_cls, tag_lbl = LANG_TAG.get(lang, ("dev", lang or "Code"))
    return {
        "slug":            meta["slug"],
        "repo":            meta["repo"],
        "source":          "github",
        "title":           meta["title"],
        "subtitle":        meta["subtitle"],
        "summary":         meta["summary"],
        "status":          meta["status"],
        "started":         meta["started"],
        "ended":           meta["ended"],
        "ongoing":         meta["ongoing"],
        "featured":        meta["featured"],
        "liveUrl":         meta["live_url"],
        "repositoryUrl":   meta["repository_url"],
        "category":        meta["category"],
        "role":            meta["role"],
        # portfolio.yml 의 tech 는 그대로, README/Claude 에서 온 목록은 기술 이름 단위로 정리
        "tech":            (meta["tech"] if meta.get("tech_from_yml") else normalize_tech(meta["tech"])) or [tag_lbl],
        "highlights":      meta["highlights"],
        "highlightsTitle": None,
        "team":            [parse_team_item(t) for t in meta["team"]],
        "myRole":          meta["my_role"],
        "unusedReason":    meta["unused_reason"],
        "pauseReason":     meta["pause_reason"],
        "replacedBy":      meta["replaced_by"],
        "coverImage":      meta["cover_image"],
        "videos":          [],
        "awards":          [],
        "language":        lang or None,
        "tagClass":        tag_cls,
        "indexable":       meta["indexable"],
        "screenshotRefresh": meta["screenshot_refresh"],
        "screenshotEnabled": meta["screenshot_enabled"],
        "hasPortfolioYml": meta["has_portfolio_yml"],
        "periodFallback":  (repo.get("updated_at") or "")[:7].replace("-", "."),
        "syncStatus":      sync_status,
        "lastSynced":      last_synced,
        "readmeSha":       readme_sha,
        "portfolioSha":    pf_sha,
    }


def load_generated(path: Path) -> dict:
    if not path.exists():
        return {"schemaVersion": SCHEMA_VERSION, "generatedAt": None, "projects": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("projects", [])
    return data


def manual_warnings(manual: list[dict]) -> list[str]:
    """projects.manual.json 에서 사람이 고친 값 중 잘못된 것 (status 오타 등)"""
    warns = []
    for p in manual:
        st = p.get("status")
        if st is not None and st not in VALID_STATUSES:
            warns.append(f"projects.manual.json [{p.get('slug')}]: 지원되지 않는 status {st!r} — "
                         f"{', '.join(VALID_STATUSES)} 또는 null")
    return warns


def load_manual(path: Path) -> list[dict]:
    """data/projects.manual.json — 사람이 편집하는 프로젝트 목록.
    레포가 없는 과거 프로젝트, 그리고 다른 사람 소유라 GitHub 에서 읽지 않는 프로젝트(`repo` 필드 지정)를 둔다.
    `repo` 가 지정된 항목은 sync 가 해당 레포를 GitHub 에서 조회하지 않는다."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    projects = data.get("projects", []) if isinstance(data, dict) else data
    out = []
    for p in projects:
        p = dict(p)
        p.setdefault("source", "manual")
        p.setdefault("slug", slugify(p.get("title", "project")))
        p.setdefault("syncStatus", "ok")
        out.append(p)
    return out


def sort_projects(projects: list[dict], prev_projects: list[dict] | None = None) -> list[dict]:
    """
    시작월 내림차순. 같은 달끼리는 이전 JSON 의 순서를 유지하고(불필요한 diff 방지),
    새 항목은 그 뒤에 입력 순서대로 붙는다.
    """
    prev_pos = {p.get("slug"): i for i, p in enumerate(prev_projects or [])}
    base = len(prev_pos)
    ordered = [t[1] for t in sorted(enumerate(projects),
                                    key=lambda t: prev_pos.get(t[1].get("slug"), base + t[0]))]
    return sorted(ordered, key=lambda p: p.get("started") or "0000.00", reverse=True)


def save_generated(path: Path, projects: list[dict], generated_at: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt":   generated_at or datetime.now(KST).isoformat(timespec="seconds"),
        "projects":      projects,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
    global FIXTURE_DIR, INDEX_HTML, CONFIG_FILE, GENERATED_JSON, MANUAL_JSON

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true", help="파일 수정 없이 탐지만")
    parser.add_argument("--force",    action="store_true", help="SHA 무시하고 전체 재생성")
    parser.add_argument("--obsidian", metavar="VAULT", help="Obsidian vault 경로 (md 파일 생성)")
    parser.add_argument("--fixtures", metavar="DIR",
                        help="GitHub API 대신 로컬 샘플 디렉터리 사용 (개발/테스트용)")
    parser.add_argument("--index",     metavar="PATH", help="대상 index.html 경로 (기본: 루트 index.html)")
    parser.add_argument("--config",    metavar="PATH", help="대상 projects.json 경로 (기본: scripts/projects.json)")
    parser.add_argument("--generated", metavar="PATH", help="대상 projects.generated.json 경로 (기본: data/)")
    parser.add_argument("--manual",    metavar="PATH", help="수동 프로젝트 JSON 경로 (기본: data/projects.manual.json)")
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
    if args.generated:
        GENERATED_JSON = Path(args.generated).expanduser().resolve()
    if args.manual:
        MANUAL_JSON = Path(args.manual).expanduser().resolve()

    using_claude = bool(os.environ.get("ANTHROPIC_API_KEY", ""))
    authenticated = bool(FIXTURE_DIR) or bool(os.environ.get("GITHUB_TOKEN", ""))
    mode_str = "Claude AI 분석" if using_claude else "README 직접 파싱 (ANTHROPIC_API_KEY 없음)"
    print(f"모드: {mode_str}")
    if FIXTURE_DIR:
        print(f"소스: 로컬 fixtures ({FIXTURE_DIR})")
    else:
        print(f"GitHub repos 조회 중 ({GITHUB_USER}){'' if authenticated else ' — 토큰 없음, public 레포만'}…")
    print()

    cfg      = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}
    excluded = set(cfg.get("excluded", []))
    skip     = set(cfg.get("skip_repos", []))
    repo_cfg = cfg.get("repos", {})

    prev        = load_generated(GENERATED_JSON)
    manual      = load_manual(MANUAL_JSON)
    # manual 에서 관리하는 레포 이름 — GitHub 조회 대상에서 제외
    manual_repos = {p["repo"] for p in manual if p.get("repo")}
    prev_github = {p["repo"]: p for p in prev["projects"]
                   if p.get("source") == "github" and p.get("repo") and p["repo"] not in manual_repos}

    repos = fetch_repos()
    if not repos and not FIXTURE_DIR:
        print("[ERROR] 레포 목록을 가져오지 못했습니다 (토큰/권한/rate limit 확인). 아무것도 변경하지 않습니다.",
              file=sys.stderr)
        sys.exit(1)
    html  = INDEX_HTML.read_text(encoding="utf-8")

    # 현재 index.html에 이미 존재하는 수동 카드 제목 수집 (AUTO 구간 밖에 남아 있는 카드 기준)
    existing_titles = scan_existing_titles(html)
    auto_titles = set(re.findall(
        r'<!-- AUTO:[\w\-\.]+ -->.*?class="proj-title">([^<]+)<', html, re.DOTALL
    ))
    manual_only_titles = (existing_titles - auto_titles) | {p.get("title", "") for p in manual}
    print(f"수동 프로젝트 {len(manual)}개 (projects.manual.json), 이전 github 항목 {len(prev_github)}개\n")

    today_str = date.today().isoformat()
    new_entries: dict[str, dict] = {}
    seen: list[str] = []
    stats = {"checked": 0, "updated": 0, "skipped": 0, "failed": 0}
    all_warnings: list[str] = manual_warnings(manual)
    for w in all_warnings:
        print(f"  [WARN] {w}")
    failures: list[str] = []

    for repo in repos:
        name      = repo["name"]
        full_name = repo.get("full_name", f"{GITHUB_USER}/{name}")

        if name in excluded:
            continue
        if name in skip:
            print(f"  [{name}] skip_repos 목록 — 스킵")
            stats["skipped"] += 1
            continue
        if name in manual_repos:
            print(f"  [{name}] projects.manual.json 에서 관리 — GitHub 조회 안 함")
            stats["skipped"] += 1
            continue

        stats["checked"] += 1

        if name not in prev_github and is_duplicate(name, manual_only_titles):
            print(f"  [{name}] 수동 카드 중복 감지 — 스킵 (skip_repos에 추가 권장)")
            skip.add(name)
            stats["skipped"] += 1
            continue

        seen.append(name)

        # 레포 하나의 오류가 전체 Sync 를 멈추지 않도록 감싼다
        try:
            readme_text, readme_sha = fetch_readme(full_name)
            pf_text, pf_sha = fetch_portfolio_yml(full_name)
            if not readme_text and not pf_text:
                print(f"  [{name}] README / portfolio.yml 없음 — 스킵")
                stats["skipped"] += 1
                seen.remove(name)
                continue

            saved       = repo_cfg.get(name, {})
            prev_entry  = prev_github.get(name)
            is_new      = name not in repo_cfg or prev_entry is None
            sha_changed = (readme_sha != saved.get("sha", "")
                           or pf_sha != saved.get("portfolioSha", ""))
            has_placeholder = prev_entry is not None and not prev_entry.get("summary")

            if not is_new and not sha_changed and not args.force and not has_placeholder:
                print(f"  [{name}] 변경 없음 — 스킵")
                stats["skipped"] += 1
                continue
            if has_placeholder and not is_new:
                print(f"  [{name}] 빈 소개 감지 — 내용 재생성")

            action = "신규" if is_new else "업데이트"
            print(f"  [{name}] {action} 처리 중…{' (portfolio.yml)' if pf_text else ''}")

            yml: dict = {}
            if pf_text:
                try:
                    yml = load_yaml(pf_text)
                except Exception as e:
                    print(f"    [WARN] portfolio.yml 파싱 실패 — README 로 대체: {e}", file=sys.stderr)
                    all_warnings.append(f"{name}: portfolio.yml 파싱 실패 ({e})")
                    yml = {}

            commit_start, commit_end = fetch_period(full_name)
            if not commit_start:
                commit_start = saved.get("commitStart", saved.get("start", ""))
            if not commit_end:
                commit_end = saved.get("commitEnd", saved.get("end", ""))

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
            print(f"    기술: {meta['tech'] if meta.get('tech_from_yml') else normalize_tech(meta['tech'])}")
            print(f"    기능: {meta['highlights'][:3]}")

            new_entries[name] = to_project_entry(meta, repo, readme_sha, pf_sha, "ok", today_str)
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
            stats["updated"] += 1

        except Exception as e:
            stats["failed"] += 1
            failures.append(f"{name}: {e}")
            print(f"    [ERROR] {name} 처리 실패 — 기존 데이터 유지: {e}", file=sys.stderr)

        print()

    # ── 프로젝트 목록 조립: 새 항목 + 변경 없는 이전 항목 + 사라진 레포(unavailable) + 수동 ──
    github_entries: list[dict] = []
    for name in seen:
        if name in new_entries:
            github_entries.append(new_entries[name])
        elif name in prev_github:
            entry = dict(prev_github[name])
            if entry.get("syncStatus") == "unavailable":   # 다시 보이면 복구
                entry["syncStatus"] = "ok"
            github_entries.append(entry)
    for name, entry in prev_github.items():
        if name in seen or name in excluded or name in skip:
            continue
        entry = dict(entry)
        if authenticated and entry.get("syncStatus") != "unavailable":
            entry["syncStatus"] = "unavailable"
            msg = f"{name}: 레포 목록에 없음 (삭제/비공개?) — 기존 데이터 유지, syncStatus=unavailable"
            print(f"  [WARN] {msg}")
            all_warnings.append(msg)
        github_entries.append(entry)

    projects = sort_projects(github_entries + manual, prev["projects"])
    # Screenshot (scripts/screenshot_projects.py 가 만든 manifest) 를 붙인다 — 파일이 있을 때만
    shots_manifest = GENERATED_JSON.parent / "screenshots.json"
    if shots_manifest.exists():
        attach_screenshots(projects,
                           json.loads(shots_manifest.read_text(encoding="utf-8")).get("screenshots", {}),
                           GENERATED_JSON.parent.parent)
    changed  = projects != prev["projects"] or args.force

    if changed and not args.dry_run:
        generated_at = datetime.now(KST).isoformat(timespec="seconds")
        save_generated(GENERATED_JSON, projects, generated_at)
        INDEX_HTML.write_text(render_auto_section(html, projects, generated_at), encoding="utf-8")
        cfg["repos"]      = repo_cfg
        cfg["excluded"]   = sorted(excluded)
        cfg["skip_repos"] = sorted(skip)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{GENERATED_JSON.name} ({len(projects)}개), index.html, projects.json 저장 완료.")
        print("git add index.html data/projects.generated.json scripts/projects.json "
              "&& git commit -m 'sync projects' && git push")
        if args.obsidian:
            _write_obsidian(args.obsidian, repo_cfg)
    elif not changed and not args.dry_run:
        print("업데이트할 내용 없음.")

    print()
    print(f"Checked: {stats['checked']}  Updated: {stats['updated']}  "
          f"Skipped: {stats['skipped']}  Failed: {stats['failed']}  Warnings: {len(all_warnings)}"
          f"  Projects: {len(projects)}")
    if args.dry_run:
        print(f"Dry run — 파일을 수정하지 않았습니다. ({'변경 있음' if changed else '변경 없음'})")
    for w in all_warnings:
        print(f"  [WARN] {w}")
    for f in failures:
        print(f"  [ERROR] {f}")
    if failures:
        sys.exit(2)


if __name__ == "__main__":
    main()
