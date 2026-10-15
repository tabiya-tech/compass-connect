#!/bin/bash
# Idempotent: initiates the replica set, creates the user mongot connects with, and writes mongot's password file
# (mongot refuses to start unless the file is readable by its owner only).
set -euo pipefail

: "${MONGOT_PASSWORD:?MONGOT_PASSWORD must be set}"

mongosh --host mongod --quiet --eval '
  try { rs.status(); print("replica set already initiated"); }
  catch (e) { printjson(rs.initiate({_id: "rs0", members: [{_id: 0, host: "mongod:27017"}]})); }
'

until mongosh --host mongod --quiet --eval 'quit(db.hello().isWritablePrimary ? 0 : 1)'; do
  echo "waiting for the primary..."; sleep 1
done

mongosh --host mongod --quiet --eval '
  const admin = db.getSiblingDB("admin");
  if (!admin.getUser("mongotUser")) {
    admin.createUser({user: "mongotUser", pwd: process.env.MONGOT_PASSWORD, roles: ["searchCoordinator"]});
    print("created mongotUser");
  } else {
    print("mongotUser already exists");
  }
'

printf '%s' "$MONGOT_PASSWORD" > /secrets/passwordFile
chmod 400 /secrets/passwordFile
echo "mongot password file written"
