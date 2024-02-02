import logging
import sys
import os
import subprocess
import shlex
from pathlib import Path
from typing import Optional, Dict, Any, List
from collections import deque
import re

import click
from jinja2 import Environment, FileSystemLoader, select_autoescape
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.console import Console
from rich.theme import Theme
from git.repo import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError


log = logging.getLogger("Mathlib tools")
log.setLevel(logging.INFO)
if (log.hasHandlers()):
    log.handlers.clear()
log.addHandler(logging.StreamHandler())

# Click aliases from Stephen Rauch at
# https://stackoverflow.com/questions/46641928
class CustomMultiCommand(click.Group):
    def command(self, *args, **kwargs):
        """Behaves the same as `click.Group.command()` except if passed
        a list of names, all after the first will be aliases for the first.
        """
        def decorator(f):
            if args and isinstance(args[0], list):
                _args = [args[0][0]] + list(args[1:])
                for alias in args[0][1:]:
                    cmd = super(CustomMultiCommand, self).command(
                        alias, *args[1:], **kwargs)(f)
                    cmd.short_help = "Alias for '{}'".format(_args[0])
                    cmd.hidden = True
            else:
                _args = args
            cmd = super(CustomMultiCommand, self).command(
                *_args, **kwargs)(f)
            return cmd

        return decorator

    """Allows the user to shorten commands to a (unique) prefix."""
    def get_command(self, ctx, cmd_name):
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        matches = [x for x in self.list_commands(ctx)
                   if x.startswith(cmd_name)]
        if not matches:
            return None
        elif len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])
        ctx.fail('Too many matches: %s' % ', '.join(sorted(matches)))

debug = False

def handle_exception(exc, msg):
    if debug:
        raise exc
    else:
        log.error(msg)
        sys.exit(-1)


custom_theme = Theme({
    "info": "italic",
    "warning": "yellow",
    "error": "bold red",
    "title": "bold",
    "prompt.default": "dim",
    "prompt.choices": "default"
})

console = Console(theme=custom_theme)

def ask(*args, **kwargs) -> str:
    kwargs.update({'console': console})
    return Prompt.ask(*args, **kwargs)

def confirm(*args, **kwargs) -> bool:
    kwargs.update({'console': console})
    return Confirm.ask(*args, **kwargs)

def askInt(*args, **kwargs) -> int:
    kwargs.update({'console': console})
    return IntPrompt.ask(*args, **kwargs)

def warning(msg: str) -> None:
    console.print(f"[warning]Warning:[/] {msg}")

def error(msg: str) -> None:
    console.print(f"[error]Error:[/] {msg}")
    sys.exit(1)

@click.group(cls=CustomMultiCommand, context_settings={ 'help_option_names':['-h', '--help']})
@click.option('--debug', 'python_debug', default=False, is_flag=True,
              help='Display python tracebacks in case of error.')
@click.version_option()
def cli(python_debug: bool) -> None:
    """Command line client to manage Lean blueprints.
    Use leanblueprint COMMAND --help to get more help on any specific command."""
    global  debug
    debug = python_debug

repo: Optional[Repo] = None
try:
    repo = Repo(".", search_parent_directories=True)
except InvalidGitRepositoryError:
    error("Could not find a Lean project. Please run this command from inside your project folder.")

assert repo is not None
if not (Path(repo.working_dir)/"lakefile.lean").exists():
    error("Could not find a Lean project. Please run this command from inside your project folder.")

blueprint_root = Path(repo.working_dir)/"blueprint"

