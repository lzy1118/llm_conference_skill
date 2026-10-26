"""Conference-level source discovery registry.

The registry intentionally stores only stable resolver configuration. Yearly
proceedings URLs are discovered at runtime.
"""

CONFERENCE_REGISTRY = {
    "crypto": {
        "aliases": [
            "crypto",
            "international cryptology conference",
        ],
        "discovery": "dblp",
        "dblp_key": "crypto",
        "backend": "dblp",
        "cfp_url_template": "https://crypto.iacr.org/{year}/callforpapers.php",
    },
    "www": {
        "aliases": [
            "www",
            "the web conference",
            "acm web conference",
        ],
        "discovery": "dblp",
        "dblp_key": "www",
        "backend": "acm",
    },
    "neurips": {
        "aliases": [
            "neurips",
            "nips",
        ],
        "discovery": "neurips",
        "backend": "neurips",
        "cfp_url_template": "https://neurips.cc/Conferences/{year}/CallForPapers",
    },
    "icml": {
        "aliases": [
            "icml",
            "international conference on machine learning",
        ],
        "discovery": "pmlr",
        "backend": "pmlr",
        "cfp_url_template": "https://icml.cc/Conferences/{year}/CallForPapers",
    },
}
