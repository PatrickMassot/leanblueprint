"""
Package Lean blueprint

Options:
project: lean project path
dep_graph_target: dependency graph output file (relative to global output
directory)
dep_graph_tpl: template file for dependency graph, relative to the current
directory

coverage_tpl: template file for coverage report, relative to the current
directory
coverage_target: coverage report output file (relative to global output
directory)
coverage_thms: list of theorem environment covered, separated by +
coverage_sectioning: coverage report section grouping

showmore: enable buttons showing or hiding proofs.

"""
import os
import string
import pickle
from pathlib import Path
from typing import List, Optional

from jinja2 import Template
from pygraphviz import AGraph
from mathlibtools.lib import LeanProject

from plasTeX import Command, Environment
from plasTeX.PackageResource import (
        PackageTemplateDir, PackageJs, PackageCss, PackagePreCleanupCB)

from plasTeX.Logging import getLogger
log = getLogger()

PKG_DIR = Path(__file__).parent
STATIC_DIR = Path(__file__).parent.parent/'static'
DEFAULT_TYPES = 'definition+lemma+proposition+theorem+corollary'


def item_kind(node) -> str:
    """Return the kind of declaration corresponding to node"""
    if hasattr(node, 'thmName'):
        return node.thmName
    if node.parentNode:
        return item_kind(node.parentNode)
    return ''

class DepGraph():
    """
    A TeX declarations dependency graph.
    Contrasting with leancrawler dependencies graph,
    each node and edge is human declarated in the TeX source.
    """
    def __init__(self):
        self.nodes = set()
        self.edges = set()
        self.proof_edges = set()

    def to_dot(self, shapes: dict()) -> AGraph:
        """Convert to pygraphviz AGraph"""
        graph = AGraph(directed=True)
        graph.node_attr['penwidth'] = 1.8
        graph.edge_attr.update(arrowhead='vee')
        for node in self.nodes:
            mathlib = node.userdata.get('mathlibok')
            stated = node.userdata.get('leanok')
            can_state = node.userdata.get('can_state')
            can_prove = node.userdata.get('can_prove')
            proof = node.userdata.get('proved_by')
            proved = proof.userdata.get('leanok', False) if proof else False

            color = ''
            fillcolor = ''
            if mathlib:
                color = 'darkgreen'
            elif stated:
                color = 'green'
            elif can_state:
                color = 'blue'
            if proved:
                fillcolor = "#9cec8b"
            elif can_prove and (can_state or stated):
                fillcolor = "#a3d6ff"
            if stated and item_kind(node) == 'definition':
                fillcolor = "#b0eca3"

            if fillcolor:
                graph.add_node(node.id,
                               label=node.id.split(':')[-1],
                               shape=shapes.get(item_kind(node), 'ellipse'),
                               style='filled',
                               color=color,
                               fillcolor=fillcolor)
            else:
                graph.add_node(node.id,
                               label=node.id.split(':')[-1],
                               shape=shapes.get(item_kind(node), 'ellipse'),
                               style='',
                               color=color)
        for s, t in self.edges:
            graph.add_edge(s.id, t.id, style='dashed')
        for s, t in self.proof_edges:
            graph.add_edge(s.id, t.id)
        return graph


class home(Command):
    r"""\home{url}"""
    args = 'url:url'

    def invoke(self, tex):
        Command.invoke(self, tex)
        self.ownerDocument.userdata['project_home'] = self.attributes['url']
        return []

class github(Command):
    r"""\github{url}"""
    args = 'url:url'

    def invoke(self, tex):
        Command.invoke(self, tex)
        self.ownerDocument.userdata['project_github'] = self.attributes['url'].textContent
        return []


class uses(Command):
    r"""\uses{labels list}"""
    args = 'labels:list:nox'

    def digest(self, tokens):
        Command.digest(self, tokens)
        node = self.parentNode
        doc = self.ownerDocument
        def update_used():
            labels_dict = doc.context.labels
            used = [labels_dict[label]
                    for label in self.attributes['labels'] if label in labels_dict]
            node.setUserData('uses', used)

        doc.addPostParseCallbacks(10, update_used)


class proves(Command):
    r"""\proves{label}"""
    args = 'label:str'

    def digest(self, tokens):
        Command.digest(self, tokens)
        node = self.parentNode
        doc = self.ownerDocument
        def update_proved() -> None:
            labels_dict = doc.context.labels
            proved = labels_dict.get(self.attributes['label'])
            if proved:
                node.setUserData('proves', proved)
                proved.userdata['proved_by'] = node
        doc.addPostParseCallbacks(10, update_proved)


class leanok(Command):
    r"""\leanok"""
    def digest(self, tokens):
        Command.digest(self, tokens)
        self.parentNode.userdata['leanok'] = True


class mathlibok(Command):
    r"""\mathlibok"""
    def digest(self, tokens):
        Command.digest(self, tokens)
        self.parentNode.userdata['leanok'] = True
        self.parentNode.userdata['mathlibok'] = True


