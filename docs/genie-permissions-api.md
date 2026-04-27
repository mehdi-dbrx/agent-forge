
# Genie Space Permissions via API

`PATCH /api/2.0/preview/permissions/genie/{space_id}`

Use the `space_id` directly (from `genie.create_space()` or `GET /genie/spaces`).

## Grant API

```bash
curl -X PATCH \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "$HOST/api/2.0/preview/permissions/genie/$SPACE_ID" \
  -d '{"access_control_list": [{"group_name": "users", "permission_level": "CAN_RUN"}]}'
```

## Read

```bash
curl -X GET -H "Authorization: Bearer $TOKEN" \
  "$HOST/api/2.0/preview/permissions/genie/$SPACE_ID"
```

## SDK

```python
# No SDK method — use requests
import requests
requests.patch(
    f"{host}/api/2.0/preview/permissions/genie/{space_id}",
    headers={"Authorization": f"Bearer {token}"},
    json={"access_control_list": [
        {"group_name": "users", "permission_level": "CAN_RUN"}
    ]},
)
```

## Examples

```bash
# SP gets CAN_MANAGE
-d '{"access_control_list": [{"service_principal_name": "54668f03-...", "permission_level": "CAN_MANAGE"}]}'

# Specific user gets CAN_EDIT
-d '{"access_control_list": [{"user_name": "alice@company.com", "permission_level": "CAN_EDIT"}]}'

# Multiple grants in one call
-d '{"access_control_list": [
  {"group_name": "users", "permission_level": "CAN_RUN"},
  {"service_principal_name": "my-sp-id", "permission_level": "CAN_MANAGE"}
]}'
```

## Note

App SPs need at least `CAN_RUN` to query Genie via MCP. Granting to `users` group covers all SPs.
