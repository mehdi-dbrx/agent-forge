"""ConfigProvider - abstract base class + Local/Forge implementations.

v2: JSON-based config (config.json) replacing flat .env.local.
"""
from __future__ import annotations

import copy
import io
import json
import os
import re
import threading
import zipfile
from pathlib import Path
from typing import Any

import urllib.request

SENSITIVE_PATTERN = re.compile(r"TOKEN|SECRET|PASSWORD|PAT\b|API_KEY", re.IGNORECASE)

_config_lock = threading.Lock()

# ── Default empty config schema ─────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "workspace": {
        "host": None,
        "token": None,
        "config_profile": None,
        "refresh_token": None,
        "token_endpoint": None,
        "client_id": None,
        "client_secret": None,
        "warehouse_id": None,
        "unity_catalog_schema": None,
    },
    "model": {
        "endpoint": None,
        "token": None,
    },
    "app": {
        "name": None,
        "mlflow_experiment_id": None,
    },
    "tools": {
        "genie_spaces": [],
        "functions": [],
        "vector_search": {"index": None, "endpoint": None},
        "ka": {},
        "mcp": {},
        "api": {},
        "a2a": {},
    },
    "features": {
        "MEMORY": {"enabled": False},
        "CHART": {"enabled": True},
        "VOICE": {"enabled": False},
        "VISION": {"enabled": False},
        "PERSONAS": {"enabled": False},
    },
    "bricks": {
        "KA": {"enabled": False},
        "INFO_EXTRACTION": {"enabled": False},
        "DOC_PARSING": {"enabled": False},
        "TEXT_CLASSIFICATION": {"enabled": False},
    },
    "data": {
        "use_demo_data": True,
        "use_gen_data": False,
        "stash_dir": None,
    },
    "lakebase": {
        "instance_name": None,
        "agent_memory_schema": None,
    },
    "env_store": {
        "host": None,
        "token": None,
        "catalog_volume_path": None,
    },
    "genie_room": {
        "name": None,
        "description": None,
    },
    "branding": {
        "logo_url": None,
        "brandfetch_api_key": None,
    },
}

# ── Flatten: JSON -> flat env var dict ──────────────────────────────────────

# Scalar mappings: (json_path_tuple, env_var_name)
_SCALAR_MAP: list[tuple[tuple[str, ...], str]] = [
    (("workspace", "host"), "DATABRICKS_HOST"),
    (("workspace", "token"), "DATABRICKS_TOKEN"),
    (("workspace", "config_profile"), "DATABRICKS_CONFIG_PROFILE"),
    (("workspace", "refresh_token"), "DATABRICKS_REFRESH_TOKEN"),
    (("workspace", "token_endpoint"), "DATABRICKS_TOKEN_ENDPOINT"),
    (("workspace", "client_id"), "DATABRICKS_CLIENT_ID"),
    (("workspace", "client_secret"), "DATABRICKS_CLIENT_SECRET"),
    (("workspace", "warehouse_id"), "DATABRICKS_WAREHOUSE_ID"),
    (("workspace", "unity_catalog_schema"), "PROJECT_UNITY_CATALOG_SCHEMA"),
    (("model", "endpoint"), "AGENT_MODEL"),
    (("model", "token"), "AGENT_MODEL_TOKEN"),
    (("app", "name"), "DBX_APP_NAME"),
    (("app", "mlflow_experiment_id"), "MLFLOW_EXPERIMENT_ID"),
    (("tools", "vector_search", "index"), "PROJECT_VS_INDEX"),
    (("tools", "vector_search", "endpoint"), "PROJECT_VS_ENDPOINT"),
    (("data", "use_demo_data"), "USE_DEMO_DATA"),
    (("data", "use_gen_data"), "USE_GEN_DATA"),
    (("data", "stash_dir"), "FORGE_STASH_DIR"),
    (("lakebase", "instance_name"), "LAKEBASE_INSTANCE_NAME"),
    (("lakebase", "agent_memory_schema"), "LAKEBASE_AGENT_MEMORY_SCHEMA"),
    (("env_store", "host"), "ENV_STORE_HOST"),
    (("env_store", "token"), "ENV_STORE_TOKEN"),
    (("env_store", "catalog_volume_path"), "ENV_STORE_CATALOG_VOLUME_PATH"),
    (("genie_room", "name"), "GENIE_ROOM_NAME"),
    (("genie_room", "description"), "GENIE_DESCRIPTION"),
    (("branding", "logo_url"), "PROJECT_LOGO_URL"),
    (("branding", "brandfetch_api_key"), "BRANDFETCH_API_KEY"),
]

