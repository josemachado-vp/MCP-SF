"""
Shared async HTTP client for SAP SuccessFactors OData v2 API.

Handles data center resolution and Bearer token auth (OIDC).
Provides methods for metadata, OData queries, and picklist retrieval.
"""

from __future__ import annotations

import httpx
from typing import Optional


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


class SFClientError(Exception):
    """Raised when an SF API call fails."""

    def __init__(self, status_code: int, message: str, url: str):
        self.status_code = status_code
        self.message = message
        self.url = url
        super().__init__(f"SF API Error {status_code} for {url}: {message}")


class SFClient:
    """
    Async HTTP client for SAP SuccessFactors OData v2 API.

    Uses Bearer token authentication (OIDC via IAS).
    """

    def __init__(self, http_client: httpx.AsyncClient):
        self._client = http_client

    def resolve_base_url(self, data_center: str) -> str:
        """Resolve data center name to API base URL.

        Accepts a key from DATA_CENTERS (e.g. 'DC4') or a full URL.
        """
        dc_upper = data_center.upper().replace(" ", "_")
        if dc_upper in DATA_CENTERS:
            return DATA_CENTERS[dc_upper]
        if data_center.startswith("https://"):
            return data_center.rstrip("/")
        raise ValueError(
            f"Unknown data center '{data_center}'. "
            f"Valid options: {', '.join(sorted(DATA_CENTERS.keys()))} "
            f"or a full URL like https://api4.successfactors.com"
        )

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

        Automatically appends $format=json.
        """
        base_url = self.resolve_base_url(data_center)
        url = f"{base_url}/odata/v2/{entity}"

        query_params = {"$format": "json"}
        if params:
            query_params.update(params)

        response = await self._client.get(
            url,
            params=query_params,
            headers=self._bearer_headers(bearer_token),
            timeout=60.0,
        )
        if response.status_code != 200:
            raise SFClientError(response.status_code, response.text[:500], url)
        return response.json()

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
