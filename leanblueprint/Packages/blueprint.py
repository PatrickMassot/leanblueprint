"""
Package Lean blueprint

This depends on the depgraph plugin. This plugin has to be installed but then it is
used automatically.

Options:
* project: lean project path

* showmore: enable buttons showing or hiding proofs (this requires the showmore plugin).

You can also add options that will be passed to the dependency graph package.
"""

import json
import re
import string
from pathlib import Path

from jinja2 import Template
from plasTeX import Command
from plasTeX.Logging import getLogger
from plasTeX.PackageResource import PackageCss, PackageTemplateDir
from plastexdepgraph.Packages.depgraph import item_kind

log = getLogger()

PKG_DIR = Path(__file__).parent
STATIC_DIR = Path(__file__).parent.parent / "static"


def rewrite_lean_links(html_str: str, document) -> str:
    """Jinja2 filter to rewrite doc-gen links at render time.

    - Links to declarations in the blueprint → blueprint URL (using node.url)
    - Links not in blueprint → project dochome
    """
    lean_to_node = document.userdata.get("lean_to_blueprint_node", {})
    project_dochome = document.userdata.get(
        "project_dochome_for_links",
        "https://leanprover-community.github.io/mathlib4_docs",
    )
    project_dochome = project_dochome.rstrip("/")

    def replace_link(match):
        href = match.group(1)
        link_text = match.group(2)

        # Extract the Lean declaration name from the href
        hash_match = re.search(r'#([^"]+)', href)
        if hash_match:
            lean_name = hash_match.group(1)

            # Check if in blueprint
            if lean_name in lean_to_node:
                node = lean_to_node[lean_name]
                # At render time, node.url should be available
                try:
                    node_url = node.url
                    if node_url:
                        return f'<a href="{node_url}" class="blueprint-link" title="View in blueprint">{link_text}</a>'
                except Exception:
                    pass

        # Not in blueprint - rewrite to dochome
        if href.startswith("./"):
            new_href = project_dochome + href[1:]
        elif href.startswith("../"):
            path = href
            while path.startswith("../"):
                path = path[3:]
            new_href = f"{project_dochome}/{path}"
        else:
            new_href = href

        return f'<a href="{new_href}" title="View in docs">{link_text}</a>'

    # Match <a href="...">...</a> patterns
    return re.sub(
        r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', replace_link, html_str, flags=re.DOTALL
    )


def load_docgen_declarations(document) -> dict:
    """Load declaration data from doc-gen4 declaration-data.bmp."""
    search_paths = [
        document.userdata.get("docgen_declarations_path"),
        "../docbuild/.lake/build/doc/declarations/declaration-data.bmp",
        "../../docbuild/.lake/build/doc/declarations/declaration-data.bmp",
    ]
    working_dir = Path(document.userdata.get("working-dir", "."))

    for rel_path in search_paths:
        if rel_path is None:
            continue
        full_path = working_dir / rel_path
        if full_path.exists():
            try:
                data = json.loads(full_path.read_text())
                return data.get("declarations", {})
            except Exception as e:
                log.warning(f"Failed to parse {full_path}: {e}")
    return {}


