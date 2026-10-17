#!/bin/sh
# Container entrypoint: make the data layout, then guarantee an API token.
#
# API_TOKEN from the environment (or server/.env) always wins. When it is empty
# a long random key is generated once into the mounted data folder, so the
# server never exposes an unauthenticated remote API by accident.
set -e

DATA_DIR="${DATA_DIR:-/app/data}"
TOKEN_FILE="${TOKEN_FILE:-$DATA_DIR/.api-token}"
EXPORT_DIR="${EXPORT_DIR:-$DATA_DIR/exports}"
TMP_DIR="${TMP_DIR:-$DATA_DIR/tmp}"

mkdir -p "$EXPORT_DIR" "$TMP_DIR"

if [ -z "${API_TOKEN:-}" ]; then
    if [ -f "$TOKEN_FILE" ]; then
        API_TOKEN="$(cat "$TOKEN_FILE")"
    else
        API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
        umask 077
        printf '%s' "$API_TOKEN" > "$TOKEN_FILE"
        echo "[entrypoint] Generated a new API token at $TOKEN_FILE"
    fi
    export API_TOKEN
    echo "[entrypoint] Read the key from $TOKEN_FILE for the client and dashboard."
else
    echo "[entrypoint] Using API_TOKEN from the environment."
fi

exec "$@"
