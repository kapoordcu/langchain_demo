#!/usr/bin/env python3

import argparse
import json
import os
import sys
import uuid
from typing import Any, Dict, Optional

import requests


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ORAGUARD_CLIENT_ID = os.getenv("ORAGUARD_CLIENT_ID")
ORAGUARD_CLIENT_SECRET = os.getenv("ORAGUARD_CLIENT_SECRET")
LSAIDP_CLIENT_ID = os.getenv("LSAIDP_CLIENT_ID")
LSAIDP_CLIENT_SECRET = os.getenv("LSAIDP_CLIENT_SECRET")

ORAGUARD_IDCS_URL = os.getenv("ORAGUARD_IDCS_URL")
AUTHZ_URL = os.getenv("AUTHZ_URL")
LSAIDP_IDCS_URL = os.getenv("LSAIDP_IDCS_URL")
AGENT_URL = os.getenv("AGENT_URL")

CUSTOMER_ID = os.getenv("CUSTOMER_ID", "test")

# Same values as your shell flow.
ORAGUARD_SCOPE = "orazguard.captoken"
LSAIDP_SCOPE = (
    "urn:agent-platform-api:"
    "agents:aidp-query-understanding-agent:invoke"
)

AUTHZ_SUB = os.getenv("AUTHZ_SUB", ORAGUARD_CLIENT_ID or "")
AUTHZ_ACT = "oracle-evidence"
AUTHZ_AUD = "query-understanding"
AUTHZ_PURPOSE = "oracle-evidence-investigation"

AUTHZ_PERMISSIONS = [
    {
        "resourceId": (
            "urn:rs:data-catalog:oracle:"
            "namespace:realworldevidence"
        ),
        "action": "read",
    },
    {
        "resourceId": (
            "urn:rs:data-catalog:test:"
            "namespace:lsdi:"
            "project:c0c0b310-c897-45f0-ac23-1a545fc20663"
        ),
        "action": "manage",
    },
]

TIMEOUT = 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fail(message: str) -> None:
    print(f"\nERROR: {message}", file=sys.stderr)
    sys.exit(1)


def require_env(name: str, value: Optional[str]) -> str:
    if not value:
        fail(f"Required environment variable is missing: {name}")
    return value


def pretty(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def response_body(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def check_response(
    response: requests.Response,
    operation: str,
) -> Any:
    body = response_body(response)

    print(f"\n[{operation}] HTTP {response.status_code}")

    if not response.ok:
        print(pretty(body) if isinstance(body, (dict, list)) else body)
        fail(f"{operation} failed with HTTP {response.status_code}")

    return body


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------

def get_oauth_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    scope: str,
    label: str,
) -> str:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "evidence-investigation-service/1.0",
    }

    data = {
        "grant_type": "client_credentials",
        "scope": scope,
    }

    print(f"\n=== {label}: requesting OAuth token ===")

    response = requests.post(
        token_url,
        headers=headers,
        data=data,
        auth=(client_id, client_secret),
        timeout=TIMEOUT,
    )

    body = check_response(response, f"{label} OAuth")

    token = body.get("access_token") if isinstance(body, dict) else None

    if not token:
        fail(f"{label} OAuth response did not contain access_token")

    print(f"{label}: token acquired successfully")
    return token


# ---------------------------------------------------------------------------
# CAP token
# ---------------------------------------------------------------------------

def get_cap_token(oraguard_oauth_token: str) -> str:
    print("\n=== AUTHZ: requesting CAP token ===")

    headers = {
        "Authorization": f"Bearer {oraguard_oauth_token}",
        "oh-hdils-customer-id": CUSTOMER_ID,
        "ttl": "3600",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "customerId": CUSTOMER_ID,
        "sub": AUTHZ_SUB,
        "act": AUTHZ_ACT,
        "aud": AUTHZ_AUD,
        "allowedAudiences": [AUTHZ_AUD],
        "permissions": AUTHZ_PERMISSIONS,
        "purpose": AUTHZ_PURPOSE,
    }

    response = requests.post(
        AUTHZ_URL,
        headers=headers,
        json=payload,
        timeout=TIMEOUT,
    )

    body = check_response(response, "AUTHZ CAP token")

    # Your shell flow accepts either field.
    cap_token = None
    if isinstance(body, dict):
        cap_token = body.get("access_token") or body.get("token")

    if not cap_token:
        fail("AUTHZ response did not contain access_token or token")

    print("CAP token acquired successfully")
    print("\nCAP response:")
    print(pretty(body))

    return cap_token


# ---------------------------------------------------------------------------
# Agent calls
# ---------------------------------------------------------------------------

