#!/usr/bin/env python3
"""
Verifies a Compass Connect setup (local, on-premise or cloud project): is the configuration complete, and do the
Google Cloud, Firebase and search settings actually work? Run by docker compose from the backend image, or by hand.

  preflight   Before anything else starts: is the .env complete, and do the Google Cloud / Firebase
              settings actually work?  (configuration, GCP key, Vertex embeddings, Gemini, Cloud DLP, Firebase)
  search      After the databases are ready: does a vector search over the taxonomy return results through
              mongot, using the same query path as the backend?

Every problem is reported in plain language, with a hint on how to fix it. ERRORS stop the stack from
starting; WARNINGS are printed but do not.

Usage: python scripts/verify_setup.py {preflight|search}
"""
import base64
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
import warnings

warnings.filterwarnings("ignore", message="This feature is deprecated")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the backend root, to import the app settings
from app.agent.config import GEMINI_DEFAULT_MODELS, ModelTier  # noqa: E402
from app.users.auth import SELF_HOSTED_ENVIRONMENT_TYPE  # noqa: E402

# The environment variable that overrides the model of each tier, and the model used when it is not set
# (the same defaults the backend uses)
GEMINI_TIERS = {
    "LLM_DEFAULT_MODEL": GEMINI_DEFAULT_MODELS[ModelTier.DEFAULT],
    "LLM_REASONING_MODEL": GEMINI_DEFAULT_MODELS[ModelTier.REASONING],
    "LLM_DEEP_REASONING_MODEL": GEMINI_DEFAULT_MODELS[ModelTier.DEEP_REASONING],
}

# Settings that must have a real value for the stack to work
REQUIRED_SETTINGS = [
    "MONGOT_PASSWORD",
    "FIREBASE_API_KEY",
    "FIREBASE_AUTH_DOMAIN",
    "SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY",
    "SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY_ID",
    "FRONTEND_URL",
    "BACKEND_URL",
    "TAXONOMY_MODEL_ID",
    "EMBEDDINGS_MODEL_NAME",
    "VERTEX_API_EMBEDDINGS_REGION",
    "VERTEX_API_GEN_AI_REGION",
]
# Only required when the backend verifies the Firebase tokens itself (TARGET_ENVIRONMENT_TYPE=selfhosted)
SELF_HOSTED_REQUIRED_SETTINGS = ["FIREBASE_PROJECT_ID"]
# Settings that must exist, but may be empty
MUST_EXIST_SETTINGS = ["MATCHING_SERVICE_URL", "MATCHING_SERVICE_API_KEY"]

DEBUG = bool(os.getenv("CHECK_DEBUG"))


class Report:
    def __init__(self):
        self.errors = 0
        self.warnings = 0

    def ok(self, name, detail=""):
        print(f"  [ OK ] {name}" + (f": {detail}" if detail else ""))

    def error(self, name, problem, hint=""):
        self.errors += 1
        print(f"  [ERROR] {name}: {problem}")
        if hint:
            print(f"          -> {hint}")

    def warn(self, name, problem, hint=""):
        self.warnings += 1
        print(f"  [WARN ] {name}: {problem}")
        if hint:
            print(f"          -> {hint}")

    def finish(self, title):
        print()
        if self.errors:
            print(f"{title}: FAILED with {self.errors} error(s) and {self.warnings} warning(s). "
                  f"Fix the errors above in your configuration (the .env file) and run the check again; "
                  f"with docker compose: `docker compose up -d`.")
            sys.exit(1)
        print(f"{title}: passed" + (f" with {self.warnings} warning(s)" if self.warnings else ""))
        sys.exit(0)


def first_line(e: Exception) -> str:
    return f"{e.__class__.__name__}: {str(e).splitlines()[0][:300] if str(e) else ''}"


def is_placeholder(value: str) -> bool:
    return value.startswith("<") and value.endswith(">")


