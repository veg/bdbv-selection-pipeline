import os
import time
import urllib.request
import json
import getpass
from bioblend.galaxy import GalaxyInstance

# Configuration
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
ASSEMBLIES_DIR = os.path.join(WORKSPACE, "assemblies")
REF_CDS_FILE = os.path.join(WORKSPACE, "ref_cds.fasta")
WF_URL = "https://raw.githubusercontent.com/galaxyproject/iwc/main/workflows/comparative_genomics/hyphy/capheine-core-and-compare.ga"
CACHE_FILE = os.path.join(WORKSPACE, "galaxy_cache.json")
CONFIG_FILE = os.path.join(WORKSPACE, "pipeline_config.json")

# Load configuration
if not os.path.exists(CONFIG_FILE):
    print(f"Error: Configuration file not found at {CONFIG_FILE}. Please run 'download_data.py' first.")
    exit(1)

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

# Step UUIDs from workflow GA file
REF_CDS_UUID = "b2b2453a-80ab-4318-ab5f-36a07827a6e8"
ASSEMBLIES_UUID = "bc274029-0e45-4df0-866f-b7c3aef39f81"
FOREGROUND_REGEX_UUID = "0f08a268-d600-4e5e-8eab-1297a8f164bc"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not read cache file: {e}")
    return {}

def save_cache(cache_data):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not write cache file: {e}")

