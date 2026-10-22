# Identity that GitHub Actions assumes through OIDC: no client secret anywhere.
# It can plan Terraform (reads the resource group and the state) and deploy the Function.

resource "azuread_application" "github" {
  display_name = "github-${local.name}"
}

resource "azuread_service_principal" "github" {
  client_id = azuread_application.github.client_id
}

locals {
  github_subjects = {
    main         = "repo:${var.github_repository}:ref:refs/heads/main"
    pull_request = "repo:${var.github_repository}:pull_request"
    env_azure    = "repo:${var.github_repository}:environment:azure"
  }
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
