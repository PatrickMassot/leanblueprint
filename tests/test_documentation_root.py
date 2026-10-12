"""Run with Python from an environment containing the patched leanblueprint.

Validates actual plasTeX HTML links/warnings. Does not check Lean or TeX images.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
source = '\\documentclass{article}\n\\usepackage{amsthm}\n\\usepackage[dep_graph]{blueprint}\n\\newtheorem{theorem}{Theorem}\n\\begin{document}\n\n\\begin{theorem}\n\\label{thm:add_comm}\n\\lean{Example.add_comm}\nFor natural numbers $a,b$, $a+b=b+a$.\n\\end{theorem}\n\n\\end{document}\n'
class DocumentationRootRenderTest(unittest.TestCase):
    def test_documentation_roots(self):
        with tempfile.TemporaryDirectory(prefix='leanblueprint-render-') as temporary:
            for name, text, warnings, link in [
                ('missing',source,1,'https://leanprover-community.github.io/mathlib4_docs/find/#doc/Example.add_comm'),
                ('configured',source.replace(r'\begin{document}',r'\dochome{https://example.org/project-docs}'+'\n'+r'\begin{document}'),0,'https://example.org/project-docs/find/#doc/Example.add_comm'),
                ('empty',source.replace(r'\lean{Example.add_comm}',''),0,None),
            ]:
                work=Path(temporary)/name;work.mkdir();(work/'web.tex').write_text(text)
                run=subprocess.run([str(Path(sys.executable).with_name('plastex')),'--plugins','leanblueprint','plastexdepgraph','plastexshowmore','--renderer','HTML5','--disable-images','--dir','html','web.tex'],cwd=work,capture_output=True,text=True)
                log=run.stdout+run.stderr
                assert run.returncode==0,log
                html=(work/'html/index.html').read_text()
                assert log.count('Lean declarations found')==warnings,log
                if link:assert 'href="'+link+'"' in html
                else:assert '/find/#doc/' not in html

if __name__ == "__main__":
    unittest.main()
