# Azure setup (free tier, Terraform)

Everything in Azure is created by `infra/` with Terraform. The only manual step is the storage
account that holds the Terraform state itself.

## One-time
1. `az login --tenant <tenant> --scope https://management.azure.com//.default` (the Azure for
   Students tenant enforces MFA through security defaults; a cached token without it is rejected
   with `AADSTS530035`).
2. `scripts/bootstrap_tfstate.sh swedencentral` creates `rg-transitpulse-tfstate`, a storage
   account with blob versioning and the `tfstate` container, and prints the `backend.hcl` values.
3. In `infra/`, copy `backend.hcl.example` to `backend.hcl` and `terraform.tfvars.example` to
   `terraform.tfvars` and fill them in (both are git-ignored).
4. `terraform init -backend-config=backend.hcl && terraform plan -out tfplan && terraform apply tfplan`
   (on Git Bash for Windows set `MSYS_NO_PATHCONV=1`, otherwise `/subscriptions/...` scopes are
   rewritten as file paths and Azure answers `MissingSubscription`).
5. Set the GitHub repository variables printed by `terraform output` (see below), then push: the
   deploy workflow builds the Function package and deploys it; nothing stores a secret.

## What the stack contains
| Resource | Purpose | Free because |
|---|---|---|
| Resource group `rg-transitpulse-dev` | everything below | |
| Storage account (ADLS Gen2), container `lake` | raw Parquet deltas, collector state | tens of MB a day; raw moves to Cool after 30 days |
| Storage account (Function host) | timer leases, deployed package | a few MB |
| Service plan Y1 (Linux Consumption) + Function App, Python 3.11 | the collector, every 60 s | 1M executions and 400k GB-s per month free |
| System-assigned identity + role `Storage Blob Data Contributor` on the lake | write without keys | |
| Log Analytics (daily cap 0.2 GB) + Application Insights | JSON logs, execution results | first 5 GB per month free |
| Key Vault (RBAC) with secret `alert-webhook` | chat webhook, read by the Function through a Key Vault reference | fractions of a cent |
| Action group (email) + scheduled-query alert `collector-unhealthy` | no successful run in 15 min, or 3+ failures | about 0.50 USD per month |
| Budget `budget-transitpulse-dev` | 2 per month, alerts at 50/90/100 percent | free |
| Entra app `github-transitpulse-dev` + 6 federated credentials | GitHub Actions log in with OIDC (main, pull requests, environment `azure`; each in the plain subject form and in the newer form with owner and repository IDs, which this repository uses) | free |

## Lessons from doing it (2026-10-22)
- **OIDC subject with IDs:** the first plan from a pull request failed with `AADSTS700213` because
  GitHub presented `repo:Parsaka@115464667/transitpulse-de@1430309278:pull_request`, not
  `repo:Parsaka/transitpulse-de:pull_request`. New repositories get the ID form; Terraform now
  registers both (`github_owner_id`, `github_repository_id`).
- **Git Bash rewrites `/subscriptions/...`** into `C:/Program Files/Git/subscriptions/...` in any
  argument: `az role assignment create --scope` failed with `MissingSubscription` and a GitHub
  variable was stored mangled. `export MSYS_NO_PATHCONV=1` before such commands.
- The whole stack applied on the first try (27 resources, about 4 minutes); re-plan: no changes.

## GitHub repository variables
| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | `terraform output github_client_id` |
| `AZURE_TENANT_ID` | `terraform output tenant_id` |
| `AZURE_SUBSCRIPTION_ID` | subscription id |
| `AZURE_RESOURCE_GROUP` | `rg-transitpulse-dev` |
| `FUNCTION_APP_NAME` | `terraform output function_app_name` |
| `TFSTATE_RESOURCE_GROUP`, `TFSTATE_STORAGE_ACCOUNT`, `TFSTATE_STORAGE_ACCOUNT_ID` | from the bootstrap |
| `ALERT_EMAIL`, `ADMIN_PRINCIPAL_ID`, `BUDGET_START_DATE` | same values as `terraform.tfvars` |

The GitHub environment `azure` must exist (Settings > Environments); the free plan cannot require
reviewers on a private repository, so the apply stays a laptop step.

## Changing the polling interval
`schedule` in `terraform.tfvars` (NCRONTAB) and `terraform apply`: the Function reads it from the
app setting `TP_SCHEDULE`, no redeploy needed. This is the knob of the phase-6 interval experiment.

## Tear down
`terraform destroy` in `infra/` removes everything but the state account; delete
`rg-transitpulse-tfstate` last.