def parse_docgen_statement(html_path: Path, decl_name: str) -> dict:
    """Parse the Lean statement, equation, and structure fields from a doc-gen HTML file.

    Returns a dict with keys:
        - statement_text: plain text of the declaration header
        - equation_text: plain text of equations (for defs)
        - statement_html: HTML of the declaration header
        - equation_html: HTML of equations (for defs)
        - fields_html: HTML of structure fields (for structures)
        - fields_text: plain text of structure fields (for structures)

    Links are kept as-is - they will be rewritten at render time by a Jinja2 filter.
    """
    result = {
        "statement_text": "",
        "equation_text": "",
        "statement_html": "",
        "equation_html": "",
        "fields_html": "",
        "fields_text": "",
    }

    if not html_path.exists():
        return result

    try:
        content = html_path.read_text()

        # Find the specific declaration block
        start_pattern = rf'<div class="decl" id="{re.escape(decl_name)}">'
        start_match = re.search(start_pattern, content)
        if not start_match:
            return result

        start_pos = start_match.end()

        # Find where this declaration ends - look for next declaration or mod_doc
        end_pattern = r'<div class="(?:decl|mod_doc)"'
        end_match = re.search(end_pattern, content[start_pos:])
        if end_match:
            decl_html = content[start_pos : start_pos + end_match.start()]
        else:
            decl_html = content[start_pos:]

        # Extract the raw decl_header HTML for styled display
        # Keep links as-is - they'll be rewritten at render time
        # Note: decl_header may contain nested divs (e.g., decl_type), so we need to match balanced tags
        header_start_pattern = r'<div class="decl_header">'
        header_start_match = re.search(header_start_pattern, decl_html)
        if header_start_match:
            # Find the matching closing </div> by counting nested divs
            start_idx = header_start_match.end()
            depth = 1
            pos = start_idx
            while depth > 0 and pos < len(decl_html):
                next_open = decl_html.find("<div", pos)
                next_close = decl_html.find("</div>", pos)
                if next_close == -1:
                    break
                if next_open != -1 and next_open < next_close:
                    depth += 1
                    pos = next_open + 4
                else:
                    depth -= 1
                    if depth == 0:
                        raw_header = decl_html[start_idx:next_close]
                        result["statement_html"] = (
                            f'<div class="decl_header">{raw_header}</div>'
                        )
                        # Also extract plain text version as fallback
                        header_text = raw_header
                        header_text = re.sub(
                            r'<span class="decl_kind">.*?</span>', "", header_text
                        )
                        header_text = re.sub(
                            r'<span class="decl_name">.*?</span>', "", header_text
                        )
                        header_text = re.sub(
                            r'<a[^>]*class="break_within"[^>]*>.*?</a>', "", header_text
                        )
                        header_text = re.sub(r"<a[^>]*>", "", header_text)
                        header_text = re.sub(r"</a>", "", header_text)
                        header_text = re.sub(r"<span[^>]*>", "", header_text)
                        header_text = re.sub(r"</span>", "", header_text)
                        header_text = re.sub(
                            r'<div class="decl_type">', " : ", header_text
                        )
                        header_text = re.sub(r"</div>", "", header_text)
                        header_text = re.sub(r"<[^>]+>", "", header_text)
                        header_text = re.sub(r"\s+", " ", header_text).strip()
                        header_text = re.sub(r"^[\s.]+", "", header_text)
                        header_text = re.sub(r":\s*:", ":", header_text)
                        result["statement_text"] = header_text
                    pos = next_close + 6

        # Extract equation from Equations details block - only within THIS declaration
        eq_pattern = r'<details><summary>Equations</summary><ul class="equations">(.*?)</ul></details>'
        eq_match = re.search(eq_pattern, decl_html, re.DOTALL)
        if eq_match:
            eq_html = eq_match.group(1)

            # Keep links as-is for render-time rewriting
            result["equation_html"] = (
                f'<ul class="equations lean-equations">{eq_html}</ul>'
            )

            # Also create plain text version
            eq_html_clean = re.sub(r"<a[^>]*>", "", eq_html)
            eq_html_clean = re.sub(r"</a>", "", eq_html_clean)
            eq_html_clean = re.sub(r"<span[^>]*>", "", eq_html_clean)
            eq_html_clean = re.sub(r"</span>", "", eq_html_clean)
            eq_html_clean = re.sub(r'<li class="equation">', "", eq_html_clean)
            eq_html_clean = re.sub(r"</li>", "\n", eq_html_clean)
            eq_html_clean = re.sub(r"<[^>]+>", "", eq_html_clean)
            eq_html_clean = re.sub(r"\s+", " ", eq_html_clean).strip()
            result["equation_text"] = eq_html_clean

        # Extract structure fields from structure_fields ul - only within THIS declaration
        fields_pattern = r'<ul class="structure_fields"[^>]*>(.*?)</ul>'
        fields_match = re.search(fields_pattern, decl_html, re.DOTALL)
        if fields_match:
            fields_html = fields_match.group(1)

            # Keep links as-is for render-time rewriting
            result["fields_html"] = (
                f'<ul class="structure_fields lean-structure-fields">{fields_html}</ul>'
            )

            # Also create plain text version
            fields_text_parts = []
            field_pattern = r'<li[^>]*class="structure_field"[^>]*>.*?<div class="structure_field_info">(.*?)</div>'
            for field_match in re.finditer(field_pattern, fields_html, re.DOTALL):
                field_info = field_match.group(1)
                # Strip HTML tags for plain text
                field_text = re.sub(r"<[^>]+>", "", field_info)
                field_text = re.sub(r"\s+", " ", field_text).strip()
                if field_text:
                    fields_text_parts.append(field_text)
            result["fields_text"] = "\n".join(fields_text_parts)

        return result
    except Exception as e:
        log.warning(f"Failed to parse statement from {html_path}: {e}")
    return result