class lean(Command):
    r"""\lean{decl list} """
    args = 'decls:list:nox'

    def digest(self, tokens):
        Command.digest(self, tokens)
        decls = [dec.strip() for dec in self.attributes['decls']]
        self.parentNode.setUserData('leandecls', decls)


class DeclReport():
    """
    A declaration formalization report
    """

    def __init__(self, id_, kind: str, caption: str, statement: str, leanl: List[str],
                 stated: bool, proved: bool,
                 can_state: bool, can_prove: bool):
        """Constructor for DeclReport"""
        self.id = id_
        self.caption = caption
        self.kind = kind
        self.statement = statement
        self.lean = leanl
        self.stated = stated
        self.proved = proved
        self.can_state = can_state
        self.can_prove = can_prove

    @property
    def done(self):
        """This item is fully done"""
        return self.stated if self.kind == 'definition' else self.proved

    @classmethod
    def from_thm(cls, thm):
        """Create a DeclReport from a thmenv node"""
        caption = thm.caption + ' ' + thm.ref
        stated = thm.userdata.get('leanok', False)
        can_state = thm.userdata.get('can_state', False)
        can_prove = thm.userdata.get('can_prove', False)
        proof = thm.userdata.get('proved_by')
        proved = proof.userdata.get('leanok', False) if proof else False
        return cls(thm.id, thm.thmName,
                   caption, str(thm), thm.userdata.get('lean', []),
                   stated, proved, can_state, can_prove)


class PartialReport():
    """Report on formalization status for part of a blueprint."""
    def __init__(self, title, nb_thms, nb_not_covered, thm_reports):
        self.nb_thms = nb_thms
        self.nb_not_covered = nb_not_covered
        self.coverage = int(100 * (nb_thms - nb_not_covered) / nb_thms if nb_thms else 100)
        self.thm_reports = thm_reports
        self.title = title
        self.define_next = [thm for thm in thm_reports
                            if thm.kind == 'definition' and not thm.done and
                            thm.can_state]
        self.state_next = [thm for thm in thm_reports
                           if thm.kind != 'definition' and not thm.stated and
                           thm.can_state]
        self.prove_next = [thm for thm in thm_reports
                           if thm.kind != 'definition' and thm.stated and
                           not thm.proved and thm.can_prove]
        if self.coverage == 100:
            self.status = 'ok'
        elif self.coverage > 0:
            self.status = 'partial'
        else:
            self.status = 'void'

    @classmethod
    def from_section(cls, section, thm_types):
        """Create a PartialReport from a document section."""
        nb_thms = 0
        nb_not_covered = 0
        thm_reports = []
        theorems = []
        for thm_type in thm_types:
            theorems += section.getElementsByTagName(thm_type)
        for thm in sorted(theorems, key=lambda x: str(x.ref).split('.')):
            nb_thms += 1
            thm_report = DeclReport.from_thm(thm)
            if thm_report.kind == 'definition':
                if not thm_report.stated:
                    nb_not_covered += 1
            elif not thm_report.proved:
                nb_not_covered += 1
            thm_reports.append(thm_report)
        return cls(section.fullTocEntry, nb_thms, nb_not_covered, thm_reports)


class Report():
    """A full report."""

    def __init__(self, partials):
        """Constructor for Report"""
        self.partials = partials
        self.nb_thms = sum([p.nb_thms for p in partials])
        self.nb_not_covered = sum([p.nb_not_covered for p in partials])
        self.coverage = 100 * (self.nb_thms - self.nb_not_covered) / self.nb_thms \
                        if self.nb_thms else 100

def find_proved_thm(proof) -> Optional[Environment]:
    """From a proof node, try to find the statement."""
    node = proof.parentNode
    while node.previousSibling:
        childNodes = node.previousSibling.childNodes
        if childNodes and childNodes[0].nodeName == 'thmenv':
            return childNodes[0]
        node = node.previousSibling
    return None


