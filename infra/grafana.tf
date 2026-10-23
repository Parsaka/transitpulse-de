# Read-only identity for Grafana Cloud's Azure Monitor data source: it can query Log Analytics
# and read metrics, nothing else. The client secret is a Terraform output (sensitive) that the
# owner pastes into the Grafana data source once; Grafana Cloud Free has no OIDC for Azure.

data "azuread_client_config" "current" {}

resource "azuread_application" "grafana" {
  display_name = "grafana-${local.name}"
  # The CI identity plans this stack and may only read applications it owns (no Graph roles).
  owners = [data.azuread_client_config.current.object_id, azuread_service_principal.github.object_id]
}

resource "azuread_service_principal" "grafana" {
  client_id = azuread_application.grafana.client_id
}

resource "time_rotating" "grafana_secret" {
  rotation_days = 180
}

resource "azuread_application_password" "grafana" {
  application_id = azuread_application.grafana.id
  display_name   = "grafana-cloud"
  rotate_when_changed = {
    rotation = time_rotating.grafana_secret.id
  }
}

resource "azurerm_role_assignment" "grafana_logs_reader" {
  scope                = azurerm_log_analytics_workspace.main.id
  role_definition_name = "Log Analytics Reader"
  principal_id         = azuread_service_principal.grafana.object_id
}

resource "azurerm_role_assignment" "grafana_monitoring_reader" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Monitoring Reader"
  principal_id         = azuread_service_principal.grafana.object_id
}

output "grafana_client_id" {
  value = azuread_application.grafana.client_id
}

output "grafana_client_secret" {
  value     = azuread_application_password.grafana.value
  sensitive = true
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.main.workspace_id
}

output "status_site_url" {
  value = azurerm_storage_account.lake.primary_web_endpoint
}
