#!/usr/bin/env bash
# Build the Function package exactly like the deploy workflow and run it in the official Azure
# Functions Python image with Azurite, feeding it the fixture feed over HTTP. Passes only when the
# host indexes `collect` and one execution succeeds and writes Parquet. Catches what the cloud host
# reports as a silent "0 functions found" (for example the protobuf runtime clash of 2026-10-22).
#
# Usage: scripts/smoke_function.sh            (needs Docker; about 3 minutes)
set -euo pipefail
export MSYS_NO_PATHCONV=1 # Git Bash on Windows would rewrite /home/... paths

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=${SMOKE_DIR:-$ROOT/.smoke}
IMAGE=${FUNCTIONS_IMAGE:-mcr.microsoft.com/azure-functions/python:4-python3.11}
NET=tp-smoke-net
AZURITE_KEY="Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==" # Azurite's public dev key

cleanup() { docker rm -f tp-smoke-func tp-smoke-azurite tp-smoke-fixture >/dev/null 2>&1 || true; docker network rm $NET >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

if [ "${SMOKE_SKIP_BUILD:-0}" = 1 ] && [ -d "$WORK/wwwroot/.python_packages" ]; then
  echo "== reusing the package in $WORK/wwwroot (SMOKE_SKIP_BUILD=1) =="
  cp "$ROOT"/function_app/host.json "$ROOT"/function_app/function_app.py "$WORK/wwwroot/"
else
echo "== build package (same layout as deploy-function.yml, inside the Functions image) =="
rm -rf "$WORK" && mkdir -p "$WORK/wwwroot" "$WORK/wheel"
cp "$ROOT"/function_app/host.json "$ROOT"/function_app/function_app.py "$ROOT"/function_app/requirements.txt "$WORK/wwwroot/"
# transitpulse is pure Python, so its wheel can be built with whatever Python runs this script.
# The dependencies are resolved INSIDE the Functions image: same Python and, above all, the same
# glibc (Debian 11, 2.31). Wheels picked on a newer host (manylinux_2_34 cryptography) fail there.
ROOT_NATIVE=$(cd "$ROOT" && (pwd -W 2>/dev/null || pwd)) # a Windows Python needs C:/... not /c/...
WHEEL_DIR_NATIVE=$(cd "$WORK/wheel" && (pwd -W 2>/dev/null || pwd))
${PYTHON:-python} -m pip wheel -q --no-deps -w "$WHEEL_DIR_NATIVE" "$ROOT_NATIVE"
WHEEL=$(basename "$(ls "$WORK"/wheel/transitpulse-*.whl)")
docker run --rm -v "$ROOT/function_app/requirements.txt:/req.txt:ro" -v "$WORK/wheel:/wheel:ro" -v "$WORK/wwwroot:/out" "$IMAGE" bash -c   "pip install -q --no-cache-dir --target /out/.python_packages/lib/site-packages -r /req.txt 'transitpulse[azure] @ file:///wheel/$WHEEL' && du -sh /out/.python_packages | cut -f1"
fi

echo "== start Azurite and the fixture feed server =="
docker network create $NET >/dev/null
docker run -d --name tp-smoke-azurite --network $NET mcr.microsoft.com/azure-storage/azurite azurite --silent --blobHost 0.0.0.0 --queueHost 0.0.0.0 --tableHost 0.0.0.0 >/dev/null
docker run -d --name tp-smoke-fixture --network $NET -v "$ROOT/tests/fixtures:/srv:ro" -w /srv python:3.11-slim python -m http.server 8000 >/dev/null

echo "== start the Functions host =="
docker run -d --name tp-smoke-func --network $NET \
  -e AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
  -e AzureWebJobsScriptRoot=/home/site/wwwroot \
  -e FUNCTIONS_WORKER_RUNTIME=python \
  -e PYTHON_ISOLATE_WORKER_DEPENDENCIES=1 \
  -e "AzureWebJobsStorage=DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=$AZURITE_KEY;BlobEndpoint=http://tp-smoke-azurite:10000/devstoreaccount1;QueueEndpoint=http://tp-smoke-azurite:10001/devstoreaccount1;TableEndpoint=http://tp-smoke-azurite:10002/devstoreaccount1;" \
  -e TP_SCHEDULE="*/15 * * * * *" -e TP_FEEDS=vbb -e TP_LAKE_BACKEND=local -e TP_DATA_DIR=/tmp/tp -e TP_LOG_FORMAT=json \
  -e 'TP_FEED_URLS={"vbb":"http://tp-smoke-fixture:8000/vbb_sample.pb"}' \
  -v "$WORK/wwwroot:/home/site/wwwroot" "$IMAGE" >/dev/null

echo "== wait for indexing and one successful execution (up to 150 s) =="
ok=0
for i in $(seq 1 30); do
  sleep 5
  logs=$(docker logs tp-smoke-func 2>&1 || true)
  # host.json keeps Host.Startup at Warning, so "Found the following functions" is not printed;
  # a succeeded execution proves indexing anyway.
  if grep -qE "Executed 'Functions.collect' \(Succeeded" <<<"$logs"; then ok=1; break; fi
  if grep -qE "Executed 'Functions.collect' \(Failed" <<<"$logs"; then break; fi
done
grep -E "Executed 'Functions.collect'|functions loaded|VersionError|GLIBC|Traceback" <<<"$logs" | cut -c1-160 | head -6
if [ "$ok" != 1 ]; then echo "SMOKE FAILED"; docker logs tp-smoke-func 2>&1 | tail -60; exit 1; fi
echo "== files written inside the container =="
docker exec tp-smoke-func find /tmp/tp -name "*.parquet" | sed 's#^/tmp/tp/##'
echo "SMOKE OK"
