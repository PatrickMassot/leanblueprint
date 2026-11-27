from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tests.project import init_project, run_new


class NewLibrariesTest(TestCase):
    def test_finds_an_inline_default_library(self):
        lakefile = """import Lake
open Lake DSL
package demo
lean_lib Other
@[default_target] lean_lib Demo
"""
        with TemporaryDirectory() as directory:
            repo = init_project(directory, {"lakefile.lean": lakefile})
            # Accept the configuration defaults, create the blueprint, skip optional steps.
            result = run_new(repo, [""] * 12 + ["y", "n", "n", "n", "n", "n"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Lean library name [Demo/Other] (Demo)", result.stdout)

    def test_creates_a_blueprint_for_an_executable_only_project(self):
        lakefile = 'name = "demo"\n[[lean_exe]]\nname = "demo"\nroot = "Main"\n'
        with TemporaryDirectory() as directory:
            repo = init_project(directory, {"lakefile.toml": lakefile})
            result = run_new(repo, [""] * 11 + ["y", "n", "n", "n", "n"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((Path(directory) / "blueprint/src/content.tex").is_file())
            self.assertNotIn("Configure continuous integration", result.stdout)
