variable "resource_group_name" {
  description = "Name of the resource group to create or reuse."
  type        = string
  default     = "whalez-ai-rg"
}

variable "location" {
  description = "Azure location/region for the resources (e.g., eastus, westeurope)."
  type        = string
  default     = "eastus"
}

variable "cluster_name" {
  description = "Name of the AKS cluster."
  type        = string
  default     = "whalez-ai-aks"
}

variable "k8s_version" {
  description = "Kubernetes version for the AKS cluster."
  type        = string
  default     = "1.28.3"
}

variable "repo" {
  description = "GitHub repository in the form <org>/<repo> that will deploy this infrastructure via GitHub Actions."
  type        = string
}

variable "environment" {
  description = "Environment name used for the OIDC federated credential subject (e.g. production, staging)."
  type        = string
  default     = "production"
}