# --------------------------------------------------------------------------------------------- configuration

def check_configuration(r: Report):
    print("Configuration")
    problems = False
    required = list(REQUIRED_SETTINGS)
    if os.getenv("TARGET_ENVIRONMENT_TYPE") == SELF_HOSTED_ENVIRONMENT_TYPE:
        required += SELF_HOSTED_REQUIRED_SETTINGS
    for name in required:
        value = os.getenv(name)
        if value is None or not value.strip():
            r.error(name, "is not set", f"set {name} in your .env file (see .env.example)")
            problems = True
        elif is_placeholder(value.strip()):
            r.error(name, f"still has the placeholder value {value!r}", f"replace it with a real value in .env")
            problems = True
    for name in MUST_EXIST_SETTINGS:
        if os.getenv(name) is None:
            r.error(name, "is missing", f"keep `{name}=` in your .env file, even if empty (the backend fails to start without it)")
            problems = True
    if os.getenv("TARGET_ENVIRONMENT_TYPE") == "local":
        r.warn("TARGET_ENVIRONMENT_TYPE", "is 'local': the backend does NOT verify user tokens in this mode",
               "fine for testing on your own machine; never expose this stack to the internet")
    if os.getenv("TARGET_ENVIRONMENT_TYPE") == SELF_HOSTED_ENVIRONMENT_TYPE:
        project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
        auth_domain = os.getenv("FIREBASE_AUTH_DOMAIN", "").strip()
        if project_id and auth_domain and not auth_domain.startswith(project_id):
            r.warn("FIREBASE_PROJECT_ID", f"{project_id!r} does not match FIREBASE_AUTH_DOMAIN {auth_domain!r}",
                   "check both come from the same Firebase project; tokens of another project are rejected")
        if not os.getenv("API_KEYS", "").strip():
            r.warn("API_KEYS", "is empty: the x-api-key endpoints (/analytics/*, occupation and skill search) are disabled",
                   "fine unless you integrate an analytics or search client; set API_KEYS to enable them")
    if os.getenv("GOOGLE_CLOUD_PROJECT"):
        r.warn("GOOGLE_CLOUD_PROJECT", "is set; the project is normally taken from the service-account key",
               "remove it unless you know you need it")
    if not problems:
        r.ok("settings", "all required settings have values")


def check_rsa_key(r: Report):
    key = os.getenv("SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY", "").strip()
    if not key or is_placeholder(key):
        return  # already reported
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import load_der_public_key
        public_key = load_der_public_key(base64.b64decode(key.replace("-----BEGIN PUBLIC KEY-----", "")
                                                          .replace("-----END PUBLIC KEY-----", "").replace("\n", "")))
        if not isinstance(public_key, rsa.RSAPublicKey):
            raise ValueError("not an RSA key")
        r.ok("RSA public key", f"valid, {public_key.key_size} bits")
    except Exception as e:
        r.error("SENSITIVE_PERSONAL_DATA_RSA_ENCRYPTION_KEY", f"is not a valid RSA public key ({first_line(e)})",
                "paste only the base64 body of public-key.pem on ONE line, without the BEGIN/END lines")


# --------------------------------------------------------------------------------------------- Google Cloud

def load_gcp_key(r: Report):
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not path:
        r.error("GOOGLE_APPLICATION_CREDENTIALS", "is not set", "this is set by docker compose; check GCP_CREDENTIALS_FILE in .env")
        return None
    if os.path.isdir(path):
        r.error("GCP key file", f"{path} is a directory, not a file",
                "GCP_CREDENTIALS_FILE in .env must point to an existing JSON key file on the host")
        return None
    if not os.path.isfile(path):
        r.error("GCP key file", f"{path} was not found", "check GCP_CREDENTIALS_FILE in .env")
        return None
    try:
        with open(path) as f:
            key = json.load(f)
    except Exception as e:
        r.error("GCP key file", f"is not valid JSON ({first_line(e)})", "download the key again as JSON from the Google Cloud console")
        return None
    if key.get("type") != "service_account" or not key.get("project_id") or not key.get("client_email"):
        r.error("GCP key file", "is not a service-account key (missing type/project_id/client_email)",
                "create a key for a SERVICE ACCOUNT: IAM & Admin -> Service accounts -> Keys -> Add key -> JSON")
        return None
    r.ok("GCP key file", f"project {key['project_id']}, service account {key['client_email']}")
    return key


