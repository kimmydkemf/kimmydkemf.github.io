#!/usr/bin/env python3
"""
validate_site.py — commit/push 전에 사이트 산출물을 검사한다 (네트워크 없음)
===========================================================================
검사 항목:
  1. data/projects.generated.json  — JSON 파싱, schemaVersion, 필수 필드, slug 중복, status/URL 형식
  2. index.html                    — AUTO 마커, <details> 균형, 정적 카드 == JSON 프로젝트, css/js 로더
  3. CNAME                         — dounselor.com 유지 (Pages 커스텀 도메인 보호)
  4. Secret 패턴                   — 커밋 대상 파일에 토큰/키가 없는지
  5. 파일 크기                     — 커밋 대상 파일이 너무 크지 않은지

사용법:
  python3 scripts/validate_site.py                     # 기본 대상 검사
  python3 scripts/validate_site.py --files a b c       # Secret/크기 검사 대상 지정
  python3 scripts/validate_site.py --root PATH         # 다른 사본 검사 (Preview 등)

종료 코드: 0 = 통과 (경고는 있을 수 있음), 1 = 실패
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_CNAME = "dounselor.com"
VALID_STATUSES = {"active", "completed", "paused", "unused", "archived"}
VALID_SOURCES = {"github", "manual"}
MAX_FILE_BYTES = 5 * 1024 * 1024
DEFAULT_FILES = ("index.html", "data/projects.generated.json", "data/projects.manual.json",
                 "scripts/projects.json")

SECRET_PATTERNS = [
    ("GitHub token",        re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
    ("GitHub fine-grained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("Anthropic key",       re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI key",          re.compile(r"\bsk-(proj-)?[A-Za-z0-9]{32,}\b")),
    ("AWS access key",      re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Private key",         re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def scan_secrets(text: str) -> list[str]:
    return [name for name, pat in SECRET_PATTERNS if pat.search(text)]


def check_generated(root: Path, r: Report) -> list[dict]:
    path = root / "data" / "projects.generated.json"
    if not path.exists():
        r.error(f"{path.relative_to(root)} 없음")
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        r.error(f"projects.generated.json 파싱 실패: {e}")
        return []
    if data.get("schemaVersion") != 1:
        r.error(f"schemaVersion 이 1 이 아님: {data.get('schemaVersion')!r}")
    projects = data.get("projects")
    if not isinstance(projects, list):
        r.error("projects 가 배열이 아님")
        return []
    if not projects:
        r.error("projects 가 비어 있음 — sync 실패 가능성 (기존 데이터를 덮어쓰지 않도록 중단)")
    seen = set()
    for i, p in enumerate(projects):
        label = p.get("slug") or f"#{i}"
        for key in ("slug", "title", "source"):
            if not p.get(key):
                r.error(f"[{label}] 필수 필드 누락: {key}")
        if p.get("slug") in seen:
            r.error(f"[{label}] slug 중복")
        seen.add(p.get("slug"))
        if p.get("source") and p["source"] not in VALID_SOURCES:
            r.error(f"[{label}] 알 수 없는 source: {p['source']!r}")
        if p.get("status") is not None and p["status"] not in VALID_STATUSES:
            r.error(f"[{label}] 알 수 없는 status: {p['status']!r}")
        for key in ("liveUrl", "repositoryUrl"):
            v = p.get(key) or ""
            if v and not re.match(r"^https?://", v):
                r.error(f"[{label}] {key} 가 http(s) URL 이 아님: {v!r}")
        for key, f in (p.get("screenshots") or {}).items():
            if f and not (root / f).exists():
                r.error(f"[{label}] screenshots.{key} 파일 없음: {f}")
        if p.get("syncStatus") == "unavailable":
            r.warn(f"[{label}] syncStatus=unavailable (레포 삭제/비공개?) — 확인 후 필요하면 excluded 에 추가")
    return projects


def check_index(root: Path, projects: list[dict], r: Report) -> None:
    path = root / "index.html"
    if not path.exists():
        r.error("index.html 없음")
        return
    html = path.read_text(encoding="utf-8")
    for marker in ("<!-- AUTO:START", "<!-- AUTO:END -->"):
        n = html.count(marker)
        if n != 1:
            r.error(f"index.html 의 '{marker}' 마커가 {n}개 (1개여야 함)")
    opened, closed = html.count("<details"), html.count("</details>")
    if opened != closed:
        r.error(f"index.html <details> 불균형: {opened} / {closed}")
    if 'href="assets/css/style.css"' not in html:
        r.error("index.html 에 style.css 링크 없음")
    if 'src="assets/js/projects.js"' not in html:
        r.warn("index.html 에 projects.js 로더 없음 (필터/JSON 렌더 비활성)")
    s, e = html.find("<!-- AUTO:START"), html.find("<!-- AUTO:END -->")
    if s != -1 and e != -1 and projects:
        region = html[s:e]
        ids = re.findall(r'<details[^>]*\bid="proj-([^"]+)"', region)
        slugs = [p.get("slug") for p in projects]
        if sorted(ids) != sorted(slugs):
            missing = sorted(set(slugs) - set(ids))
            extra = sorted(set(ids) - set(slugs))
            r.error(f"index.html 정적 카드와 JSON 불일치 — 누락 {missing} / 초과 {extra}")


def check_cname(root: Path, r: Report) -> None:
    path = root / "CNAME"
    if not path.exists():
        r.error("CNAME 없음 — dounselor.com 연결이 끊어짐")
        return
    value = path.read_text(encoding="utf-8").strip()
    if value != EXPECTED_CNAME:
        r.error(f"CNAME 이 '{value}' — '{EXPECTED_CNAME}' 이어야 함")


def check_files(root: Path, files: list[str], r: Report) -> None:
    for f in files:
        path = root / f
        if not path.exists() or path.is_dir():
            continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            r.error(f"{f} 크기 {size // 1024}KB — {MAX_FILE_BYTES // 1024 // 1024}MB 초과")
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            r.error(f"{f} — .env 파일은 커밋하지 않음")
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name in scan_secrets(text):
            r.error(f"{f} 에 Secret 패턴 발견: {name}")


def validate(root: Path, files: list[str]) -> Report:
    r = Report()
    projects = check_generated(root, r)
    check_index(root, projects, r)
    check_cname(root, r)
    check_files(root, files, r)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--files", nargs="*", help="Secret/크기 검사 대상 (기본: sync 산출물)")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    files = args.files if args.files is not None else list(DEFAULT_FILES)
    r = validate(root, files)
    for w in r.warnings:
        print(f"  [WARN] {w}")
    for e in r.errors:
        print(f"  [FAIL] {e}")
    if r.errors:
        print(f"Validation 실패: 오류 {len(r.errors)}개, 경고 {len(r.warnings)}개")
        sys.exit(1)
    print(f"Validation 통과 (경고 {len(r.warnings)}개)")


if __name__ == "__main__":
    main()
