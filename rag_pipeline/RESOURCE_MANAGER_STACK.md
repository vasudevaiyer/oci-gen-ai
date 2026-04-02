# OCI RAG Pipeline Resource Manager Stack

This guide describes how to deploy the OCI RAG Pipeline through OCI Resource Manager.

## What The Stack Provisions

- VCN, subnets, NSGs, route tables, and gateways
- private Autonomous AI Database
- private application VM
- public jump host VM
- public API Gateway for the UI and APIs
- Vault secret for the generated application schema password

## Deployment Model

The design stays intentionally simple:

- Resource Manager zip = Terraform stack
- `app_source_url` = application source that the VM pulls during bootstrap

The stack zip does not bundle the application code itself.

## Required Inputs

Resource Manager auto-populates these OCI context variables when present in Terraform:

- `tenancy_ocid`
- `compartment_ocid`
- `region`

The operator still provides:

- `home_region`
- `vault_ocid`
- `kms_key_ocid`
- `adb_admin_password_secret_ocid`
- `instance_image_ocid`
- `ssh_public_key`
- `app_source_type`
- `app_source_url`
- `app_source_ref`

## Recommended First-Run Values

- `environment = dev`
- `region_code = ord`
- `vm_shape = VM.Standard.E4.Flex`
- `vm_ocpus = 2`
- `vm_memory_gbs = 16`
- `jump_host_shape = VM.Standard.E4.Flex`
- `jump_host_ocpus = 1`
- `jump_host_memory_gbs = 8`
- `adb_compute_count = 2`
- `adb_storage_size_gb = 50`
- `adb_db_version = 26ai`
- `app_source_type = git`
- `app_source_url = https://github.com/vasudevaiyer/oci-gen-ai.git`
- `app_source_ref = main`

## Resource Manager Console Steps

1. Open `Developer Services` -> `Resource Manager` -> `Stacks`.
2. Click `Create stack`.
3. Choose `My configuration`.
4. Upload the sanitized Resource Manager bundle.
5. Review the `schema.yaml` guided form.
6. Confirm the auto-populated OCI values.
7. Fill in the remaining required values.
8. Run `Plan`.
9. Review the plan.
10. Run `Apply`.

## Expected Outputs

After apply, the stack should expose:

- API Gateway base URL
- chat endpoint
- health endpoint
- app VM private IP
- jump host public IP
- Autonomous Database OCID and name
- generated application schema name
- generated application schema password secret name and OCID

## Post-Apply Validation

1. Open the API Gateway base URL in a browser.
2. Open `/governance`.
3. Upload a small `.txt` document.
4. Confirm `/health` returns `200`.
5. Ask a simple grounded question from the main UI.

## IAM Note

The application VM uses instance principals. If OCI Generative AI access or secret-bundle reads fail after deployment, verify that the required dynamic-group policies exist in the tenancy home region.
