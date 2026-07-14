import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


def sync_newsletter_contact(email, list_id=None):
    if not settings.BREVO_API_KEY:
        return False, "BREVO_API_KEY nao configurada."
    payload = {
        "email": email,
        "updateEnabled": True,
    }
    if list_id:
        payload["listIds"] = [list_id]
    request = Request(
        "https://api.brevo.com/v3/contacts",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "api-key": settings.BREVO_API_KEY,
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status in {200, 201, 204}, ""
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {detail[:500]}"
    except (URLError, TimeoutError) as exc:
        return False, str(exc)[:500]
