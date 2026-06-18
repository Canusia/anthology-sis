"""Configuration loaded from environment variables (and optionally a .env file).

Call load_config() once at startup. Nothing here hardcodes secrets — the
Application Key lives in .env (gitignored) or the real environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urljoin


def _load_dotenv() -> None:
    """Populate os.environ from a .env file if python-dotenv is installed.

    Kept optional so the package works with plain environment variables too.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


@dataclass(frozen=True)
class Config:
    root_uri: str
    auth_mode: str          # "apikey" or "basic"
    api_key: str
    api_key_scheme: str
    username: str
    password: str
    sections_path: str
    terms_path: str
    timeout: int

    @property
    def authorization_header(self) -> str | None:
        """The Authorization header value for apikey mode, or None for basic."""
        if self.auth_mode != "apikey":
            return None
        key = self.api_key
        if not key:
            raise RuntimeError(
                "CNX_AUTH_MODE=apikey but CNX_API_KEY is empty. "
                "Set it in your .env file."
            )
        return key if " " in key else f"{self.api_key_scheme} {key}"

    def url(self, path: str) -> str:
        return urljoin(self.root_uri, path)


def load_config() -> Config:
    _load_dotenv()

    root = os.environ.get(
        "CNX_ROOT_URI", "https://sisclientweb-test-100910.campusnexus.cloud/"
    )
    if not root.endswith("/"):
        root += "/"

    return Config(
        root_uri=root,
        auth_mode=os.environ.get("CNX_AUTH_MODE", "apikey").lower(),
        api_key=os.environ.get("CNX_API_KEY", ""),
        api_key_scheme=os.environ.get("CNX_API_KEY_SCHEME", "ApplicationKey"),
        username=os.environ.get("CNX_USERNAME", ""),
        password=os.environ.get("CNX_PASSWORD", ""),
        sections_path=os.environ.get("CNX_SECTIONS_PATH", "ds/odata/ClassSectionTerms"),
        terms_path=os.environ.get("CNX_TERMS_PATH", "ds/odata/Terms"),
        timeout=int(os.environ.get("CNX_TIMEOUT", "30")),
    )
