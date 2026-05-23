import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_security_backend():
    module_name = "security_real_backend_fixture_test"
    module_path = ROOT / "conference-paper-extraction/scripts/security_real_backend.py"
    scripts_dir = str(module_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


SECURITY_BACKEND = load_security_backend()


class SecurityParserFixtureTests(unittest.TestCase):
    def test_parse_usenix_affiliations_html(self):
        html = """
        <html><head>
        <meta name="citation_author" content="Alice Example">
        <meta name="citation_author_institution" content="MIT">
        <meta name="citation_author" content="Bob Example">
        <meta name="citation_author_institution" content="University of Toronto">
        </head></html>
        """

        rows = SECURITY_BACKEND.parse_usenix_affiliations_html(html)
        self.assertEqual(rows, [
            {"name": "Alice Example", "affiliations": ["MIT"]},
            {"name": "Bob Example", "affiliations": ["University of Toronto"]},
        ])

    def test_parse_usenix_affiliations_html_falls_back_to_people_block(self):
        html = """
        <html><body>
        <div class="field field-name-field-paper-people-text field-type-text-long field-label-hidden">
          <div class="field-items field-items"><div class="field-item odd">
            <p>Henrique Teles Maia and Chang Xiao, <em>Columbia University;</em>
            Dingzeyu Li, <em>Adobe Research;</em>
            Eitan Grinspun, <em>Columbia University &amp; University of Toronto;</em>
            Changxi Zheng, <em>Columbia University</em></p>
          </div></div>
        </div>
        </body></html>
        """

        rows = SECURITY_BACKEND.parse_usenix_affiliations_html(html)
        self.assertEqual(rows, [
            {"name": "Henrique Teles Maia", "affiliations": ["Columbia University"]},
            {"name": "Chang Xiao", "affiliations": ["Columbia University"]},
            {"name": "Dingzeyu Li", "affiliations": ["Adobe Research"]},
            {"name": "Eitan Grinspun", "affiliations": ["Columbia University & University of Toronto"]},
            {"name": "Changxi Zheng", "affiliations": ["Columbia University"]},
        ])

    def test_parse_ndss_affiliations_html(self):
        html = """
        <html><body>
        <h1>Interesting NDSS Paper</h1>
        <div>
          Alice Example (Stanford University), Bob Example (ETH Zurich)
        </div>
        </body></html>
        """

        rows = SECURITY_BACKEND.parse_ndss_affiliations_html(html)
        self.assertEqual(rows, [
            {"name": "Alice Example", "affiliations": ["Stanford University"]},
            {"name": "Bob Example", "affiliations": ["ETH Zurich"]},
        ])

    def test_parse_ieee_affiliations_html(self):
        html = """
        <html><body><script>
        xplGlobal.document.metadata = {
          "authors": [
            {"name": "Alice Example", "affiliation": ["MIT"]},
            {"name": "Bob Example", "affiliation": ["University of Toronto"]}
          ]
        };
        </script></body></html>
        """

        rows = SECURITY_BACKEND.parse_ieee_affiliations_html(html)
        self.assertEqual(rows, [
            {"name": "Alice Example", "affiliations": ["MIT"]},
            {"name": "Bob Example", "affiliations": ["University of Toronto"]},
        ])
