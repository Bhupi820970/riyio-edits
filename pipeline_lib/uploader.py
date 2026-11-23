"""Publish 4K renders directly via Buffer GraphQL API.

Uses BUFFER_ACCESS_TOKEN (API key or OAuth Bearer token).

- 4K 16:9 -> all connected YouTube + X (Twitter) Buffer channels
- 4K 9:16 -> all connected Instagram Buffer channels

Media must be a publicly reachable HTTPS URL (Buffer fetches it at publish time).
Gracefully skips the entire Buffer publish if BUFFER_ACCESS_TOKEN is not set.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any

BUFFER_ENDPOINT = "https://api.buffer.com"


def _token() -> str | None:
    return (os.environ.get("BUFFER_ACCESS_TOKEN") or "").strip() or None


def _auth_header(token: str) -> str:
    # Support both raw API key and Bearer-style OAuth token
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


def _gql(query: str, variables: dict | None = None) -> dict[str, Any]:
    token = _token()
    if not token:
        raise RuntimeError("BUFFER_ACCESS_TOKEN not set")
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        BUFFER_ENDPOINT,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": _auth_header(token),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    if "errors" in data and data["errors"]:
        raise RuntimeError(f"Buffer GraphQL error: {data['errors']}")
    return data.get("data") or {}


def get_organization_id() -> str | None:
    data = _gql("""
        query {
          account {
            organizations { id name }
          }
        }
    """)
    orgs = (data.get("account") or {}).get("organizations") or []
    if not orgs:
        return None
    return orgs[0]["id"]


def list_channels(org_id: str) -> list[dict]:
    data = _gql("""
        query GetChannels($org: OrganizationId!) {
          channels(input: { organizationId: $org }) {
            id
            name
            displayName
            service
          }
        }
    """, {"org": org_id})
    return data.get("channels") or []


def create_video_post(channel_id: str, text: str, video_url: str | None,
                      service: str | None = None, title: str | None = None) -> dict:
    assets = []
    if video_url:
        assets = [{"video": {"url": video_url}}]
    input_obj: dict = {
        "text": text or "RIYIO edit",
        "channelId": channel_id,
        "schedulingType": "automatic",
        "mode": "addToQueue",
        "assets": assets,
    }
    # YouTube requires title + category; Shorts also prefer vertical
    if service and "youtube" in service.lower():
        input_obj["metadata"] = {
            "youtube": {
                "title": (title or text or "RIYIO Edit")[:70],
                "categoryId": "24",  # Entertainment (Buffer requires categoryId)
                "madeForKids": False,
            }
        }
    mutation = """
        mutation CreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess {
              post { id text status }
            }
            ... on MutationError {
              message
            }
          }
        }
    """
    return _gql(mutation, {"input": input_obj})


def _service_match(service: str, targets: set[str]) -> bool:
    s = (service or "").lower()
    return s in targets or any(t in s for t in targets)


def publish_via_buffer(
    shorts_url: str | None,
    title: str,
    caption: str = "",
    demo_only: bool = False,
) -> dict:
    """Post the SAME 4K 9:16 vertical Shorts to YouTube, X, and Instagram.

    YouTube receives title + categoryId=24 (Entertainment) + madeForKids=false.
    If demo_only is True, channel list is printed but no posts are created.
    """
    token = _token()
    if not token:
        print("BUFFER_ACCESS_TOKEN not set — skipping Buffer publish")
        return {"skipped": True, "reason": "no BUFFER_ACCESS_TOKEN"}

    try:
        org_id = get_organization_id()
        if not org_id:
            print("No Buffer organization found — skipping")
            return {"skipped": True, "reason": "no organization"}
        channels = list_channels(org_id)
        print("Detected Buffer channels:")
        for c in channels:
            print(f"  - id={c.get('id')} service={c.get('service')} name={c.get('name') or c.get('displayName')}")
    except Exception as e:
        print(f"Buffer channel list failed: {e}")
        return {"skipped": True, "reason": str(e)}

    if demo_only:
        print("DEMO_ONLY=true — Buffer posting skipped")
        return {"skipped": True, "reason": "demo_only", "channels": len(channels)}

    targets = [c for c in channels if _service_match(
        c.get("service", ""), {"youtube", "twitter", "x", "instagram"}
    )]
    text = caption or title or "RIYIO 4K edit"
    results = {"posts": [], "skipped": False}

    for ch in targets:
        if not shorts_url:
            print(f"[{ch.get('service')}] no public 9:16 URL — skipping {ch.get('name')}")
            continue
        try:
            res = create_video_post(
                ch["id"], text, shorts_url,
                service=ch.get("service"), title=title,
            )
            results["posts"].append({"channel": ch.get("name"), "service": ch.get("service"), "ok": True, "res": res})
            print(f"Buffer posted 9:16 to {ch.get('service')} / {ch.get('name')}")
        except Exception as e:
            results["posts"].append({"channel": ch.get("name"), "service": ch.get("service"), "ok": False, "error": str(e)})
            print(f"Buffer fail {ch.get('name')}: {e}")

    return results


# Backwards-compatible wrapper
def upload_dual(wide: Path, shorts: Path, title: str, caption: str = "",
                wide_url: str | None = None, shorts_url: str | None = None,
                demo_only: bool = False) -> dict:
    """All platforms now receive the 9:16 shorts URL."""
    return publish_via_buffer(shorts_url or wide_url, title, caption, demo_only=demo_only)
