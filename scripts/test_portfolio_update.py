#!/usr/bin/env python3
"""
scripts/portfolio_update.sh 통합 테스트 (네트워크 없음)

임시 디렉터리에 현재 작업 트리 사본 + bare 원격 저장소를 만들고,
PORTFOLIO_SYNC_ARGS="--fixtures fixtures/repos" 로 GitHub 대신 샘플 데이터를 쓴다.
실제 저장소나 GitHub 에는 아무것도 push 하지 않는다.

실행:
  python3 scripts/test_portfolio_update.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import validate_site as vs  # noqa: E402

FAKE_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"   # 형식만 흉내 낸 가짜 값


def sh(*args, cwd, check=True, **kw):
    r = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, **kw)
    if check and r.returncode != 0:
        raise AssertionError(f"{args} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


class UpdaterTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="updater-test-"))
        self.work = self.tmp / "work"
        self.remote = self.tmp / "remote.git"
        ignore = shutil.ignore_patterns(".git", "__pycache__", "logs", ".env", ".env.*")
        shutil.copytree(ROOT, self.work, ignore=ignore)
        g = lambda *a: sh("git", *a, cwd=self.work)
        g("init", "-q", "-b", "main")
        g("config", "user.name", "Test")
        g("config", "user.email", "test@example.com")
        g("add", "-A")
        g("commit", "-q", "-m", "base")
        sh("git", "init", "-q", "--bare", str(self.remote), cwd=self.tmp)
        g("remote", "add", "origin", str(self.remote))
        g("push", "-q", "-u", "origin", "main")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_updater(self, *args, stdin="", env_extra=None):
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.tmp),                 # 사용자 git 설정/자격증명 격리
            "PORTFOLIO_SYNC_ARGS": "--fixtures fixtures/repos",
            "PORTFOLIO_NO_OPEN": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
        }
        env.update(env_extra or {})
        return subprocess.run(["/bin/bash", "scripts/portfolio_update.sh", *args], cwd=self.work,
                              input=stdin, capture_output=True, text=True, env=env, timeout=120)

    def head(self, where=None):
        return sh("git", "log", "-1", "--format=%s", *( [where] if where else [] ), cwd=self.work).stdout.strip()

    def remote_head(self):
        return sh("git", "--git-dir", str(self.remote), "log", "-1", "--format=%s", "main", cwd=self.tmp).stdout.strip()

    def dirty(self):
        return sh("git", "status", "--porcelain", cwd=self.work).stdout.strip()


class TestUpdater(UpdaterTestBase):
    def test_dry_run_changes_nothing(self):
        r = self.run_updater("--mode", "dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("No files were changed or committed.", r.stdout)
        self.assertIn("Dry run", r.stdout)
        self.assertEqual(self.dirty(), "")
        self.assertEqual(self.head(), "base")

    def test_preview_uses_temp_copy(self):
        r = self.run_updater("--mode", "preview")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("미리보기 서버: http://127.0.0.1:", r.stdout)
        self.assertIn("추가 4", r.stdout)                         # fixture 4개가 새로 보임
        self.assertIn("Validation 통과", r.stdout)
        self.assertIn("저장소 파일은 변경되지 않았습니다", r.stdout)
        self.assertEqual(self.dirty(), "")

    def test_update_commits_and_pushes_then_idempotent(self):
        r = self.run_updater("--mode", "update", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Validation 통과", r.stdout)
        self.assertIn("push 완료 → origin/main", r.stdout)
        self.assertTrue(self.head().startswith("chore: sync portfolio projects ("), self.head())
        self.assertEqual(self.remote_head(), self.head())
        files = sh("git", "show", "--name-only", "--format=", "HEAD", cwd=self.work).stdout.split()
        self.assertEqual(sorted(files), ["data/projects.generated.json", "index.html", "scripts/projects.json"])
        self.assertEqual(self.dirty(), "")
        log = (self.work / "logs" / "portfolio-sync.log").read_text(encoding="utf-8")
        self.assertIn("update: pushed", log)
        self.assertNotIn("ghp_", log)

        # 두 번째 실행: 변경 없음 → commit 없음
        before = self.head()
        r2 = self.run_updater("--mode", "update", "--yes")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertIn("변경 없음 — commit 하지 않습니다.", r2.stdout)
        self.assertEqual(self.head(), before)

    def test_no_push(self):
        r = self.run_updater("--mode", "update", "--yes", "--no-push")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("push 생략", r.stdout)
        self.assertTrue(self.head().startswith("chore: sync"))
        self.assertEqual(self.remote_head(), "base")

    def test_interactive_decline_and_restore(self):
        # 메뉴 3 → 미리보기? n → commit? n → 되돌릴까요? y
        r = self.run_updater(stdin="3\nn\nn\ny\n", env_extra={"PORTFOLIO_ALLOW_PIPED_INPUT": "1"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("되돌렸습니다.", r.stdout)
        self.assertEqual(self.dirty(), "")
        self.assertEqual(self.head(), "base")

    def test_menu_cancel(self):
        r = self.run_updater(stdin="4\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("취소했습니다.", r.stdout)
        self.assertEqual(self.dirty(), "")

    def test_non_interactive_update_without_yes_does_not_commit(self):
        r = self.run_updater("--mode", "update")                  # stdin 이 tty 가 아님 → 확인 질문은 n
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("(비대화형)", r.stdout)
        self.assertEqual(self.head(), "base")

    def test_secret_in_outputs_blocks_commit(self):
        manual = self.work / "data" / "projects.manual.json"
        text = manual.read_text(encoding="utf-8")
        manual.write_text(text.replace('"subtitle": "', f'"subtitle": "{FAKE_TOKEN} ', 1), encoding="utf-8")
        r = self.run_updater("--mode", "update", "--yes", "--no-pull")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Secret 패턴 발견", r.stdout)
        self.assertEqual(self.head(), "base")
        self.assertEqual(self.remote_head(), "base")

    def test_dirty_outputs_block_pull(self):
        (self.work / "index.html").write_text("changed", encoding="utf-8")
        r = self.run_updater("--mode", "update", "--yes")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("커밋되지 않은 변경", r.stdout + r.stderr)
        self.assertEqual(self.head(), "base")

    def test_unrelated_dirty_file_is_not_committed(self):
        (self.work / "notes.txt").write_text("local only", encoding="utf-8")
        r = self.run_updater("--mode", "update", "--yes", "--no-push")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        files = sh("git", "show", "--name-only", "--format=", "HEAD", cwd=self.work).stdout.split()
        self.assertNotIn("notes.txt", files)
        self.assertIn("?? notes.txt", self.dirty())

    def test_branch_guard(self):
        r = self.run_updater("--mode", "update", "--yes", env_extra={"PORTFOLIO_BRANCH": "develop"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("PORTFOLIO_BRANCH=develop", r.stdout + r.stderr)
        self.assertEqual(self.head(), "base")

    def test_missing_token_without_fixtures(self):
        r = self.run_updater("--mode", "dry-run", env_extra={"PORTFOLIO_SYNC_ARGS": ""})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("GITHUB_TOKEN 이 없습니다", r.stdout + r.stderr)

    def test_env_file_loading_does_not_print_values(self):
        (self.work / ".env").write_text(f"# comment\nexport GITHUB_TOKEN=\"{FAKE_TOKEN}\"  # note\nOTHER=ignored\n",
                                        encoding="utf-8")
        r = self.run_updater("--mode", "dry-run", env_extra={"PORTFOLIO_SYNC_ARGS": "--fixtures fixtures/repos"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("GITHUB_TOKEN 설정됨", r.stdout)
        self.assertNotIn(FAKE_TOKEN, r.stdout + r.stderr)
        self.assertNotIn(FAKE_TOKEN, (self.work / "logs" / "portfolio-sync.log").read_text(encoding="utf-8"))


class TestValidateSite(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="validate-test-"))
        for f in ("index.html", "CNAME", "data/projects.generated.json", "data/projects.manual.json",
                  "scripts/projects.json"):
            (self.tmp / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / f, self.tmp / f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def validate(self):
        return vs.validate(self.tmp, list(vs.DEFAULT_FILES))

    def test_current_repo_passes(self):
        r = vs.validate(ROOT, list(vs.DEFAULT_FILES))
        self.assertEqual(r.errors, [])

    def test_cname_guard(self):
        (self.tmp / "CNAME").write_text("example.com\n", encoding="utf-8")
        self.assertTrue(any("CNAME" in e for e in self.validate().errors))
        (self.tmp / "CNAME").unlink()
        self.assertTrue(any("CNAME 없음" in e for e in self.validate().errors))

    def test_index_json_mismatch(self):
        p = self.tmp / "index.html"
        p.write_text(p.read_text(encoding="utf-8").replace('id="proj-mynote"', 'id="proj-other"', 1), encoding="utf-8")
        self.assertTrue(any("불일치" in e for e in self.validate().errors))

    def test_empty_projects_fails(self):
        (self.tmp / "data" / "projects.generated.json").write_text('{"schemaVersion":1,"projects":[]}', encoding="utf-8")
        self.assertTrue(any("비어 있음" in e for e in self.validate().errors))

    def test_env_files(self):
        (self.tmp / ".env").write_text("GITHUB_TOKEN=\n", encoding="utf-8")
        (self.tmp / ".env.local").write_text("X=1\n", encoding="utf-8")
        shutil.copy(ROOT / ".env.example", self.tmp / ".env.example")
        errs = vs.validate(self.tmp, [".env", ".env.local", ".env.example"]).errors
        self.assertEqual(sorted(e.split(" ")[0] for e in errs), [".env", ".env.local"])

    def test_secret_patterns(self):
        self.assertEqual(vs.scan_secrets(FAKE_TOKEN), ["GitHub token"])
        self.assertEqual(vs.scan_secrets("github_pat_" + "a" * 50), ["GitHub fine-grained"])
        self.assertEqual(vs.scan_secrets("sk-ant-api03-" + "x" * 30), ["Anthropic key"])
        self.assertEqual(vs.scan_secrets("-----BEGIN OPENSSH PRIVATE KEY-----"), ["Private key"])
        # README 예시 같은 placeholder 는 통과
        self.assertEqual(vs.scan_secrets("GITHUB_TOKEN=github_pat_xxxxxxxxxxxx ghp_xxxx sk-ant-xxx"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
