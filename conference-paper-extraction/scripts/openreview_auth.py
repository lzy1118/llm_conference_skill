from __future__ import annotations

import os
from dataclasses import dataclass


OPENREVIEW_BASEURL = "https://api2.openreview.net"
OPENREVIEW_USERNAME_ENV = "OPENREVIEW_USERNAME"
OPENREVIEW_PASSWORD_ENV = "OPENREVIEW_PASSWORD"


@dataclass(frozen=True)
class OpenReviewCredentials:
    username: str
    password: str
    baseurl: str = OPENREVIEW_BASEURL


def get_openreview_credentials() -> OpenReviewCredentials | None:
    username = os.environ.get(OPENREVIEW_USERNAME_ENV, "").strip()
    password = os.environ.get(OPENREVIEW_PASSWORD_ENV, "").strip()
    if not username or not password:
        return None
    return OpenReviewCredentials(username=username, password=password)


def require_openreview_credentials() -> OpenReviewCredentials:
    credentials = get_openreview_credentials()
    if credentials is None:
        raise RuntimeError(
            "OpenReview credentials are not set. Export OPENREVIEW_USERNAME and OPENREVIEW_PASSWORD in the environment before running authenticated OpenReview workflows."
        )
    return credentials
