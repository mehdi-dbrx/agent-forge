"""
FE Vending Machine API client.

Uses a Playwright-captured session cookie for authentication.
Cookie can be refreshed via grab_cookies() when it expires.
"""

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = "https://vending-machine-main-2481552415672103.aws.databricksapps.com"
COOKIES_FILE = Path(__file__).parent / "session_cookies.json"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def load_session_cookie(cookies_file: Path = COOKIES_FILE) -> str:
    """Load the __Host-databricksapps session cookie from disk."""
    cookies = json.loads(cookies_file.read_text())
    for c in cookies:
        if c["name"] == "__Host-databricksapps":
            return c["value"]
    raise ValueError(f"Session cookie not found in {cookies_file}. Run grab_cookies() to refresh.")


def grab_cookies(cookies_file: Path = COOKIES_FILE) -> None:
    """
    Open a real browser, let the user log in, and save session cookies to disk.
    Requires playwright: uv add playwright && playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright is required: pip install playwright && playwright install chromium")

    import time

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        print(f"[fevm] Opening browser → {BASE_URL}")
        page.goto(BASE_URL)
        page.wait_for_url(
            lambda url: "vending-machine-main" in url and ".auth" not in url,
            timeout=120_000,
        )
        time.sleep(3)
        cookies = context.cookies()
        cookies_file.write_text(json.dumps(cookies, indent=2))
        print(f"[fevm] {len(cookies)} cookies saved to {cookies_file}")
        browser.close()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _request(method: str, path: str, body: dict | None = None) -> Any:
    cookie = load_session_cookie()
    url = BASE_URL + path
    data = json.dumps(body).encode() if body else None
    headers = {
        "Cookie": f"__Host-databricksapps={cookie}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {body}") from e


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def get_template(template_id: str) -> dict:
    """Fetch template definition."""
    return _request("GET", f"/api/templates/{template_id}")


def get_workspaces(region: str = "us-east-1", cloud_provider: str = "aws") -> dict:
    """List available deployment workspaces."""
    return _request("GET", f"/api/deployments/workspaces?region={region}&cloud_provider={cloud_provider}")


def get_quotas() -> dict:
    """Get current quota usage."""
    return _request("GET", "/api/quotas/templates")


def list_deployments() -> dict:
    """List your deployments."""
    return _request("GET", "/api/deployments")


def deploy_standalone_catalog(
    catalog_name: str,
    region: str = "us-east-1",
    resource_lifetime: int = 90,
    intent: str = "Customer Demo/Testing",
    environment: str = "stable",
    cloud_provider: str = "aws",
) -> dict:
    """
    Deploy a standalone catalog resource.

    Args:
        catalog_name:      Name for the catalog (letters, numbers, underscores only).
        region:            AWS region (default: us-east-1).
        resource_lifetime: Days until auto-deletion, 1-180 (default: 90).
        intent:            Deployment intent description.
        environment:       Environment tier (default: stable).
        cloud_provider:    Cloud provider (default: aws).

    Returns:
        API response dict with deployment details.
    """
    if not catalog_name.replace("_", "").isalnum():
        raise ValueError("catalog_name may only contain letters, numbers, and underscores.")
    if not (1 <= resource_lifetime <= 180):
        raise ValueError("resource_lifetime must be between 1 and 180 days.")

    payload = {
        "template_id": "standalone_catalog",
        "resource_name": catalog_name,
        "environment": environment,
        "cloud_provider": cloud_provider,
        "region": region,
        "variables": {
            "aws_region": region,
            "catalog_name": catalog_name,
            "resource_lifetime": str(resource_lifetime),
        },
        "intent": intent,
    }
    return _request("POST", "/api/deployments", payload)


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if "--refresh-cookies" in sys.argv:
        grab_cookies()
        sys.exit(0)

    print("Quotas:", json.dumps(get_quotas(), indent=2))
    print("Template:", json.dumps(get_template("standalone_catalog"), indent=2))
