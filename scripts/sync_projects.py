#!/usr/bin/env python3
"""
sync_projects.py
----------------
GitHub API로 kimmydkemf의 새 repo를 감지하면:
  1. index.html에 프로젝트 카드 플레이스홀더를 자동 삽입
  2. --obsidian <vault_path> 옵션을 주면 Obsidian md 파일도 생성

사용법:
  # GitHub Actions (GITHUB_TOKEN 환경변수 필요)
  python3 scripts/sync_projects.py

  # 로컬 (Obsidian md 생성 포함)
  GITHUB_TOKEN=ghp_xxxx python3 scripts/sync_projects.py \
    --obsidian ~/Workspace/MyNotes
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

GITHUB_USER = "kimmydkemf"
INDEX_HTML   = Path(__file__).parent.parent / "index.html"
CONFIG_FILE  = Path(__file__).parent / "projects.json"
AUTO_START   = "<!-- AUTO:START"
AUTO_END     = "<!-- AUTO:END -->"

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
}


def github_get(url: str) -> dict | list:
    token = os.environ.get("GITHUB_TOKEN", "")
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def fetch_repos() -> list[dict]:
    url = f"https://api.github.com/users/{GITHUB_USER}/repos?per_page=100&sort=updated"
    return github_get(url)


def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {"known": [], "excluded": []}


def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")


def make_card(repo: dict) -> str:
    name        = repo["name"]
    description = repo.get("description") or "설명을 입력하세요."
    language    = repo.get("language") or ""
    url         = repo.get("html_url", "")
    updated     = repo.get("updated_at", "")[:10]

    tag_class, tag_label = LANG_TAG.get(language, ("dev", language or "Code"))

    return f"""
      <!-- AUTO:{name} -->
      <details>
        <summary>
          <span class="proj-period">{updated[:7]}</span>
          <div class="proj-main">
            <div class="proj-title">{name}</div>
            <div class="proj-sub">{description}</div>
            <div class="proj-chips">
              <span class="chip {tag_class}">{tag_label}</span>
            </div>
          </div>
          <span class="arrow">▶</span>
        </summary>
        <div class="detail">
          <div class="dl-section">
            <h4>프로젝트 소개</h4>
            <p>내용을 입력하세요.</p>
          </div>
          <div class="dl-section">
            <h4>Repository</h4>
            <p><a href="{url}" target="_blank">{url}</a></p>
          </div>
        </div>
      </details>"""


def insert_into_html(card: str):
    html = INDEX_HTML.read_text(encoding="utf-8")
    if AUTO_END not in html:
        print(f"[ERROR] {AUTO_END} 마커를 index.html에서 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)
    html = html.replace(AUTO_END, card + "\n      " + AUTO_END)
    INDEX_HTML.write_text(html, encoding="utf-8")


def make_obsidian_md(repo: dict, vault: Path) -> Path:
    name        = repo["name"]
    description = repo.get("description") or ""
    language    = repo.get("language") or ""
    url         = repo.get("html_url", "")
    updated     = repo.get("updated_at", "")[:10]
    today       = datetime.now().strftime("%Y-%m-%d")

    target_dir = vault / "20-projects" / name
    target_dir.mkdir(parents=True, exist_ok=True)
    md_path = target_dir / f"{name}.md"

    content = f"""# {name}

> {description}

## 기본 정보

- **언어**: {language}
- **GitHub**: {url}
- **마지막 업데이트**: {updated}
- **메모 생성**: {today}

## 프로젝트 소개

<!-- 내용을 입력하세요 -->

## 기술 스택

<!-- 사용한 기술을 입력하세요 -->

## 주요 기능

<!-- 주요 기능을 나열하세요 -->

## 팀 구성

<!-- 팀원을 나열하세요 -->
"""
    md_path.write_text(content, encoding="utf-8")
    return md_path


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--obsidian", metavar="PATH",
                        help="Obsidian vault 경로 (md 파일 생성)")
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 파일 수정 없이 탐지만 출력")
    args = parser.parse_args()

    cfg  = load_config()
    known    = set(cfg.get("known", []))
    excluded = set(cfg.get("excluded", []))

    print(f"GitHub API: {GITHUB_USER} repos 조회 중...")
    try:
        repos = fetch_repos()
    except urllib.error.URLError as e:
        print(f"[ERROR] GitHub API 요청 실패: {e}", file=sys.stderr)
        sys.exit(1)

    new_repos = [
        r for r in repos
        if r["name"] not in known and r["name"] not in excluded
    ]

    if not new_repos:
        print("새 repo 없음 — 업데이트 불필요.")
        return

    for repo in new_repos:
        name = repo["name"]
        print(f"  새 repo 발견: {name}")
        if args.dry_run:
            continue

        # 1. index.html에 카드 삽입
        card = make_card(repo)
        insert_into_html(card)
        print(f"    → index.html에 카드 삽입 완료")

        # 2. Obsidian md 생성 (옵션)
        if args.obsidian:
            vault = Path(args.obsidian).expanduser()
            md = make_obsidian_md(repo, vault)
            print(f"    → Obsidian md 생성: {md}")

        # 3. known 목록에 추가
        known.add(name)

    if not args.dry_run:
        cfg["known"] = sorted(known)
        save_config(cfg)
        print("projects.json 업데이트 완료.")


if __name__ == "__main__":
    main()
