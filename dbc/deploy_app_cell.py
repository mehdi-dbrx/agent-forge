# Cell 8: Deploy Databricks App
import random

wait_msgs = [
    "Brewing coffee while the app spins up...",
    "The app is warming up its neurons...",
    "Still provisioning -- good things take time...",
    "The bits are being arranged very carefully...",
    "App is getting its ducks in a row...",
    "Patience, young padawan...",
    "Almost there... probably...",
    "The app is doing push-ups before going live...",
    "Somewhere, a container is working very hard for you...",
    "This is the cloud equivalent of watching paint dry...",
    "Fun fact: you could make a sandwich while waiting...",
    "The hamsters powering the app are running fast...",
    "Provisioning... because instant gratification is overrated...",
    "Your app is putting on its cape...",
    "Loading awesomeness... please stand by...",
]

# --- Generate app.yaml ---
print("[*] Generating app.yaml...")

app_yaml_content = f"""command: ["uv", "run", "python", "-c", "from agent.start_server import main; main()"]
env:
  - name: MLFLOW_TRACKING_URI
    value: "databricks"
  - name: MLFLOW_REGISTRY_URI
    value: "databricks-uc"
  - name: API_PROXY
    value: "http://localhost:8000/invocations"
  - name: CHAT_APP_PORT
    value: "3000"
  - name: TASK_EVENTS_URL
    value: "http://127.0.0.1:3000"
  - name: CHAT_PROXY_TIMEOUT_SECONDS
    value: "300"
  - name: AGENT_MODEL_ENDPOINT
    value: "databricks-claude-sonnet-4-6"
  - name: PROJECT_UNITY_CATALOG_SCHEMA
    value: "{CATALOG}.{SCHEMA}"
  - name: DATABRICKS_WAREHOUSE_ID
    value: "{WAREHOUSE_ID}"
  - name: PROJECT_GENIE_CHECKIN
    value: "{GENIE_SPACE_ID or ''}"
  - name: PROJECT_VS_INDEX
    value: "{VS_INDEX_NAME}"
  - name: PROJECT_VS_ENDPOINT
    value: "{VS_ENDPOINT}"
"""

upload_file(f"{WORKSPACE_PATH}/app.yaml", app_yaml_content.encode("utf-8"))
print("[+] app.yaml uploaded to workspace")

# --- Create app ---
from databricks.sdk.service.apps import App, AppDeployment

print(f"\n[*] Creating app '{APP_NAME}'...")

app_exists = False
app_ready = False
try:
    existing = w.apps.get(APP_NAME)
    compute = getattr(existing, "compute_status", None)
    c_state = getattr(compute, "state", "") if compute else ""
    if hasattr(c_state, "value"):
        c_state = c_state.value
    print(f"[+] App already exists: {APP_NAME}")
    print(f"    Compute: {c_state}")
    print(f"    URL: {getattr(existing, 'url', 'unknown')}")
    app_exists = True
    if c_state == "ACTIVE":
        print(f"[+] Compute already ACTIVE -- skipping wait")
        app_ready = True
except Exception:
    print(f"[*] App not found -- creating it now...")
    try:
        create_resp = w.apps.create(
            app=App(name=APP_NAME, description="Agent Forge - AI Ops Advisor for flight operations"),
        )
        print(f"[+] App creation initiated")
    except Exception as e:
        if "ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
            print(f"[+] App already exists (race condition)")
            app_exists = True
        else:
            raise

# --- Wait for app compute to be ACTIVE ---
if not app_ready:
    print(f"\n[*] Waiting for app compute to be ACTIVE...")
    print(f"    This typically takes 2-5 minutes.")
    print()

elapsed = 0
for attempt in range(30):
    if app_ready:
        break
    try:
        app_info = w.apps.get(APP_NAME)
        compute = getattr(app_info, "compute_status", None)
        compute_state = ""
        if compute:
            compute_state = getattr(compute, "state", "")
            if hasattr(compute_state, "value"):
                compute_state = compute_state.value
        compute_msg = getattr(compute, "message", "") if compute else ""

        if compute_state == "ACTIVE":
            print(f"\n[+] App compute is ACTIVE!")
            app_ready = True
            break
        elif compute_state in ("ERROR", "FAILED"):
            print(f"\n[!] App compute failed: {compute_state} - {compute_msg}")
            break

        mins_elapsed = elapsed // 60
        mins_remaining = max(0, 5 - mins_elapsed)
        msg = random.choice(wait_msgs)
        print(f"  [{mins_elapsed}min] compute={compute_state} | {msg} (~{mins_remaining} min to go)")

    except Exception as ex:
        mins_elapsed = elapsed // 60
        print(f"  [{mins_elapsed}min] checking... ({ex})")

    time.sleep(60)
    elapsed += 60

if not app_ready and not app_exists:
    print("[!] App compute not active after 5 min -- attempting deployment anyway")

# --- Wait for any pending deployment to clear ---
print(f"\n[*] Checking for pending deployments...")
for wait_attempt in range(20):
    app_info = w.apps.get(APP_NAME)
    pending_dep = getattr(app_info, "pending_deployment", None)
    if not pending_dep:
        print("[+] No pending deployment -- ready to deploy")
        break
    pend_st = getattr(pending_dep, "status", None)
    pend_state = ""
    if pend_st:
        pend_state = getattr(pend_st, "state", "")
        if hasattr(pend_state, "value"):
            pend_state = pend_state.value
    mins = wait_attempt
    msg = random.choice(wait_msgs)
    print(f"  [{mins}min] Pending deployment ({pend_state}) | {msg}")
    time.sleep(60)