# Multi-instance tool sections: (json_section, env_prefix, field_suffix_pairs)
_MULTI_INSTANCE_DEFS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("ka", "PROJECT_KA_", [("endpoint", "")]),
    ("mcp", "PROJECT_MCP_", [("url", ""), ("header", "_HEADER")]),
    ("a2a", "PROJECT_A2A_", [("url", ""), ("header", "_HEADER")]),
    ("api", "PROJECT_API_", [
        ("conn", "_CONN"), ("url", "_URL"), ("method", "_METHOD"),
        ("path", "_PATH"), ("desc", "_DESC"), ("params", "_PARAMS"),
        ("header", "_HEADER"),
    ]),
]

# All known scalar env var keys (for clean env wipe on project switch)
_ALL_SCALAR_KEYS = {env_key for _, env_key in _SCALAR_MAP}
_MULTI_PREFIXES = {prefix for _, prefix, _ in _MULTI_INSTANCE_DEFS} | {"PROJECT_TOOL_", "PROJECT_BRICK_", "PROJECT_GENIE_SPACES", "PROJECT_FUNCTIONS"}

# Reverse mapper for instance CRUD: env prefix -> JSON section path
INSTANCE_PREFIX_MAP: dict[str, str] = {
    "PROJECT_KA_": "tools.ka",
    "PROJECT_MCP_": "tools.mcp",
    "PROJECT_API_": "tools.api",
    "PROJECT_A2A_": "tools.a2a",
}


def _deep_get(data: dict, path: tuple[str, ...]) -> Any:
    """Get a value from a nested dict by path tuple."""
    val = data
    for key in path:
        if not isinstance(val, dict):
            return None
        val = val.get(key)
    return val


def _deep_set(data: dict, path: tuple[str, ...], value: Any) -> None:
    """Set a value in a nested dict by path tuple, creating intermediates."""
    for key in path[:-1]:
        if key not in data or not isinstance(data[key], dict):
            data[key] = {}
        data = data[key]
    data[path[-1]] = value


def flatten(config: dict) -> dict[str, str]:
    """Convert structured config JSON to flat env var dict.

    Rules:
    - Null values are omitted
    - Booleans emit "true"/"false"
    - Arrays join with ","
    - Multi-instance entries with enabled=false are omitted
    - KA entries require BOTH bricks.KA.enabled AND entry.enabled
    """
    out: dict[str, str] = {}

    # Scalar mappings
    for path, env_key in _SCALAR_MAP:
        val = _deep_get(config, path)
        if val is None:
            continue
        if isinstance(val, bool):
            out[env_key] = str(val).lower()
        else:
            out[env_key] = str(val)

    # Array fields -> comma-joined
    for arr_field, env_key in [("genie_spaces", "PROJECT_GENIE_SPACES"), ("functions", "PROJECT_FUNCTIONS")]:
        arr = (config.get("tools") or {}).get(arr_field, [])
        if arr:
            out[env_key] = ",".join(str(x) for x in arr)

    # Multi-instance tools (ka, mcp, api, a2a)
    tools = config.get("tools") or {}
    bricks = config.get("bricks") or {}
    for section, prefix, fields in _MULTI_INSTANCE_DEFS:
        items = tools.get(section) or {}
        for slug, entry in items.items():
            if not isinstance(entry, dict):
                continue
            if not entry.get("enabled", True):
                continue
            # KA double-gate: check bricks.KA.enabled too
            if section == "ka" and not (bricks.get("KA") or {}).get("enabled", False):
                continue
            for field, suffix in fields:
                val = entry.get(field)
                if val is not None:
                    out[f"{prefix}{slug}{suffix}"] = str(val)

    # Feature toggles -> always emit
    for key, entry in (config.get("features") or {}).items():
        if isinstance(entry, dict):
            out[f"PROJECT_TOOL_{key}"] = str(entry.get("enabled", False)).lower()

    # Brick toggles -> always emit
    for key, entry in (config.get("bricks") or {}).items():
        if isinstance(entry, dict):
            out[f"PROJECT_BRICK_{key}"] = str(entry.get("enabled", False)).lower()

    return out


