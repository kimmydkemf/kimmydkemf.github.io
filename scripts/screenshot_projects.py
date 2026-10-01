#!/usr/bin/env python3
"""
screenshot_projects.py — live_url 이 있는 프로젝트의 Desktop / Mobile Screenshot 생성
=====================================================================================
data/projects.generated.json 을 읽고, 갱신이 필요한 프로젝트만 캡처해

  assets/projects/{slug}/desktop.webp   (1440×900)
  assets/projects/{slug}/mobile.webp    (390×844, 2x)
  data/screenshots.json                 (manifest: url, 파일, 캡처 시각, 마지막 오류)

에 저장한 뒤, generated JSON 의 각 항목에 `screenshots` 를 붙이고 index.html 정적 카드를 다시 만든다.

갱신 조건 (SPEC §18) — 하나라도 해당하면 캡처, 아니면 기존 파일 유지:
  - 새 프로젝트 (manifest 에 없음 / 파일 없음)
  - live_url 변경
  - 명시적 refresh (--refresh SLUG, --refresh-all, portfolio.yml screenshot_refresh: true)
  - 마지막 캡처 후 --max-age-days (기본 30일) 경과

대상: liveUrl 이 있고, status 가 unused 가 아니고, portfolio.yml 에서 screenshot: false 가 아닌 프로젝트.
캡처 실패는 경고만 남기고 기존 Screenshot 을 유지한다 (종료 코드 0). --strict 면 실패 시 1.

캡처 엔진 (자동 선택):
  1. Playwright (python)  — Desktop + Mobile.  설치: python3 -m pip install --user playwright
                            브라우저: 시스템 Chrome 사용, 없으면 python3 -m playwright install chromium
  2. Chrome / Chromium CLI — Desktop 만 (headless CLI 는 모바일 뷰포트를 만들 수 없음)
이미지 변환: Pillow(webp) → cwebp → sips(jpeg) → png 순으로 사용 가능한 것.

사용법:
  python3 scripts/screenshot_projects.py                 # 필요한 것만
  python3 scripts/screenshot_projects.py --dry-run       # 무엇을 캡처할지 출력만
  python3 scripts/screenshot_projects.py --refresh pacer --refresh-all --max-age-days 7
  python3 scripts/screenshot_projects.py --root PATH     # 다른 사본 (Preview)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from render_cards import render_auto_section  # noqa: E402

KST = timezone(timedelta(hours=9))
DESKTOP = {"width": 1440, "height": 900, "scale": 1}
MOBILE = {"width": 390, "height": 844, "scale": 2}
NAV_TIMEOUT_MS = 20000
SETTLE_MS = 1200
DEFAULT_MAX_AGE_DAYS = 30
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "google-chrome", "chromium", "chromium-browser",
)


def now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def parse_iso(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


# ── 정책 ──────────────────────────────────────────────────────────────────────
def is_target(p: dict) -> bool:
    return bool(p.get("liveUrl")) and p.get("status") != "unused" and p.get("screenshotEnabled", True) is not False


def capture_reason(p: dict, entry: dict | None, root: Path, now: datetime,
                   refresh: set[str], refresh_all: bool, max_age_days: int) -> str | None:
    """캡처해야 하면 이유 문자열, 아니면 None"""
    slug = p.get("slug")
    if refresh_all or slug in refresh:
        return "명시적 refresh"
    if p.get("screenshotRefresh"):
        return "screenshot_refresh: true"
    if not entry or not entry.get("desktop"):
        return "새 프로젝트"
    if entry.get("url") != p.get("liveUrl"):
        return "live_url 변경"
    for key in ("desktop", "mobile"):
        f = entry.get(key)
        if f and not (root / f).exists():
            return f"{key} 파일 없음"
    captured = parse_iso(entry.get("capturedAt"))
    if not captured or now - captured > timedelta(days=max_age_days):
        return f"{max_age_days}일 경과"
    return None


def check_url(url: str, timeout: int = 15) -> None:
    """캡처 전 확인: http(s) 이고 응답 코드가 400 미만이어야 한다 (오류 페이지를 Screenshot 으로 저장하지 않기 위해)"""
    if not url.startswith(("http://", "https://")):
        raise RuntimeError(f"http(s) URL 이 아님: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "dounselor-portfolio-screenshot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:
        raise RuntimeError(f"접속 실패: {e}") from None
    if code >= 400:
        raise RuntimeError(f"HTTP {code}")


# ── 이미지 변환 ───────────────────────────────────────────────────────────────
def _pillow_webp():
    try:
        from PIL import Image, features  # type: ignore
        return Image if features.check("webp") else None
    except Exception:
        return None


def encode_image(png: Path, dest_noext: Path) -> Path:
    """PNG → webp/jpeg/png. 최종 파일 경로 반환"""
    Image = _pillow_webp()
    if Image is not None:
        out = dest_noext.with_suffix(".webp")
        with Image.open(png) as im:
            im.convert("RGB").save(out, "WEBP", quality=80, method=6)
        return out
    if shutil.which("cwebp"):
        out = dest_noext.with_suffix(".webp")
        r = subprocess.run(["cwebp", "-quiet", "-q", "80", str(png), "-o", str(out)], capture_output=True)
        if r.returncode == 0 and out.exists():
            return out
    if shutil.which("sips"):
        out = dest_noext.with_suffix(".jpg")
        r = subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "80", str(png), "--out", str(out)],
                           capture_output=True)
        if r.returncode == 0 and out.exists():
            return out
    out = dest_noext.with_suffix(".png")
    shutil.copyfile(png, out)
    return out


# ── 캡처 엔진 ─────────────────────────────────────────────────────────────────
class PlaywrightBackend:
    name = "playwright"
    supports_mobile = True

    def __init__(self):
        from playwright.sync_api import sync_playwright  # type: ignore
        self._pw = sync_playwright().start()
        self._browser = None
        errors = []
        for kwargs in ({"channel": "chrome"}, {}):
            try:
                self._browser = self._pw.chromium.launch(headless=True, **kwargs)
                self.name = "playwright" + (" (system chrome)" if kwargs else " (chromium)")
                break
            except Exception as e:  # 브라우저 미설치 등
                errors.append(str(e).splitlines()[0])
        if self._browser is None:
            self._pw.stop()
            raise RuntimeError("Playwright 브라우저를 실행할 수 없음: " + " / ".join(errors))

    def capture(self, url: str, out_png: Path, view: dict) -> None:
        ctx = self._browser.new_context(
            viewport={"width": view["width"], "height": view["height"]},
            device_scale_factor=view["scale"],
            is_mobile=view is MOBILE, has_touch=view is MOBILE,
            color_scheme="light",
        )
        try:
            page = ctx.new_page()
            resp = page.goto(url, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
            if resp is not None and resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}")
            page.wait_for_timeout(SETTLE_MS)
            page.screenshot(path=str(out_png), full_page=False)
        finally:
            ctx.close()

    def close(self):
        try:
            self._browser.close()
        finally:
            self._pw.stop()


class ChromeCliBackend:
    name = "chrome-cli"
    supports_mobile = False

    def __init__(self, binary: str):
        self.binary = binary
        self.profile = Path(tempfile.mkdtemp(prefix="shot-profile-"))

    def capture(self, url: str, out_png: Path, view: dict) -> None:
        args = [self.binary, "--headless=new", "--no-first-run", "--disable-gpu", "--hide-scrollbars",
                f"--user-data-dir={self.profile}", f"--window-size={view['width']},{view['height']}",
                f"--force-device-scale-factor={view['scale']}", "--virtual-time-budget=5000",
                f"--screenshot={out_png}", url]
        # headless Chrome 은 스크린샷 후에도 종료되지 않는 경우가 있어 파일 생성으로 완료를 판단
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = datetime.now() + timedelta(milliseconds=NAV_TIMEOUT_MS + 10000)
            last = -1
            while datetime.now() < deadline:
                if proc.poll() is not None and not out_png.exists():
                    break
                if out_png.exists():
                    size = out_png.stat().st_size
                    if size > 0 and size == last:
                        return
                    last = size
                proc_wait(proc, 0.5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        if not out_png.exists() or out_png.stat().st_size == 0:
            raise RuntimeError("Chrome CLI 스크린샷 실패 (timeout)")

    def close(self):
        shutil.rmtree(self.profile, ignore_errors=True)


def proc_wait(proc, seconds):
    try:
        proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        pass


def find_chrome() -> str | None:
    env = os.environ.get("CHROME_PATH")
    if env and Path(env).exists():
        return env
    for c in CHROME_CANDIDATES:
        if os.path.isabs(c):
            if Path(c).exists():
                return c
        elif shutil.which(c):
            return shutil.which(c)
    return None


def make_backend(prefer: str = "auto"):
    errors = []
    if prefer in ("auto", "playwright"):
        try:
            return PlaywrightBackend()
        except ImportError:
            errors.append("playwright 미설치 (python3 -m pip install --user playwright)")
        except Exception as e:
            errors.append(str(e))
        if prefer == "playwright":
            raise RuntimeError("; ".join(errors))
    if prefer in ("auto", "chrome"):
        chrome = find_chrome()
        if chrome:
            return ChromeCliBackend(chrome)
        errors.append("Chrome/Chromium 없음")
    raise RuntimeError("사용 가능한 캡처 엔진 없음 — " + "; ".join(errors))


# ── 실행 ──────────────────────────────────────────────────────────────────────
def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def attach_screenshots(projects: list[dict], manifest: dict, root: Path) -> None:
    """manifest 의 파일이 실제로 있을 때만 project['screenshots'] 를 붙인다 (sync_projects 와 공용)"""
    for p in projects:
        e = manifest.get(p.get("slug")) or {}
        shots = {k: e[k] for k in ("desktop", "mobile") if e.get(k) and (root / e[k]).exists()}
        if shots.get("desktop") and is_target(p):
            p["screenshots"] = shots
        else:
            p.pop("screenshots", None)


def capture_project(backend, p: dict, root: Path, out_dir_rel: str) -> dict:
    """한 프로젝트 캡처. 성공하면 새 manifest 항목, 실패하면 예외"""
    slug = p["slug"]
    out_dir = root / out_dir_rel / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    check_url(p["liveUrl"])
    result = {"url": p["liveUrl"], "capturedAt": now_iso(), "engine": backend.name}
    with tempfile.TemporaryDirectory(prefix="shot-") as tmp:
        views = [("desktop", DESKTOP)] + ([("mobile", MOBILE)] if backend.supports_mobile else [])
        for key, view in views:
            png = Path(tmp) / f"{key}.png"
            backend.capture(p["liveUrl"], png, view)
            # 이전 확장자 파일 정리 후 저장
            for old in out_dir.glob(f"{key}.*"):
                old.unlink()
            final = encode_image(png, out_dir / key)
            result[key] = final.relative_to(root).as_posix()
    return result


def run(root: Path, *, dry_run=False, refresh=(), refresh_all=False, max_age_days=DEFAULT_MAX_AGE_DAYS,
        backend_pref="auto", strict=False, backend=None, now=None) -> int:
    gen_path = root / "data" / "projects.generated.json"
    man_path = root / "data" / "screenshots.json"
    index_path = root / "index.html"
    data = load_json(gen_path, None)
    if not data:
        print(f"[ERROR] {gen_path} 없음", file=sys.stderr)
        return 1
    manifest_doc = load_json(man_path, {"schemaVersion": 1, "screenshots": {}})
    manifest = manifest_doc.setdefault("screenshots", {})
    now = now or datetime.now(KST)
    refresh = set(refresh)

    projects = data["projects"]
    todo = []
    for p in projects:
        if not is_target(p):
            continue
        reason = capture_reason(p, manifest.get(p["slug"]), root, now, refresh, refresh_all, max_age_days)
        if reason:
            todo.append((p, reason))
        else:
            print(f"  [{p['slug']}] 유지 (마지막 캡처 {manifest[p['slug']].get('capturedAt', '?')})")

    print(f"Screenshot 대상 {sum(1 for p in projects if is_target(p))}개, 캡처 필요 {len(todo)}개")
    for p, reason in todo:
        print(f"  [{p['slug']}] 캡처 예정 — {reason}: {p['liveUrl']}")
        if p.get("screenshotRefresh"):
            print(f"    [WARN] portfolio.yml 의 screenshot_refresh: true 는 매 sync 마다 다시 캡처합니다. 확인 후 false 로 돌려두세요.")
    if dry_run:
        print("Dry run — 캡처/파일 변경 없음")
        return 0

    failures = 0
    if todo:
        own_backend = backend is None
        try:
            backend = backend or make_backend(backend_pref)
        except RuntimeError as e:
            print(f"[WARN] {e} — Screenshot 을 건너뜁니다 (기존 파일 유지)", file=sys.stderr)
            backend = None
            failures = len(todo)
        if backend is not None:
            print(f"엔진: {backend.name}" + ("" if backend.supports_mobile else " — Desktop 만 (Mobile 은 Playwright 필요)"))
            try:
                for p, reason in todo:
                    slug = p["slug"]
                    try:
                        entry = capture_project(backend, p, root, "assets/projects")
                        if not backend.supports_mobile:
                            old = manifest.get(slug) or {}
                            if old.get("mobile") and old.get("url") == p["liveUrl"] and (root / old["mobile"]).exists():
                                entry["mobile"] = old["mobile"]           # 기존 모바일 유지
                        manifest[slug] = entry
                        print(f"  [{slug}] 완료 → {entry['desktop']}" + (f", {entry['mobile']}" if entry.get("mobile") else ""))
                    except Exception as e:
                        failures += 1
                        prev = manifest.get(slug) or {}
                        prev.update({"lastError": str(e).splitlines()[0][:300], "lastAttemptAt": now_iso()})
                        manifest[slug] = prev
                        print(f"  [WARN] [{slug}] 캡처 실패 — 기존 Screenshot 유지: {str(e).splitlines()[0]}",
                              file=sys.stderr)
            finally:
                if own_backend:
                    backend.close()

    # 결과 반영 (변경이 있을 때만 파일 쓰기)
    before_projects = json.dumps(projects, ensure_ascii=False, sort_keys=True)
    attach_screenshots(projects, manifest, root)
    old_manifest = load_json(man_path, None)
    if old_manifest != manifest_doc:
        write_json(man_path, manifest_doc)
    if json.dumps(projects, ensure_ascii=False, sort_keys=True) != before_projects:
        write_json(gen_path, data)
        if index_path.exists():
            index_path.write_text(render_auto_section(index_path.read_text(encoding="utf-8"), projects,
                                                      data.get("generatedAt")),
                                  encoding="utf-8")
        print("projects.generated.json / index.html 에 Screenshot 반영")
    print(f"Screenshot: 캡처 {len(todo) - failures}, 실패 {failures}, 유지 {sum(1 for p in projects if is_target(p)) - len(todo)}")
    return 1 if (strict and failures) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(HERE.parent))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="append", default=[], metavar="SLUG")
    ap.add_argument("--refresh-all", action="store_true")
    ap.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    ap.add_argument("--backend", choices=("auto", "playwright", "chrome"), default="auto")
    ap.add_argument("--strict", action="store_true", help="캡처 실패 시 종료 코드 1")
    a = ap.parse_args()
    sys.exit(run(Path(a.root).resolve(), dry_run=a.dry_run, refresh=a.refresh, refresh_all=a.refresh_all,
                 max_age_days=a.max_age_days, backend_pref=a.backend, strict=a.strict))


if __name__ == "__main__":
    main()