def get_docgen_base_path(document) -> Path:
    """Get the base path for doc-gen HTML files."""
    search_paths = [
        "../docbuild/.lake/build/doc",
        "../../docbuild/.lake/build/doc",
    ]
    working_dir = Path(document.userdata.get("working-dir", "."))

    for rel_path in search_paths:
        full_path = working_dir / rel_path
        if full_path.exists():
            return full_path
    return None


class home(Command):
    r"""\home{url}"""

    args = "url:url"

    def invoke(self, tex):
        Command.invoke(self, tex)
        self.ownerDocument.userdata["project_home"] = self.attributes["url"]
        return []


class github(Command):
    r"""\github{url}"""

    args = "url:url"

    def invoke(self, tex):
        Command.invoke(self, tex)
        self.ownerDocument.userdata["project_github"] = self.attributes[
            "url"
        ].textContent.rstrip("/")
        return []


class dochome(Command):
    r"""\dochome{url}"""

    args = "url:url"

    def invoke(self, tex):
        Command.invoke(self, tex)
        self.ownerDocument.userdata["project_dochome"] = self.attributes[
            "url"
        ].textContent
        return []


class graphcolor(Command):
    r"""\graphcolor{node_type}{color}{color_descr}"""

    args = "node_type:str color:str color_descr:str"

    def digest(self, tokens):
        Command.digest(self, tokens)
        attrs = self.attributes
        colors = self.ownerDocument.userdata["dep_graph"]["colors"]
        node_type = attrs["node_type"]
        if node_type not in colors:
            log.warning(f"Unknown node type {node_type}")
        colors[node_type] = (attrs["color"].strip(), attrs["color_descr"].strip())


class leanok(Command):
    r"""\leanok"""

    def digest(self, tokens):
        Command.digest(self, tokens)
        self.parentNode.userdata["leanok"] = True


class leantarget(Command):
    r"""\leantarget - marks this theorem/definition as a main target result"""

    def digest(self, tokens):
        Command.digest(self, tokens)
        self.parentNode.userdata["leantarget"] = True


class leanhelper(Command):
    r"""\leanhelper - marks this theorem/lemma as a helper/auxiliary result"""

    def digest(self, tokens):
        Command.digest(self, tokens)
        self.parentNode.userdata["leanhelper"] = True


class notready(Command):
    r"""\notready"""

    def digest(self, tokens):
        Command.digest(self, tokens)
        self.parentNode.userdata["notready"] = True


class mathlibok(Command):
    r"""\mathlibok"""

    def digest(self, tokens):
        Command.digest(self, tokens)
        self.parentNode.userdata["leanok"] = True
        self.parentNode.userdata["mathlibok"] = True


class lean(Command):
    r"""\lean{decl list}"""

    args = "decls:list:nox"

    def digest(self, tokens):
        Command.digest(self, tokens)
        decls = [dec.strip() for dec in self.attributes["decls"]]
        self.parentNode.setUserData("leandecls", decls)
        all_decls = self.ownerDocument.userdata.setdefault("lean_decls", [])
        all_decls.extend(decls)


class discussion(Command):
    r"""\discussion{issue_number}"""

    args = "issue:str"

    def digest(self, tokens):
        Command.digest(self, tokens)
        self.parentNode.setUserData(
            "issue", self.attributes["issue"].lstrip("#").strip()
        )


CHECKMARK_TPL = Template(
    """
    {% if obj.userdata.leanok and ('proved_by' not in obj.userdata or obj.userdata.proved_by.userdata.leanok ) %}
    ✓
    {% endif %}
"""
)