def gcp_hint(e: Exception, project: str) -> str:
    text = f"{e.__class__.__name__} {e}"
    if "SERVICE_DISABLED" in text or "has not been used" in text or "is not enabled" in text:
        return f"enable the API in project {project}: Vertex AI (aiplatform.googleapis.com) / Cloud DLP (dlp.googleapis.com)"
    if "PermissionDenied" in text or "403" in text:
        return "give the service account the roles 'Vertex AI User' (roles/aiplatform.user) and 'DLP User' (roles/dlp.user)"
    if "TooManyRequests" in text or "ResourceExhausted" in text or "429" in text:
        return "quota exhausted (common on new projects); retry later, request more quota, or set VERTEX_API_GEN_AI_REGION=global"
    if "NotFound" in text or "404" in text:
        return "that model is not available in this region/project: check the region and model name settings"
    if "billing" in text.lower():
        return f"link a billing account to project {project}"
    return "set CHECK_DEBUG=1 to see the full traceback"


def with_429_retries(fn, retries=3):
    from google.genai.errors import ClientError
    for attempt in range(retries + 1):
        try:
            return fn()
        except ClientError as e:
            if e.code != 429 or attempt == retries:
                raise
            time.sleep(2 ** (attempt + 2))  # 4s, 8s, 16s


def check_vertex(r: Report, key: dict):
    print("\nGoogle Cloud (Vertex AI)")
    project = key["project_id"]
    from google import genai
    from google.genai.types import EmbedContentConfig

    embeddings_region = os.getenv("VERTEX_API_EMBEDDINGS_REGION", "us-central1")
    gen_ai_region = os.getenv("VERTEX_API_GEN_AI_REGION", "global")  # same default as the backend
    model_name = os.getenv("EMBEDDINGS_MODEL_NAME", "text-embedding-005")
    if os.getenv("EMBEDDINGS_SERVICE_NAME", "GOOGLE-VERTEX-AI") != "GOOGLE-VERTEX-AI":
        r.error("EMBEDDINGS_SERVICE_NAME", "only GOOGLE-VERTEX-AI is supported", "set EMBEDDINGS_SERVICE_NAME=GOOGLE-VERTEX-AI")

    try:
        embeddings_client = genai.Client(vertexai=True, project=project, location=embeddings_region)
        values = with_429_retries(lambda: embeddings_client.models.embed_content(
            model=model_name, contents=["baker"], config=EmbedContentConfig(task_type="RETRIEVAL_QUERY")).embeddings[0].values)
        if len(values) != 768:
            r.error(f"Embeddings {model_name}", f"returned {len(values)} dimensions, the taxonomy snapshot needs 768",
                    "use EMBEDDINGS_MODEL_NAME=text-embedding-005, the model the taxonomy vectors were computed with")
        else:
            r.ok(f"Embeddings {model_name} ({embeddings_region})", "768 dimensions")
    except Exception as e:
        if DEBUG:
            traceback.print_exc()
        r.error(f"Embeddings {model_name} ({embeddings_region})", first_line(e), gcp_hint(e, project))

    provider = os.getenv("LLM_PROVIDER", "gemini")
    if provider != "gemini":
        r.warn("LLM_PROVIDER", f"is '{provider}': the Gemini model checks were skipped",
               "that provider's own settings are not verified by this check")
        return
    gen_ai_client = genai.Client(vertexai=True, project=project, location=gen_ai_region)
    for env_name, default_model in GEMINI_TIERS.items():
        model = os.getenv(env_name) or default_model
        try:
            # the backend calls the models through the Interactions API
            text = with_429_retries(lambda: (gen_ai_client.interactions.create(
                model=model, input="Reply with exactly: OK", store=False).output_text or "").strip())
            r.ok(f"Gemini {model} ({env_name}, {gen_ai_region})", f"replied {text[:20]!r}")
        except Exception as e:
            if DEBUG:
                traceback.print_exc()
            r.error(f"Gemini {model} ({env_name}, {gen_ai_region})", first_line(e), gcp_hint(e, project))
        time.sleep(2)  # new projects have low per-minute limits