def main():
    print("==================================================")
    print("Galaxy BioBlend CAPHEINE Pipeline Automator (Resume-enabled)")
    print("==================================================")
    
    # Load Cache
    cache = load_cache()
    
    # 1. Establish Galaxy Connection
    galaxy_url = input("Galaxy Instance URL [default: https://usegalaxy.org]: ").strip()
    if not galaxy_url:
        galaxy_url = "https://usegalaxy.org"
        
    api_key = os.environ.get("GALAXY_API_KEY", "").strip()
    if not api_key:
        api_key = getpass.getpass("Enter your Galaxy API Key: ").strip()
        
    if not api_key:
        print("Error: API Key is required.")
        return
        
    try:
        print(f"\nConnecting to Galaxy instance at {galaxy_url}...")
        gi = GalaxyInstance(url=galaxy_url, key=api_key)
        version_info = gi.config.get_version()
        print(f"Successfully connected! Galaxy Version: {version_info.get('version_major')}.{version_info.get('version_minor')}")
    except Exception as e:
        print(f"Connection error: {e}")
        return

    # 2. Retrieve or Create History
    history_name = config.get("galaxy_history_name", "Viral CAPHEINE Selection Analysis")
    history_id = cache.get("history_id")
    
    # Verify cached history exists
    if history_id:
        try:
            gi.histories.show_history(history_id)
            print(f"Using cached History ID: {history_id}")
        except Exception:
            print("Cached History ID is invalid or deleted. Searching server...")
            history_id = None
            
    # Search by name on server if not resolved
    if not history_id:
        try:
            existing_histories = gi.histories.get_histories(name=history_name)
            if existing_histories:
                history_id = existing_histories[0]["id"]
                print(f"Found existing history on server: '{history_name}' (ID: {history_id})")
            else:
                print(f"Creating new history: '{history_name}'...")
                new_hist = gi.histories.create_history(name=history_name)
                history_id = new_hist["id"]
                print(f"Created History ID: {history_id}")
        except Exception as e:
            print(f"Error resolving history: {e}")
            return
            
    cache["history_id"] = history_id
    save_cache(cache)

    # 3. Retrieve History contents to check what datasets already exist (mapped by ID and Name)
    print("Retrieving history contents...")
    server_ids = {}        # dataset_id -> state
    server_names = {}      # name -> dataset_id
    server_collections = {} # name -> collection_id
    try:
        contents = gi.histories.show_history(history_id, contents=True)
        for item in contents:
            c_type = item.get("history_content_type")
            name = item.get("name")
            item_id = item.get("id")
            if c_type == "dataset":
                state = item.get("state", "unknown")
                server_ids[item_id] = state
                server_names[name] = item_id
            elif c_type == "dataset_collection":
                server_collections[name] = item_id
    except Exception as e:
        print(f"Warning: Could not fetch history contents: {e}")
        
    # 4. Upload Reference CDS
    if not os.path.exists(REF_CDS_FILE):
        print(f"Error: Reference CDS file not found at {REF_CDS_FILE}. Please run 'download_data.py' first.")
        return
        
    ref_name = os.path.basename(REF_CDS_FILE)
    ref_dataset_id = cache.get("ref_dataset_id")
    
    # Validate cached ref dataset id by checking its existence in server_ids
    if ref_dataset_id:
        if ref_dataset_id in server_ids:
            print(f"Using cached Reference CDS (ID: {ref_dataset_id}, State: {server_ids[ref_dataset_id]})")
        else:
            ref_dataset_id = None
            
    # Check server by name if not cached
    if not ref_dataset_id:
        if ref_name in server_names:
            ref_dataset_id = server_names[ref_name]
            print(f"Found Reference CDS on server by filename (ID: {ref_dataset_id}, State: {server_ids[ref_dataset_id]})")
        elif os.path.splitext(ref_name)[0] in server_names:
            ref_dataset_id = server_names[os.path.splitext(ref_name)[0]]
            print(f"Found Reference CDS on server by stem name (ID: {ref_dataset_id}, State: {server_ids[ref_dataset_id]})")
        
    # Upload if still unresolved
    if not ref_dataset_id:
        print(f"Uploading Reference CDS: {ref_name}...")
        try:
            ref_upload = gi.tools.upload_file(REF_CDS_FILE, history_id)
            ref_dataset_id = ref_upload["outputs"][0]["id"]
            print(f"Uploaded Reference CDS ID: {ref_dataset_id}")
        except Exception as e:
            print(f"Error uploading Reference CDS: {e}")
            return
            
    cache["ref_dataset_id"] = ref_dataset_id
    save_cache(cache)

    # 5. Upload Assemblies
    if not os.path.exists(ASSEMBLIES_DIR) or not os.listdir(ASSEMBLIES_DIR):
        print(f"Error: Assemblies directory {ASSEMBLIES_DIR} is empty. Please run 'download_data.py' first.")
        return
        
    uploaded_datasets = cache.get("uploaded_datasets", {})
    
    # Filter out cached datasets that are no longer valid on the server
    validated_uploaded = {}
    for name, ds_id in uploaded_datasets.items():
        if ds_id in server_ids:
            validated_uploaded[name] = ds_id
            
    uploaded_datasets = validated_uploaded
    print("\nChecking assemblies status...")
    
    for filename in sorted(os.listdir(ASSEMBLIES_DIR)):
        if filename.endswith(".fasta") or filename.endswith(".fa"):
            filepath = os.path.join(ASSEMBLIES_DIR, filename)
            name = os.path.splitext(filename)[0]
            
            # Check cache
            if name in uploaded_datasets:
                print(f"  {filename} in cache (ID: {uploaded_datasets[name]})")
                continue
                
            # Check server by name (try both stem and full filename)
            server_ds_id = None
            if name in server_names:
                server_ds_id = server_names[name]
            elif filename in server_names:
                server_ds_id = server_names[filename]
                
            if server_ds_id:
                state = server_ids[server_ds_id]
                if state in ["ok", "queued", "running"]:
                    print(f"  {filename} found on server (ID: {server_ds_id}, State: {state})")
                    uploaded_datasets[name] = server_ds_id
                    cache["uploaded_datasets"] = uploaded_datasets
                    save_cache(cache)
                    continue
                    
            # Upload
            print(f"  Uploading {filename}...")
            try:
                resp = gi.tools.upload_file(filepath, history_id)
                dataset_id = resp["outputs"][0]["id"]
                uploaded_datasets[name] = dataset_id
                cache["uploaded_datasets"] = uploaded_datasets
                save_cache(cache)
            except Exception as e:
                print(f"    Error uploading {filename}: {e}")
                
    # 6. Poll History until datasets are OK
    print("\nWaiting for all uploaded datasets to finish processing (state: ok)...")
    while True:
        try:
            contents = gi.histories.show_history(history_id, contents=True)
            content_states = {item["id"]: item.get("state", "unknown") for item in contents if item.get("history_content_type") == "dataset"}
            
            states = {}
            all_ok = True
            failed = []
            
            for name, dataset_id in [("Reference CDS", ref_dataset_id)] + list(uploaded_datasets.items()):
                state = content_states.get(dataset_id, "unknown")
                states[state] = states.get(state, 0) + 1
                if state != "ok":
                    all_ok = False
                    if state == "error":
                        failed.append(name)
                        
            print(f"  Dataset status summary: {dict(sorted(states.items()))}")
            
            if failed:
                print(f"\nError: Some datasets failed to process: {failed}")
                return
                
            if all_ok:
                print("\nAll datasets uploaded and processed successfully!")
                break
                
        except Exception as e:
            print(f"  Warning: Error querying history status: {e}")
            
        time.sleep(10)

    # 7. Create List Collection of Assemblies
    collection_name = "Unaligned Assemblies Collection"
    collection_id = cache.get("collection_id")
    
    if collection_id:
        if collection_id in server_collections.values():
            print(f"\nUsing cached collection ID: {collection_id}")
        else:
            collection_id = None
            
    if not collection_id and collection_name in server_collections:
        collection_id = server_collections[collection_name]
        print(f"\nFound existing collection on server: '{collection_name}' (ID: {collection_id})")
        
    if not collection_id:
        print("\nCreating dataset collection (list) of Assemblies...")
        collection_description = {
            "name": collection_name,
            "collection_type": "list",
            "element_identifiers": [
                {
                    "id": dataset_id,
                    "name": name,
                    "src": "hda"
                }
                for name, dataset_id in sorted(uploaded_datasets.items())
            ]
        }
        try:
            coll_resp = gi.histories.create_dataset_collection(history_id, collection_description)
            collection_id = coll_resp["id"]
            print(f"Dataset collection created successfully! Collection ID: {collection_id}")
        except Exception as e:
            print(f"Error creating dataset collection: {e}")
            return
            
    cache["collection_id"] = collection_id
    save_cache(cache)

    # 8. Import or Find CAPHEINE Workflow
    wf_name = "CAPHEINE: Combined HyPhy Core and Compare"
    workflow_id = cache.get("workflow_id")
    
    if workflow_id:
        try:
            gi.workflows.show_workflow(workflow_id)
            print(f"\nUsing cached workflow ID: {workflow_id}")
        except Exception:
            workflow_id = None
            
    if not workflow_id:
        try:
            existing_wfs = gi.workflows.get_workflows(name=wf_name)
            if existing_wfs:
                workflow_id = existing_wfs[0]["id"]
                print(f"\nFound existing workflow '{wf_name}' on server (ID: {workflow_id})")
        except Exception as e:
            print(f"Warning searching workflows: {e}")
            
    if not workflow_id:
        print(f"\nDownloading CAPHEINE workflow definition from:\n{WF_URL}...")
        try:
            req = urllib.request.Request(WF_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as resp:
                wf_dict = json.loads(resp.read().decode('utf-8'))
                
            print("Importing workflow into your Galaxy account...")
            imported_wf = gi.workflows.import_workflow_dict(wf_dict)
            workflow_id = imported_wf["id"]
            print(f"Workflow imported successfully! Workflow ID: {workflow_id}")
        except Exception as e:
            print(f"Error importing workflow: {e}")
            return
            
    cache["workflow_id"] = workflow_id
    save_cache(cache)

    # 9. Invoke Workflow (Self-correcting candidates loop)
    print("\nConfiguring inputs and invoking the workflow (trying candidate payload structures)...")
    
    fg_suffix = config.get("foreground_suffix", "_foreground")
    candidates = [
        # Candidate 1: Parameter in inputs as raw string (UUID-based)
        {
            "name": "Candidate 1: Parameter in inputs as raw string (UUID-based)",
            "inputs": {
                REF_CDS_UUID: {"src": "hda", "id": ref_dataset_id},
                ASSEMBLIES_UUID: {"src": "hdca", "id": collection_id},
                FOREGROUND_REGEX_UUID: fg_suffix
            },
            "params": None,
            "inputs_by": "step_uuid"
        },
        # Candidate 2: Parameter in inputs as raw string (Index-based)
        {
            "name": "Candidate 2: Parameter in inputs as raw string (Index-based)",
            "inputs": {
                "0": {"src": "hda", "id": ref_dataset_id},
                "1": {"src": "hdca", "id": collection_id},
                "2": fg_suffix
            },
            "params": None,
            "inputs_by": "step_index"
        },
        # Candidate 3: Parameter in inputs as dict with 'value' key (UUID-based)
        {
            "name": "Candidate 3: Parameter in inputs as dict with 'value' key (UUID-based)",
            "inputs": {
                REF_CDS_UUID: {"src": "hda", "id": ref_dataset_id},
                ASSEMBLIES_UUID: {"src": "hdca", "id": collection_id},
                FOREGROUND_REGEX_UUID: {"value": fg_suffix}
            },
            "params": None,
            "inputs_by": "step_uuid"
        },
        # Candidate 4: Parameter in inputs as dict with 'value' key (Index-based)
        {
            "name": "Candidate 4: Parameter in inputs as dict with 'value' key (Index-based)",
            "inputs": {
                "0": {"src": "hda", "id": ref_dataset_id},
                "1": {"src": "hdca", "id": collection_id},
                "2": {"value": fg_suffix}
            },
            "params": None,
            "inputs_by": "step_index"
        },
        # Candidate 5: Parameter in params as raw value (Index-based)
        {
            "name": "Candidate 5: Parameter in params as raw value (Index-based)",
            "inputs": {
                "0": {"src": "hda", "id": ref_dataset_id},
                "1": {"src": "hdca", "id": collection_id}
            },
            "params": {
                "2": fg_suffix
            },
            "inputs_by": "step_index"
        },
        # Candidate 6: Parameter in params as raw value (UUID-based)
        {
            "name": "Candidate 6: Parameter in params as raw value (UUID-based)",
            "inputs": {
                "0": {"src": "hda", "id": ref_dataset_id},
                "1": {"src": "hdca", "id": collection_id}
            },
            "params": {
                FOREGROUND_REGEX_UUID: fg_suffix
            },
            "inputs_by": "step_uuid"
        },
        # Candidate 7: Required inputs only, omitting optional parameter (UUID-based)
        {
            "name": "Candidate 7: Required inputs only, omitting optional parameter (UUID-based)",
            "inputs": {
                REF_CDS_UUID: {"src": "hda", "id": ref_dataset_id},
                ASSEMBLIES_UUID: {"src": "hdca", "id": collection_id}
            },
            "params": None,
            "inputs_by": "step_uuid"
        },
        # Candidate 8: Required inputs only, omitting optional parameter (Index-based)
        {
            "name": "Candidate 8: Required inputs only, omitting optional parameter (Index-based)",
            "inputs": {
                "0": {"src": "hda", "id": ref_dataset_id},
                "1": {"src": "hdca", "id": collection_id}
            },
            "params": None,
            "inputs_by": "step_index"
        }
    ]
    
    success = False
    for i, cand in enumerate(candidates, 1):
        print(f"\n[{i}/{len(candidates)}] Trying {cand['name']}...")
        try:
            invocation = gi.workflows.invoke_workflow(
                workflow_id=workflow_id,
                inputs=cand["inputs"],
                params=cand["params"],
                history_id=history_id,
                inputs_by=cand["inputs_by"]
            )
            print("==================================================")
            print(f"SUCCESS! {cand['name']} worked!")
            print("==================================================")
            print(f"Invocation ID: {invocation.get('id')}")
            print(f"Invocation State: {invocation.get('state')}")
            print(f"\nYou can monitor the execution in your browser at:")
            base_url = galaxy_url.rstrip('/')
            print(f"{base_url}/histories/view?id={history_id}")
            print("==================================================")
            success = True
            break
        except Exception as e:
            print(f"  Failed: {e}")
            if hasattr(e, 'body'):
                # Strip and print only first 500 chars to avoid clutter
                body = e.body.strip()
                print(f"  Server response body: {body[:500]}")
            elif hasattr(e, 'read'):
                try:
                    body = e.read().decode().strip()
                    print(f"  Server response body: {body[:500]}")
                except Exception:
                    pass
                    
    if success:
        # Clear cache file on successful invocation
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
    else:
        print("\n==================================================")
        print("ERROR: All candidate invocation payloads failed.")
        print("==================================================")
        return

if __name__ == "__main__":
    main()
