"""
GHL OAuth token management.

Access tokens last ~24h. Refresh tokens last ~1 year but rotate on every refresh
(old refresh token becomes invalid). This module:
- refreshes with a process lock + DB row lock (avoids concurrent refresh races)
- refreshes proactively when access token is near expiry
- powers 401 retry for API callers
"""
from __future__ import annotations

import base64
import json
import logging
import threading
from datetime import timedelta
from typing import Optional

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import GHLAuthCredentials

logger = logging.getLogger(__name__)

TOKEN_URL = "https://services.leadconnectorhq.com/oauth/token"
# Refresh before hard expiry so brief beat/redis downtime cannot strand us.
REFRESH_SKEW = timedelta(hours=2)
REQUEST_TIMEOUT = 20

_locks_guard = threading.Lock()
_refresh_locks: dict[str, threading.Lock] = {}


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        if key not in _refresh_locks:
            _refresh_locks[key] = threading.Lock()
        return _refresh_locks[key]


def decode_jwt_payload(token: str) -> dict:
    if not token or "." not in token:
        return {}
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def access_token_expires_at(access_token: str) -> Optional[float]:
    exp = decode_jwt_payload(access_token).get("exp")
    try:
        return float(exp) if exp is not None else None
    except (TypeError, ValueError):
        return None


def is_access_token_fresh(credentials: GHLAuthCredentials, skew: timedelta = REFRESH_SKEW) -> bool:
    exp = access_token_expires_at(credentials.access_token or "")
    if not exp:
        return False
    return timezone.now().timestamp() < (exp - skew.total_seconds())


def is_ghl_auth_failure(status_code: int, body_text: str = "") -> bool:
    if status_code != 401:
        return False
    text = (body_text or "").lower()
    # GHL commonly returns {"statusCode":401,"message":"Invalid JWT"}
    return ("jwt" in text) or ("unauthorized" in text) or ("invalid" in text) or not text


def get_credentials(location_id: Optional[str] = None) -> Optional[GHLAuthCredentials]:
    if location_id:
        creds = GHLAuthCredentials.objects.filter(location_id=location_id).first()
        if creds:
            return creds
    return GHLAuthCredentials.objects.first()


def refresh_credentials(
    credentials: Optional[GHLAuthCredentials] = None,
    *,
    location_id: Optional[str] = None,
    force: bool = False,
) -> GHLAuthCredentials:
    """
    Refresh GHL OAuth tokens for one credential row.
    Safe to call from celery beat, cron, or request path on 401.
    """
    creds = credentials or get_credentials(location_id)
    if not creds:
        raise RuntimeError("No GHL credentials configured")

    lock_key = creds.location_id or str(creds.pk)
    lock = _lock_for(lock_key)

    with lock:
        with transaction.atomic():
            creds = GHLAuthCredentials.objects.select_for_update().get(pk=creds.pk)

            if not force and is_access_token_fresh(creds):
                logger.info(
                    "Skipping refresh for location %s — access token still fresh",
                    creds.location_id,
                )
                return creds

            client_id = settings.GHL_CLIENT_ID
            client_secret = settings.GHL_CLIENT_SECRET
            if not client_id or not client_secret:
                raise RuntimeError("GHL_CLIENT_ID / GHL_CLIENT_SECRET not configured")

            logger.info("Refreshing GHL token for location %s (force=%s)", creds.location_id, force)
            response = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": creds.refresh_token,
                },
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code != 200:
                logger.error(
                    "Token refresh failed for location %s. Status=%s Body=%s",
                    creds.location_id,
                    response.status_code,
                    response.text[:500],
                )
                raise RuntimeError(
                    f"GHL token refresh failed ({response.status_code}): {response.text[:300]}"
                )

            new_tokens = response.json()
            if not new_tokens.get("access_token") or not new_tokens.get("refresh_token"):
                logger.error("Invalid token response for location %s: %s", creds.location_id, new_tokens)
                raise RuntimeError("GHL token refresh returned incomplete payload")

            # Keep the existing row (do not create a second row if locationId missing).
            location = new_tokens.get("locationId") or creds.location_id
            if location and location != creds.location_id:
                # Rare: location changed — update lookup key on same row.
                creds.location_id = location

            creds.access_token = new_tokens["access_token"]
            creds.refresh_token = new_tokens["refresh_token"]
            creds.expires_in = new_tokens.get("expires_in") or creds.expires_in
            if new_tokens.get("scope"):
                creds.scope = new_tokens.get("scope")
            if new_tokens.get("userType"):
                creds.user_type = new_tokens.get("userType")
            if new_tokens.get("companyId"):
                creds.company_id = new_tokens.get("companyId")
            if new_tokens.get("userId"):
                creds.user_id = new_tokens.get("userId")
            creds.save()

            logger.info("Successfully refreshed GHL token for location %s", creds.location_id)
            return creds


def refresh_all_credentials(*, force: bool = False) -> dict:
    """Refresh every stored GHL credential. Used by beat task + management command."""
    results = {"ok": [], "failed": [], "skipped": []}
    for creds in GHLAuthCredentials.objects.all():
        try:
            if not force and is_access_token_fresh(creds):
                results["skipped"].append(creds.location_id)
                continue
            refreshed = refresh_credentials(creds, force=True)
            results["ok"].append(refreshed.location_id)
        except Exception as exc:
            logger.exception("Failed refreshing location %s", creds.location_id)
            results["failed"].append({"location_id": creds.location_id, "error": str(exc)})
    return results


def ensure_fresh_credentials(
    credentials: Optional[GHLAuthCredentials] = None,
    *,
    location_id: Optional[str] = None,
) -> GHLAuthCredentials:
    """Return credentials, refreshing first if access token is near expiry."""
    creds = credentials or get_credentials(location_id)
    if not creds:
        raise RuntimeError("No GHL credentials configured")
    if not is_access_token_fresh(creds):
        return refresh_credentials(creds, force=True)
    return creds


def ghl_request(
    method: str,
    url: str,
    *,
    credentials: Optional[GHLAuthCredentials] = None,
    location_id: Optional[str] = None,
    headers: Optional[dict] = None,
    retry_on_401: bool = True,
    timeout: int = 30,
    **kwargs,
) -> requests.Response:
    """
    HTTP helper that auto-refreshes on GHL 401 Invalid JWT and retries once.
    Mutates the provided credentials instance in-memory after refresh.
    """
    creds = ensure_fresh_credentials(credentials, location_id=location_id)
    req_headers = {
        "Accept": "application/json",
        "Version": "2021-07-28",
        "Content-Type": "application/json",
    }
    if headers:
        # Caller headers first; Authorization always set from freshest token last.
        req_headers.update({k: v for k, v in headers.items() if k.lower() != "authorization"})
    req_headers["Authorization"] = f"Bearer {creds.access_token}"

    response = requests.request(method, url, headers=req_headers, timeout=timeout, **kwargs)

    if retry_on_401 and is_ghl_auth_failure(response.status_code, response.text):
        logger.warning(
            "GHL auth failure on %s %s — refreshing token and retrying once",
            method.upper(),
            url,
        )
        creds = refresh_credentials(creds, force=True)
        if credentials is not None:
            credentials.access_token = creds.access_token
            credentials.refresh_token = creds.refresh_token
            credentials.expires_in = creds.expires_in
            credentials.user_id = creds.user_id
            credentials.location_id = creds.location_id
        req_headers["Authorization"] = f"Bearer {creds.access_token}"
        response = requests.request(method, url, headers=req_headers, timeout=timeout, **kwargs)

    return response
