#!/usr/bin/env python3
"""
screenshot_projects.py 테스트 (외부 네트워크 없음 — 로컬 HTTP 서버만 사용)

  python3 scripts/test_screenshot_projects.py
  # Playwright 엔진까지 확인하려면 playwright 가 설치된 python 으로 실행
"""
import functools
import http.server
import json
import shutil
import struct
import sys
import tempfile
import threading
import unittest
import zlib
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import screenshot_projects as ss   # noqa: E402
import render_cards as rc          # noqa: E402
import validate_site as vs         # noqa: E402

try:
    import playwright  # noqa: F401
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def tiny_png(path: Path, w=4, h=3, rgb=(30, 120, 220)) -> None:
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class FakeBackend:
    name = "fake"
    supports_mobile = True

    def __init__(self, fail_slugs=()):
        self.calls = []
        self.fail = set(fail_slugs)

    def capture(self, url, out_png, view):
        self.calls.append((url, view["width"]))
        if any(s in url for s in self.fail):
            raise RuntimeError("boom")
        tiny_png(out_png)

    def close(self):
        pass


class LiveServer:
    """테스트용 로컬 'live' 사이트: /ok → 200, /missing → 404"""
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="live-"))
        (self.dir / "ok").mkdir()
        (self.dir / "ok" / "index.html").write_text(
            "<!doctype html><meta name=viewport content='width=device-width'>"
            "<body style='margin:0;background:#0b5;font:48px sans-serif'><h1>Sample Live</h1></body>",
            encoding="utf-8")
        handler = functools.partial(QuietHandler, directory=str(self.dir))
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}/{path}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def project(slug, live, **over):
    p = {"slug": slug, "repo": slug, "source": "github", "title": slug.title(), "subtitle": "sub",
         "summary": "s", "status": "active", "started": "2026.01", "ended": "", "ongoing": True,
         "featured": True, "liveUrl": live, "repositoryUrl": f"https://github.com/u/{slug}",
         "tech": ["T"], "highlights": [], "team": [], "tagClass": "dev", "screenshotRefresh": False}
    p.update(over)
    return p


class Site:
    """임시 사이트 루트 (index.html 은 저장소 것을 사용, 프로젝트 목록만 교체)"""
    def __init__(self, projects, manifest=None):
        self.root = Path(tempfile.mkdtemp(prefix="shot-site-"))
        (self.root / "data").mkdir()
        shutil.copy(ROOT / "index.html", self.root / "index.html")
        shutil.copy(ROOT / "CNAME", self.root / "CNAME")
        self.write_projects(projects)
        html = (self.root / "index.html").read_text(encoding="utf-8")
        (self.root / "index.html").write_text(rc.render_auto_section(html, projects), encoding="utf-8")
        if manifest is not None:
            (self.root / "data" / "screenshots.json").write_text(
                json.dumps({"schemaVersion": 1, "screenshots": manifest}), encoding="utf-8")

    def write_projects(self, projects):
        (self.root / "data" / "projects.generated.json").write_text(
            json.dumps({"schemaVersion": 1, "generatedAt": None, "projects": projects}, ensure_ascii=False),
            encoding="utf-8")

    def projects(self):
        return json.loads((self.root / "data" / "projects.generated.json").read_text(encoding="utf-8"))["projects"]

    def manifest(self):
        return json.loads((self.root / "data" / "screenshots.json").read_text(encoding="utf-8"))["screenshots"]

    def html(self):
        return (self.root / "index.html").read_text(encoding="utf-8")

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


