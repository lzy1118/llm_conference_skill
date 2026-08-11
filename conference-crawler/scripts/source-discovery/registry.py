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
    },
    "icml": {
        "aliases": [
            "icml",
            "international conference on machine learning",
        ],
        "discovery": "pmlr",
        "backend": "pmlr",
    },
}
