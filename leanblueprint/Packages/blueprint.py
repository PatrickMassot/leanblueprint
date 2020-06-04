"""
Package blueprint
Goodies for theorem environment and sample specific plasTeX package.

Options:
dep_graph: produce dependency graph

d3_url: url for the D3js library
jquery_url: url for the jquery library
dep_graph_target: dependency graph output file (relative to global output
directory)
dep_graph_tpl: template file for dependency graph, relative to the current
directory

coverage: produce coverage report

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
from pathlib import Path
from typing import List, Optional
from pdb import set_trace as st

from jinja2 import Template
from pygraphviz import AGraph

from plasTeX import Command, Environment, TeXDocument
from plasTeX.PackageResource import (
        PackageTemplateDir, PackageJs, PackageCss, PackagePreCleanupCB)

from plasTeX.Logging import getLogger
log = getLogger()

PKG_DIR = Path(__file__).parent
STATIC_DIR = Path(__file__).parent.parent/'static'

def item_kind(node) -> str:
    if hasattr(node, 'thmName'):
        return node.thmName
    elif node.parentNode:
        return item_kind(node.parentNode)
    else:
        return ''

class DepGraph():
    def __init__(self):
        self.nodes = set()
        self.edges = set()
        self.proof_edges = set()

    def to_dot(self, shapes: dict()) -> AGraph:
        graph = AGraph(directed=True, bgcolor='#e8e8e8')
        graph.node_attr['penwidth'] = 1.5
        graph.edge_attr.update(arrowhead='vee')
        for node in self.nodes:
            stated = node.userdata.get('leanok')
            can_state = node.userdata.get('can_state')
            can_prove = node.userdata.get('can_prove')
            proof = node.userdata.get('proved_by')
            proved = proof.userdata.get('leanok', False) if proof else False

            color = ''
            fillcolor = ''
            if stated:
                color = 'green'
            elif can_state:
                color = 'blue'
            if proved:
                fillcolor = "#92f67c"
            elif can_prove:
                fillcolor = "#9acaf1"

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

class uses(Command):
    r"""\uses{labels list}"""
    args = 'labels:list:nox'

    def digest(self, tokens):
        Command.digest(self, tokens)
        node = self.parentNode
        doc = self.ownerDocument
        def update_used():
            labels_dict = doc.context.labels
            used = [labels_dict[label] for label in self.attributes['labels'] if label in labels_dict]
            node.setUserData('uses', used)

        doc.postParseCallbacks.append(update_used)

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
        doc.postParseCallbacks.append(update_proved)

class leanok(Command):
    r"""\leanok"""
    def digest(self, tokens):
        Command.digest(self, tokens)
        self.parentNode.userdata['leanok'] = True


class collectproofs(Command):
    """Collects all proofs and try to link to their statement"""
    # FIXME: We define a command here because we are missing a hook
    # to call a function after everything is parsed but before rendering
    # This command should be at the end of the document
    # Could we hook that into AtDocumentEnd?

    def digest(self, tokens):
        Command.digest(self, tokens)
        doc = self.ownerDocument
        def update_proofs() -> None:
            for proof in doc.getElementsByTagName('proof'):
                proved = proof.userdata.setdefault('proves', find_proved_thm(proof))
                if proved:
                    proved.userdata['proved_by'] = proof
        doc.postParseCallbacks.append(update_proofs)

class makegraph(Command):
    """Make the dep graph"""
    # FIXME: We define a command here because we are missing a hook
    # to call a function after everything is parsed but before rendering
    # This command should be at the end of the document
    # Could we hook that into AtDocumentEnd?

    def digest(self, tokens):
        Command.digest(self, tokens)
        doc = self.ownerDocument
        def makeit() -> None:
            nodes = []
            for thm_type in doc.userdata['thm_types']:
                nodes += doc.getElementsByTagName(thm_type)
            graph = doc.userdata.get('blueprint_dep_graph')
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

        doc.postParseCallbacks.append(makeit)

class lean(Command):
    r"""\lean{decl list} """
    args = 'decls:list:nox'

    def digest(self, tokens):
        Command.digest(self, tokens)
        decl, url = self.attributes['decls']

        decls = self.parentNode.userdata.get('leandecls', [])
        decls.append((decl, url))
        self.parentNode.setUserData('leandecls', decls)


class ThmReport():
    """"""

    def __init__(self, id_, kind: str, caption: str, statement: str, lean: List[str],
            stated: bool, proved: bool,
            can_state: bool, can_prove: bool):
        """Constructor for ThmReport"""
        self.id = id_
        self.caption = caption
        self.kind = kind
        self.statement = statement
        self.lean = lean
        self.stated = stated
        self.proved = proved
        self.can_state = can_state
        self.can_prove = can_prove

    @classmethod
    def from_thm(cls, thm):
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
    def __init__(self, title, nb_thms, nb_not_covered, thm_reports):
        self.nb_thms = nb_thms
        self.nb_not_covered = nb_not_covered
        self.coverage = int(100 * (nb_thms - nb_not_covered) / nb_thms if nb_thms else 100)
        self.thm_reports = thm_reports
        self.title = title
        if self.coverage == 100:
            self.status = 'ok'
        elif self.coverage > 0:
            self.status = 'partial'
        else:
            self.status = 'void'

    @classmethod
    def from_section(cls, section, thm_types):
        nb_thms = 0
        nb_not_covered = 0
        thm_reports = []
        theorems = []
        for thm_type in thm_types:
            theorems += section.getElementsByTagName(thm_type)
        for thm in sorted(theorems, key=lambda x: str(x.ref).split('.')):
            nb_thms += 1
            thm_report = ThmReport.from_thm(thm)
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
        self.coverage = 100 * (self.nb_thms - self.nb_not_covered) / self.nb_thms if self.nb_thms else 100

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

    package_option = document.context.packages['blueprint'] = {}
    templatedir = PackageTemplateDir(
            renderers=['html5'],
            path=PKG_DIR/'renderer_templates')

    document.addPackageResource(templatedir)

    jobname = document.userdata['jobname']
    outdir = document.config['files']['directory']
    outdir = string.Template(outdir).substitute({'jobname': jobname})

    package_option['links'] = 'usage_links' in options

    ## Dep graph
    d3_url = options.get('d3_url', 'https://d3js.org/d3.v5.min.js')
    jquery_url = options.get('jquery_url', 'http://code.jquery.com/jquery.min.js')
    title = options.get('title', 'Dependencies')
    document.userdata['blueprint_dep_graph'] = DepGraph()
    graph_target = options.get( 'dep_graph_target', 'dep_graph.html')

    default_tpl_path = PKG_DIR.parent/'templates'/'dep_graph.j2'
    graph_tpl_path = Path(options.get('dep_graph_tpl', default_tpl_path))
    try:
        graph_tpl = Template(graph_tpl_path.read_text())
    except IOError:
        log.warning('DepGraph template read error, using default template')
        graph_tpl = Template(default_tpl_path.read_text())

    def makeDepGraph(document):
        graph = document.userdata['blueprint_dep_graph']
        dot = graph.to_dot({'definition': 'box'}).to_string()
        graph_tpl.stream(
                graph=graph,
                dot=dot,
                context=document.context,
                d3_url=d3_url,
                jquery_url=jquery_url,
                title=title,
                config=document.config).dump(graph_target)
        return [graph_target]

    cb = PackagePreCleanupCB(
            renderers=['html5'],
            data=makeDepGraph)
    # FIXME: All those resources are included in all pages. Need a flag in
    # PackageResource to copy only without adding to the rendererdata
    css = PackageCss(
            renderers=['html5'],
            path=STATIC_DIR/'dep_graph.css')
    d3js = PackageJs(
            renderers=['html5'],
            path=STATIC_DIR/'d3.min.js')
    hpccjs = PackageJs(
            renderers=['html5'],
            path=STATIC_DIR/'hpcc.min.js')
    vizjs = PackageJs(
            renderers=['html5'],
            path=STATIC_DIR/'d3-graphviz.js')
    document.addPackageResource([cb, css, d3js, hpccjs, vizjs])

    ## Coverage
    default_tpl_path = PKG_DIR.parent/'templates'/'coverage.j2'
    cov_tpl_path = options.get( 'coverage_tpl', default_tpl_path)
    try:
        cov_tpl = Template(cov_tpl_path.read_text())
    except IOError:
        log.warning('Coverage template read error, using default template')
        cov_tpl = Template(default_tpl_path.read_text())


    coverage_target = options.get( 'coverage_target', 'coverage.html')
    outfile = os.path.join(outdir, coverage_target)

    thm_types = [thm.strip()
            for thm in options.get('coverage_thms',
                'definition+lemma+proposition+theorem+corollary').split('+')]
    document.userdata['thm_types'] = thm_types
    section = options.get('coverage_sectioning', 'chapter')

    def makeCoverageReport(document):
        sections = document.getElementsByTagName(section)
        report = Report([PartialReport.from_section(sec, thm_types) for sec in sections])
        cov_tpl.stream(
                report=report,
                config=document.config,
                terms=document.context.terms).dump(outfile)
        return [outfile]

    cb = PackagePreCleanupCB(
            renderers=['html5'],
            data=makeCoverageReport)
    css = PackageCss(
            renderers=['html5'],
            path=STATIC_DIR/'style_coverage.css')
    js = PackageJs(
            renderers=['html5'],
            path=STATIC_DIR/'coverage.js')
    document.addPackageResource([cb, css, js])

    if 'showmore' in options:
        navs = [{'icon': 'eye-minus', 'id': 'showmore-minus', 'class': 'showmore'},
                {'icon': 'eye-plus', 'id': 'showmore-plus', 'class': 'showmore'}]
        if 'extra-nav' in document.rendererdata['html5']:
            document.rendererdata['html5']['extra-nav'].extend(navs)
        else:
            document.rendererdata['html5']['extra-nav'] = navs

        css = PackageCss(
                renderers=['html5'],
                path=STATIC_DIR/'showmore.css')
        js = PackageJs(
                renderers=['html5'],
                path=STATIC_DIR/'showmore.js')
        js2 = PackageJs(
                renderers=['html5'],
                path=STATIC_DIR/'jquery.cookie.js')
        document.addPackageResource([css, js, js2])
