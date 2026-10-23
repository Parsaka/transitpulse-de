# Identity that GitHub Actions assumes through OIDC: no client secret anywhere.
# It can plan Terraform (reads the resource group and the state) and deploy the Function.

resource "azuread_application" "github" {
  display_name = "github-${local.name}"
}

resource "azuread_service_principal" "github" {
  client_id = azuread_application.github.client_id
}

locals {
  # GitHub presents the subject with owner and repository IDs embedded for repositories created
  # after mid-2026 ("repo:Parsaka@115464667/transitpulse-de@1430309278:pull_request"); older
  # repositories still send the plain form. Both are registered.
  github_owner      = split("/", var.github_repository)[0]
  github_name       = split("/", var.github_repository)[1]
  github_repo_plain = "repo:${var.github_repository}"
  github_repo_ids   = "repo:${local.github_owner}@${var.github_owner_id}/${local.github_name}@${var.github_repository_id}"
  github_claim_tails = {
    main         = "ref:refs/heads/main"
    pull_request = "pull_request"
    env_azure    = "environment:azure"
    env_dbx      = "environment:databricks" # dbt prod job (Azure login for ops-sync + static site)
  }
  github_subjects = merge(
    { for k, v in local.github_claim_tails : "${k}-plain" => "${local.github_repo_plain}:${v}" },
    { for k, v in local.github_claim_tails : "${k}-ids" => "${local.github_repo_ids}:${v}" },
  )
}

resource "azuread_application_federated_identity_credential" "github" {
  for_each       = local.github_subjects
  application_id = azuread_application.github.id
  display_name   = "github-${each.key}"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = "https://token.actions.githubusercontent.com"
  subject        = each.value
}

resource "azurerm_role_assignment" "github_rg_contributor" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Contributor"
  principal_id         = azuread_service_principal.github.object_id
}

resource "azurerm_role_assignment" "github_tfstate" {
  scope                = var.tfstate_storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azuread_service_principal.github.object_id
}

resource "azurerm_role_assignment" "github_kv_reader" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azuread_service_principal.github.object_id
}

# Reading its own role assignment on the state account (outside the resource group) needs Reader
# there; without it the CI plan fails with 403 on azurerm_role_assignment.github_tfstate.
resource "azurerm_role_assignment" "github_tfstate_reader" {
  scope                = var.tfstate_storage_account_id
  role_definition_name = "Reader"
  principal_id         = azuread_service_principal.github.object_id
}

# CI publishes status.json and the dbt docs to the static website and lands collector metrics.
resource "azurerm_role_assignment" "github_lake_writer" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azuread_service_principal.github.object_id
}

# Terraform in CI reads the other application objects (the Grafana identity) through Microsoft
# Graph; a service principal may only read its own application unless it holds this read-only
# Graph role. Granting it needs an admin (the owner's laptop applies it once).
data "azuread_service_principal" "msgraph" {
  client_id = "00000003-0000-0000-c000-000000000000"
}

resource "azuread_app_role_assignment" "github_application_read" {
  app_role_id         = data.azuread_service_principal.msgraph.app_role_ids["Application.Read.All"]
  principal_object_id = azuread_service_principal.github.object_id
  resource_object_id  = data.azuread_service_principal.msgraph.object_id
}
