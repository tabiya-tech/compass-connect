#!/usr/bin/env python3
"""
Compass Connect - Google Cloud smoke test.

Checks that a service-account key can call everything the Compass Connect backend uses on GCP:
  1. Vertex AI embeddings (text-embedding-005)
  2. Gemini, the 3 model tiers (the backend's default models, or the LLM_*_MODEL environment variables)
  3. Cloud DLP (deidentify)

Usage (with the Python of the backend virtual environment):
  python gcp_smoke_test.py [--key keys/credentials.json] [--region us-central1] [--gen-ai-region global]

Cost: a handful of tiny requests, a fraction of a cent.
"""
import argparse
import json
import os
import sys
import time
import traceback

TIERS = {
    "LLM_DEFAULT_MODEL": "gemini-3.5-flash-lite",
    "LLM_REASONING_MODEL": "gemini-3.8-flash",
    "LLM_DEEP_REASONING_MODEL": "gemini-3.1-pro-preview",
}


def check(name, fn):
    try:
        detail = fn()
        print(f"  [OK] {name}: {detail}")
        return True
    except Exception as e:  # report every failure, keep going
        print(f"  [FAILED] {name}: {e.__class__.__name__}: {str(e).splitlines()[0][:300]}")
        if os.getenv("SMOKE_DEBUG"):
            traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", default="keys/credentials.json")
    parser.add_argument("--region", default="us-central1", help="region for the embeddings")
    parser.add_argument("--gen-ai-region", default="global", help="region for Gemini")
    parser.add_argument("--retries", type=int, default=3, help="retries with backoff on 429 (resource exhausted)")
    args = parser.parse_args()

    with open(args.key) as f:
        key = json.load(f)
    project = key["project_id"]
    # The backend picks these up the same way (google.auth.default()).
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(args.key)
    print(f"Project: {project}\nService account: {key['client_email']}\n"
          f"Embeddings region: {args.region}\nGen-AI region: {args.gen_ai_region}\n")

    from google import genai
    from google.genai.errors import APIError
    import google.cloud.dlp_v2

    results = []

    def embeddings():
        client = genai.Client(vertexai=True, project=project, location=args.region)
        values = client.models.embed_content(model="text-embedding-005", contents=["baker"]).embeddings[0].values
        if len(values) != 768:
            raise ValueError(f"expected 768 dimensions, got {len(values)}")
        return f"{len(values)} dimensions"

    results.append(check("Embeddings text-embedding-005", embeddings))

    gen_ai_client = genai.Client(vertexai=True, project=project, location=args.gen_ai_region)
    for env_name, default_model in TIERS.items():
        model = os.getenv(env_name) or default_model

        def gemini(model=model):
            # The backend calls Gemini through the Interactions API, so this is what we test.
            for attempt in range(args.retries + 1):
                try:
                    text = (gen_ai_client.interactions.create(model=model, input="Reply with exactly: OK",
                                                              store=False).output_text or "").strip()
                    return f"replied {text[:40]!r}" + (f" (after {attempt} retries)" if attempt else "")
                except APIError as e:
                    if e.code != 429 or attempt == args.retries:
                        raise
                    time.sleep(2 ** (attempt + 2))  # 4s, 8s, 16s

        results.append(check(f"Gemini {model} ({env_name})", gemini))
        time.sleep(3)  # space out calls; new projects have low per-minute limits

    def dlp():
        response = google.cloud.dlp_v2.DlpServiceClient().deidentify_content(request={
            "parent": f"projects/{project}",
            "inspect_config": {"info_types": [{"name": "EMAIL_ADDRESS"}]},
            "deidentify_config": {"info_type_transformations": {"transformations": [
                {"primitive_transformation": {"replace_with_info_type_config": {}}}]}},
            "item": {"value": "write to jane@example.com"},
        })
        return f"{response.item.value!r}"

    results.append(check("Cloud DLP deidentify", dlp))

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    if passed != len(results):
        print("Hints: PermissionDenied -> check the roles on the service account (aiplatform.user, dlp.user); "
              "'API has not been used' / SERVICE_DISABLED -> enable aiplatform.googleapis.com and dlp.googleapis.com; "
              "429 ResourceExhausted -> shared capacity; try --gen-ai-region global, or request quota; "
              "NotFound on a model -> that model isn't available in this region/project; "
              "billing errors -> link a billing account. Set SMOKE_DEBUG=1 for tracebacks.")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
