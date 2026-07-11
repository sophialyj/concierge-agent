# Terraform Infrastructure Configuration

This directory contains the Infrastructure as Code (IaC) configuration files using Terraform to provision the Google Cloud Platform (GCP) resources required by the Concierge Agent.

## Resources Provisioned
1. **Google Cloud Run (or Vertex AI Agent Engine)**: Deploys and runs the FastAPI containerized agent application.
2. **Artifact Registry**: Docker repository to store the agent container image.
3. **Google Cloud Storage (GCS) Buckets**: 
   - Feedback logging bucket.
   - Tracing/OTel telemetry bucket.
   - Remote Terraform state storage bucket.
4. **Service Account**: Configures least-privilege IAM roles for the application runtime:
   - `roles/aiplatform.user`
   - `roles/storage.objectAdmin`
   - `roles/cloudtrace.agent`
5. **APIs Enabled**: Automatically enables necessary Google Cloud APIs (`run.googleapis.com`, `aiplatform.googleapis.com`, `storage.googleapis.com`, `cloudtrace.googleapis.com`).

## How to Apply

1. Initialize Terraform:
   ```bash
   terraform init
   ```

2. Plan the deployment to verify resources:
   ```bash
   terraform plan -var-file="vars/env.tfvars"
   ```

3. Apply the changes:
   ```bash
   terraform apply -var-file="vars/env.tfvars" -auto-approve
   ```