# ── Unflatten: flat env var dict -> JSON (for migration) ───────────────────

def env_local_to_config_json(env_file: str | Path) -> dict[str, Any]:
    """One-time migration: parse .env.local and build config.json structure."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    env_path = Path(env_file)
    if not env_path.exists():
        return config

    raw = env_path.read_text()
    active: dict[str, str] = {}
    disabled: dict[str, str] = {}

    for line in raw.split("\n"):
        trimmed = line.strip()
        if not trimmed:
            continue
        if trimmed.startswith("#"):
            content = re.sub(r"^#\s*", "", trimmed)
            eq = content.find("=")
            if eq >= 0:
                disabled[content[:eq].strip()] = content[eq + 1:]
            continue
        eq = trimmed.find("=")
        if eq < 0:
            continue
        key = trimmed[:eq].strip()
        active[key] = trimmed[eq + 1:]

    # Reverse scalar map: env_var -> json_path
    reverse_scalar: dict[str, tuple[str, ...]] = {env_key: path for path, env_key in _SCALAR_MAP}

    for key, val in active.items():
        # Check scalar mapping
        if key in reverse_scalar:
            path = reverse_scalar[key]
            # Convert boolean strings
            if val.lower() in ("true", "false"):
                _deep_set(config, path, val.lower() == "true")
            else:
                _deep_set(config, path, val)
            continue

        # Arrays
        if key == "PROJECT_GENIE_SPACES":
            config["tools"]["genie_spaces"] = [s.strip() for s in val.split(",") if s.strip()]
            continue
        if key == "PROJECT_FUNCTIONS":
            config["tools"]["functions"] = [s.strip() for s in val.split(",") if s.strip()]
            continue

        # Multi-instance prefix patterns
        matched = False
        for section, prefix, fields in _MULTI_INSTANCE_DEFS:
            if key.startswith(prefix):
                remainder = key[len(prefix):]
                # Check if it's a suffix field (e.g. WEATHER_HEADER)
                slug = remainder
                field_name = fields[0][0]  # default field (url, endpoint, etc.)
                for fname, fsuffix in fields:
                    if fsuffix and remainder.endswith(fsuffix):
                        slug = remainder[: -len(fsuffix)]
                        field_name = fname
                        break
                if slug not in config["tools"][section]:
                    config["tools"][section][slug] = {"enabled": True}
                config["tools"][section][slug][field_name] = val
                matched = True
                break
        if matched:
            continue

        # Feature toggles
        if key.startswith("PROJECT_TOOL_"):
            feat = key[len("PROJECT_TOOL_"):]
            if feat not in config["features"]:
                config["features"][feat] = {}
            config["features"][feat]["enabled"] = val.lower() not in ("false", "0", "")
            continue

        # Brick toggles
        if key.startswith("PROJECT_BRICK_"):
            brick = key[len("PROJECT_BRICK_"):]
            if brick not in config["bricks"]:
                config["bricks"][brick] = {}
            config["bricks"][brick]["enabled"] = val.lower() not in ("false", "0", "")
            continue

        # Legacy: AGENT_MODEL_ENDPOINT -> model.endpoint
        if key == "AGENT_MODEL_ENDPOINT":
            if not config["model"]["endpoint"]:
                config["model"]["endpoint"] = val
            continue

        # Legacy: USE_DEFAULT_DATA -> data.use_demo_data
        if key == "USE_DEFAULT_DATA":
            config["data"]["use_demo_data"] = val.lower() not in ("false", "0", "")
            continue

    # Process disabled entries -> mark as enabled=false for multi-instance
    for key, val in disabled.items():
        for section, prefix, fields in _MULTI_INSTANCE_DEFS:
            if key.startswith(prefix):
                remainder = key[len(prefix):]
                slug = remainder
                field_name = fields[0][0]
                for fname, fsuffix in fields:
                    if fsuffix and remainder.endswith(fsuffix):
                        slug = remainder[: -len(fsuffix)]
                        field_name = fname
                        break
                if slug not in config["tools"][section]:
                    config["tools"][section][slug] = {"enabled": False}
                else:
                    config["tools"][section][slug]["enabled"] = False
                config["tools"][section][slug][field_name] = val
                break

    return config


# ── ConfigProvider base class ───────────────────────────────────────────────

class ConfigProvider:
    """Abstract base class for JSON config operations."""

    _data: dict[str, Any]

    def get(self, path: str) -> Any:
        """Get a value by dot-separated path. e.g. 'workspace.host'"""
        keys = path.split(".")
        val = self._data
        for k in keys:
            if not isinstance(val, dict):
                return None
            val = val.get(k)
        return val

    def set(self, path: str, value: Any) -> None:
        """Set a value by dot-separated path. e.g. 'workspace.host'"""
        keys = tuple(path.split("."))
        with _config_lock:
            _deep_set(self._data, keys, value)
            self._sync_env()
            self._save()

    def get_section(self, path: str) -> Any:
        """Get a section (dict, list, or scalar) by dot path."""
        return self.get(path)

    def set_section(self, path: str, value: Any) -> None:
        """Set a section by dot path. Triggers save + env sync."""
        self.set(path, value)

    def flatten(self) -> dict[str, str]:
        """Flatten config to env var dict."""
        return flatten(self._data)

    def _sync_env(self) -> None:
        """Replace config-managed env vars. Clears ALL known config keys first."""
        # Clear all known config env vars (scalar keys + multi-instance prefixes)
        for key in list(os.environ.keys()):
            if key in _ALL_SCALAR_KEYS:
                del os.environ[key]
            elif any(key.startswith(p) for p in _MULTI_PREFIXES):
                del os.environ[key]
        # Set new values from current config
        flat = flatten(self._data)
        os.environ.update(flat)

    def _save(self) -> None:
        """Persist config to storage. Override in subclasses."""
        raise NotImplementedError

    @property
    def data(self) -> dict[str, Any]:
        """Direct access to the config dict (read-only intent)."""
        return self._data

    # ── Legacy-compatible API (used by routes until fully migrated) ──────

    def list(self) -> list[dict[str, Any]]:
        """Return flat list of {key, value, sensitive} for all config values."""
        flat = flatten(self._data)
        return [{"key": k, "value": v, "sensitive": bool(SENSITIVE_PATTERN.search(k))} for k, v in flat.items()]

    def to_env_dict(self) -> dict[str, str]:
        """Return flat dict of all config values."""
        return flatten(self._data)

    def set_many(self, updates: dict[str, str]) -> None:
        """Legacy: set multiple flat env vars. Maps to structured paths where possible."""
        reverse_scalar = {env_key: path for path, env_key in _SCALAR_MAP}
        with _config_lock:
            for key, val in updates.items():
                if key in reverse_scalar:
                    _deep_set(self._data, reverse_scalar[key], val)
                elif key == "PROJECT_GENIE_SPACES":
                    self._data.setdefault("tools", {})["genie_spaces"] = [s.strip() for s in val.split(",") if s.strip()]
                elif key == "PROJECT_FUNCTIONS":
                    self._data.setdefault("tools", {})["functions"] = [s.strip() for s in val.split(",") if s.strip()]
                else:
                    # Multi-instance or unknown: try prefix mapping
                    self._set_flat_key(key, val)
            self._sync_env()
            self._save()

    def _set_flat_key(self, key: str, val: str) -> None:
        """Map a flat env var key to its JSON location. For legacy set_many support."""
        # Feature toggles
        if key.startswith("PROJECT_TOOL_"):
            feat = key[len("PROJECT_TOOL_"):]
            self._data.setdefault("features", {}).setdefault(feat, {})["enabled"] = val.lower() not in ("false", "0", "")
            return
        # Brick toggles
        if key.startswith("PROJECT_BRICK_"):
            brick = key[len("PROJECT_BRICK_"):]
            self._data.setdefault("bricks", {}).setdefault(brick, {})["enabled"] = val.lower() not in ("false", "0", "")
            return
        # Multi-instance prefixes
        for section, prefix, fields in _MULTI_INSTANCE_DEFS:
            if key.startswith(prefix):
                remainder = key[len(prefix):]
                slug = remainder
                field_name = fields[0][0]
                for fname, fsuffix in fields:
                    if fsuffix and remainder.endswith(fsuffix):
                        slug = remainder[: -len(fsuffix)]
                        field_name = fname
                        break
                tools = self._data.setdefault("tools", {})
                section_data = tools.setdefault(section, {})
                entry = section_data.setdefault(slug, {"enabled": True})
                entry[field_name] = val
                return

    def disable(self, key: str) -> None:
        """Legacy: disable a key (set to null for scalars, enabled=false for instances)."""
        self.disable_many([key])

    def disable_many(self, keys: list[str]) -> None:
        """Legacy: disable keys."""
        reverse_scalar = {env_key: path for path, env_key in _SCALAR_MAP}
        with _config_lock:
            for key in keys:
                if key in reverse_scalar:
                    _deep_set(self._data, reverse_scalar[key], None)
                else:
                    # Multi-instance: set enabled=false
                    for section, prefix, _ in _MULTI_INSTANCE_DEFS:
                        if key.startswith(prefix):
                            slug = key[len(prefix):]
                            tools = self._data.setdefault("tools", {})
                            entry = tools.setdefault(section, {}).get(slug)
                            if isinstance(entry, dict):
                                entry["enabled"] = False
                            break
            self._sync_env()
            self._save()

    def toggle(self, key: str) -> bool:
        """Legacy: toggle a key's enabled state."""
        # Multi-instance prefixes
        for section, prefix, _ in _MULTI_INSTANCE_DEFS:
            if key.startswith(prefix):
                slug = key[len(prefix):]
                entry = (self._data.get("tools") or {}).get(section, {}).get(slug)
                if isinstance(entry, dict):
                    with _config_lock:
                        entry["enabled"] = not entry.get("enabled", True)
                        self._sync_env()
                        self._save()
                    return True
                return False
        # Feature toggles
        if key.startswith("PROJECT_TOOL_"):
            feat = key[len("PROJECT_TOOL_"):]
            entry = (self._data.get("features") or {}).get(feat)
            if isinstance(entry, dict):
                with _config_lock:
                    entry["enabled"] = not entry.get("enabled", False)
                    self._sync_env()
                    self._save()
                return True
            return False
        # Brick toggles
        if key.startswith("PROJECT_BRICK_"):
            brick = key[len("PROJECT_BRICK_"):]
            entry = (self._data.get("bricks") or {}).get(brick)
            if isinstance(entry, dict):
                with _config_lock:
                    entry["enabled"] = not entry.get("enabled", False)
                    self._sync_env()
                    self._save()
                return True
            return False
        return False

    def list_by_prefix(self, prefix: str) -> list[dict[str, Any]]:
        """Legacy: list instances by env var prefix."""
        results: list[dict[str, Any]] = []

        # Features: PROJECT_TOOL_*
        if prefix == "PROJECT_TOOL_":
            for key, entry in (self._data.get("features") or {}).items():
                if isinstance(entry, dict):
                    results.append({
                        "key": f"PROJECT_TOOL_{key}",
                        "value": str(entry.get("enabled", False)).lower(),
                        "enabled": entry.get("enabled", False),
                        "label": key.lower().replace("_", " "),
                    })
            return results

        # Bricks: PROJECT_BRICK_*
        if prefix == "PROJECT_BRICK_":
            for key, entry in (self._data.get("bricks") or {}).items():
                if isinstance(entry, dict):
                    results.append({
                        "key": f"PROJECT_BRICK_{key}",
                        "value": str(entry.get("enabled", False)).lower(),
                        "enabled": entry.get("enabled", False),
                        "label": key.lower().replace("_", " "),
                    })
            return results

        # Multi-instance tools (ka, mcp, api, a2a)
        for section, pfx, fields in _MULTI_INSTANCE_DEFS:
            if pfx == prefix:
                items = (self._data.get("tools") or {}).get(section, {})
                for slug, entry in items.items():
                    if not isinstance(entry, dict):
                        continue
                    enabled = entry.get("enabled", True)
                    # For API: emit each field as a separate instance (matches old prefix-scan behavior)
                    if section == "api":
                        for fname, fsuffix in fields:
                            v = entry.get(fname)
                            if v:
                                results.append({
                                    "key": f"{prefix}{slug}{fsuffix}",
                                    "value": v,
                                    "enabled": enabled,
                                    "label": slug.lower().replace("_", " "),
                                })
                    else:
                        # Use first non-null field as display value
                        val = ""
                        for fname, _ in fields:
                            v = entry.get(fname)
                            if v:
                                val = v
                                break
                        results.append({
                            "key": f"{prefix}{slug}",
                            "value": val,
                            "enabled": enabled,
                            "label": slug.lower().replace("_", " "),
                        })
                return results

        # Scalar prefix scan (VS, etc.) -- scan flattened output
        flat = flatten(self._data)
        for key, val in flat.items():
            if key.startswith(prefix):
                slug = key[len(prefix):]
                results.append({
                    "key": key,
                    "value": val,
                    "enabled": True,
                    "label": slug.lower().replace("_", " "),
                })
        return results

    def delete_key(self, key: str) -> None:
        """Legacy: delete a key entirely."""
        # Multi-instance prefixes
        for section, prefix, _ in _MULTI_INSTANCE_DEFS:
            if key.startswith(prefix):
                slug = key[len(prefix):]
                tools = self._data.get("tools", {})
                section_data = tools.get(section, {})
                if slug in section_data:
                    with _config_lock:
                        del section_data[slug]
                        self._sync_env()
                        self._save()
                return
        # Array fields: PROJECT_GENIE_SPACES[N], PROJECT_FUNCTIONS[N]
        import re as _re
        arr_match = _re.match(r"(PROJECT_GENIE_SPACES|PROJECT_FUNCTIONS)\[(\d+)\]", key)
        if arr_match:
            arr_key, idx_str = arr_match.group(1), int(arr_match.group(2))
            arr_field = "genie_spaces" if arr_key == "PROJECT_GENIE_SPACES" else "functions"
            arr = self._data.get("tools", {}).get(arr_field, [])
            if 0 <= idx_str < len(arr):
                with _config_lock:
                    arr.pop(idx_str)
                    self._sync_env()
                    self._save()
            return

        # Scalar: set to null
        reverse_scalar = {env_key: path for path, env_key in _SCALAR_MAP}
        if key in reverse_scalar:
            with _config_lock:
                _deep_set(self._data, reverse_scalar[key], None)
                self._sync_env()
                self._save()


