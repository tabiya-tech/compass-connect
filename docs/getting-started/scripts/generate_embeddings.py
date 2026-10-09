#!/usr/bin/env python3
"""
Wrapper around backend/scripts/embeddings/generate_taxonomy_embeddings.py.

Why a wrapper:
  - The target MongoDB URI is read from an environment variable (TARGET_MONGODB_URI by default), so the password
    stays out of the command line and the shell history.
  - It sets the GCP / Vertex AI variables the script needs from your service-account key.
  - It can skip the creation of the vector search indexes (--no-indexes).

The original script is used unchanged: it is imported and its main() is called.

Usage (with the Python of the backend virtual environment):
  export TARGET_MONGODB_URI="mongodb+srv://user:password@your-cluster.mongodb.net/"
  backend/venv-backend/bin/python generate_embeddings.py \
      --compass-repo <path/to/compass-connect> --credentials <path/to/credentials.json> \
      --source-db tabiya-platform --target-db compass-taxonomy [--hot-run] [--no-indexes]

Without --hot-run nothing is written.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

DEFAULT_MODEL_ID = "68933862382aab4c7de13ec6"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--compass-repo", required=True, type=Path, help="Path to your clone of compass-connect")
    parser.add_argument("--credentials", required=True, type=Path, help="GCP service-account key (JSON)")
    parser.add_argument("--source-db", default="tabiya-platform", help="DB made by import_taxonomy_csv.py")
    parser.add_argument("--source-uri", default="mongodb://127.0.0.1:27017")
    parser.add_argument("--target-db", required=True, help="DB to write the embeddings to (e.g. compass-taxonomy)")
    parser.add_argument("--target-uri-env", default="TARGET_MONGODB_URI",
                        help="Name of the environment variable holding the target MongoDB URI")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--region", default="us-central1",
                        help="VERTEX_API_EMBEDDINGS_REGION (us-central1 allows 250 texts per batch)")
    parser.add_argument("--hot-run", action="store_true")
    parser.add_argument("--no-indexes", action="store_true", help="generate embeddings only, do not create the indexes")
    args = parser.parse_args()

    target_uri = os.environ.get(args.target_uri_env)
    if not target_uri:
        raise SystemExit(f"Set the {args.target_uri_env} environment variable to the target MongoDB URI first")

    backend = args.compass_repo.resolve() / "backend"
    embeddings_dir = backend / "scripts" / "embeddings"
    if not (embeddings_dir / "generate_taxonomy_embeddings.py").exists():
        raise SystemExit(f"{embeddings_dir} not found: is --compass-repo the compass-connect clone?")

    key_path = args.credentials.resolve()
    project = json.loads(key_path.read_text())["project_id"]
    os.environ.update({
        "GOOGLE_APPLICATION_CREDENTIALS": str(key_path),
        # GOOGLE_CLOUD_PROJECT is deliberately not set: google.auth.default() reads the project from the key file,
        # while setting it makes the Google client call the Cloud Resource Manager API, which may be disabled.
        "VERTEX_API_EMBEDDINGS_REGION": args.region,
        "EMBEDDINGS_SCRIPT_TABIYA_MONGODB_URI": args.source_uri,
        "EMBEDDINGS_SCRIPT_TABIYA_DB_NAME": args.source_db,
        "EMBEDDINGS_SCRIPT_TABIYA_MODEL_ID": args.model_id,
        "EMBEDDINGS_SCRIPT_COMPASS_TAXONOMY_DB_URI": target_uri,
        "EMBEDDINGS_SCRIPT_COMPASS_TAXONOMY_DB_NAME": args.target_db,
        "EMBEDDINGS_SCRIPT_EMBEDDINGS_SERVICE_NAME": "GOOGLE-VERTEX-AI",
        "EMBEDDINGS_SCRIPT_EMBEDDINGS_MODEL_NAME": "text-embedding-005",
    })
    print(f"project={project} region={args.region} source={args.source_uri}/{args.source_db} "
          f"target={args.target_db} model={args.model_id} hot_run={args.hot_run} indexes={not args.no_indexes}")

    # The script resolves 'logging.cfg.yaml' and '_base_data_settings' relative to its own folder,
    # and 'app.*' / 'scripts.*' relative to backend/.
    os.chdir(embeddings_dir)
    sys.argv[0] = str(embeddings_dir / "generate_taxonomy_embeddings.py")  # logging.cfg.yaml is resolved next to __main__
    sys.modules["__main__"].__file__ = sys.argv[0]
    sys.path[:0] = [str(embeddings_dir), str(backend)]
    import generate_taxonomy_embeddings as gen  # noqa: E402 (env must be set before import)

    asyncio.run(gen.main(gen.Options(
        hot_run=args.hot_run,
        generate_embeddings=True,
        generate_indexes=not args.no_indexes,
    )))


if __name__ == "__main__":
    main()
