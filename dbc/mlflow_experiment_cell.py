# Cell 5: Create MLflow Experiment
import mlflow

EXPERIMENT_NAME = "/Shared/agent-forge-experiment"

try:
    exp_id = mlflow.create_experiment(EXPERIMENT_NAME)
    print(f"[+] Experiment created: {EXPERIMENT_NAME} (id={exp_id})")
except mlflow.exceptions.MlflowException as e:
    if "RESOURCE_ALREADY_EXISTS" in str(e):
        exp = mlflow.get_experiment_by_name(EXPERIMENT_NAME)
        exp_id = exp.experiment_id
        print(f"[+] Experiment already exists: {EXPERIMENT_NAME} (id={exp_id})")
    else:
        raise

# Grant permissions
from databricks.sdk.service.iam import ObjectPermissions
try:
    w.permissions.set(
        request_object_type="experiments",
        request_object_id=exp_id,
        access_control_list=[
            {"group_name": "users", "all_permissions": [{"permission_level": "CAN_MANAGE"}]}
        ],
    )
    print("[+] Experiment permissions granted")
except Exception as e:
    print(f"[!] Could not set experiment permissions: {e}")
