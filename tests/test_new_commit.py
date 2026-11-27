from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tests.project import init_project, run_new


class NewCommitTest(TestCase):
    def test_commits_the_manifest_only_when_present(self):
        files = {"lakefile.toml": 'name = "demo"\n[[lean_lib]]\nname = "Demo"\n'}
        for has_manifest in (False, True):
            with self.subTest(has_manifest=has_manifest), TemporaryDirectory() as directory:
                repo = init_project(directory, files)
                original = repo.head.commit
                if has_manifest:
                    (Path(directory) / "lake-manifest.json").write_text("{}\n", encoding="utf8")
                # Keep the defaults, skip both Lake updates, homepage and CI, then commit.
                result = run_new(repo, [""] * 11 + ["y", "n", "n", "n", "n", "y", ""])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                commit = repo.head.commit
                self.assertEqual(list(commit.parents), [original])
                self.assertEqual((commit.tree / "blueprint/src/content.tex").type, "blob")
                self.assertEqual("lake-manifest.json" in commit.tree, has_manifest)
