variable "subscription_id" {
  type        = string
  description = "Azure subscription ID."
}

variable "location" {
  type        = string
  default     = "swedencentral"
  description = <<-EOT
    Azure region. Azure for Students only allows belgiumcentral, swedencentral, denmarkeast,
    switzerlandnorth and italynorth (policy "Allowed resource deployment regions").
  EOT
}

variable "project" {
  type    = string
  default = "transitpulse"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "alert_email" {
  type        = string
  description = "Receives budget and pipeline alerts."
}

variable "budget_amount" {
  type        = number
  default     = 2
  description = "Monthly budget for the resource group in the subscription's currency; alerts at 50/90/100 percent."
}

variable "budget_start_date" {
  type        = string
  description = "First day of a month, RFC3339, e.g. 2026-11-01T00:00:00Z."
}

variable "admin_principal_id" {
  type        = string
  description = "Object ID of the human who administers Key Vault and may write to the lake (az ad signed-in-user show --query id -o tsv)."
}

variable "github_repository" {
  type        = string
  default     = "Parsaka/transitpulse-de"
  description = "owner/name of the GitHub repository whose Actions log in with OIDC."
}

variable "tfstate_storage_account_id" {
  type        = string
  description = "Resource ID of the Terraform state storage account (so CI can read and lock the state)."
}

variable "status_cors_origins" {
  type        = list(string)
  default     = ["https://parsa-kamali.de", "https://www.parsa-kamali.de"]
  description = "Origins allowed to read the status site (status.json) from the browser."
}

variable "feeds" {
  type        = string
  default     = "vbb"
  description = "Comma-separated feeds the minute timer collects (regional, cheap per poll)."
}

variable "national_feeds" {
  type        = string
  default     = "gtfsde"
  description = "Feeds of the slower nationwide timer (about 13 GB-s per poll, docs/scale.md)."
}

variable "national_schedule" {
  type        = string
  default     = "0 */5 * * * *"
  description = "NCRONTAB schedule of the nationwide timer. Every minute would exceed the free Functions grant."
}

variable "schedule" {
  type        = string
  default     = "0 * * * * *"
  description = "NCRONTAB schedule of the collector (default: every minute). Changed in place for the polling experiment."
}

variable "python_version" {
  type    = string
  default = "3.11"
}

variable "alert_webhook_url" {
  type        = string
  default     = "none"
  sensitive   = true
  description = "Chat webhook for pipeline alerts, stored in Key Vault. 'none' disables it."
}

variable "user_agent" {
  type        = string
  default     = "transitpulse-de/0.1 (portfolio project; https://github.com/Parsaka/transitpulse-de)"
  description = "Sent to the feed providers, who ask for an informative User-Agent."
}

variable "github_owner_id" {
  type        = number
  default     = 115464667
  description = "Numeric GitHub owner ID (gh api repos/<owner>/<name> --jq .owner.id); part of the OIDC subject."
}

variable "github_repository_id" {
  type        = number
  default     = 1430309278
  description = "Numeric GitHub repository ID (gh api repos/<owner>/<name> --jq .id); part of the OIDC subject."
}

variable "databricks_host" {
  type        = string
  default     = ""
  description = "Databricks Free Edition workspace URL (https://dbc-....cloud.databricks.com). Empty = the Function writes the Azure lake only."
}

variable "databricks_token" {
  type        = string
  default     = "none"
  sensitive   = true
  description = "Personal access token for the Files API upload into the landing Volume, stored in Key Vault. 'none' disables the Volume sink."
}

variable "databricks_volume_path" {
  type    = string
  default = "/Volumes/workspace/tp_landing/raw"
}

variable "weather_schedule" {
  type        = string
  default     = "0 7 * * * *"
  description = "NCRONTAB schedule of the hourly Open-Meteo fetch (minute 7, after the hour's observations exist)."
}
