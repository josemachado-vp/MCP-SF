"""
Test script for 2-step OIDC OAuth flow with SAP SuccessFactors via IAS.

Step 1: Get id_token from IAS via password grant
Step 2: Exchange id_token for SF-targeted access_token via jwt-bearer on IAS
Step 3: Use access_token as Bearer on SF API
"""

import os
import httpx
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

SF_HOST = os.environ["SF_API_HOST"]
SF_COMPANY_ID = os.environ["SF_COMPANY_ID"]
SF_USER_ID = os.environ["SF_USER_ID"]
SF_PASSWORD = os.environ["SF_PASSWORD"]
IAS_HOST = os.environ["IAS_HOST"]
CLIENT_ID = os.environ["OIDC_CLIENT_ID"]
CLIENT_SECRET = os.environ["OIDC_CLIENT_SECRET"]
DEPENDENCY_NAME = os.environ["IAS_DEPENDENCY_NAME"]

IAS_TOKEN_URL = f"https://{IAS_HOST}/oauth2/token"


def step1_get_ias_id_token() -> str:
    """Step 1: Get id_token from IAS using password grant."""
    print(f"\n{'='*60}")
    print("STEP 1: Get id_token from IAS (password grant)")
    print(f"{'='*60}")

    response = httpx.post(
        IAS_TOKEN_URL,
        data={
            "grant_type": "password",
            "username": SF_USER_ID,
            "password": SF_PASSWORD,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "openid",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )

    print(f"  Status: {response.status_code}")
    if response.status_code != 200:
        print(f"  ERROR: {response.text}")
        raise Exception(f"Step 1 failed: {response.status_code}")

    data = response.json()
    id_token = data["id_token"]
    print(f"  id_token OK (first 50 chars): {id_token[:50]}...")
    return id_token


def step2_exchange_for_sf_token(id_token: str) -> str:
    """Step 2: Exchange id_token for SF-targeted access_token via jwt-bearer."""
    print(f"\n{'='*60}")
    print("STEP 2: Exchange id_token for SF access_token (jwt-bearer)")
    print(f"{'='*60}")

    response = httpx.post(
        IAS_TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": id_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "resource": f"urn:sap:identity:application:provider:name:{DEPENDENCY_NAME}",
            "scope": "openid",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )

    print(f"  Status: {response.status_code}")
    if response.status_code != 200:
        print(f"  ERROR: {response.text}")
        raise Exception(f"Step 2 failed: {response.status_code}")

    sf_token = response.json()["access_token"]
    print(f"  SF token OK (first 50 chars): {sf_token[:50]}...")
    print(f"  Expires in: {response.json().get('expires_in', '?')} seconds")
    return sf_token


def step3_test_api(sf_token: str):
    """Step 3: Test SF API call with Bearer token."""
    url = f"{SF_HOST}/odata/v2/User?$top=3&$select=userId,firstName,lastName&$format=json"

    print(f"\n{'='*60}")
    print("STEP 3: Test SF API call with Bearer token")
    print(f"{'='*60}")

    response = httpx.get(
        url,
        headers={"Authorization": f"Bearer {sf_token}"},
        timeout=30.0,
    )

    print(f"  Status: {response.status_code}")
    if response.status_code != 200:
        print(f"  ERROR: {response.text[:500]}")
        raise Exception(f"Step 3 failed: {response.status_code}")

    results = response.json().get("d", {}).get("results", [])
    for user in results:
        print(f"  User: {user.get('firstName', '?')} {user.get('lastName', '?')} ({user.get('userId', '?')})")
    print(f"  Total users returned: {len(results)}")


if __name__ == "__main__":
    print("SAP SuccessFactors OIDC OAuth 2.0 - Connection Test")
    print(f"SF Host: {SF_HOST}")
    print(f"IAS Host: {IAS_HOST}")
    print(f"Company: {SF_COMPANY_ID}")

    try:
        id_token = step1_get_ias_id_token()
        sf_token = step2_exchange_for_sf_token(id_token)
        step3_test_api(sf_token)
        print(f"\n{'='*60}")
        print("ALL STEPS PASSED - OIDC connection is working!")
        print(f"{'='*60}")
    except Exception as e:
        print(f"\nFAILED: {e}")
