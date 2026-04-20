# FE Vending Machine (FEVM) Client

Programmatic Python client for the [FE Vending Machine](https://vending-machine-main-2481552415672103.aws.databricksapps.com) — a Databricks internal tool for deploying pre-configured resources (workspaces, catalogs, etc.) on demand.

---

## How Auth Works

The app uses its own OAuth client (`client_id=00a0c111-9215-48a4-94cc-ab15abead39c`) tied to browser sessions — standard Databricks bearer tokens are rejected with 401. The client works around this by:

1. Opening a real Chromium browser via Playwright
2. Letting you log in once through the normal OAuth flow
3. Capturing and saving the `__Host-databricksapps` session cookie to `session_cookies.json`
4. Using that cookie on all subsequent programmatic API calls

The cookie lasts days to weeks. When it expires, re-run `grab_cookies()`.

---

## Setup

### 1. Install dependencies

```bash
uv add playwright
playwright install chromium
```

### 2. Grab your session cookie (one-time)

```bash
python -c "from fevm.client import grab_cookies; grab_cookies()"
```

A browser window will open. Log in with your Databricks account. The cookie is saved to `internal/fevm/session_cookies.json` automatically.

### 3. You're ready

```python
from internal.fevm.client import deploy_standalone_catalog, get_quotas
```

---

## API Reference

### `deploy_standalone_catalog`

Deploy a standalone Unity Catalog resource.

```python
result = deploy_standalone_catalog(
    catalog_name="my_catalog",       # letters, numbers, underscores only
    region="us-east-1",              # see allowed regions below
    resource_lifetime=90,            # days until auto-deletion (1–180)
    intent="Customer Demo/Testing",  # free-text description of use case
    environment="stable",            # "stable" or "sandbox"
    cloud_provider="aws",
)
```

**Allowed regions:** `us-east-1`, `us-east-2`, `us-west-1`, `us-west-2`, `eu-central-1`, `ap-northeast-1`

**Default user quota:** 2 concurrent deployments. Delete one before deploying if at limit.

**Returns:** deployment details dict from the API.

---

### `list_deployments`

List all your active deployments.

```python
deployments = list_deployments()
```

---

### `get_quotas`

Check your current quota usage across all template types.

```python
quotas = get_quotas()
# Returns per-template user quota and global limits
```

---

### `get_template`

Fetch the full configuration for a template, including variable defaults and constraints.

```python
template = get_template("standalone_catalog")
```

---

### `get_workspaces`

List available deployment workspaces for a given region and cloud.

```python
workspaces = get_workspaces(region="us-east-1", cloud_provider="aws")
```

---

### `grab_cookies`

Re-authenticate via browser and refresh the session cookie on disk.

```python
from internal.fevm.client import grab_cookies
grab_cookies()
```

Or from the command line:

```bash
python internal/fevm/client.py --refresh-cookies
```

---

## Files

| File | Description |
|---|---|
| `client.py` | API client — all functions live here |
| `session_cookies.json` | Browser session cookie (gitignored, refresh with `grab_cookies()`) |
| `doc/README.md` | This file |

> **Note:** `session_cookies.json` should never be committed to git — add it to `.gitignore`.

---

## Available Templates

Beyond `standalone_catalog`, the vending machine supports other templates you can pass to `get_template()`:

| Template ID | Description |
|---|---|
| `standalone_catalog` | Standalone Unity Catalog (AWS only) |
| `aws_sandbox_classic` | AWS sandbox classic workspace |
| `aws_sandbox_serverless` | AWS sandbox serverless workspace |
| `aws_stable_classic` | AWS stable classic workspace |
| `aws_stable_serverless` | AWS stable serverless workspace |
| `azure_sandbox_classic` | Azure sandbox classic workspace |
| `azure_stable_classic` | Azure stable classic workspace |
| `gcp_sandbox_classic` | GCP sandbox classic workspace |
| `gcp_sandbox_serverless` | GCP sandbox serverless workspace |
| `gcp_stable_classic` | GCP stable classic workspace |
| `gcp_stable_serverless` | GCP stable serverless workspace |
| `delta_sharing_catalog` | Delta Sharing catalog |
| `metastore_permission` | Metastore permissions |

---

## Example: Full Deploy Flow

```python
from internal.fevm.client import get_quotas, deploy_standalone_catalog

# Check quota first
quotas = get_quotas()
catalog_quota = next(
    t for t in quotas["templates"]
    if t["user_quota"]["template_id"] == "standalone_catalog"
)
print(f"Remaining slots: {catalog_quota['user_quota']['remaining']}")

# Deploy
if catalog_quota["can_deploy"]:
    result = deploy_standalone_catalog(
        catalog_name="engie_demo_catalog",
        region="eu-central-1",
        resource_lifetime=30,
        intent="Customer Demo/Testing",
    )
    print(result)
else:
    print("Quota full:", catalog_quota["blocking_reason"])
```
