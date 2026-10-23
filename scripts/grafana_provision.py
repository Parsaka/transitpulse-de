"""Provision the Grafana Cloud stack: two data sources, the dashboard, and a public dashboard link.

Grafana Cloud Free has no Terraform-friendly OIDC, so this is a small idempotent script run once
by the owner (and again after dashboard changes). It never prints secrets.

Environment:
  GRAFANA_URL            https://<stack>.grafana.net
  GRAFANA_TOKEN          service account token with Admin role (Administration > Service accounts)
  AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID
  GRAFANA_AZURE_CLIENT_ID, GRAFANA_AZURE_CLIENT_SECRET   (terraform output grafana_client_id / grafana_client_secret)
  LOG_ANALYTICS_RESOURCE_ID  /subscriptions/.../resourceGroups/rg-transitpulse-dev/providers/Microsoft.OperationalInsights/workspaces/log-transitpulse-dev
  STATUS_URL             https://<account>.z1.web.core.windows.net  (no trailing slash)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

ENV = {
    k: os.environ.get(k, "")
    for k in (
        "GRAFANA_URL",
        "GRAFANA_TOKEN",
        "AZURE_TENANT_ID",
        "AZURE_SUBSCRIPTION_ID",
        "GRAFANA_AZURE_CLIENT_ID",
        "GRAFANA_AZURE_CLIENT_SECRET",
        "LOG_ANALYTICS_RESOURCE_ID",
        "STATUS_URL",
    )
}
missing = [k for k, v in ENV.items() if not v]
if missing:
    sys.exit(f"missing environment variables: {', '.join(missing)}")

api = httpx.Client(
    base_url=ENV["GRAFANA_URL"].rstrip("/"),
    headers={"Authorization": f"Bearer {ENV['GRAFANA_TOKEN']}", "Content-Type": "application/json"},
    timeout=60,
)


def upsert_datasource(body: dict) -> str:
    r = api.get(f"/api/datasources/name/{body['name']}")
    if r.status_code == 200:
        ds_id = r.json()["id"]
        api.put(f"/api/datasources/{ds_id}", json=body).raise_for_status()
        return r.json()["uid"]
    r = api.post("/api/datasources", json=body)
    r.raise_for_status()
    return r.json()["datasource"]["uid"]


azure_uid = upsert_datasource(
    {
        "name": "Azure Monitor (TransitPulse)",
        "type": "grafana-azure-monitor-datasource",
        "access": "proxy",
        "jsonData": {
            "azureAuthType": "clientsecret",
            "cloudName": "azuremonitor",
            "tenantId": ENV["AZURE_TENANT_ID"],
            "clientId": ENV["GRAFANA_AZURE_CLIENT_ID"],
            "subscriptionId": ENV["AZURE_SUBSCRIPTION_ID"],
        },
        "secureJsonData": {"clientSecret": ENV["GRAFANA_AZURE_CLIENT_SECRET"]},
    }
)
infinity_uid = upsert_datasource(
    {
        "name": "Infinity (status.json)",
        "type": "yesoreyeram-infinity-datasource",
        "access": "proxy",
        "jsonData": {"allowedHosts": [ENV["STATUS_URL"]]},
    }
)

dashboard = json.loads(
    (Path(__file__).resolve().parent.parent / "grafana" / "dashboard.json").read_text(
        encoding="utf-8"
    )
)
text = json.dumps(dashboard)
for k, v in {
    "${DS_AZURE}": azure_uid,
    "${DS_INFINITY}": infinity_uid,
    "${LOG_ANALYTICS_RESOURCE_ID}": ENV["LOG_ANALYTICS_RESOURCE_ID"],
    "${STATUS_URL}": ENV["STATUS_URL"],
}.items():
    text = text.replace(k, v)
dashboard = json.loads(text)
dashboard["id"] = None
r = api.post(
    "/api/dashboards/db",
    json={
        "dashboard": dashboard,
        "overwrite": True,
        "message": "provisioned by scripts/grafana_provision.py",
    },
)
r.raise_for_status()
uid = r.json()["uid"]
url = ENV["GRAFANA_URL"].rstrip("/") + r.json()["url"]

# public dashboard (anyone with the link, no login); idempotent
pub = api.get(f"/api/dashboards/uid/{uid}/public-dashboards/")
if pub.status_code == 404:
    pub = api.post(
        f"/api/dashboards/uid/{uid}/public-dashboards/",
        json={"isEnabled": True, "timeSelectionEnabled": True, "share": "public"},
    )
pub.raise_for_status()
access = pub.json().get("accessToken")
print(
    json.dumps(
        {
            "dashboard": url,
            "public": f"{ENV['GRAFANA_URL'].rstrip('/')}/public-dashboards/{access}"
            if access
            else None,
        }
    )
)