# ── 정책 ──────────────────────────────────────────────────────────────────────
class TestPolicy(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="policy-"))
        (self.root / "assets/projects/a").mkdir(parents=True)
        tiny_png(self.root / "assets/projects/a/desktop.webp")
        self.now = datetime(2026, 10, 1, tzinfo=ss.KST)
        self.entry = {"url": "https://a.example", "desktop": "assets/projects/a/desktop.webp",
                      "capturedAt": (self.now - timedelta(days=3)).isoformat()}

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def reason(self, p, entry, **kw):
        return ss.capture_reason(p, entry, self.root, self.now, kw.get("refresh", set()),
                                 kw.get("refresh_all", False), kw.get("max_age", 30))

    def test_is_target(self):
        self.assertTrue(ss.is_target(project("a", "https://a.example")))
        self.assertFalse(ss.is_target(project("a", "")))
        self.assertFalse(ss.is_target(project("a", "https://a.example", status="unused")))
        self.assertFalse(ss.is_target(project("a", "https://a.example", screenshotEnabled=False)))
        self.assertTrue(ss.is_target(project("a", "https://a.example", status=None)))

    def test_reasons(self):
        p = project("a", "https://a.example")
        self.assertIsNone(self.reason(p, self.entry))
        self.assertEqual(self.reason(p, None), "새 프로젝트")
        self.assertEqual(self.reason(project("a", "https://b.example"), self.entry), "live_url 변경")
        self.assertEqual(self.reason(p, self.entry, refresh={"a"}), "명시적 refresh")
        self.assertEqual(self.reason(p, self.entry, refresh_all=True), "명시적 refresh")
        self.assertEqual(self.reason(project("a", "https://a.example", screenshotRefresh=True), self.entry),
                         "screenshot_refresh: true")
        self.assertEqual(self.reason(p, self.entry, max_age=2), "2일 경과")
        gone = dict(self.entry, mobile="assets/projects/a/mobile.webp")
        self.assertEqual(self.reason(p, gone), "mobile 파일 없음")

    def test_attach_only_existing_files(self):
        ps = [project("a", "https://a.example"), project("b", "https://b.example"),
              project("c", "https://c.example", status="unused")]
        man = {"a": self.entry, "b": {"desktop": "assets/projects/b/desktop.webp"},
               "c": self.entry}
        ss.attach_screenshots(ps, man, self.root)
        self.assertEqual(ps[0]["screenshots"], {"desktop": "assets/projects/a/desktop.webp"})
        self.assertNotIn("screenshots", ps[1])          # 파일 없음
        self.assertNotIn("screenshots", ps[2])          # unused

    def test_encode_image(self):
        png = self.root / "x.png"
        tiny_png(png)
        out = ss.encode_image(png, self.root / "out")
        self.assertTrue(out.exists())
        self.assertIn(out.suffix, (".webp", ".jpg", ".png"))

    def test_check_url_rejects_non_http(self):
        with self.assertRaises(RuntimeError):
            ss.check_url("ftp://x")


