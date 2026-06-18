"""Thin OData client for the Anthology Student (CampusNexus) Query API.

Handles auth (Application Key or Basic), retries, and @odata.nextLink paging.
"""

from __future__ import annotations

from typing import Any, Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Config


class ODataClient:
    def __init__(self, config: Config, session: requests.Session | None = None):
        self.config = config
        self.session = session or self._build_session(config)

    @staticmethod
    def _build_session(config: Config) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=4,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({"Accept": "application/json"})

        if config.auth_mode == "basic":
            session.auth = (config.username, config.password)
        elif config.auth_mode == "apikey":
            header = config.authorization_header
            if header:
                session.headers["Authorization"] = header
        else:
            raise ValueError(f"Unknown auth mode: {config.auth_mode!r}")
        return session

    @staticmethod
    def build_params(
        *,
        select: str | None = None,
        filter_: str | None = None,
        orderby: str | None = None,
        expand: str | None = None,
        top: int | None = None,
    ) -> dict[str, str]:
        params: dict[str, str] = {}
        if select:
            params["$select"] = select
        if filter_:
            params["$filter"] = filter_
        if orderby:
            params["$orderby"] = orderby
        if expand:
            params["$expand"] = expand
        if top is not None:
            params["$top"] = str(top)
        return params

    def get_entity(self, path: str, key: int | str,
                   *, select: str | None = None,
                   expand: str | None = None) -> dict[str, Any]:
        """Fetch a single entity by key, e.g. ClassSections(113884)."""
        url = self.config.url(f"{path}({key})")
        params = self.build_params(select=select, expand=expand)
        resp = self.session.get(url, params=params, timeout=self.config.timeout)
        self._check(resp)
        return resp.json()

    def iter_collection(
        self,
        path: str,
        *,
        select: str | None = None,
        filter_: str | None = None,
        orderby: str | None = None,
        expand: str | None = None,
        top: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield every row from a collection, following @odata.nextLink paging."""
        params = self.build_params(
            select=select, filter_=filter_, orderby=orderby,
            expand=expand, top=top,
        )
        url: str | None = self.config.url(path)
        first = True
        while url:
            resp = self.session.get(
                url, params=params if first else None, timeout=self.config.timeout
            )
            first = False
            self._check(resp)
            payload = resp.json()
            rows = payload.get(
                "value", payload if isinstance(payload, list) else [payload]
            )
            yield from rows
            url = payload.get("@odata.nextLink")

    @staticmethod
    def _check(resp: requests.Response) -> None:
        if resp.status_code == 401:
            raise PermissionError(
                "401 Unauthorized — check the Application Key / scheme."
            )
        if resp.status_code == 403:
            raise PermissionError(
                "403 Forbidden — the key authenticates but lacks rights to this query."
            )
        resp.raise_for_status()
