#!/usr/bin/env bash
# Asks Databricks to start the dbt SQL warehouse and reports whether the workspace lets it.
# Prints one line "gate=<ok|inactive|quota|other>" plus the reason, never the token.
# Exit code: 0 ok, 2 workspace INACTIVE, 3 daily quota, 1 anything else.
# Free Edition marks a workspace INACTIVE when nobody signs in to the website for a while
# (token/API traffic does not count); only a browser sign-in brings it back (docs/databricks.md).
set -uo pipefail
: "${DATABRICKS_HOST:?}" "${DATABRICKS_TOKEN:?}"
WH="${WAREHOUSE_ID:-a25edf12d5fff14a}"
body=$(curl -s -m 60 -w '\n%{http_code}' -X POST -H "Authorization: Bearer $DATABRICKS_TOKEN" \
  "$DATABRICKS_HOST/api/2.0/sql/warehouses/$WH/start")
code=${body##*$'\n'}
body=${body%$'\n'*}
if [ "$code" = "200" ]; then
  echo "gate=ok (warehouse start accepted)"
  exit 0
fi
if grep -q 'INACTIVE' <<<"$body"; then
  echo "gate=inactive HTTP $code: $(head -c 400 <<<"$body")"
  exit 2
fi
if grep -qi 'daily limit\|RESOURCE_EXHAUSTED' <<<"$body"; then
  echo "gate=quota HTTP $code: $(head -c 400 <<<"$body")"
  exit 3
fi
echo "gate=other HTTP $code: $(head -c 400 <<<"$body")"
exit 1