# ── 실행 흐름 (가짜 엔진) ─────────────────────────────────────────────────────
class TestRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = LiveServer()

    @classmethod
    def tearDownClass(cls):
        cls.live.close()

    def setUp(self):
        self.sites = []

    def tearDown(self):
        for s in self.sites:
            s.close()

    def site(self, projects, manifest=None):
        s = Site(projects, manifest)
        self.sites.append(s)
        return s

    def test_capture_attach_render_then_keep(self):
        ok = self.live.url("ok/")
        s = self.site([project("alpha", ok), project("norepo", ""), project("old", ok, status="unused")])
        fb = FakeBackend()
        self.assertEqual(ss.run(s.root, backend=fb), 0)
        self.assertEqual([w for _, w in fb.calls], [1440, 390])          # alpha 만, desktop + mobile
        man = s.manifest()
        self.assertEqual(set(man), {"alpha"})
        self.assertEqual(man["alpha"]["url"], ok)
        for key in ("desktop", "mobile"):
            self.assertTrue((s.root / man["alpha"][key]).exists())
            self.assertTrue(man["alpha"][key].startswith("assets/projects/alpha/"))
        alpha = next(p for p in s.projects() if p["slug"] == "alpha")
        self.assertEqual(alpha["screenshots"], {"desktop": man["alpha"]["desktop"], "mobile": man["alpha"]["mobile"]})
        html = s.html()
        self.assertIn(f'<img src="{man["alpha"]["desktop"]}" alt="Alpha 미리보기"', html)   # Featured 커버
        self.assertIn('class="shot-desktop"', html)
        self.assertIn('class="shot-mobile"', html)
        self.assertEqual(vs.validate(s.root, []).errors, [])

        # 두 번째 실행: 갱신 조건 없음 → 캡처 안 함, 파일 변경 없음
        before = (s.root / "data" / "screenshots.json").read_text(encoding="utf-8"), s.html()
        fb2 = FakeBackend()
        self.assertEqual(ss.run(s.root, backend=fb2), 0)
        self.assertEqual(fb2.calls, [])
        self.assertEqual(((s.root / "data" / "screenshots.json").read_text(encoding="utf-8"), s.html()), before)

        # --refresh alpha → 다시 캡처
        fb3 = FakeBackend()
        ss.run(s.root, backend=fb3, refresh=["alpha"])
        self.assertEqual(len(fb3.calls), 2)

    def test_failure_keeps_previous_and_continues(self):
        ok = self.live.url("ok/")
        s = self.site([project("alpha", ok), project("beta", ok + "?beta")])
        ss.run(s.root, backend=FakeBackend())
        first = s.manifest()
        # beta 의 URL 이 바뀌었지만 캡처 실패 → 기존 Screenshot 유지, alpha 는 영향 없음
        ps = s.projects()
        for p in ps:
            if p["slug"] == "beta":
                p["liveUrl"] = ok + "?beta2"
        s.write_projects(ps)
        rc_ = ss.run(s.root, backend=FakeBackend(fail_slugs=["beta2"]))
        self.assertEqual(rc_, 0)
        man = s.manifest()
        self.assertEqual(man["beta"]["desktop"], first["beta"]["desktop"])
        self.assertEqual(man["beta"]["lastError"], "boom")
        self.assertTrue((s.root / man["beta"]["desktop"]).exists())
        self.assertEqual(man["alpha"], first["alpha"])
        self.assertEqual(ss.run(s.root, backend=FakeBackend(fail_slugs=["beta2"]), strict=True), 1)

    def test_http_error_page_is_not_captured(self):
        s = self.site([project("gone", self.live.url("missing/"))])
        fb = FakeBackend()
        self.assertEqual(ss.run(s.root, backend=fb), 0)
        self.assertEqual(fb.calls, [])                        # 404 → 캡처 시도 안 함
        self.assertIn("HTTP 404", s.manifest()["gone"]["lastError"])
        self.assertFalse((s.root / "assets" / "projects" / "gone").exists() and
                         any((s.root / "assets" / "projects" / "gone").iterdir()))
        self.assertNotIn("screenshots", s.projects()[0])

    def test_no_backend_is_not_fatal(self):
        s = self.site([project("alpha", self.live.url("ok/"))])
        orig = ss.make_backend
        ss.make_backend = lambda pref="auto": (_ for _ in ()).throw(RuntimeError("엔진 없음"))
        try:
            self.assertEqual(ss.run(s.root), 0)
            self.assertEqual(ss.run(s.root, strict=True), 1)
        finally:
            ss.make_backend = orig
        self.assertNotIn("screenshots", s.projects()[0])

    def test_dry_run_writes_nothing(self):
        s = self.site([project("alpha", self.live.url("ok/"))])
        before = s.html()
        fb = FakeBackend()
        self.assertEqual(ss.run(s.root, backend=fb, dry_run=True), 0)
        self.assertEqual(fb.calls, [])
        self.assertFalse((s.root / "data" / "screenshots.json").exists())
        self.assertEqual(s.html(), before)

    def test_desktop_only_backend_keeps_old_mobile(self):
        ok = self.live.url("ok/")
        s = self.site([project("alpha", ok)])
        ss.run(s.root, backend=FakeBackend())
        mobile = s.manifest()["alpha"]["mobile"]
        fb = FakeBackend()
        fb.supports_mobile = False
        ss.run(s.root, backend=fb, refresh_all=True)
        self.assertEqual([w for _, w in fb.calls], [1440])
        self.assertEqual(s.manifest()["alpha"]["mobile"], mobile)


# ── 실제 엔진 (있을 때만) ─────────────────────────────────────────────────────
class TestRealBackends(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = LiveServer()

    @classmethod
    def tearDownClass(cls):
        cls.live.close()

    def check_capture(self, backend, expect_mobile):
        s = Site([project("alpha", self.live.url("ok/"))])
        try:
            self.assertEqual(ss.run(s.root, backend=backend), 0)
            man = s.manifest()["alpha"]
            self.assertNotIn("lastError", man)
            desktop = s.root / man["desktop"]
            self.assertGreater(desktop.stat().st_size, 1000)
            self.assertEqual("mobile" in man, expect_mobile)
            try:
                from PIL import Image
                with Image.open(desktop) as im:
                    self.assertEqual(im.size, (1440, 900))
                if expect_mobile:
                    with Image.open(s.root / man["mobile"]) as im:
                        self.assertEqual(im.size, (780, 1688))          # 390×844 @2x
            except ImportError:
                pass
        finally:
            s.close()

    @unittest.skipIf(ss.find_chrome() is None, "Chrome 없음")
    def test_chrome_cli(self):
        b = ss.ChromeCliBackend(ss.find_chrome())
        try:
            self.check_capture(b, expect_mobile=False)
        finally:
            b.close()

    @unittest.skipUnless(HAS_PLAYWRIGHT, "playwright 미설치")
    def test_playwright(self):
        b = ss.PlaywrightBackend()
        try:
            self.check_capture(b, expect_mobile=True)
        finally:
            b.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
