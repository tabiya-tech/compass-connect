#!/usr/bin/env python3
"""
One-shot step of the Docker stack: builds the taxonomy the backend searches on, using the same scripts as the manual
setup (backend/scripts/taxonomy_setup/setup_taxonomy.py): download the public CSV export, import it, generate the
embeddings with Vertex AI and create the vector search indexes.

Idempotent: when the taxonomy was already built for TAXONOMY_MODEL_ID (same or a bigger TAXONOMY_MODE) it does nothing,
so `docker compose up` is fast after the first run. Settings (.env): TAXONOMY_URL, TAXONOMY_MODE, TAXONOMY_MODEL_ID,
TAXONOMY_DATABASE_NAME, TAXONOMY_SKILLS_LIMIT, VERTEX_API_EMBEDDINGS_REGION.
"""
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from pymongo import MongoClient

REPO = "/repo"  # the compass-connect checkout, mounted by docker-compose.yml
SETUP_SCRIPT = f"{REPO}/backend/scripts/taxonomy_setup/setup_taxonomy.py"
SOURCE_DB = "tabiya-platform"  # scratch database the CSVs are imported into
STATE_COLLECTION = "taxonomy_setup_state"
EMBEDDING_COLLECTIONS = ("occupationmodelsembeddings", "skillsmodelsembeddings")


def fail(message: str) -> None:
    print(f"\nERROR: {message}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    url = os.getenv("TAXONOMY_URL", "").strip()
    mode = os.getenv("TAXONOMY_MODE", "partial").strip() or "partial"
    model_id = os.getenv("TAXONOMY_MODEL_ID", "").strip()
    database = os.getenv("TAXONOMY_DATABASE_NAME", "compass-taxonomy")
    uri = os.environ["TAXONOMY_MONGODB_URI"]
    region = os.getenv("VERTEX_API_EMBEDDINGS_REGION", "us-central1")

    if not url:
        fail("TAXONOMY_URL is not set in .env. Use the link of a taxonomy export (.zip) from "
             "https://taxonomy.tabiya.tech/#/modeldirectory")
    if mode not in ("partial", "full"):
        fail(f"TAXONOMY_MODE is '{mode}': it must be 'partial' or 'full'")
    url_model_id = url.rsplit("/", 1)[-1].split("-", 1)[0]
    if not re.fullmatch(r"[0-9a-f]{24}", url_model_id):
        fail(f"cannot read a model id from the start of the file name in TAXONOMY_URL ({url})")
    if model_id != url_model_id:
        fail(f"TAXONOMY_MODEL_ID is '{model_id}' but the file in TAXONOMY_URL belongs to model '{url_model_id}'. "
             f"Set TAXONOMY_MODEL_ID={url_model_id} in .env (the backend must search the model that was built)")

    db = MongoClient(uri, serverSelectionTimeoutMS=30000)[database]
    state = db[STATE_COLLECTION].find_one({"_id": model_id})
    complete = state and (state["mode"] == mode or state["mode"] == "full")
    if complete and all(db[c].count_documents({}, limit=1) for c in EMBEDDING_COLLECTIONS):
        print(f"Taxonomy {model_id} is already built in '{database}' (mode {state['mode']}, "
              f"finished {state['completedAt']:%Y-%m-%d %H:%M} UTC): nothing to do.")
        return

    print(f"Building taxonomy {model_id} (mode {mode}) from {url}")
    if mode == "full":
        print("The first run embeds the whole taxonomy with Vertex AI (billed) and takes a while; "
              "later starts skip this step. Use TAXONOMY_MODE=partial for a smaller, cheaper taxonomy.")
    credentials = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    command = [sys.executable, SETUP_SCRIPT, "--credentials", credentials, "--mode", mode, "--taxonomy-url", url,
               "--model-id", model_id, "--compass-repo", REPO, "--work-dir", "/work",
               "--source-uri", uri, "--source-db", SOURCE_DB, "--target-db", database,
               "--region", region, "--index-timeout", "1800", "--hot-run"]
    if os.getenv("TAXONOMY_SKILLS_LIMIT"):
        command += ["--skills-limit", os.environ["TAXONOMY_SKILLS_LIMIT"]]
    # setup_taxonomy.py reads the target database URI from this variable
    result = subprocess.run(command, env={**os.environ, "TARGET_MONGODB_URI": uri})
    if result.returncode != 0:
        fail("the taxonomy setup failed (see above). Fix the cause and run `docker compose up -d` again: "
             "the steps are repeatable and embeddings already generated are skipped.")

    db[STATE_COLLECTION].replace_one(
        {"_id": model_id},
        {"_id": model_id, "mode": mode, "url": url, "completedAt": datetime.now(timezone.utc)}, upsert=True)
    MongoClient(uri).drop_database(SOURCE_DB)  # the imported CSV copy is only needed to generate the embeddings
    print(f"\nTaxonomy {model_id} is ready in '{database}'.")


if __name__ == "__main__":
    main()