# ── LocalConfigProvider (file-based) ────────────────────────────────────────

class LocalConfigProvider(ConfigProvider):
    """Reads/writes config from a config.json file."""

    def __init__(self, config_file: str | Path):
        self._config_file = Path(config_file)
        self._project_file: Path | None = None  # auto-save mirror for active project
        self._data = self._load()

    @property
    def project_dir(self) -> Path | None:
        """Artifact directory for the active project (projects/{name}/)."""
        if self._project_file:
            return self._project_file.parent / self._project_file.stem
        return None

    def _load(self) -> dict[str, Any]:
        """Load config.json, falling back to default schema if missing."""
        if self._config_file.exists():
            try:
                raw = self._config_file.read_text()
                data = json.loads(raw)
                # Merge with defaults to fill any missing keys
                return _merge_defaults(data, DEFAULT_CONFIG)
            except (json.JSONDecodeError, ValueError):
                return copy.deepcopy(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)

    # Keys to strip from disk (secrets that should never be persisted as plaintext)
    _STRIP_ON_SAVE = [("workspace", "token"), ("model", "token")]

    def _save(self) -> None:
        """Write config.json to disk + mirror to active project file.
        Strips secrets (tokens) from the written data -- they stay in _data (memory) only."""
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        data_copy = copy.deepcopy(self._data)
        for section, key in self._STRIP_ON_SAVE:
            if section in data_copy and key in data_copy[section]:
                data_copy[section][key] = None
        payload = json.dumps(data_copy, indent=2) + "\n"
        self._config_file.write_text(payload)
        if self._project_file and self._project_file.exists():
            self._project_file.write_text(payload)