@cli.command()
def new() -> None:
    """Create a new Lean blueprint in the given repository.
    """
    loader = FileSystemLoader(Path(__file__).parent/"templates")
    env = Environment(loader=loader, variable_start_string='{|', variable_end_string='|}',
                      comment_start_string='{--', comment_end_string='--}')

    console.print("Welcome to Lean blueprint", style="title")
    can_try_ci = True

    if repo is None:
        error("Could not find a Lean project. Please run this command from inside your project folder.")
    assert repo is not None

    if repo.is_dirty():
        error("The repository contains uncommitted changes. Please clean it up before creating a blueprint.")

    # Will no try to guess the author name
    try:
        name = repo.git.config("user.name")
    except GitCommandError:
        try:
            # Name of the author of the first commit.
            name = deque(repo.iter_commits(),1)[0].author.name
        except IndexError:
            # This will happen if there is no commit in the repo.
            name = "Anonymous"

    lakefile_path = Path(repo.working_dir)/"lakefile.lean"
    if not lakefile_path.exists():
        error("Could not find lakefile.lean in {repo.working_dir}")
    libs = []
    lib_re = re.compile(r"\s*lean_lib\s*([^ ]*)\b")
    default_re = re.compile(r"@\[default_target\]")
    default_lib = ""
    found_default = False
    with lakefile_path.open("r", encoding="utf8") as lf:
        for line in lf:
            m = lib_re.match(line)
            if m:
                libs.append(m.group(1))
                if found_default:
                    default_lib = m.group(1)
            found_default = bool(default_re.match(line))
    if not libs:
        warning("Could not find Lean library names in lakefile. Will not propose to setup continuous integration.")
        can_try_ci = False

    # Will now try to guess the GitHub url
    github = ""
    githubIO = ""
    doc_home = ""
    githubUserName = ""
    githubRepoName = ""
    try:
        url = repo.remote().url
    except ValueError:
        url = None
    if url:
        m = re.match(r"https://github.com/(.*)/(.*)\.git", url)
        if m:
            githubUserName = m.group(1)
            githubRepoName = m.group(2)
        else:
            m = re.match(r"git@github.com:(.*)/(.*)\.git", url)
            if m:
                githubUserName = m.group(1)
                githubRepoName = m.group(2)
        if githubUserName:
            github = f"https://github.com/{githubUserName}/{githubRepoName}"
            githubIO = f"https://{githubUserName}.github.io/{githubRepoName}"
            doc_home  = f"https://{githubUserName}.github.io/{githubRepoName}/docs"
        else:
            warning("Could not guess GitHub information. Will not propose to setup continuous integration.")
            can_try_ci = False

    out_dir = Path(repo.working_dir)/"blueprint"
    if out_dir.exists():
        error("There is already a blueprint folder. Aborting blueprint creation.")

    console.print("We will now ask some questions to configure your blueprint. All answers can ce changed later by editing either the plastex.cfg file or the tex files.")
    config: Dict[str, Any] = dict()

    if 'master' in repo.branches:
        config['master_branch'] = "master"
    elif 'main' in repo.branches:
        config['master_branch'] = "main"
    else:
        config['master_branch'] = ask("\nName of your main Git branch")

    config['github_username'] = githubUserName
    config['github_projectname'] = githubRepoName


    console.print("\nGeneral information about the project", style="title")
    config['title'] = ask("Project title", default="My formalization project")
    config['lib_name'] = ask("Lean library name", choices=libs, default=default_lib or libs[0])
    config['author'] = ask("Author ([info]use \\and to separate authors if needed[/])", default=name)

    config['github'] = ask("Url of github repository", default=github)
    config['home'] = ask("Url of project website", default=githubIO)
    config['dochome'] = ask("Url of project API documentation", default=doc_home)

    console.print("\nLaTeX settings for the pdf version", style="title")
    config['documentclass'] = ask("LaTeX document class", default="report")
    config['paper'] = ask("LaTeX paper", default="a4paper")

    console.print("\nLaTeX settings for the web version", style="title")
    config['showmore'] = confirm("Show buttons allowing to show or hide all proofs", default=True)
    config['toc_depth'] = askInt("Table of contents depth", default=3)
    config['split_level'] = askInt("Split file level [info](0 means each chapter gets a file, 1 means the same for sections etc.[/])", default=0)
    config['localtoc_depth'] = askInt("Per html file local table of contents depth [info](0 means there will be no local table of contents)[/]", default=0)

    console.print("\nConfiguration completed", style="title")

    if not confirm("Proceed with blueprint creation?"):
        error("Aborting blueprint creation per user request.")

    out_dir.mkdir()
    (out_dir/"src").mkdir()
    for tpl_name in env.list_templates():
        if tpl_name.endswith("blueprint.yml"):
            continue
        tpl = env.get_template(tpl_name)
        path = out_dir/"src"/tpl_name
        path.parent.mkdir(exist_ok=True)
        tpl.stream(config).dump(str(path))

    console.print("\nBlueprint source sucessfully created in the blueprint folder :tada:\n")

    workflow_files: List[Path] = []
    if can_try_ci and confirm("Configure continuous integration to compile blueprint?",
               default=True):
        tpl = env.get_template("blueprint.yml")
        path = Path(repo.working_dir)/".github"/"workflows"
        path.mkdir(parents=True, exist_ok=True)
        tpl.stream(config).dump(str(path/"blueprint.yml"))
        console.print(f"GitHub workflow file created at {path/'blueprint.yml'}")
        workflow_files.append(path/'blueprint.yml')


    if not confirm("\nCommit to git repository?"):
        sys.exit(0)

    msg = ask("Commit message", default="Setup blueprint")
    repo.index.add([out_dir] + workflow_files)
    repo.index.commit(msg)
    console.print("Git commit created. Don't forget to push when you are ready.")

@cli.command()
def pdf() -> None:
    (blueprint_root/"print").mkdir(exist_ok=True)
    args = shlex.split("xelatex -output-directory=../print print.tex")
    subprocess.run(args, cwd=str(blueprint_root/"src"), check=True)

def safe_cli():
    try:
        cli() # pylint: disable=no-value-for-parameter
    except Exception as err:
        handle_exception(err, str(err))

if __name__ == "__main__":
    # This allows `python3 -m leanblueprint.client`.
    # This is useful for when python is on the path but its installed scripts are not
    safe_cli()
