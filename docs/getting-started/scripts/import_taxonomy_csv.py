#!/usr/bin/env python3
"""
Imports a Tabiya Taxonomy Platform CSV export into a MongoDB laid out like the platform's own database,
so that backend/scripts/embeddings/generate_taxonomy_embeddings.py can read it unchanged.

Collections written:
  modelinfos                      <- model_info.csv
  occupationmodels                <- occupations.csv
  skillmodels                     <- skills.csv
  occupationtoskillrelationmodels <- occupation_to_skill_relations.csv

Groups, hierarchies and skill-to-skill relations are not imported: neither the embeddings script nor the backend reads them.

Dry run (default) parses, validates and prints a sample; --hot-run writes.

--skills-limit N keeps all the occupations but only the N most used skills (and the relations to them), so the
embeddings fit a small database such as the Atlas free tier. Skills are ranked by
2 x essential links + 3 x high-signal links + links from ICATUS occupations + total links;
skills used by ICATUS (unpaid work) occupations are always kept.

Usage:
  python import_taxonomy_csv.py --csv-dir ./extracted --model-id 68933862382aab4c7de13ec6 [--skills-limit 5500] [--hot-run] [--drop]
"""
import argparse
import csv
import sys
from datetime import datetime
from pprint import pformat

from bson import ObjectId
from pymongo import ASCENDING, MongoClient

csv.field_size_limit(sys.maxsize)

MODEL_INFOS = "modelinfos"
OCCUPATIONS = "occupationmodels"
SKILLS = "skillmodels"
RELATIONS = "occupationtoskillrelationmodels"


