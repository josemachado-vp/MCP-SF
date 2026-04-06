"""
Credential store abstraction for multi-tenant support.

Provides pluggable credential storage:
- EnvCredentialStore: reads from environment variables (default, backwards-compatible)
- GCPSecretManagerStore: reads from Google Cloud Secret Manager (optional)
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class TenantCredentials:
    """Credentials for a specific tenant."""

    api_host: str
    user_id: str
    password: str
    company_id: str
    ias_host: str
    oidc_client_id: str
    oidc_client_secret: str
    ias_dependency_name: str


class CredentialStore(ABC):
    """Abstract interface for credential storage."""

    @abstractmethod
    async def get_credentials(self, tenant_id: str) -> TenantCredentials:
        """Retrieve credentials for a tenant."""
        ...

    @abstractmethod
    async def store_credentials(self, tenant_id: str, creds: TenantCredentials) -> None:
        """Store credentials for a tenant."""
        ...


class EnvCredentialStore(CredentialStore):
    """Read credentials from environment variables. Backwards-compatible default."""

    async def get_credentials(self, tenant_id: str = "default") -> TenantCredentials:
        """Read credentials from env vars. tenant_id is ignored (single-tenant)."""
        return TenantCredentials(
            api_host=os.environ.get("SF_API_HOST", ""),
            user_id=os.environ.get("SF_USER_ID", ""),
            password=os.environ.get("SF_PASSWORD", ""),
            company_id=os.environ.get("SF_COMPANY_ID", ""),
            ias_host=os.environ.get("IAS_HOST", ""),
            oidc_client_id=os.environ.get("OIDC_CLIENT_ID", ""),
            oidc_client_secret=os.environ.get("OIDC_CLIENT_SECRET", ""),
            ias_dependency_name=os.environ.get("IAS_DEPENDENCY_NAME", ""),
        )

    async def store_credentials(self, tenant_id: str, creds: TenantCredentials) -> None:
        """Not supported for env store."""
        raise NotImplementedError("Cannot store credentials in environment variable store")


class GCPSecretManagerStore(CredentialStore):
    """Read credentials from Google Cloud Secret Manager.

    Requires: google-cloud-secret-manager >= 2.0.0
    Install with: uv sync --extra gcp

    Secret naming convention: sf-{tenant_id}-{field}
    Example: sf-acme-api_host, sf-acme-user_id, etc.
    """

    def __init__(self, project_id: str, prefix: str = "sf"):
        self._project_id = project_id
        self._prefix = prefix
        self._client: Optional[object] = None

    def _get_client(self):
        if self._client is None:
            try:
                from google.cloud import secretmanager
                self._client = secretmanager.SecretManagerServiceClient()
            except ImportError:
                raise ImportError(
                    "google-cloud-secret-manager is required. "
                    "Install with: uv sync --extra gcp"
                )
        return self._client

    async def get_credentials(self, tenant_id: str) -> TenantCredentials:
        """Read credentials from GCP Secret Manager."""
        import asyncio

        client = self._get_client()
        fields = [
            "api_host", "user_id", "password", "company_id",
            "ias_host", "oidc_client_id", "oidc_client_secret", "ias_dependency_name",
        ]

        def _read_secret(field: str) -> str:
            secret_name = f"projects/{self._project_id}/secrets/{self._prefix}-{tenant_id}-{field}/versions/latest"
            try:
                response = client.access_secret_version(request={"name": secret_name})
                return response.payload.data.decode("UTF-8")
            except Exception:
                return ""

        loop = asyncio.get_event_loop()
        values = await asyncio.gather(
            *[loop.run_in_executor(None, _read_secret, f) for f in fields]
        )

        return TenantCredentials(**dict(zip(fields, values)))

    async def store_credentials(self, tenant_id: str, creds: TenantCredentials) -> None:
        """Store credentials in GCP Secret Manager."""
        import asyncio

        client = self._get_client()
        creds_dict = {
            "api_host": creds.api_host,
            "user_id": creds.user_id,
            "password": creds.password,
            "company_id": creds.company_id,
            "ias_host": creds.ias_host,
            "oidc_client_id": creds.oidc_client_id,
            "oidc_client_secret": creds.oidc_client_secret,
            "ias_dependency_name": creds.ias_dependency_name,
        }

        def _store_secret(field: str, value: str) -> None:
            secret_id = f"{self._prefix}-{tenant_id}-{field}"
            parent = f"projects/{self._project_id}"
            secret_path = f"{parent}/secrets/{secret_id}"

            try:
                client.get_secret(request={"name": secret_path})
            except Exception:
                client.create_secret(
                    request={
                        "parent": parent,
                        "secret_id": secret_id,
                        "secret": {"replication": {"automatic": {}}},
                    }
                )

            client.add_secret_version(
                request={
                    "parent": secret_path,
                    "payload": {"data": value.encode("UTF-8")},
                }
            )

        loop = asyncio.get_event_loop()
        await asyncio.gather(
            *[loop.run_in_executor(None, _store_secret, f, v) for f, v in creds_dict.items()]
        )
