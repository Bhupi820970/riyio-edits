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


def create_video_post(channel_id: str, text: str, video_url: str | None) -> dict:
    assets = []
    if video_url:
        assets = [{"video": {"url": video_url}}]
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
    variables = {
        "input": {
            "text": text or "RIYIO edit",
            "channelId": channel_id,
            "schedulingType": "automatic",
            "mode": "addToQueue",
            "assets": assets,
        }
    }
    return _gql(mutation, variables)


def _service_match(service: str, targets: set[str]) -> bool:
    s = (service or "").lower()
    return s in targets or any(t in s for t in targets)


def publish_via_buffer(
    wide_url: str | None,
    shorts_url: str | None,
    title: str,
    caption: str = "",
) -> dict:
    """Post 16:9 to YouTube+X channels, 9:16 to Instagram channels.

    Returns a summary dict. Never raises if token is missing.
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

    yt_x = [c for c in channels if _service_match(c.get("service", ""), {"youtube", "twitter", "x"})]
    ig = [c for c in channels if _service_match(c.get("service", ""), {"instagram"})]

    text = caption or title or "RIYIO 4K edit"
    results = {"youtube_x": [], "instagram": [], "skipped": False}

    for ch in yt_x:
        if not wide_url:
            print(f"[{ch.get('service')}] no public 16:9 URL — skipping {ch.get('name')}")
            continue
        try:
            res = create_video_post(ch["id"], text, wide_url)
            results["youtube_x"].append({"channel": ch.get("name"), "ok": True, "res": res})
            print(f"Buffer posted 16:9 to {ch.get('service')} / {ch.get('name')}")
        except Exception as e:
            results["youtube_x"].append({"channel": ch.get("name"), "ok": False, "error": str(e)})
            print(f"Buffer fail {ch.get('name')}: {e}")

    for ch in ig:
        if not shorts_url:
            print(f"[instagram] no public 9:16 URL — skipping {ch.get('name')}")
            continue
        try:
            res = create_video_post(ch["id"], text, shorts_url)
            results["instagram"].append({"channel": ch.get("name"), "ok": True, "res": res})
            print(f"Buffer posted 9:16 to Instagram / {ch.get('name')}")
        except Exception as e:
            results["instagram"].append({"channel": ch.get("name"), "ok": False, "error": str(e)})
            print(f"Buffer fail {ch.get('name')}: {e}")

    return results


# Backwards-compatible wrapper used by pipeline.py
def upload_dual(wide: Path, shorts: Path, title: str, caption: str = "",
                wide_url: str | None = None, shorts_url: str | None = None) -> dict:
    """If public URLs are supplied, publish via Buffer. Otherwise skip gracefully."""
    return publish_via_buffer(wide_url, shorts_url, title, caption)
