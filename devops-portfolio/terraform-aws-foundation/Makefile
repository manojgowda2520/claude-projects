# Thin wrapper so every environment is driven the same way.
#   make plan ENV=dev
#   make apply ENV=prod
ENV ?= dev
DIR := envs/$(ENV)

.PHONY: help init fmt validate lint security plan apply destroy clean check

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

init: ## terraform init for $(ENV)
	terraform -chdir=$(DIR) init -backend-config=backend.hcl

fmt: ## Rewrite all files to canonical HCL formatting
	terraform fmt -recursive .

validate: ## Validate the configuration for $(ENV)
	terraform -chdir=$(DIR) validate

lint: ## Run tflint across modules and environments
	tflint --recursive

security: ## Run static security analysis
	trivy config --severity HIGH,CRITICAL .
	checkov -d . --quiet --compact

plan: ## Show the execution plan for $(ENV)
	terraform -chdir=$(DIR) plan -out=tfplan

apply: ## Apply the saved plan for $(ENV)
	terraform -chdir=$(DIR) apply tfplan

destroy: ## Tear down $(ENV) - always run this when you stop working
	terraform -chdir=$(DIR) destroy

check: fmt validate lint security ## Everything CI runs, locally

clean: ## Remove local plan files and provider caches
	find . -name tfplan -delete
	find . -type d -name .terraform -prune -exec rm -rf {} +
