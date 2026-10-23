locals {
  name = "${var.project}-${var.environment}"
  tags = {
    project     = var.project
    environment = var.environment
    managed_by  = "terraform"
  }
}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 5
  special = false
  upper   = false
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

# ---------- Data lake (raw deltas + collector state) ----------

resource "azurerm_storage_account" "lake" {
  name                            = "st${var.project}${var.environment}${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  is_hns_enabled                  = true # ADLS Gen2
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_storage_data_lake_gen2_filesystem" "lake" {
  name               = "lake"
  storage_account_id = azurerm_storage_account.lake.id
}

# Raw deltas are small (tens of MB a day); keep them, just move cold ones to the Cool tier.
resource "azurerm_storage_management_policy" "lake" {
  storage_account_id = azurerm_storage_account.lake.id

  rule {
    name    = "raw-to-cool"
    enabled = true
    filters {
      prefix_match = ["lake/raw/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than = 30
      }
    }
  }
}

# Data-plane access for the administrator (Owner alone cannot read or write blobs).
resource "azurerm_role_assignment" "lake_admin" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.admin_principal_id
}

# ---------- Observability ----------

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.2 # the first 5 GB/month are free; this cap keeps a bug from costing money
  tags                = local.tags
}

resource "azurerm_application_insights" "main" {
  name                = "appi-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "other"
  sampling_percentage = 100
  tags                = local.tags
}

# ---------- Secrets ----------

resource "azurerm_key_vault" "main" {
  name                       = "kv-${var.project}-${random_string.suffix.result}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  tags                       = local.tags
}

resource "azurerm_role_assignment" "kv_admin" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = var.admin_principal_id
}

resource "azurerm_key_vault_secret" "alert_webhook" {
  name         = "alert-webhook"
  value        = var.alert_webhook_url
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.kv_admin]
}

# Databricks Free Edition cannot read the lake, so the Function also pushes each delta into a
# Unity Catalog Volume; the token never leaves Key Vault (Key Vault reference in the app setting).
resource "azurerm_key_vault_secret" "databricks_token" {
  name         = "databricks-token"
  value        = var.databricks_token
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.kv_admin]
}

# ---------- Collector: Azure Function, Consumption plan (free grant) ----------

# The Functions host needs its own general-purpose account (hierarchical namespace is not
# supported for AzureWebJobsStorage); it holds timer leases and the deployed package.
resource "azurerm_storage_account" "func" {
  name                            = "stfn${var.project}${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_service_plan" "func" {
  name                = "plan-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "Y1" # Consumption: 1M executions and 400k GB-s per month free
  tags                = local.tags
}

resource "azurerm_linux_function_app" "collector" {
  name                       = "func-${local.name}-${random_string.suffix.result}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  service_plan_id            = azurerm_service_plan.func.id
  storage_account_name       = azurerm_storage_account.func.name
  storage_account_access_key = azurerm_storage_account.func.primary_access_key
  https_only                 = true
  tags                       = local.tags

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_insights_connection_string = azurerm_application_insights.main.connection_string
    ftps_state                             = "Disabled"
    application_stack {
      python_version = var.python_version
    }
  }

  app_settings = {
    SCM_DO_BUILD_DURING_DEPLOYMENT = "false"
    # The worker bundles protobuf 5.x and would shadow ours (gtfs-realtime-bindings 3.x is generated
    # with protobuf 7.x): without isolation the import fails and the host silently indexes 0 functions.
    PYTHON_ISOLATE_WORKER_DEPENDENCIES = "1"
    ENABLE_ORYX_BUILD                  = "false"
    TP_SCHEDULE                        = var.schedule
    TP_FEEDS                           = var.feeds
    TP_LAKE_BACKEND                    = "azure"
    TP_ADLS_ACCOUNT_URL                = azurerm_storage_account.lake.primary_blob_endpoint
    TP_LAKE_CONTAINER                  = azurerm_storage_data_lake_gen2_filesystem.lake.name
    TP_LOG_FORMAT                      = "json"
    TP_USER_AGENT                      = var.user_agent
    TP_ALERT_WEBHOOK                   = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.alert_webhook.versionless_id})"
    TP_DATABRICKS_HOST                 = var.databricks_host
    TP_DATABRICKS_TOKEN                = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.databricks_token.versionless_id})"
    TP_VOLUME_PATH                     = var.databricks_volume_path
  }

  lifecycle {
    # Set by the deploy workflow (zip deploy), not by Terraform.
    ignore_changes = [
      app_settings["WEBSITE_RUN_FROM_PACKAGE"],
      app_settings["WEBSITE_ENABLE_SYNC_UPDATE_SITE"],
      tags["hidden-link: /app-insights-resource-id"],
    ]
  }
}

# The Function writes the lake with its managed identity: no storage key in any setting.
resource "azurerm_role_assignment" "func_lake_writer" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_linux_function_app.collector.identity[0].principal_id
}

resource "azurerm_role_assignment" "func_kv_reader" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_function_app.collector.identity[0].principal_id
}

# ---------- Alerting ----------

resource "azurerm_monitor_action_group" "ops" {
  name                = "ag-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "tpulse"
  tags                = local.tags

  email_receiver {
    name                    = "owner"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }
}

# One log alert (about 0.50 USD/month at 15-minute frequency) covering both failure modes:
# the collector went silent (no successful execution in 15 min) or it keeps failing.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "collector_unhealthy" {
  name                 = "alert-${local.name}-collector-unhealthy"
  resource_group_name  = azurerm_resource_group.main.name
  location             = azurerm_resource_group.main.location
  scopes               = [azurerm_application_insights.main.id]
  severity             = 1
  enabled              = true
  evaluation_frequency = "PT15M"
  window_duration      = "PT15M"
  description          = "No successful collector run in 15 minutes, or 3+ failed runs. Runbook: docs/runbook.md"
  tags                 = local.tags

  criteria {
    query                   = <<-KQL
      requests
      | where name == "collect"
      | summarize ok = countif(success == true), failed = countif(success == false)
      | where ok < 1 or failed >= 3
    KQL
    time_aggregation_method = "Count"
    operator                = "GreaterThan"
    threshold               = 0
  }

  auto_mitigation_enabled = true

  action {
    action_groups = [azurerm_monitor_action_group.ops.id]
  }
}

# ---------- Cost guardrail ----------

resource "azurerm_consumption_budget_resource_group" "main" {
  name              = "budget-${local.name}"
  resource_group_id = azurerm_resource_group.main.id
  amount            = var.budget_amount
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  dynamic "notification" {
    for_each = [50, 90, 100]
    content {
      enabled        = true
      threshold      = notification.value
      operator       = "GreaterThan"
      threshold_type = "Actual"
      contact_emails = [var.alert_email]
    }
  }
}

# ---------- Public status: static website on the lake storage account ----------
# Free (storage only): hosts status.json (read by Grafana and the project page) and the dbt docs.
# GitHub Pages is not available on a private repository with the Free plan.

resource "azurerm_storage_account_static_website" "status" {
  storage_account_id = azurerm_storage_account.lake.id
  index_document     = "index.html"
  error_404_document = "index.html"
}