def read_csv(csv_dir: str, name: str) -> list[dict]:
    with open(f"{csv_dir}/{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def to_list(value: str) -> list[str]:
    """Multi-valued CSV fields (UUIDHISTORY, ALTLABELS) are newline separated."""
    return [v.strip() for v in value.split("\n") if v.strip()]


def to_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def to_date(value: str) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def to_float_or_none(value: str) -> float | None:
    return float(value) if value.strip() else None


def uuid_fields(uuid_history_raw: str) -> dict:
    # The history is newest first: the current UUID is [0], the origin is [-1]
    # (confirmed by the model's release notes; the embeddings script also uses [-1] as originUUID).
    history = to_list(uuid_history_raw)
    if not history:
        raise ValueError("empty UUIDHISTORY")
    return {"UUID": history[0], "UUIDHistory": history}


def build_model_info(rows: list[dict], model_id: ObjectId) -> dict:
    if len(rows) != 1:
        raise ValueError(f"expected exactly 1 model_info row, got {len(rows)}")
    r = rows[0]
    return {
        "_id": model_id,
        **uuid_fields(r["UUIDHISTORY"]),
        "name": r["NAME"],
        "locale": r["LOCALE"],
        "description": r["DESCRIPTION"],
        "version": r["VERSION"],
        "released": to_bool(r["RELEASED"]),
        "releaseNotes": r["RELEASENOTES"],
        "createdAt": to_date(r["CREATEDAT"]),
        "updatedAt": to_date(r["UPDATEDAT"]),
    }


def build_occupation(r: dict, model_id: ObjectId) -> dict:
    return {
        "_id": ObjectId(r["ID"]),
        "modelId": model_id,
        **uuid_fields(r["UUIDHISTORY"]),
        "originUri": r["ORIGINURI"],
        "occupationGroupCode": r["OCCUPATIONGROUPCODE"],
        "code": r["CODE"],
        "definition": r["DEFINITION"],
        "scopeNote": r["SCOPENOTE"],
        "regulatedProfessionNote": r["REGULATEDPROFESSIONNOTE"],
        "occupationType": r["OCCUPATIONTYPE"],
        "isLocalized": to_bool(r["ISLOCALIZED"]),
        "preferredLabel": r["PREFERREDLABEL"],
        "altLabels": to_list(r["ALTLABELS"]),
        "description": r["DESCRIPTION"],
        "createdAt": to_date(r["CREATEDAT"]),
        "updatedAt": to_date(r["UPDATEDAT"]),
    }


def build_skill(r: dict, model_id: ObjectId) -> dict:
    return {
        "_id": ObjectId(r["ID"]),
        "modelId": model_id,
        **uuid_fields(r["UUIDHISTORY"]),
        "originUri": r["ORIGINURI"],
        "definition": r["DEFINITION"],
        "scopeNote": r["SCOPENOTE"],
        "reuseLevel": r["REUSELEVEL"],
        "skillType": r["SKILLTYPE"],
        "isLocalized": to_bool(r["ISLOCALIZED"]),
        "preferredLabel": r["PREFERREDLABEL"],
        "altLabels": to_list(r["ALTLABELS"]),
        "description": r["DESCRIPTION"],
        "createdAt": to_date(r["CREATEDAT"]),
        "updatedAt": to_date(r["UPDATEDAT"]),
    }


def build_relation(r: dict, model_id: ObjectId) -> dict:
    # Field names match what backend/app/vector_search/esco_search_service.py queries
    return {
        "modelId": model_id,
        "requiringOccupationId": ObjectId(r["OCCUPATIONID"]),
        "requiringOccupationType": r["OCCUPATIONTYPE"],
        "requiredSkillId": ObjectId(r["SKILLID"]),
        "relationType": r["RELATIONTYPE"],
        "signallingValueLabel": r["SIGNALLINGVALUELABEL"],
        "signallingValue": to_float_or_none(r["SIGNALLINGVALUE"]),
        "createdAt": to_date(r["CREATEDAT"]),
        "updatedAt": to_date(r["UPDATEDAT"]),
    }


def is_icatus(occupation_code: str) -> bool:
    return occupation_code.startswith("I")


def select_top_skills(skills: list[dict], occupations: list[dict], relations: list[dict], limit: int) -> set:
    """Returns the _ids of the `limit` most used skills (see the module docstring for the ranking)."""
    icatus_occupation_ids = {o["_id"] for o in occupations if is_icatus(o["code"])}
    score: dict = {}
    forced: set = set()
    for r in relations:
        skill_id = r["requiredSkillId"]
        points = 1
        if r["relationType"] == "essential":
            points += 2
        if r["signallingValueLabel"] == "high":
            points += 3
        if r["requiringOccupationId"] in icatus_occupation_ids:
            points += 1
            forced.add(skill_id)
        score[skill_id] = score.get(skill_id, 0) + points
    ranked = sorted((s["_id"] for s in skills), key=lambda skill_id: (-score.get(skill_id, 0), str(skill_id)))
    selected = set(forced)
    for skill_id in ranked:
        if len(selected) >= limit:
            break
        selected.add(skill_id)
    return selected


def validate(model_info: dict, occupations: list[dict], skills: list[dict], relations: list[dict]) -> list[str]:
    problems = []
    for name, docs in (("occupations", occupations), ("skills", skills)):
        ids = [d["_id"] for d in docs]
        if len(ids) != len(set(ids)):
            problems.append(f"{name}: duplicate _id values")
        uuids = [d["UUID"] for d in docs]
        if len(uuids) != len(set(uuids)):
            problems.append(f"{name}: duplicate current UUIDs")
        no_label = sum(1 for d in docs if not d["preferredLabel"])
        if no_label:
            problems.append(f"{name}: {no_label} without preferredLabel")

    occupation_ids = {d["_id"] for d in occupations}
    skill_ids = {d["_id"] for d in skills}
    dangling_occ = sum(1 for r in relations if r["requiringOccupationId"] not in occupation_ids)
    dangling_skill = sum(1 for r in relations if r["requiredSkillId"] not in skill_ids)
    if dangling_occ:
        problems.append(f"relations: {dangling_occ} point to unknown occupations")
    if dangling_skill:
        problems.append(f"relations: {dangling_skill} point to unknown skills")

    # The model id should be older than (or equal to) the records created for it
    model_ts = model_info["_id"].generation_time
    newer = sum(1 for d in occupations + skills if d["_id"].generation_time < model_ts)
    if newer:
        problems.append(f"{newer} records have ObjectIds older than the model id: is --model-id correct?")
    return problems


def summarize(occupations: list[dict], skills: list[dict], relations: list[dict]) -> None:
    def count(docs, key):
        out: dict = {}
        for d in docs:
            out[d[key]] = out.get(d[key], 0) + 1
        return dict(sorted(out.items(), key=lambda kv: str(kv[0])))

    print(f"occupations: {len(occupations)}  by occupationType={count(occupations, 'occupationType')}")
    icatus = sum(1 for d in occupations if d["code"].startswith("I"))
    print(f"   ICATUS (code starts with 'I'): {icatus}")
    print(f"skills: {len(skills)}  by skillType={count(skills, 'skillType')}")
    print(f"relations: {len(relations)}  by relationType={count(relations, 'relationType')}"
          f"  by signallingValueLabel={count(relations, 'signallingValueLabel')}")
    for name, docs in (("occupations", occupations), ("skills", skills)):
        empty_desc = sum(1 for d in docs if not d["description"])
        empty_alt = sum(1 for d in docs if not d["altLabels"])
        print(f"   {name}: {empty_desc} with empty description, {empty_alt} with no altLabels "
              f"(these get fewer than 3 embeddings)")


def write(db, docs_by_collection: dict[str, list[dict]], drop: bool) -> None:
    for name, docs in docs_by_collection.items():
        coll = db[name]
        existing = coll.count_documents({})
        if existing and not drop:
            raise SystemExit(f"'{name}' already has {existing} documents; re-run with --drop to replace them")
        if drop:
            coll.drop()
        for i in range(0, len(docs), 5000):
            coll.insert_many(docs[i:i + 5000], ordered=False)
        print(f"   wrote {coll.count_documents({})} docs to {name}")

    # Indexes matching the queries the embeddings script runs against the source DB
    db[OCCUPATIONS].create_index([("modelId", ASCENDING), ("code", ASCENDING)])
    db[SKILLS].create_index([("modelId", ASCENDING)])
    db[RELATIONS].create_index([("modelId", ASCENDING), ("requiringOccupationId", ASCENDING)])
    print("   indexes created")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--csv-dir", required=True)
    parser.add_argument("--model-id", required=True, help="ObjectId of the taxonomy model (the prefix of the export .zip name)")
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017")
    parser.add_argument("--db", default="tabiya-platform")
    parser.add_argument("--skills-limit", type=int, default=None,
                        help="Keep only the N most used skills (all occupations are kept). Default: keep all skills")
    parser.add_argument("--hot-run", action="store_true", help="Actually write to MongoDB")
    parser.add_argument("--drop", action="store_true", help="Drop the target collections before writing")
    args = parser.parse_args()

    model_id = ObjectId(args.model_id)
    print(f"Reading CSVs from {args.csv_dir} for model {model_id}")
    model_info = build_model_info(read_csv(args.csv_dir, "model_info"), model_id)
    occupations = [build_occupation(r, model_id) for r in read_csv(args.csv_dir, "occupations")]
    skills = [build_skill(r, model_id) for r in read_csv(args.csv_dir, "skills")]
    relations = [build_relation(r, model_id) for r in read_csv(args.csv_dir, "occupation_to_skill_relations")]

    if args.skills_limit is not None:
        total_skills = len(skills)
        keep = select_top_skills(skills, occupations, relations, args.skills_limit)
        skills = [s for s in skills if s["_id"] in keep]
        relations = [r for r in relations if r["requiredSkillId"] in keep]
        print(f"Partial taxonomy: kept {len(skills)} of {total_skills} skills (limit {args.skills_limit}, ICATUS skills always kept)")

    print(f"\nModel: {model_info['name']} {model_info['version']} (UUID {model_info['UUID']})\n")
    summarize(occupations, skills, relations)

    problems = validate(model_info, occupations, skills, relations)
    print("\nValidation: " + ("OK" if not problems else "PROBLEMS"))
    for p in problems:
        print(f"   - {p}")

    sample = next(d for d in occupations if d["code"] == "0110.1")
    print("\nSample occupation (code 0110.1):\n" + pformat(sample, width=120)[:1500])

    if problems:
        raise SystemExit("\nNot writing: fix the validation problems first.")
    if not args.hot_run:
        print(f"\nDRY RUN: nothing written. Re-run with --hot-run to write to {args.db}.")
        return

    print(f"\nWriting to {args.mongo_uri} / {args.db}")
    db = MongoClient(args.mongo_uri)[args.db]
    write(db, {MODEL_INFOS: [model_info], OCCUPATIONS: occupations, SKILLS: skills, RELATIONS: relations}, args.drop)
    print("Done.")


if __name__ == "__main__":
    main()