LEAN_SIDE_PANEL_TPL = Template(
    """
{% if obj.userdata.lean_entries %}
{% set has_content = [] %}
{% for entry in obj.userdata.lean_entries %}
{% if entry.statement_html or entry.statement %}{% if has_content.append(1) %}{% endif %}{% endif %}
{% endfor %}
{% if has_content %}
<div class="lean-side-panel{% if obj.userdata.leantarget %} lean-target{% endif %}{% if obj.userdata.leanhelper %} lean-helper{% endif %}">
  {% for entry in obj.userdata.lean_entries %}
  {% if entry.statement_html or entry.statement %}
  <div class="lean-entry">
    {% if entry.statement_html %}
    <div class="lean-decl-box">
      <div class="lean-decl-links">
        <a href="{{ entry.doc_url }}" class="lean-doc-link" title="View documentation">docs</a>
        {% if entry.github_url %}<a href="{{ entry.github_url }}" class="lean-src-link" title="View source">source</a>{% endif %}
      </div>
      {{ doc.userdata.rewrite_lean_links_fn(entry.statement_html, doc) | safe }}
      {% if entry.fields_html %}
      {{ doc.userdata.rewrite_lean_links_fn(entry.fields_html, doc) | safe }}
      {% elif entry.fields_text %}
      <pre class="lean-fields">{{ entry.fields_text }}</pre>
      {% endif %}
      {% if entry.equation_html %}
      {{ doc.userdata.rewrite_lean_links_fn(entry.equation_html, doc) | safe }}
      {% elif entry.equation %}
      <pre class="lean-equation">{{ entry.equation }}</pre>
      {% endif %}
    </div>
    {% elif entry.statement %}
    <div class="lean-entry-header">
      <a href="{{ entry.doc_url }}" class="lean-decl-link" title="View documentation">{{ entry.short_name }}</a>
      {% if entry.github_url %}<a href="{{ entry.github_url }}" class="lean-src" title="View source">📄</a>{% endif %}
    </div>
    <pre class="lean-statement">{{ entry.statement }}</pre>
    {% if entry.fields_html %}
    {{ doc.userdata.rewrite_lean_links_fn(entry.fields_html, doc) | safe }}
    {% elif entry.fields_text %}
    <pre class="lean-fields">{{ entry.fields_text }}</pre>
    {% endif %}
    {% if entry.equation_html %}
    {{ doc.userdata.rewrite_lean_links_fn(entry.equation_html, doc) | safe }}
    {% elif entry.equation %}
    <pre class="lean-equation">{{ entry.equation }}</pre>
    {% endif %}
    {% endif %}
  </div>
  {% endif %}
  {% endfor %}
</div>
{% endif %}
{% endif %}
"""
)

GITHUB_ISSUE_TPL = Template(
    """
    {% if obj.userdata.issue %}
    <a class="github_link" href="{{ obj.ownerDocument.userdata.project_github }}/issues/{{ obj.userdata.issue }}">Discussion</a>
    {% endif %}
"""
)

LEAN_LINKS_TPL = Template(
    """
  {% if thm.userdata['lean_urls'] -%}
    {%- if thm.userdata['lean_urls']|length > 1 -%}
  <div class="tooltip">
      <span class="lean_link">Lean</span>
      <ul class="tooltip_list">
        {% for name, url in thm.userdata['lean_urls'] %}
           <li><a href="{{ url }}" class="lean_decl">{{ name }}</a></li>
        {% endfor %}
      </ul>
  </div>
    {%- else -%}
    <a class="lean_link lean_decl" href="{{ thm.userdata['lean_urls'][0][1] }}">Lean</a>
    {%- endif -%}
    {%- endif -%}
"""
)

GITHUB_LINK_TPL = Template(
    """
  {% if thm.userdata['issue'] -%}
  <a class="issue_link" href="{{ document.userdata['project_github'] }}/issues/{{ thm.userdata['issue'] }}">Discussion</a>
  {%- endif -%}
"""
)


