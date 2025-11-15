#!/usr/bin/env bash
#
# This script illustrates how to set up secrets for CI/CD and environment variables
# required by the GitHub workflows in this repository.  It serves as an example and
# does not actually create any secrets; instead, it echoes the commands you should
# run in your own environment.

echo "To complete CI/CD setup, please create the following GitHub repository secrets:"
echo "  AZURE_CLIENT_ID       – Client ID of the Entra ID application created by Terraform"
echo "  AZURE_TENANT_ID       – Your Entra ID tenant ID"
echo "  AZURE_SUBSCRIPTION_ID – Your Azure subscription ID"
echo "  AZURE_RESOURCE_GROUP  – Resource group name for the AKS cluster"
echo "  AZURE_AKS_CLUSTER     – Name of the AKS cluster"
echo
echo "For CI and security scans, no additional secrets are required.  The CodeQL and Trivy
      jobs will run with read‑only permissions on your repository."