def check_dlp(r: Report, key: dict):
    project = key["project_id"]
    try:
        import google.cloud.dlp_v2
        response = google.cloud.dlp_v2.DlpServiceClient().deidentify_content(request={
            "parent": f"projects/{project}",
            "inspect_config": {"info_types": [{"name": "EMAIL_ADDRESS"}]},
            "deidentify_config": {"info_type_transformations": {"transformations": [
                {"primitive_transformation": {"replace_with_info_type_config": {}}}]}},
            "item": {"value": "write to jane@example.com"},
        })
        r.ok("Cloud DLP (optional)", repr(response.item.value))
    except Exception as e:
        if DEBUG:
            traceback.print_exc()
        r.warn("Cloud DLP (optional)", first_line(e),
               "DLP is only used to remove personal data from text when a request asks for it; the app works without it. "
               + gcp_hint(e, project))


# --------------------------------------------------------------------------------------------- Firebase

def firebase_call(api_key: str, endpoint: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"https://identitytoolkit.googleapis.com/v1/{endpoint}?key={api_key}",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def check_firebase(r: Report, key: dict | None):
    print("\nFirebase (login)")
    api_key = os.getenv("FIREBASE_API_KEY", "").strip()
    auth_domain = os.getenv("FIREBASE_AUTH_DOMAIN", "").strip()
    if not api_key or is_placeholder(api_key):
        return  # already reported
    try:
        # Neither call creates anything: they fail on purpose with a known error when the key and provider are fine.
        status, body = firebase_call(api_key, "accounts:lookup", {"idToken": "not-a-real-token"})
        message = body.get("error", {}).get("message", "")
        if "API_KEY_INVALID" in message or "API key not valid" in message:
            r.error("FIREBASE_API_KEY", "was rejected by Firebase", "copy `apiKey` from Firebase console -> Project settings -> Your apps (web app)")
            return
        if "SERVICE_DISABLED" in message or "has not been used" in message or status == 403:
            r.error("FIREBASE_API_KEY", f"Firebase Authentication is not enabled for this key ({message[:120]})",
                    "enable Authentication in the Firebase console and the Identity Toolkit API in Google Cloud")
            return
        r.ok("FIREBASE_API_KEY", "accepted by Firebase")

        status, body = firebase_call(api_key, "accounts:signInWithPassword",
                                     {"email": "compass-check@example.invalid", "password": "not-a-real-password",
                                      "returnSecureToken": True})
        message = body.get("error", {}).get("message", "")
        if "OPERATION_NOT_ALLOWED" in message:
            r.error("Email/Password sign-in", "is disabled in Firebase",
                    "Firebase console -> Authentication -> Sign-in method -> enable Email/Password (and Anonymous)")
        else:
            r.ok("Email/Password sign-in", "enabled")
    except Exception as e:
        r.warn("Firebase", f"could not be reached ({first_line(e)})", "check that this machine can reach identitytoolkit.googleapis.com")

    if auth_domain.endswith(".firebaseapp.com") and key and auth_domain != f"{key['project_id']}.firebaseapp.com":
        r.warn("FIREBASE_AUTH_DOMAIN",
               f"{auth_domain} does not match the Google Cloud project of the service-account key ({key['project_id']})",
               "Firebase and the service account should belong to the same project, unless you did this on purpose")
    r.ok("FIREBASE_AUTH_DOMAIN", auth_domain) if auth_domain else None


# --------------------------------------------------------------------------------------------- commands

def preflight():
    r = Report()
    print("Compass Connect preflight check\n")
    check_configuration(r)
    check_rsa_key(r)
    print("\nGoogle Cloud key")
    key = load_gcp_key(r)
    if key:
        os.environ["GOOGLE_CLOUD_PROJECT"] = key["project_id"]
        check_vertex(r, key)
        check_dlp(r, key)
    else:
        print("  (Vertex AI checks skipped: no usable key)")
    check_firebase(r, key)
    r.finish("Preflight")


def search():
    r = Report()
    print("Compass Connect search check (MongoDB + mongot + Vertex)\n")
    key = load_gcp_key(r)
    uri = os.getenv("TAXONOMY_MONGODB_URI", "")
    database = os.getenv("TAXONOMY_DATABASE_NAME", "compass-taxonomy")
    model_id = os.getenv("TAXONOMY_MODEL_ID", "")
    if not key or not uri:
        r.error("setup", "missing GCP key or TAXONOMY_MONGODB_URI")
        r.finish("Search check")
    os.environ["GOOGLE_CLOUD_PROJECT"] = key["project_id"]
    try:
        from bson import ObjectId
        from pymongo import MongoClient
        from google import genai
        from google.genai.types import EmbedContentConfig

        db = MongoClient(uri, serverSelectionTimeoutMS=15000)[database]
        model_object_id = ObjectId(model_id)
        for collection in ("occupationmodelsembeddings", "skillsmodelsembeddings"):
            count = db[collection].count_documents({"modelId": model_object_id})
            if count:
                r.ok(collection, f"{count} documents for model {model_id}")
            else:
                r.error(collection, f"no documents for taxonomy model {model_id}",
                        "TAXONOMY_MODEL_ID must be the id of the restored snapshot (see .env.example), "
                        "and `docker compose logs mongo-init-taxonomy` should show the restore")

        embeddings_region = os.getenv("VERTEX_API_EMBEDDINGS_REGION", "us-central1")
        embeddings_client = genai.Client(vertexai=True, project=key["project_id"], location=embeddings_region)
        model_name = os.getenv("EMBEDDINGS_MODEL_NAME", "text-embedding-005")
        vector = with_429_retries(lambda: embeddings_client.models.embed_content(
            model=model_name, contents=["I sell vegetables at the market"],
            config=EmbedContentConfig(task_type="RETRIEVAL_QUERY")).embeddings[0].values)

        for collection, label in (("occupationmodelsembeddings", "occupation"), ("skillsmodelsembeddings", "skill")):
            results = list(db[collection].aggregate([
                {"$vectorSearch": {"index": "embedding_index", "path": "embedding", "queryVector": vector,
                                   "numCandidates": 100, "limit": 3, "filter": {"modelId": model_object_id}}},
                {"$project": {"_id": 0, "preferredLabel": 1, "score": {"$meta": "vectorSearchScore"}}},
            ]))
            if results:
                r.ok(f"vector search ({label})", f"{results[0].get('preferredLabel')!r} (score {results[0]['score']:.3f})")
            else:
                r.error(f"vector search ({label})", "returned no results",
                        "the search index may still be building or is missing; check `docker compose logs mongo-init-taxonomy mongot`")
    except Exception as e:
        if DEBUG:
            traceback.print_exc()
        r.error("search check", first_line(e), "check `docker compose logs mongod mongot`; CHECK_DEBUG=1 gives a traceback")
    r.finish("Search check")


if __name__ == "__main__":
    commands = {"preflight": preflight, "search": search}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(__doc__)
        sys.exit(2)
    commands[sys.argv[1]]()
