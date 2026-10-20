"""
Shared async HTTP client for SAP SuccessFactors OData v2 API.

Handles data center resolution and Bearer token auth (OIDC).
Provides methods for metadata, OData queries, and picklist retrieval.

Security boundaries enforced here (not in individual tools):
  - Host allowlist: the Bearer token is only ever sent to a DATA_CENTERS
    host, the configured SF_API_HOST, or a host listed in SF_ALLOWED_HOSTS.
  - PII policy: every OData query is validated (helpers.pii_filter) before
    execution and its JSON response is scrubbed recursively afterwards, so
    no tool can bypass the PII layer by calling the client directly.
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlsplit

import httpx

from helpers.pii_filter import scrub_payload, validate_entity_name, validate_query

logger = logging.getLogger(__name__)


# Data center mapping (from SAP KBA 2215682)
DATA_CENTERS: dict[str, str] = {
    # Production
    "DC2": "https://api2.successfactors.eu",
    "DC4": "https://api4.successfactors.com",
    "DC5": "https://api5.successfactors.eu",
    "DC8": "https://api8.successfactors.com",
    "DC10": "https://api10.successfactors.com",
    "DC12": "https://api012.successfactors.eu",
    "DC15": "https://api15.sapsf.cn",
    "DC16": "https://api16.sapsf.eu",
    "DC17": "https://api17.sapsf.com",
    "DC18": "https://api18.sapsf.com",
    "DC19": "https://api19.sapsf.com",
    "DC22": "https://api22.sapsf.com",
    "DC23": "https://api23.sapsf.com",
    "DC42": "https://api42.sapsf.com",
    "DC44": "https://api44.sapsf.com",
    # Preview
    "DC2_PREVIEW": "https://api2preview.sapsf.eu",
    "DC4_PREVIEW": "https://api4preview.sapsf.com",
    "DC8_PREVIEW": "https://api8preview.sapsf.com",
    "DC10_PREVIEW": "https://api10preview.sapsf.com",
    "DC12_PREVIEW": "https://api12preview.sapsf.eu",
    # Sales Demo
    "DC4_SALESDEMO": "https://apisalesdemo4.successfactors.com",
    "DC8_SALESDEMO": "https://apisalesdemo8.successfactors.com",
    "DC2_SALESDEMO": "https://apisalesdemo2.successfactors.eu",
}


def _normalize_host(value: str) -> str:
    """Return the lowercase hostname of a host or https URL ('' if unparseable)."""
    value = value.strip()
    if "://" not in value:
        value = f"https://{value}"
    try:
        return (urlsplit(value).hostname or "").lower()
    except ValueError:
        return ""


def allowed_hosts() -> set[str]:
    """Hostnames the Bearer token may be sent to.

    DATA_CENTERS hosts + SF_API_HOST + comma-separated SF_ALLOWED_HOSTS.
    Read from the environment on each call so config reloads take effect.
    """
    hosts = {_normalize_host(url) for url in DATA_CENTERS.values()}
    hosts.add(_normalize_host(os.environ.get("SF_API_HOST", "")))
    for extra in os.environ.get("SF_ALLOWED_HOSTS", "").split(","):
        hosts.add(_normalize_host(extra))
    hosts.discard("")
    return hosts


def resolve_sf_base_url(data_center: str) -> str:
    """Resolve a data center code, hostname or https URL to an allowed base URL.

    Accepts a DATA_CENTERS key (e.g. 'DC4'), a bare hostname
    (e.g. 'api8preview.sapsf.com') or an https URL. Anything that is not
    https, carries a path/query/credentials/port, or whose host is not in
    allowed_hosts() is rejected with ValueError.
    """
    dc_upper = data_center.strip().upper().replace(" ", "_")
    if dc_upper in DATA_CENTERS:
        return DATA_CENTERS[dc_upper]

    raw = data_center.strip()
    if "://" not in raw and "." in raw:
        raw = f"https://{raw}"
    if "://" not in raw:
        raise ValueError(
            f"Unknown data center '{data_center}'. "
            f"Valid options: {', '.join(sorted(DATA_CENTERS.keys()))}, "
            "the configured SF_API_HOST, or a host listed in SF_ALLOWED_HOSTS."
        )

    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"Invalid data center URL '{data_center}'.") from exc
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or not host
        or parts.username is not None
        or parts.password is not None
        or port is not None
        or parts.path.strip("/")
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            f"Invalid data center URL '{data_center}'. "
            "Only https://<host> without path, port, query or credentials is accepted."
        )
    if host not in allowed_hosts():
        logger.warning("Rejected data center host not in allowlist: %s", host)
        raise ValueError(
            f"Host '{host}' is not an allowed SuccessFactors API host. "
            "Use a data center code, the configured SF_API_HOST, "
            "or add the host to SF_ALLOWED_HOSTS."
        )
    return f"https://{host}"


class SFClientError(Exception):
    """Raised when an SF API call fails."""

    def __init__(self, status_code: int, message: str, url: str):
        self.status_code = status_code
        self.message = message
        self.url = url
        super().__init__(f"SF API Error {status_code} for {url}: {message}")


class PIIPolicyError(SFClientError):
    """Raised, before any HTTP call, when a query violates the PII policy."""

    def __init__(self, message: str, url: str, blocked_fields: list[str]):
        self.blocked_fields = blocked_fields
        super().__init__(403, message, url)


class SFClient:
    """
    Async HTTP client for SAP SuccessFactors OData v2 API.

    Uses Bearer token authentication (OIDC via IAS).
    """

    def __init__(self, http_client: httpx.AsyncClient):
        self._client = http_client

    def resolve_base_url(self, data_center: str) -> str:
        """Resolve data center name to an allowlisted API base URL.

        See resolve_sf_base_url for the accepted forms.
        """
        return resolve_sf_base_url(data_center)

    def _bearer_headers(self, bearer_token: str) -> dict[str, str]:
        """Build Authorization headers for Bearer token auth."""
        return {"Authorization": f"Bearer {bearer_token}"}

    async def get_metadata(
        self,
        data_center: str,
        bearer_token: str,
        entity: Optional[str] = None,
    ) -> str:
        """Fetch OData $metadata (XML).

        If entity is provided: GET /odata/v2/{entity}/$metadata
        If entity is None:     GET /odata/v2/$metadata (full — can be very large)
        """
        base_url = self.resolve_base_url(data_center)
        if entity:
            validate_entity_name(entity)
            url = f"{base_url}/odata/v2/{entity}/$metadata"
        else:
            url = f"{base_url}/odata/v2/$metadata"

        response = await self._client.get(
            url,
            headers={**self._bearer_headers(bearer_token), "Accept": "application/xml"},
            timeout=60.0,
        )
        if response.status_code != 200:
            raise SFClientError(response.status_code, response.text[:500], url)
        return response.text

    async def query_odata(
        self,
        data_center: str,
        bearer_token: str,
        entity: str,
        params: Optional[dict[str, str]] = None,
    ) -> dict:
        """Execute an OData query and return JSON.

        Automatically appends $format=json. The query is validated against the
        PII policy first (PIIPolicyError, no HTTP call, if blocked) and the
        response is scrubbed recursively; names of removed fields, if any, are
        returned under the top-level key "pii_redacted_fields".
        """
        base_url = self.resolve_base_url(data_center)
        url = f"{base_url}/odata/v2/{entity}"

        query_params = {"$format": "json"}
        if params:
            query_params.update(params)

        pii_check = validate_query(
            entity,
            select=query_params.get("$select"),
            filter_expr=query_params.get("$filter"),
            expand=query_params.get("$expand"),
        )
        if not pii_check.allowed:
            raise PIIPolicyError(
                pii_check.error_message or "Query blocked by PII policy.",
                url,
                pii_check.blocked_fields,
            )

        response = await self._client.get(
            url,
            params=query_params,
            headers=self._bearer_headers(bearer_token),
            timeout=60.0,
        )
        if response.status_code != 200:
            raise SFClientError(response.status_code, response.text[:500], url)

        data = response.json()
        redacted = scrub_payload(data)
        if redacted:
            logger.info("PII scrub removed fields from %s response: %s", entity, sorted(redacted))
            data["pii_redacted_fields"] = sorted(redacted)
        return data

    async def get_picklist(
        self,
        data_center: str,
        bearer_token: str,
        picklist_id: str,
    ) -> dict:
        """Fetch picklist options for a given picklist ID."""
        return await self.query_odata(
            data_center=data_center,
            bearer_token=bearer_token,
            entity="Picklist",
            params={
                "$filter": f"picklistId eq '{picklist_id}'",
                "$expand": "picklistOptions",
            },
        )

    async def post_odata(
        self,
        data_center: str,
        bearer_token: str,
        entity: str,
        payload: dict,
    ) -> dict:
        """POST a new record to an OData entity.

        Returns the created record as JSON.
        """
        base_url = self.resolve_base_url(data_center)
        url = f"{base_url}/odata/v2/{entity}"

        response = await self._client.post(
            url,
            json=payload,
            headers={
                **self._bearer_headers(bearer_token),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=60.0,
        )
        if response.status_code not in (200, 201):
            raise SFClientError(response.status_code, response.text[:500], url)
        return response.json()

    async def put_odata(
        self,
        data_center: str,
        bearer_token: str,
        entity: str,
        key: str,
        payload: dict,
    ) -> dict:
        """PUT (update) an existing record.

        Args:
            key: OData key expression, e.g. "(userId='admin',startDate=datetime'2024-01-01')"
        """
        base_url = self.resolve_base_url(data_center)
        url = f"{base_url}/odata/v2/{entity}{key}"

        response = await self._client.put(
            url,
            json=payload,
            headers={
                **self._bearer_headers(bearer_token),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=60.0,
        )
        if response.status_code not in (200, 204):
            raise SFClientError(response.status_code, response.text[:500], url)
        if response.status_code == 204:
            return {"status": "updated"}
        return response.json()

    async def upsert_odata(
        self,
        data_center: str,
        bearer_token: str,
        entity: str,
        payload: dict,
    ) -> dict:
        """UPSERT a record (POST with upsert semantics).

        SF OData v2 treats POST as upsert when key fields are included.
        """
        return await self.post_odata(
            data_center=data_center,
            bearer_token=bearer_token,
            entity=entity,
            payload=payload,
        )
