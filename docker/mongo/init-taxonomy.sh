#!/bin/bash
# Idempotent: restores the taxonomy snapshot when the database is empty, then makes sure both vector search
# indexes exist and are queryable. Safe to run on every start.
set -euo pipefail

URI="mongodb://mongod:27017/?replicaSet=rs0"
ARCHIVE=/taxonomy/compass-taxonomy.archive.gz

LOCAL_ARCHIVE=/taxonomy/compass-taxonomy.archive.gz
CACHED_ARCHIVE=/cache/compass-taxonomy.archive.gz

count=$(mongosh "$URI" --quiet --eval 'print(db.getSiblingDB("compass-taxonomy").occupationmodelsembeddings.countDocuments({}))')
if [ "$count" -gt 0 ]; then
  echo "taxonomy already restored ($count occupation embeddings), skipping restore"
else
  if [ -f "$LOCAL_ARCHIVE" ]; then
    ARCHIVE=$LOCAL_ARCHIVE
    echo "using the local taxonomy archive docker/taxonomy/compass-taxonomy.archive.gz"
  else
    : "${TAXONOMY_ARCHIVE_URL:?ERROR: TAXONOMY_ARCHIVE_URL is not set in .env (or put compass-taxonomy.archive.gz in docker/taxonomy/)}"
    ARCHIVE=$CACHED_ARCHIVE
    if [ -f "$ARCHIVE" ] && [ -n "${TAXONOMY_ARCHIVE_SHA256:-}" ] && echo "$TAXONOMY_ARCHIVE_SHA256  $ARCHIVE" | sha256sum -c - >/dev/null 2>&1; then
      echo "using the previously downloaded taxonomy archive"
    else
      echo "downloading the taxonomy snapshot from $TAXONOMY_ARCHIVE_URL ..."
      wget -q --show-progress -O "$ARCHIVE.part" "$TAXONOMY_ARCHIVE_URL" \
        || { echo "ERROR: could not download the taxonomy archive. Check network access and TAXONOMY_ARCHIVE_URL," \
                  "or download it yourself into docker/taxonomy/compass-taxonomy.archive.gz" >&2; exit 1; }
      mv "$ARCHIVE.part" "$ARCHIVE"
    fi
  fi
  if [ "$ARCHIVE" != "$LOCAL_ARCHIVE" ] && [ -n "${TAXONOMY_ARCHIVE_SHA256:-}" ]; then
    echo "$TAXONOMY_ARCHIVE_SHA256  $ARCHIVE" | sha256sum -c - \
      || { echo "ERROR: the downloaded taxonomy archive does not match TAXONOMY_ARCHIVE_SHA256; deleting it" >&2; rm -f "$ARCHIVE"; exit 1; }
  fi
  echo "restoring taxonomy snapshot..."
  mongorestore --uri "$URI" --gzip --archive="$ARCHIVE"
fi

# Same definition as backend/scripts/embeddings/_common.py
mongosh "$URI" --quiet --eval '
  const definition = {fields: [
    {type: "vector", path: "embedding", numDimensions: 768, similarity: "cosine"},
    {type: "filter", path: "modelId"},
    {type: "filter", path: "UUID"},
  ]};
  const database = db.getSiblingDB("compass-taxonomy");
  for (const name of ["skillsmodelsembeddings", "occupationmodelsembeddings"]) {
    const collection = database.getCollection(name);
    let created = false;
    // mongot may still be starting: retry
    for (let i = 0; i < 60 && !created; i++) {
      try {
        if (collection.getSearchIndexes("embedding_index").length === 0) {
          collection.createSearchIndex("embedding_index", "vectorSearch", definition);
          print(name + ": embedding_index created");
        } else {
          print(name + ": embedding_index already exists");
        }
        created = true;
      } catch (e) { print("waiting for mongot: " + e.message); sleep(2000); }
    }
    if (!created) { print("ERROR: could not create index on " + name); quit(1); }
  }
  for (const name of ["skillsmodelsembeddings", "occupationmodelsembeddings"]) {
    let ready = false;
    for (let i = 0; i < 180 && !ready; i++) {
      ready = database.getCollection(name).getSearchIndexes("embedding_index").every(x => x.queryable);
      if (!ready) sleep(2000);
    }
    if (!ready) { print("ERROR: " + name + " index is not queryable"); quit(1); }
    print(name + ": index queryable");
  }
'
