// Terraform configuration for provisioning AKS cluster and federated identity resources on Azure.

terraform {
  required_version = ">= 1.2.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.25"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = ">= 2.44"
    }
  }
}

provider "azurerm" {
  features {}
}

provider "azuread" {}

// Create a resource group for the AKS cluster and identities.
resource "azurerm_resource_group" "whalez_ai" {
  name     = var.resource_group_name
  location = var.location
}

// Create an AKS cluster with Workload Identity enabled.
resource "azurerm_kubernetes_cluster" "whalez_ai_aks" {
  name                = var.cluster_name
  location            = var.location
  resource_group_name = azurerm_resource_group.whalez_ai.name

  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  default_node_pool {
    name       = "systempool"
    vm_size    = "Standard_DS2_v2"
    node_count = 1
  }

  // Use system-assigned managed identity for cluster components.
  identity {
    type = "SystemAssigned"
  }

  tags = {
    environment = var.environment
  }
}

// Azure AD application to represent GitHub Actions in Entra ID.
resource "azuread_application" "github_app" {
  display_name = "whalez-ai-github-deployer"
}

// Service principal for the application.
resource "azuread_service_principal" "github_sp" {
  application_id = azuread_application.github_app.application_id
}

// Federated identity credential to allow OIDC tokens from GitHub to be exchanged for Azure access tokens.
resource "azuread_application_federated_identity_credential" "github_oidc" {
  application_object_id = azuread_application.github_app.object_id
  display_name          = "github-oidc"
  description           = "OIDC trust for GitHub Actions to deploy Whalez-AI"
  issuer                = "https://token.actions.githubusercontent.com"
  subject               = "repo:${var.repo}:environment:${var.environment}"
  audiences             = ["api://AzureADTokenExchange"]
}

// Assign the service principal contributor permissions on the AKS cluster so it can deploy resources.
resource "azurerm_role_assignment" "aks_contributor" {
  principal_id         = azuread_service_principal.github_sp.object_id
  role_definition_name = "Azure Kubernetes Service RBAC Writer"
  scope                = azurerm_kubernetes_cluster.whalez_ai_aks.id
}