def ProcessOptions(options, document):
    """This is called when the package is loaded."""

    # We want to ensure the depgraph and showmore packages are loaded.
    # We first need to make sure the corresponding plugins are used.
    # This is a bit hacky but needed for backward compatibility with
    # project who used the blueprint package before the depgraph one was
    # split.
    plugins = document.config["general"].data["plugins"].value
    if "plastexdepgraph" not in plugins:
        plugins.append("plastexdepgraph")
    # And now load the package.
    document.context.loadPythonPackage(document, "depgraph", options)
    if "showmore" in options:
        if "plastexshowmore" not in plugins:
            plugins.append("plastexshowmore")
        # And now load the package.
        document.context.loadPythonPackage(document, "showmore", {})

    templatedir = PackageTemplateDir(path=PKG_DIR / "renderer_templates")
    document.addPackageResource(templatedir)

    # Register the link rewriting function for use in templates
    document.userdata["rewrite_lean_links_fn"] = rewrite_lean_links

    jobname = document.userdata["jobname"]
    outdir = document.config["files"]["directory"]
    outdir = string.Template(outdir).substitute({"jobname": jobname})

    def make_lean_data() -> None:
        """
        Build url and formalization status for nodes in the dependency graphs.
        Also create the file lean_decls of all Lean names referred to in the blueprint.
        """

        project_dochome = document.userdata.get(
            "project_dochome", "https://leanprover-community.github.io/mathlib4_docs"
        )
        project_github = document.userdata.get("project_github", "")

        # Load doc-gen data
        docgen_decls = load_docgen_declarations(document)
        docgen_base = get_docgen_base_path(document)

        # Build mapping from Lean names to blueprint nodes
        # URLs will be resolved at render time when node.url is available
        lean_to_node = {}
        for graph in document.userdata["dep_graph"]["graphs"].values():
            for node in graph.nodes:
                leandecls = node.userdata.get("leandecls", [])
                for leandecl in leandecls:
                    lean_to_node[leandecl] = node

        # Store the mapping and dochome in document for access during rendering
        document.userdata["lean_to_blueprint_node"] = lean_to_node
        document.userdata["project_dochome_for_links"] = project_dochome

        for graph in document.userdata["dep_graph"]["graphs"].values():
            nodes = graph.nodes
            for node in nodes:
                leandecls = node.userdata.get("leandecls", [])
                lean_urls = []
                lean_entries = []
                for leandecl in leandecls:
                    lean_urls.append(
                        (leandecl, f"{project_dochome}/find/#doc/{leandecl}")
                    )

                    # Build lean_entries with docgen data
                    decl_info = docgen_decls.get(leandecl, {})
                    doc_link = decl_info.get("docLink", "").lstrip("./")

                    # Parse statement and equation from doc-gen HTML if available
                    # Links are kept as relative - will be rewritten at render time
                    statement = ""
                    equation = ""
                    statement_html = ""
                    equation_html = ""
                    fields_html = ""
                    fields_text = ""
                    if docgen_base and doc_link:
                        html_file = doc_link.split("#")[0]
                        html_path = docgen_base / html_file
                        parsed = parse_docgen_statement(html_path, leandecl)
                        statement = parsed["statement_text"]
                        equation = parsed["equation_text"]
                        statement_html = parsed["statement_html"]
                        equation_html = parsed["equation_html"]
                        fields_html = parsed["fields_html"]
                        fields_text = parsed["fields_text"]

                    # Get short name (last component)
                    short_name = leandecl.split(".")[-1]

                    entry = {
                        "name": leandecl,
                        "short_name": short_name,
                        "kind": decl_info.get("kind", ""),
                        "doc_url": f"{project_dochome}/{doc_link}",
                        "statement": statement,
                        "equation": equation,
                        "statement_html": statement_html,
                        "equation_html": equation_html,
                        "fields_html": fields_html,
                        "fields_text": fields_text,
                    }
                    # GitHub URL from docLink path
                    if project_github and doc_link:
                        module_path = doc_link.split("#")[0].replace(".html", ".lean")
                        entry["github_url"] = (
                            f"{project_github}/blob/main/{module_path}"
                        )
                    lean_entries.append(entry)

                node.userdata["lean_urls"] = lean_urls
                node.userdata["lean_entries"] = lean_entries

                used = node.userdata.get("uses", [])
                node.userdata["can_state"] = all(
                    thm.userdata.get("leanok") for thm in used
                ) and not node.userdata.get("notready", False)
                proof = node.userdata.get("proved_by")
                if proof:
                    used.extend(proof.userdata.get("uses", []))
                    node.userdata["can_prove"] = all(
                        thm.userdata.get("leanok") for thm in used
                    )
                    node.userdata["proved"] = proof.userdata.get("leanok", False)
                else:
                    node.userdata["can_prove"] = False
                    node.userdata["proved"] = False

            for node in nodes:
                node.userdata["fully_proved"] = all(
                    n.userdata.get("proved", False) or item_kind(n) == "definition"
                    for n in graph.ancestors(node).union({node})
                )

        lean_decls_path = Path(document.userdata["working-dir"]).parent / "lean_decls"
        lean_decls_path.write_text("\n".join(document.userdata.get("lean_decls", [])))

    document.addPostParseCallbacks(150, make_lean_data)

    document.addPackageResource([PackageCss(path=STATIC_DIR / "blueprint.css")])

    colors = document.userdata["dep_graph"]["colors"] = {
        "mathlib": ("darkgreen", "Dark green"),
        "stated": ("green", "Green"),
        "can_state": ("blue", "Blue"),
        "not_ready": ("#FFAA33", "Orange"),
        "proved": ("#9CEC8B", "Green"),
        "can_prove": ("#A3D6FF", "Blue"),
        "defined": ("#B0ECA3", "Light green"),
        "fully_proved": ("#1CAC78", "Dark green"),
    }

    def colorizer(node) -> str:
        data = node.userdata

        color = ""
        if data.get("mathlibok"):
            color = colors["mathlib"][0]
        elif data.get("leanok"):
            color = colors["stated"][0]
        elif data.get("can_state"):
            color = colors["can_state"][0]
        elif data.get("notready"):
            color = colors["not_ready"][0]
        return color

    def fillcolorizer(node) -> str:
        data = node.userdata
        stated = data.get("leanok")
        can_state = data.get("can_state")
        can_prove = data.get("can_prove")
        proved = data.get("proved")
        fully_proved = data.get("fully_proved")

        fillcolor = ""
        if proved:
            fillcolor = colors["proved"][0]
        elif can_prove and (can_state or stated):
            fillcolor = colors["can_prove"][0]
        if item_kind(node) == "definition":
            if stated:
                fillcolor = colors["defined"][0]
            elif can_state:
                fillcolor = colors["can_prove"][0]
        elif fully_proved:
            fillcolor = colors["fully_proved"][0]
        return fillcolor

    document.userdata["dep_graph"]["colorizer"] = colorizer
    document.userdata["dep_graph"]["fillcolorizer"] = fillcolorizer

    def make_legend() -> None:
        """
        Extend the dependency graph legend defined by the depgraph plugin
        by adding information specific to Lean blueprints. This is registered
        as a post-parse callback to allow users to redefine colors and their
        descriptions.
        """
        document.userdata["dep_graph"]["legend"].extend(
            [
                (
                    f"{document.userdata['dep_graph']['colors']['can_state'][1]} border",
                    "the <em>statement</em> of this result is ready to be formalized; all prerequisites are done",
                ),
                (
                    f"{document.userdata['dep_graph']['colors']['not_ready'][1]} border",
                    "the <em>statement</em> of this result is not ready to be formalized; the blueprint needs more work",
                ),
                (
                    f"{document.userdata['dep_graph']['colors']['can_state'][1]} background",
                    "the <em>proof</em> of this result is ready to be formalized; all prerequisites are done",
                ),
                (
                    f"{document.userdata['dep_graph']['colors']['proved'][1]} border",
                    "the <em>statement</em> of this result is formalized",
                ),
                (
                    f"{document.userdata['dep_graph']['colors']['proved'][1]} background",
                    "the <em>proof</em> of this result is formalized",
                ),
                (
                    f"{document.userdata['dep_graph']['colors']['fully_proved'][1]} background",
                    "the <em>proof</em> of this result and all its ancestors are formalized",
                ),
                (
                    f"{document.userdata['dep_graph']['colors']['mathlib'][1]} border",
                    "this is in Mathlib",
                ),
            ]
        )

    document.addPostParseCallbacks(150, make_legend)

    document.userdata.setdefault("thm_header_extras_tpl", []).extend([CHECKMARK_TPL])
    document.userdata.setdefault("thm_header_hidden_extras_tpl", []).extend(
        [GITHUB_ISSUE_TPL]
    )
    # Side panel template goes in a new hook for content that appears after the theorem
    document.userdata.setdefault("thm_side_panel_tpl", []).extend([LEAN_SIDE_PANEL_TPL])
    document.userdata["dep_graph"].setdefault("extra_modal_links_tpl", []).extend(
        [LEAN_LINKS_TPL, GITHUB_LINK_TPL]
    )
