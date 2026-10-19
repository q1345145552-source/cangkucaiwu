"""Client IP after Uvicorn's trusted-proxy validation; never trust arbitrary headers."""
import os
from ipaddress import ip_address


def _ip(value):
    try:
        if not value or "%" in value:
            return None
        return str(ip_address(value.strip()))
    except ValueError:
        return None


def get_client_ip(request):
    peer = _ip(request.client.host) if request.client else None
    if peer is None:
        return None
    trusted = {_ip(value) for value in os.environ.get("FORWARDED_ALLOW_IPS", "").split(",")}
    trusted.discard(None)
    raw_forwarded = request.headers.get("X-Forwarded-For", "")
    forwarded = [_ip(value) for value in raw_forwarded.split(",")] if raw_forwarded else []
    real = _ip(request.headers.get("X-Real-IP"))

    if peer in trusted:
        # Used if Uvicorn has not rewritten the peer (e.g. X-Real-IP only).
        # Nginx appends its observed client: discard any untrusted prefix supplied
        # by the visitor instead of blindly accepting a spoofed leftmost value.
        if forwarded and all(forwarded):
            for candidate in reversed(forwarded):
                if candidate not in trusted:
                    return candidate
        return real or peer

    # A public peer is either the TCP source or Uvicorn's already validated
    # client. Header values may be used only when they agree with that source.
    if forwarded and forwarded[0] == peer:
        return forwarded[0]
    if real == peer:
        return real
    return peer
