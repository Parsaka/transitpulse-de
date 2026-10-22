#!/usr/bin/env bash
# One-time: storage account for the Terraform remote state (blob versioning on, no public access).
# Usage: scripts/bootstrap_tfstate.sh [location]   -> prints the backend.hcl values
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash on Windows would otherwise rewrite /subscriptions/... as a path
LOCATION="${1:-swedencentral}"
RG="rg-transitpulse-tfstate"
NAME="sttptfstate$(python -c 'import secrets; print(secrets.token_hex(3))')"
az group create -n "$RG" -l "$LOCATION" -o none
az storage account create -n "$NAME" -g "$RG" -l "$LOCATION" --sku Standard_LRS --kind StorageV2 \
  --min-tls-version TLS1_2 --allow-blob-public-access false -o none
az storage account blob-service-properties update --account-name "$NAME" -g "$RG" \
  --enable-versioning true -o none
ME=$(az ad signed-in-user show --query id -o tsv)
SCOPE=$(az storage account show -n "$NAME" -g "$RG" --query id -o tsv)
az role assignment create --assignee-object-id "$ME" --assignee-principal-type User \
  --role "Storage Blob Data Contributor" --scope "$SCOPE" -o none
# RBAC takes a moment to propagate before the container can be created with AAD auth.
for i in 1 2 3 4 5 6; do
  az storage container create --account-name "$NAME" -n tfstate --auth-mode login -o none 2>/dev/null && break
  sleep 10
done
cat <<OUT
resource_group_name  = "$RG"
storage_account_name = "$NAME"
container_name       = "tfstate"
key                  = "transitpulse-dev.tfstate"
use_azuread_auth     = true
# tfstate_storage_account_id = "$SCOPE"
OUT