else:
    print("[!] Pending deployment still active after 20 min -- attempting deploy anyway")

# --- Deploy (with retry) ---
print(f"\n[*] Deploying app from {WORKSPACE_PATH}...")
print(f"    This typically takes 5-10 minutes.")
print()

deployment_id = None
for deploy_try in range(3):
    try:
        deploy_resp = w.apps.deploy(
            app_name=APP_NAME,
            app_deployment=AppDeployment(source_code_path=WORKSPACE_PATH),
        )
        deployment_id = getattr(deploy_resp, "deployment_id", None)
        print(f"[+] Deployment initiated (id: {deployment_id})")
        break
    except Exception as e:
        err = str(e)
        if "pending deployment" in err.lower():
            print(f"  [retry {deploy_try+1}/3] Pending deployment still active, waiting 2 min...")
            time.sleep(120)
        else:
            print(f"[!] Deploy call failed: {e}")
            print("    You can deploy manually from the Apps UI")
            break

# --- Poll deployment status ---
# Key: don't react to CRASHED/RUNNING until our deployment is the active one.
# While our deployment is still pending, just keep polling.
elapsed = 0
deploy_done = False
for attempt in range(30):
    try:
        app_info = w.apps.get(APP_NAME)

        # app_status
        app_st = getattr(app_info, "app_status", None)
        app_state = ""
        app_msg = ""
        if app_st:
            app_state = getattr(app_st, "state", "")
            if hasattr(app_state, "value"):
                app_state = app_state.value
            app_msg = getattr(app_st, "message", "")

        # active_deployment
        active_dep = getattr(app_info, "active_deployment", None)
        active_dep_id = ""
        dep_status = ""
        if active_dep:
            active_dep_id = getattr(active_dep, "deployment_id", "")
            dep_st = getattr(active_dep, "status", None)
            if dep_st:
                dep_status = getattr(dep_st, "state", "")
                if hasattr(dep_status, "value"):
                    dep_status = dep_status.value

        # pending_deployment
        pending_dep = getattr(app_info, "pending_deployment", None)
        pend_status = ""
        pend_dep_id = ""
        if pending_dep:
            pend_dep_id = getattr(pending_dep, "deployment_id", "")
            pend_st = getattr(pending_dep, "status", None)
            if pend_st:
                pend_status = getattr(pend_st, "state", "")
                if hasattr(pend_status, "value"):
                    pend_status = pend_status.value

        # Is our deployment still pending? If so, keep waiting regardless of app_state
        our_deploy_is_pending = deployment_id and pend_dep_id and str(pend_dep_id) == str(deployment_id)
        our_deploy_is_active = deployment_id and active_dep_id and str(active_dep_id) == str(deployment_id)

        if our_deploy_is_pending:
            # Our deploy hasn't landed yet -- keep polling
            mins_elapsed = elapsed // 60
            mins_remaining = max(0, 10 - mins_elapsed)
            msg = random.choice(wait_msgs)
            print(f"  [{mins_elapsed}min] deploying ({pend_status}) | {msg} (~{mins_remaining} min to go)")
            time.sleep(60)
            elapsed += 60
            continue

        # Our deployment is now active (or we can't track it) -- check result
        if app_state == "RUNNING":
            app_url = getattr(app_info, "url", "") or f"{host}/apps/{APP_NAME}"
            print(f"\n[+] App deployed and RUNNING!")
            print(f"    Deployment: {dep_status}")
            print(f"    URL: {app_url}")
            deploy_done = True
            break

        if app_state == "CRASHED" and (our_deploy_is_active or not deployment_id):
            print(f"\n[!] App CRASHED after deployment!")
            print(f"    Message: {app_msg}")
            print(f"    Deployment status: {dep_status}")
            print("    Check app logs in the Apps UI for details")
            deploy_done = True
            break

        if "FAILED" in str(dep_status).upper() or "FAILED" in str(pend_status).upper():
            print(f"\n[!] Deployment FAILED!")
            print(f"    App status: {app_state} - {app_msg}")
            print(f"    Deployment: {dep_status or pend_status}")
            print("    Check the Apps UI for details")
            deploy_done = True
            break

        mins_elapsed = elapsed // 60
        mins_remaining = max(0, 10 - mins_elapsed)
        msg = random.choice(wait_msgs)
        detail = f"app={app_state}"
        if pend_status:
            detail += f", deploy={pend_status}"
        elif dep_status:
            detail += f", deploy={dep_status}"
        print(f"  [{mins_elapsed}min] {detail} | {msg} (~{mins_remaining} min to go)")

    except Exception as ex:
        mins_elapsed = elapsed // 60
        print(f"  [{mins_elapsed}min] checking... ({ex})")

    time.sleep(60)
    elapsed += 60

if not deploy_done:
    app_url = f"{host}/apps/{APP_NAME}"
    print(f"\n[!] Deployment not confirmed after 10 min")
    print(f"    Check manually: {app_url}")

print(f"\n[+] APP_NAME = {APP_NAME}")
