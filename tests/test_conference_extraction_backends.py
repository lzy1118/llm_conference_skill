import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name: str, relative_path: str):
    module_path = ROOT / relative_path
    import sys

    scripts_dir = str(module_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class ConferenceExtractionBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.iacr_backend = load_module(
            "iacr_top3_backend_test",
            "conference-paper-extraction/scripts/iacr_top3_backend.py",
        )
        cls.security_backend = load_module(
            "security_real_backend_test",
            "conference-paper-extraction/scripts/security_real_backend.py",
        )

    def test_iacr_backend_expands_rows_and_records_mismatch_issue(self):
        config = self.iacr_backend.CONFERENCE_CONFIGS["crypto_2025"]
        papers = [
            {
                "paperId": "p1",
                "title": "Aligned Paper",
                "authors": ["Alice", "Bob"],
                "affiliations": ["MIT", "ETH Zurich"],
            },
            {
                "paperId": "p2",
                "title": "Mismatch Paper",
                "authors": ["Carol", "Dave"],
                "affiliations": ["Stanford University"],
            },
        ]

        rows, issues = self.iacr_backend.expand_author_rows(config, papers, overrides={})
        us_rows = self.iacr_backend.filter_us_rows(rows)

        self.assertEqual(len(rows), 2)
        self.assertEqual(len(us_rows), 1)
        self.assertEqual(us_rows[0]["name"], "Alice")
        self.assertEqual(rows[0]["country"], "United States")
        self.assertEqual(rows[1]["country"], "Switzerland")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["issue"], "author_affiliation_count_mismatch")

    def test_security_backend_uses_cached_affiliations_without_network(self):
        config = self.security_backend.CONFERENCES["usenix_security_2022"]
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            cache_dir = tmp / "resolution" / "affiliation_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / "conf_uss_2022_paper1_affiliations.json"
            cache_file.write_text(
                json.dumps(
                    [
                        {"name": "Alice Example", "affiliations": ["MIT"]},
                        {"name": "Bob Example", "affiliations": ["University of Toronto"]},
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            papers = [
                {
                    "paperId": "conf/uss/2022/paper1",
                    "title": "Paper One",
                    "authors": ["Alice Example", "Bob Example"],
                    "url": "https://example.com/paper1",
                }
            ]

            rows, issues = self.security_backend.expand_author_rows(
                config,
                papers,
                overrides={},
                cache_dir=cache_dir,
                fetch_from_network=False,
            )

            self.assertEqual(len(issues), 0)
            self.assertEqual(len(rows), 2)
            self.assertTrue(any(row["inst"] == "MIT" and row["country"] == "United States" for row in rows))
            self.assertTrue(any(row["inst"] == "University of Toronto" and row["country"] == "Canada" for row in rows))

    def test_security_backend_report_exposes_missing_affiliation_paper_gap(self):
        config = self.security_backend.CONFERENCES["usenix_security_2022"]
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            raw_path = tmp / "raw" / "usenix_security_2022_papers.json"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(
                json.dumps(
                    [
                        {
                            "paperId": "p1",
                            "title": "Paper One",
                            "authors": ["Alice Example", "Bob Example"],
                            "url": "https://example.com/paper1",
                        },
                        {
                            "paperId": "p2",
                            "title": "Paper Two",
                            "authors": ["Carol Example"],
                            "url": "https://example.com/paper2",
                        },
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            cache_dir = tmp / "resolution" / "affiliation_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / "p1_affiliations.json").write_text(
                json.dumps([
                    {"name": "Alice Example", "affiliations": ["MIT"]},
                    {"name": "Bob Example", "affiliations": ["University of Toronto"]},
                ], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            report, _paper_rows, rows, issues = self.security_backend.run_single_conference(config, raw_path, tmp)

            self.assertEqual(report["papers_count"], 2)
            self.assertEqual(report["papers_with_author_rows"], 1)
            self.assertEqual(report["papers_without_affiliation_data"], 1)
            self.assertEqual(len(rows), 2)
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["paper_id"], "p2")

    def test_security_backend_refetches_when_empty_cache_exists(self):
        config = self.security_backend.CONFERENCES["usenix_security_2022"]
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            cache_dir = tmp / "resolution" / "affiliation_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / "p1_affiliations.json"
            cache_file.write_text("[]", encoding="utf-8")

            original_fetch = self.security_backend.fetch_usenix_affiliations
            self.security_backend.fetch_usenix_affiliations = lambda _url: [
                {"name": "Alice Example", "affiliations": ["MIT"]}
            ]
            try:
                rows, issues = self.security_backend.expand_author_rows(
                    config,
                    [{
                        "paperId": "p1",
                        "title": "Paper One",
                        "authors": ["Alice Example"],
                        "url": "https://example.com/paper1",
                    }],
                    overrides={},
                    cache_dir=cache_dir,
                    fetch_from_network=True,
                )
            finally:
                self.security_backend.fetch_usenix_affiliations = original_fetch

            self.assertEqual(len(rows), 1)
            self.assertEqual(len(issues), 0)
            self.assertEqual(rows[0]["inst"], "MIT")

    def test_country_classification_includes_china(self):
        result = self.iacr_backend.classify_affiliation("Tsinghua University", overrides={})
        self.assertEqual(result.country, "China")

    def test_country_classification_covers_added_high_value_unknowns(self):
        samples = [
            ("University of Chicago", "United States"),
            ("UC Riverside", "United States"),
            ("Adobe Research", "United States"),
            ("William &amp; Mary", "United States"),
            ("Xi&#039;an Jiaotong University", "China"),
            ("Shandong University", "China"),
            ("Southern University of Science and Technology", "China"),
            ("imec-DistriNet, KU Leuven", "Belgium"),
            ("University of Trento", "Italy"),
            ("Sapienza University of Rome", "Italy"),
            ("Tampere University", "Finland"),
            ("AIST", "Japan"),
            ("Aarhus University", "Denmark"),
            ("Indian Institute of Technology Kharagpur", "India"),
            ("NIT Tiruchirappalli", "India"),
            ("Radboud University", "Netherlands"),
            ("Technische Universität Braunschweig", "Germany"),
            ("Paderborn University", "Germany"),
            ("Technische Universität Berlin", "Germany"),
            ("armasuisse", "Switzerland"),
            ("Tel-Aviv University", "Israel"),
            ("Bar-Ilan University", "Israel"),
            ("Rochester Institute of Technology", "United States"),
            ("Texas Advanced Computing Center", "United States"),
            ("Trustwave", "United States"),
            ("Tower Research", "United States"),
            ("Tufts University", "United States"),
            ("NXP Semiconductors", "United States"),
            ("Washington University in St. Louis", "United States"),
            ("Brigham Young University", "United States"),
            ("University of Central Florida", "United States"),
            ("Florida International University", "United States"),
            ("University at Buffalo", "United States"),
            ("Virginia Commonwealth University", "United States"),
            ("Georgetown University", "United States"),
            ("University of Louisiana at Lafayette", "United States"),
            ("National University of Defense Technology", "China"),
            ("Sun Yat-sen University", "China"),
            ("Beijing Institute of Technology", "China"),
            ("Zhongguancun Laboratory", "China"),
            ("University of Calgary", "Canada"),
            ("University of Guelph", "Canada"),
            ("TU Wien", "Austria"),
            ("University of Innsbruck", "Austria"),
            ("TU Braunschweig", "Germany"),
            ("DeepMind", "United Kingdom"),
            ("Reichman University", "Israel"),
            ("Mozilla", "Finland"),
            ("National Institute of Information and Communications Technology", "Japan"),
            ("University of Haifa", "Israel"),
            ("University of Vienna", "Austria"),
            ("University of Wyoming", "United States"),
            ("Anhui University", "China"),
            ("Anhui University of Science and Technology", "China"),
            ("Australian National University", "Australia"),
            ("CEA, LIST, Université Paris Saclay", "France"),
            ("CSIRO's Data61", "Australia"),
            ("Concordia University", "Canada"),
            ("Xuanwu Lab, Tencent", "China"),
            ("Fordham University", "United States"),
            ("Georgia State University", "United States"),
            ("Hangzhou Dianzi University", "China"),
            ("Hunan University", "China"),
            ("JD Explore Academy", "China"),
            ("Chinese Aeronautical Establishment", "China"),
            ("Datenanfragen.de e.V.", "Germany"),
            ("IMDEA Software Institute", "Spain"),
            ("IMDEA Networks Institute", "Spain"),
            ("Indian Institute of Technology, Delhi", "India"),
            ("Southeast University", "China"),
            ("Chongqing University", "China"),
            ("Beijing Jiaotong University", "China"),
            ("Institute of Information Engineering, CAS", "China"),
            ("Key Laboratory of Cyberspace Security Defense, Institute of Information Engineering, CAS", "China"),
            ("Indiana University", "United States"),
            ("Saarland University", "Germany"),
            ("Keio University", "Japan"),
            ("RWTH Aachen University", "Germany"),
            ("Technical University of Munich", "Germany"),
            ("University of Denver", "United States"),
            ("University of Macau", "Hong Kong"),
            ("City University of Macau", "Hong Kong"),
            ("Ewha Womans University", "South Korea"),
            ("Shanghai University", "China"),
            ("University of Technology Sydney", "Australia"),
            ("Vanderbilt University", "United States"),
            ("Virginia Polytechnic Institute and State University", "United States"),
            ("Academia Sinica", "Taiwan"),
            ("Beijing University of Technology", "China"),
            ("Institute of Information Engineering, Chinese Academy of Science", "China"),
            ("ETH Zuerich", "Switzerland"),
            ("Hasso Plattner Institute, University of Potsdam", "Germany"),
            ("Kyung Hee University", "South Korea"),
            ("Leibniz Universität Hannover", "Germany"),
            ("Link Campus University of Rome", "Italy"),
            ("Information Security Center, Hon Hai Research Institute", "Taiwan"),
            ("Henan Key Laboratory of Information Security", "China"),
            ("King Abdullah University of Science and Technology, Thuwal, Saudi Arabia", "Saudi Arabia"),
            ("Simon Fraser University", "Canada"),
            ("Texas Tech University", "United States"),
            ("University of Georgia", "United States"),
            ("UCLouvain", "Belgium"),
            ("NOVA LINCS &amp; Universidade NOVA de Lisboa", "Portugal"),
            ("Pengcheng Laboratory", "China"),
            ("University of Louisville", "United States"),
            ("University of North Texas", "United States"),
            ("University of Osnabrück", "Germany"),
            ("University of South Florida", "United States"),
            ("University of Victoria", "Canada"),
            ("University of Vriginia", "United States"),
            ("University of Warwick", "United Kingdom"),
            ("Zhongguancun Lab", "China"),
            ("Information Engineering University", "China"),
            ("Institute for Network Sciences and Cyberspace (INSC", "China"),
            ("Academy of Military Sciences", "China"),
            ("ByteDance Inc.", "China"),
            ("HANG ZHOU CITY BRAIN CO., LTD", "China"),
            ("Feiyu Tech", "China"),
            ("Wichita State University", "United States"),
            ("Western Sydney University", "Australia"),
            ("Shanghai DeCareer Consulting Co., Ltd", "China"),
            ("NEC Laboratories Europe", "Japan"),
            ("The Affiliated Institute of ETRI, ROK", "South Korea"),
            ("Defence Science and Technology Group", "Australia"),
        ]
        for affiliation, country in samples:
            result = self.security_backend.classify_affiliation(affiliation, overrides={})
            self.assertEqual(result.country, country, affiliation)

    def test_security_backend_multi_country_affiliation_returns_multiple(self):
        result = self.security_backend.classify_affiliation(
            "Delft University of Technology and ICANN",
            overrides={},
        )
        self.assertEqual(result.country, "Multiple")

    def test_security_backend_normalizes_html_entity_names(self):
        result = self.security_backend.classify_affiliation("King&#039;s College London", overrides={})
        self.assertEqual(result.country, "United Kingdom")

    def test_security_backend_split_affiliation_parts_keeps_single_name_intact(self):
        parts = self.security_backend.split_affiliation_parts("King&#039;s College London")
        self.assertEqual(parts, ["King's College London"])

    def test_iacr_backend_single_conference_writes_expected_outputs(self):
        config = self.iacr_backend.CONFERENCE_CONFIGS["crypto_2025"]
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            raw_path = tmp / "raw" / "crypto_2025_papers.json"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(
                json.dumps(
                    {
                        "acceptedPapers": [
                            {
                                "paperId": "p1",
                                "title": "Aligned Paper",
                                "authors": ["Alice"],
                                "affiliations": ["MIT"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            report, paper_rows, rows, issues = self.iacr_backend.run_single_conference(config, raw_path, tmp)

            self.assertEqual(report["papers_count"], 1)
            self.assertEqual(len(paper_rows), 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(len(issues), 0)
            self.assertIn("classified_author_rows", report)
            self.assertIn("resolved_country_rows", report)
            self.assertIn("unresolved_country_rows", report)
            self.assertTrue((tmp / "interim" / "crypto_2025_institution_classification_candidates.csv").exists())
            self.assertTrue((tmp / "output" / "crypto_2025_author_affiliations.csv").exists())
            self.assertTrue((tmp / "output" / "crypto_2025_us_institutions.csv").exists())
            self.assertTrue((tmp / "interim" / "crypto_2025_author_affiliations_expanded.csv").exists())

    def test_iacr_backend_resolution_stage_writes_internal_resolution_outputs(self):
        config = self.iacr_backend.CONFERENCE_CONFIGS["crypto_2025"]
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            raw_path = tmp / "raw" / "crypto_2025_papers.json"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(
                json.dumps(
                    {
                        "acceptedPapers": [
                            {
                                "paperId": "p1",
                                "title": "Mismatch Paper",
                                "authors": ["Alice", "Bob"],
                                "affiliations": ["MIT"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            report, _paper_rows, _rows, issues = self.iacr_backend.run_single_conference(
                config,
                raw_path,
                tmp,
                resolve_mismatches=True,
                query_dblp_for_resolution=False,
            )

            self.assertEqual(len(issues), 1)
            self.assertEqual(report["resolution_tasks"], 1)
            self.assertTrue((tmp / "resolution" / "crypto_2025" / "resolution_report.json").exists())
            self.assertTrue((tmp / "resolution" / "crypto_2025" / "source_candidates.csv").exists())
