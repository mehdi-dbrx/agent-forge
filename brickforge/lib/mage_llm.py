"""
Mage LLM client - auto-detects best FMAPI model and creates ChatDatabricks instance.

Own instance, separate from the deployed agent's AGENT_MODEL.
Uses workspace token from config, not env vars.
"""

import re
from databricks.sdk import WorkspaceClient
from databricks_langchain import ChatDatabricks


# Preference order: latest Claude Sonnet > any Claude > any FMAPI
_PREFERENCE = [
    (r"databricks-claude-sonnet-4", 100),   # Claude Sonnet 4.x (latest)
    (r"databricks-claude-sonnet", 90),       # Any Claude Sonnet
    (r"databricks-claude", 80),              # Any Claude
    (r"databricks-", 10),                    # Any FMAPI
]


def detect_fmapi_model(host: str, token: str | None = None) -> str | None:
    """List serving endpoints and pick best available FMAPI model.
    Returns endpoint name or None if nothing found."""
    try:
        kwargs = {"host": host}
        if token:
            kwargs["token"] = token
        w = WorkspaceClient(**kwargs)
        endpoints = list(w.serving_endpoints.list())
    except Exception:
        return None

    scored = []
    for ep in endpoints:
        name = ep.name or ""
        for pattern, score in _PREFERENCE:
            if re.match(pattern, name):
                # Prefer higher version numbers within same tier
                version_bonus = 0
                nums = re.findall(r"(\d+)-(\d+)$", name)
                if nums:
                    version_bonus = int(nums[0][0]) * 10 + int(nums[0][1])
                scored.append((score + version_bonus, name))
                break

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def create_mage_llm(host: str, token: str, model_name: str) -> ChatDatabricks:
    """Create a ChatDatabricks instance for Mage with the given model."""
    return ChatDatabricks(
        endpoint=model_name,
        extra_params={"host": host, "token": token},
    )
