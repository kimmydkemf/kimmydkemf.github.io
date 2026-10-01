#!/usr/bin/env python3
"""
Phase 7 자동화 테스트 (네트워크 없음)

  - scripts/ci_sync.sh        : 임시 저장소 + bare 원격 + 가짜 gh CLI 로 pr / push / dry-run 모드
  - scripts/install_launchd.sh: 임시 LaunchAgents 디렉터리, launchctl 호출 생략
  - .github/workflows/sync-projects.yml : 구조 · 토큰 사용 규칙
  - validate_site --scan-repo : 실제 토큰 값이 파일에 들어가면 실패

  python3 scripts/test_automation.py
"""
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from test_portfolio_update import UpdaterTestBase, sh  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

FAKE_PAT = "pat-value-for-tests-" + "Zq7Kx2Lm9Rv4"      # 패턴에 걸리지 않는 가짜 값 → 실제 값 비교 경로를 검사

FAKE_GH = r'''#!/bin/bash
# 가짜 gh: 호출 인자를 기록하고 FAKE_GH_MODE 에 따라 응답
echo "$*" >> "$FAKE_GH_LOG"
case "$1 $2" in
  "pr list") [ "${FAKE_GH_MODE:-}" = "existing" ] && echo "https://github.com/x/y/pull/7"; exit 0 ;;
  "pr edit") exit 0 ;;
  "pr create")
    if [ "${FAKE_GH_MODE:-}" = "forbidden" ]; then
      echo "pull request create failed: GraphQL: GitHub Actions is not permitted to create or approve pull requests" >&2; exit 1
    fi
    echo "https://github.com/x/y/pull/8"; exit 0 ;;
esac
exit 0
'''


