"""Shared SQL utilities. Substitutes __SCHEMA_QUALIFIED__ and __VOLUME_PATH__ from PROJECT_UNITY_CATALOG_SCHEMA."""
import os


def _schema_to_qualified(spec: str) -> str:
    """Convert catalog.schema to `catalog`.`schema`."""
    if not spec or "." not in spec:
        return ""
    catalog, schema = spec.strip().split(".", 1)
    return f"`{catalog}`.`{schema}`"


def get_schema_qualified() -> str:
    """Return SQL-qualified schema from PROJECT_UNITY_CATALOG_SCHEMA."""
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    return _schema_to_qualified(spec)


def substitute_schema(content: str) -> str:
    """Replace placeholders with values from PROJECT_UNITY_CATALOG_SCHEMA."""
    spec = os.environ.get("PROJECT_UNITY_CATALOG_SCHEMA", "").strip()
    if "." not in spec:
        return content
    catalog, schema = spec.split(".", 1)
    schema_qualified = f"`{catalog}`.`{schema}`"
    volume_path = f"/Volumes/{catalog}/{schema}"
    return (
        content.replace("__SCHEMA_QUALIFIED__", schema_qualified)
        .replace("__VOLUME_PATH__", volume_path)
    )