def call_agent(
    lsaidp_oauth_token: str,
    cap_token: str,
    question: Optional[str] = None,
    conversation_id: Optional[str] = None,
    request_id: Optional[str] = None,
    max_events: int = 10,
) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {lsaidp_oauth_token}",
        "oh-hdils-authz": cap_token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload: Dict[str, Any] = {
        "max-events": max_events,
    }

    if question is not None:
        payload["question"] = question

    if conversation_id is not None:
        payload["conversation-id"] = conversation_id

    if request_id is not None:
        payload["request-id"] = request_id

    print("\n=== AGENT REQUEST ===")
    print(pretty(payload))

    response = requests.post(
        AGENT_URL,
        headers=headers,
        json=payload,
        timeout=TIMEOUT,
    )

    body = check_response(response, "Agent")

    print("\n=== AGENT RESPONSE ===")
    print(pretty(body) if isinstance(body, (dict, list)) else body)

    if isinstance(body, dict):
        return body

    return {"raw_response": body}


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end ORAGUARD -> AUTHZ -> LSAIDP -> Agent test"
    )

    parser.add_argument(
        "--question",
        default="How many patients are in ORWD?",
        help="Question sent to the agent",
    )

    parser.add_argument(
        "--max-events",
        type=int,
        default=10,
        help="max-events value sent to the agent",
    )

    parser.add_argument(
        "--conversation-id",
        help="Optional conversation ID for a continuation request",
    )

    parser.add_argument(
        "--request-id",
        help="Optional request ID for a continuation request",
    )

    parser.add_argument(
        "--continuation",
        action="store_true",
        help="Send the second/continuation agent request",
    )

    args = parser.parse_args()

    # Validate configuration before making requests.
    require_env("ORAGUARD_CLIENT_ID", ORAGUARD_CLIENT_ID)
    require_env("ORAGUARD_CLIENT_SECRET", ORAGUARD_CLIENT_SECRET)
    require_env("LSAIDP_CLIENT_ID", LSAIDP_CLIENT_ID)
    require_env("LSAIDP_CLIENT_SECRET", LSAIDP_CLIENT_SECRET)

    require_env("ORAGUARD_IDCS_URL", ORAGUARD_IDCS_URL)
    require_env("AUTHZ_URL", AUTHZ_URL)
    require_env("LSAIDP_IDCS_URL", LSAIDP_IDCS_URL)
    require_env("AGENT_URL", AGENT_URL)

    print("==============================================")
    print(" Oracle Evidence Agent End-to-End Test")
    print("==============================================")
    print(f"Customer ID : {CUSTOMER_ID}")
    print(f"Agent URL   : {AGENT_URL}")
    print("Credentials : loaded from environment")

    # -----------------------------------------------------------------------
    # 1. ORAGUARD OAuth
    # -----------------------------------------------------------------------

    oraguard_oauth_token = get_oauth_token(
        token_url=ORAGUARD_IDCS_URL,
        client_id=ORAGUARD_CLIENT_ID,
        client_secret=ORAGUARD_CLIENT_SECRET,
        scope=ORAGUARD_SCOPE,
        label="ORAGUARD",
    )

    # -----------------------------------------------------------------------
    # 2. CAP token
    # -----------------------------------------------------------------------

    cap_token = get_cap_token(oraguard_oauth_token)

    # -----------------------------------------------------------------------
    # 3. LSAIDP OAuth
    # -----------------------------------------------------------------------

    lsaidp_oauth_token = get_oauth_token(
        token_url=LSAIDP_IDCS_URL,
        client_id=LSAIDP_CLIENT_ID,
        client_secret=LSAIDP_CLIENT_SECRET,
        scope=LSAIDP_SCOPE,
        label="LSAIDP",
    )

    # -----------------------------------------------------------------------
    # 4. First agent request
    # -----------------------------------------------------------------------

    first_response = call_agent(
        lsaidp_oauth_token=lsaidp_oauth_token,
        cap_token=cap_token,
        question=args.question,
        max_events=args.max_events,
    )

    # Try to discover IDs from the first response for convenience.
    discovered_conversation_id = (
        first_response.get("conversation-id")
        or first_response.get("conversation_id")
        or first_response.get("conversationId")
    )

    discovered_request_id = (
        first_response.get("request-id")
        or first_response.get("request_id")
        or first_response.get("requestId")
    )

    # -----------------------------------------------------------------------
    # 5. Optional continuation request
    # -----------------------------------------------------------------------

    if args.continuation:
        conversation_id = args.conversation_id or discovered_conversation_id
        request_id = args.request_id or discovered_request_id

        if not conversation_id:
            fail(
                "Continuation requested, but no conversation ID was supplied "
                "and none was found in the first response."
            )

        if not request_id:
            fail(
                "Continuation requested, but no request ID was supplied "
                "and none was found in the first response."
            )

        print("\n==============================================")
        print(" Continuation Request")
        print("==============================================")

        call_agent(
            lsaidp_oauth_token=lsaidp_oauth_token,
            cap_token=cap_token,
            conversation_id=conversation_id,
            request_id=request_id,
            max_events=args.max_events,
        )

    print("\n==============================================")
    print(" FLOW COMPLETED SUCCESSFULLY")
    print("==============================================")


if __name__ == "__main__":
    main()