class TestCiSync(UpdaterTestBase):
    def setUp(self):
        super().setUp()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "gh").write_text(FAKE_GH, encoding="utf-8")
        (self.bin / "gh").chmod(0o755)
        self.gh_log = self.tmp / "gh.log"
        self.summary = self.tmp / "summary.md"

    def run_ci(self, **env_extra):
        env = {
            "PATH": f"{self.bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.tmp),
            "PORTFOLIO_PAT": FAKE_PAT,
            "PORTFOLIO_SYNC_ARGS": "--fixtures fixtures/repos",
            "SYNC_SCREENSHOTS": "0",
            "PORTFOLIO_NO_OPEN": "1",
            "GITHUB_STEP_SUMMARY": str(self.summary),
            "GITHUB_REPOSITORY": "kimmydkemf/kimmydkemf.github.io",
            "FAKE_GH_LOG": str(self.gh_log),
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        env.update({k: v for k, v in env_extra.items() if v is not None})
        for k, v in env_extra.items():
            if v is None:
                env.pop(k, None)
        return subprocess.run(["/bin/bash", "scripts/ci_sync.sh"], cwd=self.work, env=env,
                              capture_output=True, text=True, timeout=180)

    def remote_branches(self):
        out = sh("git", "--git-dir", str(self.remote), "branch", "--format=%(refname:short)", cwd=self.tmp).stdout
        return sorted(out.split())

    def remote_head_of(self, branch):
        return sh("git", "--git-dir", str(self.remote), "log", "-1", "--format=%s", branch, cwd=self.tmp).stdout.strip()

    def assert_no_pat(self, r):
        blob = r.stdout + r.stderr + (self.summary.read_text(encoding="utf-8") if self.summary.exists() else "")
        logf = self.work / "logs" / "portfolio-sync.log"
        if logf.exists():
            blob += logf.read_text(encoding="utf-8")
        self.assertNotIn(FAKE_PAT, blob)

    def test_missing_pat_stops(self):
        r = self.run_ci(PORTFOLIO_PAT=None)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("PORTFOLIO_PAT secret 이 없습니다", r.stdout)
        self.assertEqual(self.remote_branches(), ["main"])

    def test_pr_mode_creates_branch_and_pr(self):
        r = self.run_ci(SYNC_MODE="pr")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.remote_branches(), ["automation/portfolio-sync", "main"])
        self.assertEqual(self.remote_head_of("main"), "base")                        # main 은 그대로
        self.assertTrue(self.remote_head_of("automation/portfolio-sync").startswith("chore: sync portfolio projects"))
        gh = self.gh_log.read_text(encoding="utf-8")
        self.assertIn("pr create --head automation/portfolio-sync --base main", gh)
        summary = self.summary.read_text(encoding="utf-8")
        self.assertIn("📝 PR 생성: https://github.com/x/y/pull/8", summary)
        self.assertIn("🔒 Secret 검사 통과", summary)
        self.assert_no_pat(r)

    def test_pr_mode_updates_existing_pr(self):
        r = self.run_ci(SYNC_MODE="pr", FAKE_GH_MODE="existing")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        gh = self.gh_log.read_text(encoding="utf-8")
        self.assertIn("pr edit https://github.com/x/y/pull/7", gh)
        self.assertNotIn("pr create", gh)

    def test_pr_creation_forbidden_falls_back_to_compare_link(self):
        r = self.run_ci(SYNC_MODE="pr", FAKE_GH_MODE="forbidden")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        summary = self.summary.read_text(encoding="utf-8")
        self.assertIn("Allow GitHub Actions to create and approve pull requests", summary)
        self.assertIn("compare/main...automation/portfolio-sync", summary)
        self.assertIn("automation/portfolio-sync", self.remote_branches())

    def test_push_mode_pushes_to_base(self):
        r = self.run_ci(SYNC_MODE="push")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.remote_head_of("main").startswith("chore: sync portfolio projects"))
        self.assertEqual(self.remote_branches(), ["main"])
        self.assertFalse(self.gh_log.exists())
        self.assert_no_pat(r)
        # 두 번째 실행: 변경 없음 → push 없음
        before = self.remote_head_of("main")
        r2 = self.run_ci(SYNC_MODE="push")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertIn("변경 없음 — commit / push 하지 않음", self.summary.read_text(encoding="utf-8"))
        self.assertEqual(self.remote_head_of("main"), before)

    def test_dry_run_mode(self):
        r = self.run_ci(SYNC_MODE="dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("dry-run — 파일 변경 / commit 없음", self.summary.read_text(encoding="utf-8"))
        self.assertEqual(self.dirty(), "")
        self.assertEqual(self.remote_head_of("main"), "base")

    def test_invalid_mode(self):
        r = self.run_ci(SYNC_MODE="merge")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SYNC_MODE 는 pr | push | dry-run", r.stdout)

    def test_literal_token_in_data_blocks_push(self):
        # 패턴에는 안 걸리는 실제 토큰 값이 생성 데이터에 섞였다고 가정 → push 전 검사에서 막혀야 함
        manual = self.work / "data" / "projects.manual.json"
        manual.write_text(manual.read_text(encoding="utf-8").replace('"subtitle": "', f'"subtitle": "{FAKE_PAT} ', 1),
                          encoding="utf-8")
        sh("git", "commit", "-qam", "leak", cwd=self.work)
        sh("git", "push", "-q", "origin", "main", cwd=self.work)
        r = self.run_ci(SYNC_MODE="push")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("환경변수 GITHUB_TOKEN 의 실제 값이 들어 있음", r.stdout)
        self.assertIn("Secret 검사 실패 — push 하지 않았습니다", self.summary.read_text(encoding="utf-8"))
        self.assertEqual(self.remote_head_of("main"), "leak")                      # sync commit 은 push 안 됨
        self.assertNotIn(FAKE_PAT, r.stdout.replace(f"{FAKE_PAT} ", ""))           # 값 자체는 출력 안 함


class TestLaunchd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="launchd-test-"))
        self.env = dict(os.environ, LAUNCH_AGENTS_DIR=str(self.tmp / "LaunchAgents"), PORTFOLIO_LAUNCHD_NO_LOAD="1")
        self.plist = self.tmp / "LaunchAgents" / "com.dounselor.portfolio-sync.plist"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_sh(self, *args):
        return subprocess.run(["/bin/bash", str(HERE / "install_launchd.sh"), *args], env=self.env,
                              capture_output=True, text=True, timeout=30)

    def load(self):
        with open(self.plist, "rb") as f:
            return plistlib.load(f)

    def test_install_default_is_dry_run_at_3am(self):
        r = self.run_sh("install")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        d = self.load()
        self.assertEqual(d["Label"], "com.dounselor.portfolio-sync")
        self.assertEqual(d["ProgramArguments"][1:], [str(ROOT / "scripts" / "portfolio_update.sh"), "--mode", "dry-run"])
        self.assertEqual(d["StartCalendarInterval"], {"Hour": 3, "Minute": 0})
        self.assertNotIn("RunAtLoad", d)
        self.assertEqual(d["WorkingDirectory"], str(ROOT))
        self.assertIn("/opt/homebrew/bin", d["EnvironmentVariables"]["PATH"])
        self.assertEqual(d["StandardOutPath"], str(ROOT / "logs" / "launchd.log"))
        self.assertIn("launchctl bootstrap", r.stdout)

    def test_update_mode_and_schedule(self):
        r = self.run_sh("install", "--mode", "update", "--hour", "7", "--minute", "30", "--at-login")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        d = self.load()
        self.assertEqual(d["ProgramArguments"][-3:], ["--mode", "update", "--yes"])
        self.assertEqual(d["StartCalendarInterval"], {"Hour": 7, "Minute": 30})
        self.assertTrue(d["RunAtLoad"])
        self.assertIn("확인 없이 commit & push", r.stdout)

    def test_uninstall_and_status(self):
        self.run_sh("install")
        self.assertIn("plist:", self.run_sh("status").stdout)
        r = self.run_sh("uninstall")
        self.assertIn("해제 완료", r.stdout)
        self.assertFalse(self.plist.exists())
        self.assertIn("등록되어 있지 않습니다", self.run_sh("status").stdout)

    def test_invalid_args(self):
        for args in (("install", "--mode", "push"), ("install", "--hour", "24"), ("install", "--minute", "x")):
            self.assertNotEqual(self.run_sh(*args).returncode, 0, args)
        self.assertFalse(self.plist.exists())

    def test_print_is_valid_plist(self):
        r = self.run_sh("print", "--mode", "update")
        self.assertEqual(r.returncode, 0)
        d = plistlib.loads(r.stdout.encode())
        self.assertIn("--yes", d["ProgramArguments"])


