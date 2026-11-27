from pathlib import Path
import subprocess
import sys

from git import Repo


def init_project(directory, files):
    repo = Repo.init(directory, initial_branch="main")
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test Author")
        config.set_value("user", "email", "test@example.org")
    for name, content in files.items():
        (Path(directory) / name).write_text(content, encoding="utf8")
    repo.index.add(list(files))
    repo.index.commit("Initialize test project")
    repo.create_remote("origin", "https://github.com/example/demo.git")
    return repo


def run_new(repo, answers):
    client = Path(__file__).resolve().parents[1] / "leanblueprint" / "client.py"
    return subprocess.run(
        [sys.executable, str(client), "--debug", "new"],
        cwd=repo.working_dir, input="\n".join(answers) + "\n",
        text=True, capture_output=True,
    )
