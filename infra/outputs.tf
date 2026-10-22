output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "lake_storage_account" {
  value = azurerm_storage_account.lake.name
}

output "lake_blob_url" {
  value       = azurerm_storage_account.lake.primary_blob_endpoint
  description = "TP_ADLS_ACCOUNT_URL for a laptop run against the real lake (TP_LAKE_BACKEND=azure)."
}

output "function_app_name" {
  value       = azurerm_linux_function_app.collector.name
  description = "GitHub repository variable FUNCTION_APP_NAME."
}

output "function_principal_id" {
  value = azurerm_linux_function_app.collector.identity[0].principal_id
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "application_insights_name" {
  value = azurerm_application_insights.main.name
}

output "github_client_id" {
  value       = azuread_application.github.client_id
  description = "GitHub repository variable AZURE_CLIENT_ID."
}

output "tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}