@unittest.skipIf(yaml is None, "PyYAML 없음")
class TestWorkflow(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / ".github" / "workflows" / "sync-projects.yml"
        self.text = self.path.read_text(encoding="utf-8")
        self.wf = yaml.safe_load(self.text)

    def test_triggers(self):
        on = self.wf[True]                                   # YAML 의 'on' 은 True 로 읽힌다
        self.assertEqual(on["schedule"], [{"cron": "0 18 * * *"}])  # 03:00 KST
        self.assertEqual(on["repository_dispatch"]["types"], ["portfolio-sync"])
        self.assertEqual(on["workflow_dispatch"]["inputs"]["mode"]["default"], "pr")

    def test_permissions_and_concurrency(self):
        self.assertEqual(self.wf["permissions"], {"contents": "write", "pull-requests": "write"})
        self.assertEqual(self.wf["concurrency"]["group"], "portfolio-sync")

    def test_token_usage(self):
        steps = self.wf["jobs"]["sync"]["steps"]
        sync = next(s for s in steps if s.get("name") == "Sync")
        self.assertEqual(sync["env"]["PORTFOLIO_PAT"], "${{ secrets.PORTFOLIO_PAT }}")
        self.assertEqual(sync["run"], "bash scripts/ci_sync.sh")
        # secret 을 run 스크립트에 직접 끼워 넣지 않는다 (env 로만 전달)
        for s in steps:
            self.assertNotIn("secrets.", s.get("run", ""), s.get("name"))
        # 레포 읽기에 기본 GITHUB_TOKEN 을 쓰지 않는다
        self.assertNotIn("GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}", self.text)

    def test_referenced_scripts_exist(self):
        for s in self.wf["jobs"]["sync"]["steps"]:
            for word in s.get("run", "").split():
                if word.startswith("scripts/"):
                    self.assertTrue((ROOT / word).exists(), word)


class TestScanRepo(unittest.TestCase):
    def test_current_repo_passes(self):
        r = subprocess.run([sys.executable, str(HERE / "validate_site.py"), "--scan-repo"], cwd=ROOT,
                           capture_output=True, text=True, env=dict(os.environ, PORTFOLIO_PAT=FAKE_PAT))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("Secret 검사 통과", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