def ProcessOptions(options, document):
    """This is called when the package is loaded."""

    document.rendererdata.setdefault('html5', dict())

    templatedir = PackageTemplateDir(path=PKG_DIR/'renderer_templates')
    document.addPackageResource(templatedir)

    jobname = document.userdata['jobname']
    outdir = document.config['files']['directory']
    outdir = string.Template(outdir).substitute({'jobname': jobname})

    def update_proofs() -> None:
        for proof in document.getElementsByTagName('proof'):
            proved = proof.userdata.setdefault('proves', find_proved_thm(proof))
            if proved:
                proved.userdata['proved_by'] = proof
    document.addPostParseCallbacks(100, update_proofs)

    def make_lean_urls() -> None:
        """Build url for Lean declarations referred to in the blueprint"""
        proj = LeanProject.from_path(Path(options.get('project', '../..')))
        lean_ver = 'v{:d}.{:d}.{:d}'.format(*proj.lean_version)

        gh = document.userdata.get('project_github', '')
        base_url = {'mathlib': 'https://github.com/leanprover-community/'
                               f'mathlib/blob/{proj.mathlib_rev}/src/',
                    'core': 'https://github.com/leanprover-community/lean/blob/'
                            f'{lean_ver}/library/init/',
                    proj.name: f'{gh}/blob/{proj.rev}/src/'}
        try:
            with (proj.directory/'decls.pickle').open('rb') as data:
                decls = pickle.load(data)
        except FileNotFoundError:
            log.warning('Could not find decls.pickle')
            return

        nodes = []
        for thm_type in document.userdata['thm_types']:
            nodes += document.getElementsByTagName(thm_type)
        for node in nodes:
            leandecls = node.userdata.get('leandecls', [])
            lean_urls = []
            for leandecl in leandecls:
                if leandecl not in decls:
                    print(f'Lean declaration {leandecl} not found')
                    continue
                info = decls[leandecl]
                lean_urls.append(
                    (leandecl,
                     f'{base_url[info.origin]}{info.filepath}#L{info.line}'))

            node.userdata['lean_urls'] = lean_urls
    document.addPostParseCallbacks(100, make_lean_urls)

    ## Dep graph
    title = options.get('title', 'Dependencies')
    document.userdata['blueprint_dep_graph'] = DepGraph()

    def makegraph() -> None:
        nodes = []
        for thm_type in document.userdata['thm_types']:
            nodes += document.getElementsByTagName(thm_type)
        graph = document.userdata.get('blueprint_dep_graph')
        for node in nodes:
            graph.nodes.add(node)
            used = node.userdata.get('uses', [])
            #graph.nodes.update(used)
            for thm in used:
                graph.edges.add((thm, node))
            node.userdata['can_state'] = all(thm.userdata.get('leanok')
                                             for thm in used)
            proof = node.userdata.get('proved_by')
            if proof:
                used = proof.userdata.get('uses', [])
                for thm in used:
                    graph.proof_edges.add((thm, node))
                node.userdata['can_prove'] = all(thm.userdata.get('leanok')
                                                 for thm in used)
            else:
                node.userdata['can_prove'] = False

    document.addPostParseCallbacks(110, makegraph)
    graph_target = options.get('dep_graph_target', 'dep_graph.html')

    default_tpl_path = PKG_DIR.parent/'templates'/'dep_graph.html'
    graph_tpl_path = Path(options.get('dep_graph_tpl', default_tpl_path))
    try:
        graph_tpl = Template(graph_tpl_path.read_text())
    except IOError:
        log.warning('DepGraph template read error, using default template')
        graph_tpl = Template(default_tpl_path.read_text())

    def make_graph_html(document):
        graph = document.userdata['blueprint_dep_graph']
        dot = graph.to_dot({'definition': 'box'}).to_string()
        graph_tpl.stream(graph=graph,
                         dot=dot,
                         context=document.context,
                         title=title,
                         config=document.config).dump(graph_target)
        return [graph_target]

    cb = PackagePreCleanupCB(data=make_graph_html)
    css = PackageCss(path=STATIC_DIR/'dep_graph.css', copy_only=True)
    css2 = PackageCss(path=STATIC_DIR/'style_coverage.css', copy_only=True)
    js = [PackageJs(path=STATIC_DIR/name, copy_only=True)
          for name in ['d3.min.js', 'hpcc.min.js', 'd3-graphviz.js',
                       'expatlib.wasm', 'graphvizlib.wasm', 'coverage.js']]

    document.addPackageResource([cb, css, css2] + js)

    ## Coverage
    default_tpl_path = PKG_DIR.parent/'templates'/'coverage.html'
    cov_tpl_path = options.get('coverage_tpl', default_tpl_path)
    try:
        cov_tpl = Template(cov_tpl_path.read_text())
    except IOError:
        log.warning('Coverage template read error, using default template')
        cov_tpl = Template(default_tpl_path.read_text())


    coverage_target = options.get('coverage_target', 'coverage.html')
    outfile = os.path.join(outdir, coverage_target)

    thm_types = [thm.strip()
                 for thm in options.get('coverage_thms', DEFAULT_TYPES).split('+')]
    document.userdata['thm_types'] = thm_types
    section = options.get('coverage_sectioning', 'chapter')

    def makeCoverageReport(document):
        sections = document.getElementsByTagName(section)
        report = Report([PartialReport.from_section(sec, thm_types) for sec in sections])
        cov_tpl.stream(report=report,
                       config=document.config,
                       terms=document.context.terms).dump(outfile)
        return [outfile]
    document.addPackageResource(PackagePreCleanupCB(data=makeCoverageReport))


    if 'showmore' in options:
        navs = [{'icon': 'eye-minus', 'id': 'showmore-minus', 'class': 'showmore'},
                {'icon': 'eye-plus', 'id': 'showmore-plus', 'class': 'showmore'}]
        if 'extra-nav' in document.rendererdata['html5']:
            document.rendererdata['html5']['extra-nav'].extend(navs)
        else:
            document.rendererdata['html5']['extra-nav'] = navs

        css = PackageCss(path=STATIC_DIR/'showmore.css')
        js = PackageJs(path=STATIC_DIR/'showmore.js')
        js2 = PackageJs(path=STATIC_DIR/'jquery.cookie.js')
        document.addPackageResource([css, js, js2])