# ── ForgeConfigProvider (in-memory + UC Volume zip) ─────────────────────────

class ForgeConfigProvider(ConfigProvider):
    """In-memory JSON config, flushed to UC Volume as zip. Used in SaaS/DBX App mode."""

    def __init__(self):
        self._data = copy.deepcopy(DEFAULT_CONFIG)
        self._zip_buffer: bytes = b""
        self._volume_path: str | None = None
        self._host: str = os.environ.get("DATABRICKS_HOST", "")
        self._token: str = os.environ.get("DATABRICKS_TOKEN", "")
        self._dirty: bool = False

    async def init(self) -> None:
        schema = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "")
        if schema and "." in schema:
            self._init_volume_path(schema)
            await self._download()

    def _init_volume_path(self, schema: str) -> None:
        catalog, schema_name = schema.split(".", 1)
        self._volume_path = f"/Volumes/{catalog}/{schema_name}/brickforge/stash/current.forge.zip"

    async def _download(self) -> None:
        if not self._volume_path or not self._host:
            return
        try:
            url = f"{self._host.rstrip('/')}/api/2.0/fs/files{self._volume_path}"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self._token}"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                self._zip_buffer = resp.read()
            with zipfile.ZipFile(io.BytesIO(self._zip_buffer)) as zf:
                if "config.json" in zf.namelist():
                    raw = zf.read("config.json").decode("utf-8")
                    data = json.loads(raw)
                    self._data = _merge_defaults(data, DEFAULT_CONFIG)
                elif "config.env" in zf.namelist():
                    # Legacy migration: read old config.env format
                    self._migrate_from_config_env(zf.read("config.env").decode("utf-8"))
        except Exception:
            pass  # first run, no zip yet

    def _migrate_from_config_env(self, raw: str) -> None:
        """One-time migration from legacy config.env format in zip."""
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(raw)
            tmp_path = f.name
        try:
            self._data = env_local_to_config_json(tmp_path)
        finally:
            os.unlink(tmp_path)
        self._dirty = True

    def _save(self) -> None:
        """Flush config to UC Volume as zip."""
        self._dirty = True
        self._flush()

    def _flush(self) -> None:
        if not self._dirty:
            return
        # Build zip in memory
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("config.json", json.dumps(self._data, indent=2) + "\n")
            # Copy non-config files from old zip
            if self._zip_buffer:
                try:
                    with zipfile.ZipFile(io.BytesIO(self._zip_buffer)) as old_zf:
                        for name in old_zf.namelist():
                            if name not in ("config.json", "config.env"):
                                zf.writestr(name, old_zf.read(name))
                except Exception:
                    pass
        self._zip_buffer = buf.getvalue()

        if not self._volume_path:
            schema = (self._data.get("workspace") or {}).get("unity_catalog_schema", "")
            if schema and "." in schema:
                self._init_volume_path(schema)
            else:
                self._dirty = False
                return

        try:
            url = f"{self._host.rstrip('/')}/api/2.0/fs/files{self._volume_path}"
            req = urllib.request.Request(url, data=self._zip_buffer, method="PUT", headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/octet-stream",
            })
            urllib.request.urlopen(req, timeout=10)
            self._dirty = False
        except Exception as e:
            print(f"[forge] flush failed: {e}")

    # File management (non-config files in zip)

    def get_file(self, path: str) -> str | None:
        if not self._zip_buffer:
            return None
        try:
            with zipfile.ZipFile(io.BytesIO(self._zip_buffer)) as zf:
                return zf.read(path).decode("utf-8") if path in zf.namelist() else None
        except Exception:
            return None

    def set_file(self, path: str, content: str) -> None:
        with _config_lock:
            self._dirty = True
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("config.json", json.dumps(self._data, indent=2) + "\n")
                zf.writestr(path, content)
                if self._zip_buffer:
                    try:
                        with zipfile.ZipFile(io.BytesIO(self._zip_buffer)) as old_zf:
                            for name in old_zf.namelist():
                                if name not in ("config.json", "config.env", path):
                                    zf.writestr(name, old_zf.read(name))
                    except Exception:
                        pass
            self._zip_buffer = buf.getvalue()
            self._flush()

    def delete_file(self, path: str) -> None:
        if not self._zip_buffer:
            return
        with _config_lock:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                try:
                    with zipfile.ZipFile(io.BytesIO(self._zip_buffer)) as old_zf:
                        for name in old_zf.namelist():
                            if name != path:
                                zf.writestr(name, old_zf.read(name))
                except Exception:
                    pass
            self._zip_buffer = buf.getvalue()
            self._dirty = True
            self._flush()

    def list_files(self) -> list[str]:
        if not self._zip_buffer:
            return []
        try:
            with zipfile.ZipFile(io.BytesIO(self._zip_buffer)) as zf:
                return [n for n in zf.namelist() if n not in ("config.json", "config.env")]
        except Exception:
            return []


# ── Helpers ─────────────────────────────────────────────────────────────────

def _merge_defaults(data: dict, defaults: dict) -> dict:
    """Deep merge: fill missing keys from defaults without overwriting existing values."""
    result = copy.deepcopy(defaults)
    _deep_merge(result, data)
    return result


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base (modifies base in place)."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
