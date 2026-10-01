#!/usr/bin/env python3
"""
sync_projects / render_cards / migrate_index_cards 테스트 (네트워크 없음, fixtures 만 사용)

실행:
  python3 scripts/test_sync_projects.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import sync_projects as sp          # noqa: E402
import render_cards as rc           # noqa: E402
import migrate_index_cards as mig   # noqa: E402

FIXTURES = ROOT / "fixtures" / "repos"
LEGACY_INDEX = ROOT / "fixtures" / "index.legacy.html"
TEMPLATE = ROOT / "docs" / "portfolio.template.yml"
JS_RENDERER = ROOT / "assets" / "js" / "projects.js"
NODE = shutil.which("node")


# ── YAML 파서 ─────────────────────────────────────────────────────────────────
class TestYaml(unittest.TestCase):
    SAMPLE = """
# 주석
title: Sample Tracker
slug: sample-tracker
subtitle: "습관 & 컨디션"
status: active
started: 2026-03
ended:
featured: true
category:
  - Personal
  - Web
tech: [React, FastAPI]
empty_list: []
summary: >
  첫 줄
  둘째 줄
notes: |
  line1
  line2
replaced_by:
  title: Archive
  url: https://archive.example.com
inline_comment: value   # 뒤 주석
"""

    def test_simple_parser(self):
        d = sp._parse_simple_yaml(self.SAMPLE)
        self.assertEqual(d["title"], "Sample Tracker")
        self.assertEqual(d["subtitle"], "습관 & 컨디션")
        self.assertEqual(d["status"], "active")
        self.assertEqual(str(d["started"]), "2026-03")
        self.assertIsNone(d["ended"])
        self.assertIs(d["featured"], True)
        self.assertEqual(d["category"], ["Personal", "Web"])
        self.assertEqual(d["tech"], ["React", "FastAPI"])
        self.assertEqual(d["empty_list"], [])
        self.assertEqual(d["summary"], "첫 줄 둘째 줄")
        self.assertEqual(d["notes"], "line1\nline2")
        self.assertEqual(d["replaced_by"], {"title": "Archive", "url": "https://archive.example.com"})
        self.assertEqual(d["inline_comment"], "value")

    def test_list_at_same_indent(self):
        d = sp._parse_simple_yaml("tech:\n- A\n- B\nnext: x\n")
        self.assertEqual(d["tech"], ["A", "B"])
        self.assertEqual(d["next"], "x")

    @unittest.skipIf(sp._yaml is None, "PyYAML 없음")
    def test_matches_pyyaml_on_fixtures(self):
        files = list(FIXTURES.glob("*/portfolio.yml")) + [TEMPLATE]
        for f in files:
            text = f.read_text(encoding="utf-8")
            ref = sp._yaml.safe_load(text) or {}
            got = sp._parse_simple_yaml(text)
            self.assertEqual(_norm(got), _norm(ref), msg=f"mismatch in {f}")

    def test_load_yaml_non_mapping(self):
        self.assertEqual(sp.load_yaml(""), {})
        self.assertEqual(sp.load_yaml("- a\n- b\n"), {})


def _norm(v):
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if v is None or isinstance(v, bool):
        return v
    return str(v).strip()


# ── 기간 / 상태 ───────────────────────────────────────────────────────────────
class TestPeriod(unittest.TestCase):
    def test_parse_ym(self):
        self.assertEqual(sp.parse_ym("2026.05"), date(2026, 5, 1))
        self.assertEqual(sp.parse_ym("2026-5"), date(2026, 5, 1))
        self.assertEqual(sp.parse_ym("2026/12"), date(2026, 12, 1))
        self.assertEqual(sp.parse_ym("2026"), date(2026, 1, 1))
        self.assertEqual(sp.parse_ym(2026), date(2026, 1, 1))
        self.assertEqual(sp.parse_ym(date(2026, 5, 17)), date(2026, 5, 1))
        self.assertIsNone(sp.parse_ym("어느날"))
        self.assertIsNone(sp.parse_ym("2026.13"))
        self.assertIsNone(sp.parse_ym(None))

    def test_is_ongoing_explicit_status(self):
        today = date(2026, 10, 1)
        self.assertTrue(sp.is_ongoing("active", date(2026, 9, 1), None, today))
        for st in ("completed", "paused", "unused", "archived"):
            self.assertFalse(sp.is_ongoing(st, None, date(2026, 10, 1), today), st)

    def test_is_ongoing_by_date(self):
        today = date(2026, 10, 1)
        self.assertTrue(sp.is_ongoing(None, None, date(2026, 9, 1), today))
        self.assertTrue(sp.is_ongoing(None, None, date(2026, 7, 1), today))
        self.assertFalse(sp.is_ongoing(None, None, date(2026, 5, 1), today))
        self.assertFalse(sp.is_ongoing(None, date(2026, 9, 1), date(2026, 10, 1), today))
        self.assertFalse(sp.is_ongoing(None, None, None, today))

    def test_format_period(self):
        self.assertEqual(sp.format_period("2026.05", "", True), "2026.05 – Present")
        self.assertEqual(sp.format_period("2025.11", "2026.03", False), "2025.11 – 2026.03")
        self.assertEqual(sp.format_period("2021.08", "2021.08", False), "2021.08")
        self.assertEqual(sp.format_period("", "", False, fallback="2026.05"), "2026.05")
        self.assertEqual(sp.format_period("", "", False), "?")

    def test_fetch_period_uses_link_header(self):
        calls = []

        def fake_request(url):
            calls.append(url)
            if "page=57" in url:
                return [{"commit": {"committer": {"date": "2025-09-05T09:00:00Z"}}}], {}
            return ([{"commit": {"committer": {"date": "2026-09-20T10:00:00Z"}}}],
                    {"Link": '<https://api.github.com/x?per_page=1&page=2>; rel="next", '
                             '<https://api.github.com/x?per_page=1&page=57>; rel="last"'})

        orig = sp._gh_request
        sp._gh_request = fake_request
        try:
            self.assertEqual(sp.fetch_period("u/r"), ("2025.09", "2026.09"))
            self.assertEqual(len(calls), 2)
        finally:
            sp._gh_request = orig

    def test_fetch_period_single_page(self):
        orig = sp._gh_request
        sp._gh_request = lambda url: ([{"commit": {"committer": {"date": "2026-01-01T00:00:00Z"}}}], {})
        try:
            self.assertEqual(sp.fetch_period("u/r"), ("2026.01", "2026.01"))
        finally:
            sp._gh_request = orig


# ── 정규화 / Validation / JSON 항목 ───────────────────────────────────────────
class TestNormalize(unittest.TestCase):
    repo = {"name": "x", "html_url": "https://github.com/u/x", "description": "repo desc",
            "language": "Python", "updated_at": "2026-09-01T00:00:00Z"}
    content = {"proj_title": "README Title", "subtitle": "readme sub", "intro": "readme intro",
               "tech_items": ["Vue"], "features": ["f1"], "team": ["이상호 — 팀장"], "my_role": "dev"}

    def test_yml_wins_over_readme(self):
        yml = {"title": "YML", "subtitle": "yml sub", "summary": "yml summary", "tech": ["React"],
               "highlights": ["h1"], "status": "active", "started": "2026-03", "live_url": "https://a.b",
               "featured": True, "role": ["Planning", "Backend"]}
        m = sp.normalize_metadata("x", self.repo, yml, self.content, "2026.01", "2026.09", date(2026, 10, 1))
        self.assertEqual(m["title"], "YML")
        self.assertEqual(m["proj_title"], "YML")
        self.assertEqual(m["subtitle"], "yml sub")
        self.assertEqual(m["summary"], "yml summary")
        self.assertEqual(m["tech"], ["React"])
        self.assertEqual(m["highlights"], ["h1"])
        self.assertEqual(m["status"], "active")
        self.assertEqual(m["started"], "2026.03")
        self.assertEqual(m["ended"], "")
        self.assertTrue(m["ongoing"])
        self.assertTrue(m["featured"])
        self.assertEqual(m["live_url"], "https://a.b")
        self.assertEqual(m["my_role"], "Planning · Backend")
        self.assertEqual(m["team"], ["이상호 — 팀장"])

    def test_readme_fallback_without_yml(self):
        m = sp.normalize_metadata("x", self.repo, None, self.content, "2025.09", "2025.11", date(2026, 10, 1))
        self.assertFalse(m["has_portfolio_yml"])
        self.assertEqual(m["title"], "README Title")
        self.assertIsNone(m["status"])
        self.assertEqual(m["started"], "2025.09")
        self.assertEqual(m["ended"], "2025.11")
        self.assertFalse(m["ongoing"])
        self.assertEqual(m["live_url"], "")
        self.assertFalse(m["featured"])
        self.assertEqual(m["repository_url"], "https://github.com/u/x")
        self.assertEqual(m["slug"], "x")

    def test_invalid_status_becomes_none(self):
        m = sp.normalize_metadata("x", self.repo, {"status": "Retired"}, {}, "", "", date(2026, 10, 1))
        self.assertIsNone(m["status"])
        self.assertEqual(m["status_raw"], "retired")

    def test_replaced_by_and_unused(self):
        yml = {"title": "Old", "status": "unused", "started": "2026-01", "ended": "2026-08",
               "unused_reason": "통합됨", "replaced_by": {"title": "New", "url": "https://n"}}
        m = sp.normalize_metadata("old", self.repo, yml, {}, "2026.01", "2026.09", date(2026, 10, 1))
        self.assertEqual(m["replaced_by"], {"title": "New", "repository": "", "url": "https://n"})
        self.assertEqual(m["ended"], "2026.08")
        self.assertFalse(m["ongoing"])
        m2 = sp.normalize_metadata("old", self.repo, {"replaced_by": {}}, {}, "", "", date(2026, 10, 1))
        self.assertIsNone(m2["replaced_by"])

    def test_validate(self):
        yml = {"status": "retired", "started": "어느날", "live_url": "tracker.example.com"}
        m = sp.normalize_metadata("bad", self.repo, yml, {}, "2026.04", "2026.06", date(2026, 10, 1))
        warns = sp.validate_metadata(m, yml, "bad")
        joined = "\n".join(warns)
        self.assertIn("title 누락", joined)
        self.assertIn("지원되지 않는 status 'retired'", joined)
        self.assertIn("started 형식 인식 불가", joined)
        self.assertIn("live_url", joined)
        self.assertEqual(m["live_url"], "")

        yml2 = {"title": "T", "status": "unused", "started": "2026-01"}
        m2 = sp.normalize_metadata("u", self.repo, yml2, {}, "", "", date(2026, 10, 1))
        self.assertTrue(any("unused_reason" in w for w in sp.validate_metadata(m2, yml2, "u")))

        yml3 = {"title": "T", "status": "active", "started": "2026-01", "ended": "2026-05"}
        m3 = sp.normalize_metadata("a", self.repo, yml3, {}, "", "", date(2026, 10, 1))
        self.assertTrue(m3["ongoing"])
        self.assertTrue(any("active 는 ended" in w for w in sp.validate_metadata(m3, yml3, "a")))

        m4 = sp.normalize_metadata("r", self.repo, None, self.content, "2026.01", "2026.02", date(2026, 10, 1))
        self.assertEqual(sp.validate_metadata(m4, None, "r"), [])

    def test_to_project_entry(self):
        m = sp.normalize_metadata("x", self.repo, None, self.content, "2025.09", "2025.11", date(2026, 10, 1))
        e = sp.to_project_entry(m, self.repo, "sha1", "", "ok", "2026-10-01")
        self.assertEqual(e["source"], "github")
        self.assertEqual(e["repo"], "x")
        self.assertEqual(e["team"], [{"name": "이상호", "role": "팀장", "me": True}])
        self.assertEqual(e["tagClass"], "dev")
        self.assertEqual(e["language"], "Python")
        self.assertEqual(e["tech"], ["Vue"])
        self.assertEqual(e["readmeSha"], "sha1")
        self.assertEqual(e["periodFallback"], "2026.09")
        # tech 비어 있으면 언어 라벨 chip
        m2 = sp.normalize_metadata("y", self.repo, None, {}, "", "", date(2026, 10, 1))
        self.assertEqual(sp.to_project_entry(m2, self.repo)["tech"], ["Python"])

    def test_parse_team_item(self):
        self.assertEqual(sp.parse_team_item("홍길동 — Backend"), {"name": "홍길동", "role": "Backend", "me": False})
        self.assertEqual(sp.parse_team_item("홍길동 - Backend · CI"), {"name": "홍길동", "role": "Backend · CI", "me": False})
        self.assertEqual(sp.parse_team_item("이상호"), {"name": "이상호", "role": "", "me": True})

    def test_sort_projects_stable(self):
        ps = [{"slug": "a", "started": "2026.05"}, {"slug": "b", "started": "2026.05"},
              {"slug": "c", "started": "2020.01"}, {"slug": "d", "started": "2026.09"}]
        self.assertEqual([p["slug"] for p in sp.sort_projects(ps)], ["d", "a", "b", "c"])
        # 같은 달은 이전 JSON 순서 유지, 새 항목은 뒤에
        prev = [{"slug": "b"}, {"slug": "a"}]
        self.assertEqual([p["slug"] for p in sp.sort_projects(ps, prev)], ["d", "b", "a", "c"])


# ── 렌더링 (Python) ───────────────────────────────────────────────────────────
def entry(yml=None, content=None, repo=None, commit=("", ""), **over):
    repo = repo or {"name": "x", "html_url": "https://github.com/u/x", "language": "Python",
                    "updated_at": "2026-09-01T00:00:00Z"}
    m = sp.normalize_metadata("x", repo, yml, content or {}, commit[0], commit[1], date(2026, 10, 1))
    e = sp.to_project_entry(m, repo)
    e.update(over)
    return e


class TestRender(unittest.TestCase):
    def test_escaping(self):
        yml = {"title": "<script>alert(1)</script>", "status": "active", "started": "2026-01",
               "summary": "A & B <b>", "tech": ["C++ & <Go>"], "highlights": ["<li>x"],
               "team": ["이상호 — <lead>"], "live_url": "https://a.b/?x=1&y=2"}
        html = rc.render_card(entry(yml))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("A &amp; B &lt;b&gt;", html)
        self.assertIn("C++ &amp; &lt;Go&gt;", html)
        self.assertIn("&lt;li&gt;x", html)
        self.assertIn('href="https://a.b/?x=1&amp;y=2"', html)
        self.assertIn('<span class="me">me</span>', html)

    def test_active_card(self):
        yml = {"title": "T", "status": "active", "started": "2026-03", "live_url": "https://t.example",
               "summary": "s", "tech": ["React"], "highlights": ["h"], "featured": True, "slug": "t-slug"}
        html = rc.render_card_block(entry(yml, commit=("2026.01", "2026.09")))
        self.assertIn("<!-- AUTO:x -->", html)
        self.assertIn("<!-- /AUTO:x -->", html)
        self.assertIn("2026.03 – Present", html)
        self.assertIn('class="status-badge status-active">진행 중<', html)
        self.assertIn('class="proj-link live" href="https://t.example"', html)
        self.assertIn('href="https://github.com/u/x"', html)
        self.assertIn('data-status="active"', html)
        self.assertIn('data-slug="t-slug"', html)
        self.assertIn('data-source="github"', html)
        self.assertIn('data-featured="true"', html)
        self.assertIn('class="proj-title">T<', html)

    def test_unused_card_is_minimal(self):
        yml = {"title": "Old", "status": "unused", "started": "2026-01", "ended": "2026-08",
               "unused_reason": "통합됨\n둘째 줄", "live_url": "https://old", "tech": ["Next.js"],
               "highlights": ["h"], "summary": "long summary",
               "replaced_by": {"title": "New", "url": "https://new"}}
        html = rc.render_card(entry(yml))
        self.assertIn('class="proj-unused"', html)
        self.assertIn("2026.01 – 2026.08", html)
        self.assertIn('status-unused">미사용<', html)
        self.assertIn("미사용 사유", html)
        self.assertIn("통합됨<br>", html)
        self.assertIn("→ New 보기", html)
        self.assertNotIn("Live Demo", html)
        self.assertNotIn("Next.js", html)
        self.assertNotIn("주요 기능", html)
        self.assertNotIn("long summary", html)
        self.assertIn("https://github.com/u/x", html)

    def test_paused_no_status_and_manual_fields(self):
        yml = {"title": "P", "status": "paused", "started": "2026-01", "pause_reason": "우선순위 변경"}
        html = rc.render_card(entry(yml, commit=("", "2026.02")))
        self.assertIn("일시 중단 사유", html)
        self.assertIn("status-paused", html)

        html2 = rc.render_card(entry(None, {"proj_title": "R"}, commit=("2025.09", "2025.11")))
        self.assertNotIn("status-badge", html2)
        self.assertIn("2025.09 – 2025.11", html2)
        self.assertIn(rc.PLACEHOLDER, html2)
        self.assertIn('<span class="chip dev">Python</span>', html2)

        # manual 항목: 영상 · 수상 · 팀(me) · 핵심 구현 제목 · repositoryUrl 없음 → Links 없음
        p = {"slug": "m", "source": "manual", "title": "M", "subtitle": "s", "summary": "intro",
             "status": "archived", "started": "2019.03", "ended": "2019.07", "tech": ["Unity"],
             "awards": ["SW Festival"], "tagClass": "", "highlights": ["a"], "highlightsTitle": "핵심 구현",
             "videos": [{"label": "UCC", "url": "https://www.youtube.com/embed/abc"}, {"label": "", "url": "https://www.youtube.com/embed/def"}],
             "team": [{"name": "이상호", "role": "Unity", "me": True}, {"name": "B", "role": "", "me": False}]}
        html3 = rc.render_card(p)
        self.assertIn('<span class="chip">Unity</span>', html3)
        self.assertIn('<span class="chip award">🏆 SW Festival</span>', html3)
        self.assertIn("<h4>핵심 구현</h4>", html3)
        self.assertIn('<p class="video-label">UCC</p>', html3)
        self.assertEqual(html3.count("<iframe"), 2)
        self.assertIn('이상호<span class="me">me</span>', html3)
        self.assertNotIn("Links", html3)
        self.assertIn('status-archived">아카이브<', html3)
        self.assertIn('data-source="manual"', html3)

    def test_render_auto_section_replaces_block(self):
        html = "<x>\n      <!-- AUTO:START — old -->\n      <!-- AUTO:a -->old<!-- /AUTO:a -->\n      <!-- AUTO:END -->\n</x>"
        out = rc.render_auto_section(html, [entry({"title": "N", "status": "active", "started": "2026-01"})])
        self.assertNotIn("old", out)
        self.assertIn(rc.AUTO_START_LINE, out)
        self.assertIn("<!-- AUTO:x -->", out)
        self.assertTrue(out.startswith("<x>\n"))
        self.assertTrue(out.endswith("<!-- AUTO:END -->\n</x>"))
        with self.assertRaises(ValueError):
            rc.render_auto_section("no markers", [])


class TestSections(unittest.TestCase):
    def test_display_status(self):
        self.assertEqual(rc.display_status({"status": "paused"}), "paused")
        self.assertEqual(rc.display_status({"status": None, "ongoing": True}), "active")
        self.assertEqual(rc.display_status({"status": None, "ongoing": False}), "completed")
        self.assertEqual(rc.display_status({"status": "weird", "ongoing": True}), "active")

    def test_groups_and_featured(self):
        ps = [
            entry({"title": "A", "status": "active", "started": "2026-05", "featured": True,
                   "live_url": "https://a.example", "tech": ["1", "2", "3", "4", "5"]}, slug="a"),
            entry(None, {"proj_title": "N"}, commit=("2026.04", "2026.09"), slug="n"),        # status 없음 + 최근 커밋
            entry({"title": "P", "status": "paused", "started": "2026-01"}, slug="p"),
            entry({"title": "C", "status": "completed", "started": "2025-01", "ended": "2025-03"}, slug="c"),
            entry(None, {"proj_title": "O"}, commit=("2021.08", "2021.08"), slug="o"),        # status 없음 + 오래됨
            entry({"title": "U", "status": "unused", "started": "2024-01", "featured": True}, slug="u"),
            entry({"title": "R", "status": "archived", "started": "2019-01"}, slug="r"),
        ]
        html = rc.render_sections(ps)
        groups = re.findall(r'data-group="(\w+)"', html)
        self.assertEqual(groups, ["current", "paused", "completed", "archive"])
        def members(key):
            block = html.split(f'data-group="{key}"')[1].split('data-group=')[0]
            return re.findall(r'<details[^>]* data-slug="(\w+)"', block)
        self.assertEqual(members("current"), ["a", "n"])
        self.assertEqual(members("paused"), ["p"])
        self.assertEqual(members("completed"), ["c", "o"])
        self.assertEqual(members("archive"), ["u", "r"])
        self.assertIn('<span class="proj-group-count">2</span>', html)
        # Featured: unused 는 제외, 최대 4 chips, 링크 3개
        feat = html.split('class="proj-featured"')[1].split('class="proj-group"')[0]
        self.assertEqual(re.findall(r'feat-card" data-slug="(\w+)"', feat), ["a"])
        self.assertEqual(feat.count('class="chip dev"'), 4)
        self.assertIn('class="proj-link live" href="https://a.example"', feat)
        self.assertIn('href="#proj-a">자세히</a>', feat)
        self.assertIn('feat-cover-empty', feat)
        # 배지는 명시적 status 만, 필터용 data-display-status 는 모두
        n_card = html.split('data-slug="n"')[1].split("</summary>")[0]
        self.assertNotIn("status-badge", n_card)
        self.assertIn('id="proj-n" data-slug="n"', html)
        self.assertIn('data-slug="n" data-source="github" data-display-status="active"', html)
        # 접힌 카드의 Live 링크
        self.assertIn('<a class="proj-live" href="https://a.example"', html)
        self.assertNotIn("proj-live", html.split('data-slug="u"')[1].split("</summary>")[0])

    def test_featured_limit_and_cover(self):
        ps = [entry({"title": f"F{i}", "status": "active", "started": "2026-01", "featured": True}, slug=f"f{i}")
              for i in range(7)]
        ps[0]["coverImage"] = "assets/projects/f0/desktop.webp"
        ps[1]["coverImage"] = "docs/cover.png"             # 레포 내부 경로 → 사용 안 함
        html = rc.render_sections(ps)
        self.assertEqual(html.count('class="feat-card"'), rc.FEATURED_MAX)
        self.assertIn('<img src="assets/projects/f0/desktop.webp" alt="F0 미리보기" loading="lazy">', html)
        self.assertNotIn("docs/cover.png", html)

    def test_no_featured_section_when_none(self):
        html = rc.render_sections([entry({"title": "A", "status": "active", "started": "2026-01"})])
        self.assertNotIn("proj-featured", html)


# ── Python ↔ JS 렌더러 parity ─────────────────────────────────────────────────
@unittest.skipIf(NODE is None, "node 없음")
class TestJsParity(unittest.TestCase):
    def render_js(self, projects, fn="renderProjectList"):
        script = ("const R=require(process.argv[1]);const fs=require('fs');"
                  "const d=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(R." + fn + "(d));")
        r = subprocess.run([NODE, "-e", script, str(JS_RENDERER)], input=json.dumps(projects),
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def assert_parity(self, projects):
        py = rc.normalize_html(rc.render_project_list(projects))
        js = rc.normalize_html(self.render_js(projects))
        self.assertEqual(py, js)
        py_s = rc.normalize_html(rc.render_sections(projects))
        js_s = rc.normalize_html(self.render_js(projects, "renderSections"))
        self.assertEqual(py_s, js_s)

    def test_generated_json_parity(self):
        data = json.loads((ROOT / "data" / "projects.generated.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["projects"]), 12)
        self.assert_parity(data["projects"])

    def test_fixture_variants_parity(self):
        cases = [
            entry({"title": "A <&> \"q\" 'x'", "status": "active", "started": "2026-01", "summary": "l1\nl2",
                   "tech": ["T"], "highlights": ["h & h"], "live_url": "https://l?a=1&b=2", "featured": True,
                   "team": ["이상호 — 팀장", "B"], "role": ["Dev"]}),
            entry({"title": "U", "status": "unused", "started": "2026-01", "ended": "2026-02",
                   "unused_reason": "r1\nr2", "replaced_by": {"title": "N", "url": "https://n"}}),
            entry({"title": "U2", "status": "unused", "started": "2026-01", "subtitle": "sub",
                   "replaced_by": {"title": "N2"}}, repositoryUrl=""),
            entry({"title": "P", "status": "paused", "started": "2026-01", "pause_reason": "why"}),
            entry(None, {"proj_title": "R"}, commit=("2025.09", "2025.11")),
            entry(None, {}, repo={"name": "z", "html_url": "", "language": "", "updated_at": "2026-02-03T00:00:00Z"}),
            entry({"title": "Feat", "status": "completed", "started": "2025-01", "ended": "2025-06", "featured": True,
                   "tech": ["A", "B", "C", "D", "E"]}, coverImage="assets/projects/feat/desktop.webp", slug="feat"),
            entry({"title": "😀 Emoji", "status": "archived", "started": "2019-01", "featured": True}, slug="emoji"),
            entry({"title": "Hidden", "status": "unused", "started": "2019-01", "featured": True}, slug="hidden"),
        ]
        self.assert_parity(cases)


# ── 마이그레이션 · 기존 정보 손실 없음 ────────────────────────────────────────
DISPLAY_FIELDS = ("title", "subtitle", "summary", "started", "ended", "ongoing", "tech", "awards",
                  "tagClass", "highlights", "highlightsTitle", "myRole", "videos", "team", "repositoryUrl")


def _display(p):
    return {k: p.get(k) for k in DISPLAY_FIELDS}


class TestMigration(unittest.TestCase):
    def test_parse_period(self):
        self.assertEqual(mig.parse_period("2020.10 – 2020.11"), ("2020.10", "2020.11", False))
        self.assertEqual(mig.parse_period("2026.05 –"), ("2026.05", "", True))
        self.assertEqual(mig.parse_period("2026.05 – Present"), ("2026.05", "", True))
        self.assertEqual(mig.parse_period("2021.08 – 2021.08"), ("2021.08", "", False))
        self.assertEqual(mig.parse_period("2021.08"), ("2021.08", "", False))

    def test_legacy_index_roundtrip_no_data_loss(self):
        """legacy index.html → JSON → 정적 HTML → 다시 파싱: 표시 필드가 모두 보존된다"""
        legacy = LEGACY_INDEX.read_text(encoding="utf-8")
        cfg = json.loads((ROOT / "scripts" / "projects.json").read_text(encoding="utf-8"))
        github, manual = mig.parse_index(legacy, cfg.get("repos", {}))
        self.assertEqual(len(github), 6)
        self.assertEqual(len(manual), 6)
        self.assertEqual(sum(len(p["videos"]) for p in manual), 8)
        self.assertEqual(sum(len(p["team"]) for p in manual), 24)
        self.assertEqual([a for p in manual for a in p["awards"]],
                         ["SSAFY 자율 프로젝트 우수상", "SSAFY 공통 프로젝트 우수상", "HGU SW Festival 융합연구 공모전"])
        ps = next(p for p in manual if p["title"].startswith("P.S"))
        self.assertEqual(ps["videos"][0], {"label": "UCC", "url": "https://www.youtube.com/embed/D1ZmTUlXaPk"})
        self.assertEqual(ps["team"][0], {"name": "이상호", "role": "팀장 · 백엔드 · Android", "me": True})
        self.assertIn("기존 서비스보다 더 쉽고 편리하게", ps["summary"])
        bc = next(p for p in manual if p["title"] == "BC+")
        self.assertEqual(bc["subtitle"], "캘린더 활용 비즈니스 협업 관리 웹 프로그램 (P.S의 전신)")
        pacer = next(p for p in github if p["repo"] == "health-tracker")
        self.assertEqual(pacer["readmeSha"], cfg["repos"]["health-tracker"]["sha"])
        self.assertTrue(pacer["ongoing"])
        self.assertEqual(pacer["repositoryUrl"], "https://github.com/kimmydkemf/health-tracker")
        self.assertEqual(len(pacer["tech"]), 7)

        # 렌더 → 파싱 왕복
        rendered = mig.rewrite_index(legacy, mig.sort_projects(github + manual))
        again_github, again_manual = mig.parse_index(rendered, cfg.get("repos", {}))
        self.assertEqual(again_manual, [])                       # 수동 HTML 제거됨
        self.assertEqual(len(again_github), 12)
        self.assertIn(mig.SCRIPT_TAG, rendered)
        by_title = {p["title"]: _display(p) for p in again_github}
        for p in github + manual:
            self.assertEqual(_display(p), by_title[p["title"]], msg=p["title"])

    def test_committed_data_matches_legacy(self):
        """저장된 data/*.json 이 legacy index.html 의 정보를 잃지 않았는지.
        실제 sync 로 다시 만들어진 항목(syncStatus != migrated)과 사람이 편집한 manual 항목은 비교하지 않고,
        마이그레이션 상태 그대로인 항목만 legacy 와 비교한다. index.html ↔ JSON 일치는 항상 검사한다."""
        legacy = LEGACY_INDEX.read_text(encoding="utf-8")
        cfg = json.loads((ROOT / "scripts" / "projects.json").read_text(encoding="utf-8"))
        github, manual = mig.parse_index(legacy, cfg.get("repos", {}))
        legacy_by_title = {p["title"]: _display(p) for p in github + manual}
        saved_gen = json.loads((ROOT / "data" / "projects.generated.json").read_text(encoding="utf-8"))["projects"]
        for p in saved_gen:
            if p.get("syncStatus") == "migrated" and p["title"] in legacy_by_title:
                self.assertEqual(_display(p), legacy_by_title[p["title"]], msg=p["title"])
        # manual 파일의 모든 항목은 generated 에 그대로 들어가 있어야 한다
        saved_manual = json.loads((ROOT / "data" / "projects.manual.json").read_text(encoding="utf-8"))["projects"]
        gen_by_slug = {p["slug"]: p for p in saved_gen}
        for m in saved_manual:
            self.assertIn(m["slug"], gen_by_slug)
            self.assertEqual(_display(gen_by_slug[m["slug"]]), _display(m), msg=m["slug"])
        # 현재 index.html 의 정적 카드 == JSON
        current = (ROOT / "index.html").read_text(encoding="utf-8")
        cur_github, cur_manual = mig.parse_index(current, cfg.get("repos", {}))
        self.assertEqual(cur_manual, [])
        self.assertEqual({p["title"]: _display(p) for p in cur_github},
                         {p["title"]: _display(p) for p in saved_gen})
        self.assertEqual(len(cur_github), len(saved_gen))


# ── 통합: fixtures 로 실제 파이프라인 실행 ────────────────────────────────────
class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sync-test-"))
        self.index = self.tmp / "index.html"
        self.config = self.tmp / "projects.json"
        self.generated = self.tmp / "projects.generated.json"
        self.manual = self.tmp / "projects.manual.json"
        shutil.copy(ROOT / "index.html", self.index)
        shutil.copy(ROOT / "scripts" / "projects.json", self.config)
        shutil.copy(ROOT / "data" / "projects.generated.json", self.generated)
        shutil.copy(ROOT / "data" / "projects.manual.json", self.manual)
        self.original_html = self.index.read_text(encoding="utf-8")
        self.original_gen = json.loads(self.generated.read_text(encoding="utf-8"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_sync(self, *extra):
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONIOENCODING": "utf-8"}
        return subprocess.run(
            [sys.executable, str(HERE / "sync_projects.py"), "--fixtures", str(FIXTURES),
             "--index", str(self.index), "--config", str(self.config),
             "--generated", str(self.generated), "--manual", str(self.manual), *extra],
            capture_output=True, text=True, env=env, cwd=str(ROOT),
        )

    def test_dry_run_changes_nothing(self):
        r = self.run_sync("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Dry run", r.stdout)
        self.assertEqual(self.index.read_text(encoding="utf-8"), self.original_html)
        self.assertEqual(json.loads(self.generated.read_text(encoding="utf-8")), self.original_gen)
        self.assertIn("[sample-tracker] 신규 처리 중… (portfolio.yml)", r.stdout)
        self.assertIn("[WARN] 지원되지 않는 status 'retired'", r.stdout)

    def test_full_run_then_idempotent(self):
        r = self.run_sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        html = self.index.read_text(encoding="utf-8")
        gen = json.loads(self.generated.read_text(encoding="utf-8"))
        projects = gen["projects"]
        by_slug = {p["slug"]: p for p in projects}

        # JSON: 기존 12 + fixture 4
        self.assertEqual(len(projects), 16)
        self.assertTrue(gen["generatedAt"])
        # 기존 github 항목은 fixture 목록에 없으므로 unavailable 로 표시되지만 데이터는 그대로
        for p in self.original_gen["projects"]:
            q = by_slug[p["slug"]]
            expected = dict(p)
            if p["source"] == "github":
                expected["syncStatus"] = "unavailable"
            self.assertEqual(q, expected, msg=p["slug"])
        self.assertIn("syncStatus=unavailable", r.stdout)

        t = by_slug["sample-tracker"]
        self.assertEqual(t["status"], "active")
        self.assertEqual(t["started"], "2026.03")
        self.assertTrue(t["ongoing"])
        self.assertEqual(t["liveUrl"], "https://tracker.example.com")
        self.assertTrue(t["featured"])
        self.assertEqual(t["team"], [{"name": "샘플 사용자", "role": "기획 · 개발", "me": False}])
        self.assertEqual(t["syncStatus"], "ok")
        self.assertTrue(t["readmeSha"] and t["portfolioSha"])
        self.assertNotIn("README 기능 1", json.dumps(t, ensure_ascii=False))
        u = by_slug["sample-legacy-blog"]
        self.assertEqual(u["status"], "unused")
        self.assertEqual(u["replacedBy"]["title"], "Sample Archive")
        ro = by_slug["sample-readme-only"]
        self.assertIsNone(ro["status"])
        self.assertEqual((ro["started"], ro["ended"], ro["ongoing"]), ("2025.09", "2025.11", False))
        self.assertEqual(ro["tech"], ["Spring Boot", "MySQL", "Android"])
        self.assertEqual(ro["team"][0], {"name": "샘플 A", "role": "팀장 · 백엔드", "me": False})
        self.assertEqual(ro["portfolioSha"], "")

        # 정렬: 시작월 내림차순
        starts = [p["started"] for p in projects]
        self.assertEqual(starts, sorted(starts, reverse=True))
        slugs = [p["slug"] for p in projects]
        self.assertEqual(slugs[0], "health-tracker")               # 2026.05 (기존) 가 가장 먼저
        self.assertLess(slugs.index("mynote"), slugs.index("sample-tracker"))          # 2026.05 > 2026.03
        self.assertLess(slugs.index("sample-tracker"), slugs.index("sample-legacy-blog"))  # 2026.03 > 2026.01
        self.assertLess(slugs.index("bcplus-legacy"), slugs.index("p-s-private-secretary"))  # 2021.08 > 2020.10

        # 정적 HTML: AUTO 구간이 JSON 과 같은 순서/내용
        self.assertEqual(html.count("<details"), 16)
        self.assertEqual(html.count("<details"), html.count("</details>"))
        order_in_html = [m for m in re.findall(r"<!-- AUTO:([\w\-\.가-힣]+) -->", html) if m != "END"]
        expected_order = [p.get("repo") or p["slug"]
                          for key, _, _ in rc.GROUPS for p in projects
                          if rc.GROUP_OF[rc.display_status(p)] == key]
        self.assertEqual(order_in_html, expected_order)
        # Featured: sample-tracker (featured, active)
        self.assertIn('<article class="feat-card" data-slug="sample-tracker"', html)
        self.assertIn('href="#proj-sample-tracker">자세히</a>', html)
        self.assertIn('id="proj-sample-tracker"', html)
        self.assertIn('<a class="proj-live" href="https://tracker.example.com"', html)
        self.assertIn("&lt;fixture&gt;", html)
        self.assertIn('class="proj-unused"', html)
        self.assertNotIn('href="https://blog.example.com"', html)
        self.assertIn("2025.09 – 2025.11", html)
        self.assertIn("기능 A &amp; B", html)
        self.assertIn("<!-- AUTO:health-tracker -->", html)
        self.assertLess(html.index("<!-- AUTO:END -->"), html.index('</div><!-- .project-list -->'))

        cfg = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(cfg["repos"]["sample-tracker"]["status"], "active")
        self.assertIn("health-tracker", cfg["repos"])

        # 두 번째 실행: 변경 없음
        r2 = self.run_sync()
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("[sample-tracker] 변경 없음 — 스킵", r2.stdout)
        self.assertIn("업데이트할 내용 없음", r2.stdout)
        self.assertEqual(self.index.read_text(encoding="utf-8"), html)
        self.assertEqual(json.loads(self.generated.read_text(encoding="utf-8")), gen)

        # portfolio.yml 만 바뀌어도 갱신
        cfg["repos"]["sample-tracker"]["portfolioSha"] = "stale"
        self.config.write_text(json.dumps(cfg), encoding="utf-8")
        r3 = self.run_sync()
        self.assertIn("[sample-tracker] 업데이트 처리 중…", r3.stdout)

        # 수동 JSON 편집 → 다음 sync 에 반영
        m = json.loads(self.manual.read_text(encoding="utf-8"))
        m["projects"][0]["subtitle"] = "편집된 부제"
        self.manual.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        r4 = self.run_sync()
        self.assertEqual(r4.returncode, 0, r4.stderr)
        self.assertIn("편집된 부제", self.index.read_text(encoding="utf-8"))
        self.assertIn("편집된 부제", self.generated.read_text(encoding="utf-8"))

    def test_excluded_repo_is_dropped_from_json(self):
        cfg = json.loads(self.config.read_text(encoding="utf-8"))
        cfg["excluded"].append("health-tracker")
        self.config.write_text(json.dumps(cfg), encoding="utf-8")
        r = self.run_sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        gen = json.loads(self.generated.read_text(encoding="utf-8"))
        self.assertNotIn("health-tracker", [p.get("repo") for p in gen["projects"]])
        self.assertNotIn("<!-- AUTO:health-tracker -->", self.index.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
