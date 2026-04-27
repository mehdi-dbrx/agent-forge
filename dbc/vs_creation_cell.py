# Cell 7: Vector Search Index
import random

VS_INDEX_NAME = f"{CATALOG}.{SCHEMA}.pdf_chunks_index"
VS_TABLE_NAME = f"{CATALOG}.{SCHEMA}.pdf_chunks"

# --- Read PDFs from bundle (alongside this notebook) ---
from pypdf import PdfReader

pdf_dir = Path(LOCAL_DIR) / "data" / "pdf"
all_chunks = []

if pdf_dir.exists():
    for pdf_file in sorted(pdf_dir.glob("*.pdf")):
        reader = PdfReader(str(pdf_file))
        full_text = ""
        for page in reader.pages:
            full_text += page.extract_text() or ""

        chunk_size, overlap = 1000, 200
        source_name = pdf_file.name
        for i in range(0, len(full_text), chunk_size - overlap):
            chunk = full_text[i:i + chunk_size]
            if chunk.strip():
                all_chunks.append({
                    "content": chunk,
                    "source": source_name,
                    "chunk_id": f"{source_name}_{i}",
                })
        print(f"  [+] {source_name}: {len([c for c in all_chunks if c['source'] == source_name])} chunks")
else:
    print("[!] No data/pdf/ directory found alongside notebook")

print(f"[+] Total chunks: {len(all_chunks)}")

# --- Create Delta table ---
sql(f"DROP TABLE IF EXISTS {VS_TABLE_NAME}")
sql(f"""
    CREATE TABLE {VS_TABLE_NAME} (
        chunk_id STRING, content STRING, source STRING
    ) USING DELTA
    TBLPROPERTIES (delta.enableChangeDataFeed = true)
""")
print("[+] pdf_chunks table created")

# Insert chunks in batches
batch_size = 10
for i in range(0, len(all_chunks), batch_size):
    batch = all_chunks[i:i+batch_size]
    values = []
    for c in batch:
        esc_content = c["content"].replace("'", "''").replace("\\", "\\\\")
        esc_source = c["source"].replace("'", "''")
        esc_id = c["chunk_id"].replace("'", "''")
        values.append(f"('{esc_id}', '{esc_content}', '{esc_source}')")
    sql(f"INSERT INTO {VS_TABLE_NAME} VALUES {', '.join(values)}")
print(f"[+] Inserted {len(all_chunks)} chunks")

sql(f"GRANT SELECT ON TABLE {VS_TABLE_NAME} TO `account users`")

# --- Ensure VS endpoint exists ---
from databricks.sdk.service.vectorsearch import EndpointType

print(f"\n[*] Checking VS endpoint '{VS_ENDPOINT}'...")

endpoint_exists = False
try:
    ep = w.vector_search_endpoints.get_endpoint(VS_ENDPOINT)
    ep_status = getattr(ep, "endpoint_status", None)
    state = ""
    if ep_status:
        state = getattr(ep_status, "state", "")
        if hasattr(state, "value"):
            state = state.value
    print(f"[+] VS endpoint exists (state: {state})")
    endpoint_exists = True
except Exception:
    print(f"[*] VS endpoint not found — creating it now...")
    try:
        w.vector_search_endpoints.create_endpoint(
            name=VS_ENDPOINT,
            endpoint_type=EndpointType.STANDARD,
        )
        print(f"[+] VS endpoint creation started")
    except Exception as e:
        if "ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
            print(f"[+] VS endpoint already exists (race condition)")
            endpoint_exists = True
        else:
            raise

# --- Wait for endpoint to be ONLINE ---
wait_msgs = [
    "Brewing coffee while the endpoint spins up...",
    "Vector Search is warming up its neurons...",
    "Still provisioning — good things take time...",
    "The bits are being arranged very carefully...",
    "Endpoint is getting its ducks in a row...",
    "Patience, young padawan...",
    "Almost there... probably...",
    "VS endpoint is doing push-ups before going live...",
    "Somewhere, a GPU is working very hard for you...",
    "This is the cloud equivalent of watching paint dry...",
    "Fun fact: you could make a sandwich while waiting...",
    "The hamsters powering the endpoint are running fast...",
    "Provisioning... because instant gratification is overrated...",
    "Vector Search endpoint is putting on its cape...",
    "Loading awesomeness... please stand by...",
]

print()
print(f"[*] Waiting for VS endpoint to come ONLINE.")
print(f"    This typically takes 15-20 minutes. Grab a coffee!")
print()

elapsed = 0
vs_endpoint_online = False
for attempt in range(120):
    try:
        ep = w.vector_search_endpoints.get_endpoint(VS_ENDPOINT)
        ep_status = getattr(ep, "endpoint_status", None)
        state = ""
        if ep_status:
            state = getattr(ep_status, "state", "")
            if hasattr(state, "value"):
                state = state.value
        if state == "ONLINE":
            print(f"\n[+] VS endpoint ONLINE!")
            vs_endpoint_online = True
            break
    except Exception:
        state = "provisioning"

    # Poll: every 5 min for first 15 min, then every 1 min
    if elapsed < 900:
        interval = 300
    else:
        interval = 60

    mins_elapsed = elapsed // 60
    mins_remaining = max(0, 20 - mins_elapsed)
    msg = random.choice(wait_msgs)
    print(f"  [{mins_elapsed}min] {msg} (~{mins_remaining} min to go)")

    time.sleep(interval)
    elapsed += interval

if not vs_endpoint_online:
    print("[!] VS endpoint not ONLINE after 20 min — attempting index creation anyway")

# --- Create index ---
from databricks.vector_search.client import VectorSearchClient

vs_client = VectorSearchClient(
    workspace_url=host,
    personal_access_token=token,
    disable_notice=True,
)

try:
    vs_client.create_delta_sync_index(
        endpoint_name=VS_ENDPOINT,
        index_name=VS_INDEX_NAME,
        source_table_name=VS_TABLE_NAME,
        primary_key="chunk_id",
        pipeline_type="TRIGGERED",
        embedding_source_column="content",
        embedding_model_endpoint_name=VS_EMBEDDING_MODEL,
    )
    print("[+] VS index creation started")
except Exception as e:
    if "ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
        print("[+] VS index already exists")
    else:
        raise

# --- Wait for index to sync ---
print()
print("[*] Waiting for VS index to sync and become ready...")
print("    This typically takes 5-10 minutes.")
print()

idx = vs_client.get_index(index_name=VS_INDEX_NAME, endpoint_name=VS_ENDPOINT)
elapsed = 0
for attempt in range(120):
    desc = idx.describe()
    status_info = desc.get("status", {})
    ready = status_info.get("ready", False)
    row_count = status_info.get("indexed_row_count", "?")
    if ready:
        print(f"\n[+] VS index ONLINE ({row_count} rows indexed)")
        break

    mins_elapsed = elapsed // 60
    mins_remaining = max(0, 10 - mins_elapsed)
    msg = random.choice(wait_msgs)
    print(f"  [{mins_elapsed}min] {msg} (rows={row_count}, ~{mins_remaining} min to go)")

    time.sleep(60)
    elapsed += 60
else:
    print("[!] VS index not ready in 20 min — continuing anyway")

print(f"[+] VS_INDEX_NAME = {VS_INDEX_NAME}")
