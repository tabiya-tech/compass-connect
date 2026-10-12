#!/usr/bin/env python3
"""
Checks that the taxonomy vector search works: embeds a phrase with Vertex AI and queries MongoDB the way
Compass Connect's backend does (RETRIEVAL_QUERY embedding, $vectorSearch, group by UUID, best score).

Usage (with the Python of the backend virtual environment):
  export TAXONOMY_MONGODB_URI="mongodb+srv://user:password@your-cluster.mongodb.net/"
  export GOOGLE_APPLICATION_CREDENTIALS="path/to/credentials.json"
  python check_search.py "I sell vegetables at the market"
  python check_search.py "baking bread" --collection skills --k 5
"""
import argparse
import os
import sys

from bson import ObjectId
from google import genai
from google.genai.types import EmbedContentConfig
from pymongo import MongoClient

DEFAULT_MODEL_ID = "68933862382aab4c7de13ec6"
COLLECTIONS = {"occupations": "occupationmodelsembeddings", "skills": "skillsmodelsembeddings"}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("query", help="text to search for (the taxonomy is in English)")
    p.add_argument("--collection", choices=COLLECTIONS, default="occupations")
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--db", default="compass-taxonomy")
    p.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    p.add_argument("--region", default="us-central1")
    args = p.parse_args()

    uri = os.environ.get("TAXONOMY_MONGODB_URI")
    if not uri:
        sys.exit("Set TAXONOMY_MONGODB_URI first")

    client = genai.Client(vertexai=True, location=args.region)
    response = client.models.embed_content(model="text-embedding-005", contents=[args.query],
                                           config=EmbedContentConfig(task_type="RETRIEVAL_QUERY"))
    vector = response.embeddings[0].values

    coll = MongoClient(uri)[args.db][COLLECTIONS[args.collection]]
    k = args.k
    pipeline = [
        {"$vectorSearch": {"queryVector": vector, "path": "embedding", "numCandidates": k * 30, "limit": k * 3,
                           "index": "embedding_index", "filter": {"modelId": ObjectId(args.model_id)}}},
        {"$set": {"score": {"$meta": "vectorSearchScore"}}},
        {"$group": {"_id": "$UUID", "preferredLabel": {"$first": "$preferredLabel"}, "score": {"$max": "$score"}}},
        {"$sort": {"score": -1}},
        {"$limit": k},
    ]
    results = list(coll.aggregate(pipeline))
    print(f'\n"{args.query}" -> {args.collection}\n')
    if not results:
        sys.exit("No results: is embedding_index READY? Is --model-id the one of the taxonomy you imported?")
    for r in results:
        print(f"  {r['score']:.3f}  {r['preferredLabel']}")


if __name__ == "__main__":
    main()
