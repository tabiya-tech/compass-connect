#!/usr/bin/env python3
"""
Sets up the taxonomy Compass Connect searches on: downloads it, generates its embeddings and creates the vector indexes.

Steps:
  1. Download the taxonomy export (a .zip of CSVs from https://taxonomy.tabiya.tech) and extract it.
  2. Import the CSVs into a local MongoDB shaped like the Taxonomy Platform's database (import_taxonomy_csv.py).
  3. Generate the embeddings with Vertex AI into the target database and create the vector search indexes
     (generate_embeddings.py, which wraps backend/scripts/embeddings/generate_taxonomy_embeddings.py).
  4. Wait for the vector search indexes to be READY and run a sample search (check_search.py).

Modes:
  partial (default)  all the occupations and the --skills-limit (default 5500) most used skills. It fits the
                     MongoDB Atlas free tier (M0, 512 MB).
  full               the whole taxonomy. It needs a bigger cluster.

Without --hot-run it only downloads the taxonomy and validates it: nothing is written to any database.
The steps can be repeated: the embeddings already generated are skipped.

Usage (with the Python of the backend virtual environment):
  export TARGET_MONGODB_URI="mongodb+srv://user:password@your-cluster.mongodb.net/"
  backend/venv-backend/bin/python docs/getting-started/scripts/setup_taxonomy.py \
      --credentials backend/keys/credentials.json --mode partial [--hot-run]

To use another taxonomy, pass the link of its .zip with --taxonomy-url
(the list is at https://taxonomy.tabiya.tech/#/modeldirectory). The name of the file starts with the model id.
The backend's TAXONOMY_MODEL_ID must be set to that id.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_COMPASS_REPO = SCRIPTS_DIR.parents[2]
DEFAULT_TAXONOMY_URL = ("https://taxonomy.tabiya.tech/downloads/"
                        "68933862382aab4c7de13ec6-export-68933d936429802108f5b9af.zip")
EMBEDDING_COLLECTIONS = ("occupationmodelsembeddings", "skillsmodelsembeddings")


def step(message: str) -> None:
    print(f"\n=== {message}")


def run(command: list[str]) -> None:
    print("$ " + " ".join(command))
    subprocess.run(command, check=True)


def download(url: str, destination: Path) -> None:
    if destination.exists():
        print(f"Already downloaded: {destination}")
        return
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=60) as response, open(destination, "wb") as out:
        out.write(response.read())
    print(f"Saved {destination} ({destination.stat().st_size / 1_000_000:.1f} MB)")


def extract(archive: Path, destination: Path) -> Path:
    """Extracts the archive and returns the folder that contains the CSV files."""
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():  # refuse paths that would escape the destination
            if not (destination / member).resolve().is_relative_to(destination.resolve()):
                raise SystemExit(f"Unsafe path in the archive: {member}")
        zf.extractall(destination)
    found = list(destination.rglob("model_info.csv"))
    if not found:
        raise SystemExit("model_info.csv not found in the archive: is it a taxonomy export?")
    return found[0].parent


def wait_for_indexes(uri: str, db_name: str, timeout_seconds: int) -> bool:
    from pymongo import MongoClient
    db = MongoClient(uri)[db_name]
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        states = {}
        for name in EMBEDDING_COLLECTIONS:
            indexes = list(db[name].list_search_indexes("embedding_index"))
            states[name] = indexes[0]["status"] if indexes else "MISSING"
        print(f"   search indexes: {states}")
        if all(state == "READY" for state in states.values()):
            return True
        time.sleep(15)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--credentials", required=True, type=Path, help="GCP service-account key (JSON)")
    parser.add_argument("--mode", choices=("partial", "full"), default="partial")
    parser.add_argument("--skills-limit", type=int, default=5500, help="skills to keep in partial mode")
    parser.add_argument("--taxonomy-url", default=DEFAULT_TAXONOMY_URL, help="link to a taxonomy export .zip")
    parser.add_argument("--model-id", help="taxonomy model id (default: the prefix of the .zip file name)")
    parser.add_argument("--compass-repo", type=Path, default=DEFAULT_COMPASS_REPO)
    parser.add_argument("--work-dir", type=Path, help="where to download and extract (default: a temporary folder)")
    parser.add_argument("--source-uri", default="mongodb://127.0.0.1:27017", help="local MongoDB for the imported CSVs")
    parser.add_argument("--source-db", default="tabiya-platform")
    parser.add_argument("--target-db", default="compass-taxonomy")
    parser.add_argument("--target-uri-env", default="TARGET_MONGODB_URI",
                        help="name of the environment variable holding the target MongoDB URI (e.g. Atlas)")
    parser.add_argument("--region", default="us-central1", help="Vertex AI region for the embeddings")
    parser.add_argument("--index-timeout", type=int, default=600, help="seconds to wait for the indexes to be READY")
    parser.add_argument("--hot-run", action="store_true", help="actually write to the databases")
    args = parser.parse_args()

    target_uri = os.environ.get(args.target_uri_env)
    if not target_uri:
        raise SystemExit(f"Set the {args.target_uri_env} environment variable to the target MongoDB URI first")
    archive_name = args.taxonomy_url.rsplit("/", 1)[-1]
    model_id = args.model_id or archive_name.split("-", 1)[0]
    if not re.fullmatch(r"[0-9a-f]{24}", model_id):
        raise SystemExit(f"'{model_id}' is not a model id: pass --model-id")

    work_dir = args.work_dir or Path(tempfile.mkdtemp(prefix="compass-taxonomy-"))
    work_dir.mkdir(parents=True, exist_ok=True)
    python = sys.executable

    step("1/4 Download the taxonomy")
    archive = work_dir / archive_name
    download(args.taxonomy_url, archive)
    csv_dir = extract(archive, work_dir / "extracted")

    step(f"2/4 Import the CSVs into {args.source_uri} ({args.source_db}), mode: {args.mode}")
    import_command = [python, str(SCRIPTS_DIR / "import_taxonomy_csv.py"), "--csv-dir", str(csv_dir),
                      "--model-id", model_id, "--mongo-uri", args.source_uri, "--db", args.source_db]
    if args.mode == "partial":
        import_command += ["--skills-limit", str(args.skills_limit)]
    if args.hot_run:
        import_command += ["--hot-run", "--drop"]
    run(import_command)

    if not args.hot_run:
        print("\nDRY RUN: the taxonomy was downloaded and validated, nothing was written. "
              "Re-run with --hot-run to generate the embeddings (steps 3 and 4).")
        return

    step(f"3/4 Generate the embeddings and the indexes into {args.target_db}")
    run([python, str(SCRIPTS_DIR / "generate_embeddings.py"), "--compass-repo", str(args.compass_repo),
         "--credentials", str(args.credentials), "--source-uri", args.source_uri, "--source-db", args.source_db,
         "--target-db", args.target_db, "--target-uri-env", args.target_uri_env, "--model-id", model_id,
         "--region", args.region, "--hot-run"])

    step("4/4 Wait for the vector search indexes and run a sample search")
    if not wait_for_indexes(target_uri, args.target_db, args.index_timeout):
        raise SystemExit("The search indexes are not READY yet. Check them in Atlas, then run check_search.py.")
    os.environ["TAXONOMY_MONGODB_URI"] = target_uri
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(args.credentials.resolve())
    run([python, str(SCRIPTS_DIR / "check_search.py"), "I sell vegetables at the market",
         "--db", args.target_db, "--model-id", model_id, "--region", args.region])

    print(f"\nDone. In the backend .env set TAXONOMY_MODEL_ID={model_id} and TAXONOMY_DATABASE_NAME={args.target_db}")


if __name__ == "__main__":
    main()
