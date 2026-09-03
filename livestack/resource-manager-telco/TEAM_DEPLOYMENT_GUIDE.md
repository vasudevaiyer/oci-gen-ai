# Telco Native Stack: Team Deployment Guide

This guide explains how to deploy the VM-based Telco Native test stack in a
different OCI tenancy. OKE is not part of this deployment.

## What the deployment creates

The stack creates a VCN, private Autonomous AI Database, application VM with a
public IP, private wallet storage, and the IAM access needed by the VM. The VM
downloads the application source, bootstraps the database, and starts the
application on port `8510`.

The VM bootstrap creates the application schema, applies the versioned schema
migrations, seeds the Telco demo data, and applies the security objects before
starting the application. It also enables firewalld and opens the configured
application port. ONNX model delivery and embedding population are optional
and remain deferred unless the model artifact is supplied to the database.

## 1. Prepare repository access

The application source is:

```text
https://github.com/vasudevaiyer/oci-gen-ai.git
```

Use branch `main`. The application is in the `telco-native/` directory. The
Resource Manager operator must be able to access the repository. If it is
private, configure the required Git authentication before deployment.

## 2. Prepare OCI prerequisites

In the target tenancy, identify or create:

1. A target compartment.
2. An OCI Vault in that compartment.
3. An AES KMS key in that Vault.
4. An Oracle Linux image OCID available in the deployment region.
5. An SSH key pair. Only the public key is entered into Resource Manager.
6. Sufficient quotas for a private Autonomous AI Database, VCN, VM, public
   IPs, and Object Storage.

The operator needs permission to create the stack resources in the target
compartment. The stack also creates a dynamic group and policy in the tenancy
home region when `app_dynamic_group_enabled` is `true`.

## 3. Package the Terraform stack

Create an upload zip containing the *contents* of this directory at the root
of the archive. Do not include `.terraform/`, Terraform state, private keys,
wallets, passwords, or environment-specific variable files.

The archive root should contain files such as:

```text
provider.tf
variables.tf
outputs.tf
schema.yaml
templates/bootstrap_app.sh.tftpl
```

## 4. Create the Resource Manager stack

In the OCI Console:

1. Open **Developer Services → Resource Manager → Stacks**.
2. Select **Create stack**.
3. Choose **My configuration** and upload the stack zip.
4. Select Terraform version `1.5.x`.
5. If the working-directory field is shown, set it to `.`. If it is not
   shown, leave it unchanged; ZIP uploads use the archive root by default.
6. Give the stack a unique name, such as `telco-native-test`.
7. Continue to the variable form.

The ZIP must contain `provider.tf`, `main.tf`, `variables.tf`, and
`schema.yaml` directly at its root. Do not upload a ZIP whose first path
component is `resource-manager-telco/`; that nested layout requires a working
directory setting that the Console may not display.

### Alternative: create the stack with OCI CLI

Use this option when the Console does not accept the upload zip. The commands
require OCI CLI authentication with permission to manage Resource Manager in
the target compartment.

From the directory containing the Terraform files, create the archive:

```bash
rm -f /tmp/telco-native-resource-manager.zip
zip -qr /tmp/telco-native-resource-manager.zip . \
  -x '.terraform/*' 'terraform.tfstate*' '*.auto.tfvars' 'terraform.tfvars' \
     '.codex' '.codex/*' '*.key' '*.pem' '*.wallet' '*.env'
```

Create a protected variables file outside the Git repository. Replace every
placeholder with a value from the target tenancy:

```json
{
  "tenancy_ocid": "<target-tenancy-ocid>",
  "compartment_ocid": "<target-compartment-ocid>",
  "region": "<deployment-region>",
  "vault_ocid": "<vault-ocid>",
  "kms_key_ocid": "<kms-key-ocid>",
  "adb_admin_password": "<set-a-new-sensitive-password>",
  "instance_image_ocid": "<oracle-linux-image-ocid>",
  "ssh_public_key": "<ssh-public-key>",
  "app_source_type": "git",
  "app_source_url": "https://github.com/vasudevaiyer/oci-gen-ai.git",
  "app_source_ref": "main",
  "environment": "test",
  "region_code": "<short-region-code>",
  "enable_jump_host": "false",
  "app_dynamic_group_enabled": "true",
  "secret_name_nonce": "1"
}
```

Save it, for example, as `/tmp/telco-native-vars.json` with permissions `600`.
Do not commit it, upload it to Git, or print it in a terminal transcript.

Create the stack. Pass the zip path directly to `--config-source`:

```bash
oci resource-manager stack create \
  --compartment-id <target-compartment-ocid> \
  --display-name telco-native-test \
  --terraform-version 1.5.x \
  --config-source /tmp/telco-native-resource-manager.zip \
  --working-directory . \
  --variables file:///tmp/telco-native-vars.json
```

Record the returned stack OCID, then run Plan:

```bash
oci resource-manager job create-plan-job \
  --stack-id <stack-ocid> \
  --display-name telco-native-plan \
  --wait-for-state SUCCEEDED \
  --wait-for-state FAILED \
  --max-wait-seconds 1800
```

If Plan succeeds, run Apply:

```bash
oci resource-manager job create-apply-job \
  --stack-id <stack-ocid> \
  --display-name telco-native-apply \
  --execution-plan-strategy AUTO_APPROVED \
  --wait-for-state SUCCEEDED \
  --wait-for-state FAILED \
  --max-wait-seconds 3600
```

List jobs and retrieve outputs after Apply:

```bash
oci resource-manager job list --stack-id <stack-ocid> --all
oci resource-manager stack get --stack-id <stack-ocid>
```

Remove the protected variables file after the deployment metadata is no
longer needed:

```bash
rm -f /tmp/telco-native-vars.json
```

The CLI creates the same Resource Manager stack as the Console. It does not
bypass OCI Vault, IAM, quota, or provider-service errors.

## 5. Enter the stack variables

Use the target tenancy's values for all OCIDs. Resource Manager normally
prepopulates the tenancy, compartment, and region fields.

Required values:

| Variable | Value |
|---|---|
| `tenancy_ocid` | Target tenancy OCID |
| `compartment_ocid` | Target compartment OCID |
| `region` | Target deployment region |
| `vault_ocid` | Existing Vault OCID |
| `kms_key_ocid` | AES key OCID in that Vault |
| `adb_admin_password` | New ADB ADMIN password, entered as sensitive input |
| `instance_image_ocid` | Oracle Linux image OCID for the target region |
| `ssh_public_key` | Public SSH key for operator access |
| `app_source_type` | `git` |
| `app_source_url` | `https://github.com/vasudevaiyer/oci-gen-ai.git` |
| `app_source_ref` | `main` |

Recommended test values:

| Variable | Value |
|---|---|
| `environment` | `test` |
| `region_code` | A short code for the selected region, such as `ord` |
| `enable_jump_host` | `false` |
| `app_dynamic_group_enabled` | `true` |
| `adb_db_version` | `26ai` |
| `adb_compute_count` | `2` |
| `adb_storage_size_gb` | `50` |
| `vm_ocpus` | `2` |
| `vm_memory_gbs` | `16` |

Do not commit the ADB password, private SSH key, wallet, or any generated
secret value. `secret_name_nonce` can remain at its default for the first
deployment. If a destroyed stack's Vault secrets are still pending deletion,
increase this value before Plan.

## 6. Run Plan

Select **Plan** and wait for it to finish. Confirm that:

- All OCIDs belong to the target tenancy.
- The region and image are correct.
- The ADB is being created in the intended compartment.
- No resources reference the original development tenancy.
- OKE resources are not included.

Do not continue if Plan shows an unexpected tenancy, compartment, or resource.

## 7. Run Apply

Select **Apply** after reviewing the plan. The apply may take several minutes
because the ADB and wallet are created before the VM bootstrap runs.

The application schema password is generated and stored in the configured
Vault. The ADB wallet is stored in a private Object Storage bucket and is
downloaded by the VM using instance-principal authentication.

## 8. Verify the deployment

After Apply succeeds:

1. In the OCI Console, open the application VM and copy its public IP address.
   The VM is created in the public subnet for this test deployment.
2. Confirm the health endpoint returns HTTP 200:

   ```text
   http://<app_vm_public_ip>:8510/api/health
   ```

3. Open `http://<app_vm_public_ip>:8510` in a browser.
4. Confirm the application can reach the database.
5. Confirm the `app_schema_name`, wallet bucket, and database outputs exist.
6. Confirm TCP 8510 is allowed by the VM firewall. Cloud-init configures this
   automatically, but it can be checked over SSH with `sudo firewall-cmd
   --zone=public --list-ports`.
7. Check the VM boot or cloud-init logs if the VM is running but the app is not
   healthy.

## 9. Destroy the test environment

When testing is complete, use the Resource Manager **Destroy** job for this
stack. Wait for the job to finish before attempting another deployment.

If a later deployment reports that a Vault secret name already exists because
the previous secret is pending deletion, increase `secret_name_nonce`, run
Plan, and then run Apply again.

## Troubleshooting

- **Vault HTTP 500 or circuit breaker open:** wait and retry once after
  verifying the Vault and KMS key are `ACTIVE`. Repeated HTTP 500 responses
  should be reported to OCI Support with the Resource Manager job ID and OCI
  request IDs.
- **Secret already exists:** increase `secret_name_nonce` and run Plan again.
- **Image not found:** select an Oracle Linux image from the target region;
  image OCIDs are region-specific.
- **IAM policy failure:** have a tenancy administrator create the required
  dynamic-group policy in the tenancy home region, or run the stack with the
  appropriate IAM permissions.
- **Git clone failure:** verify repository access, URL, branch, and any private
  repository authentication required by the VM bootstrap.
- **Health endpoint unreachable:** verify the VM public IP, the NSG ingress
  rule, and that firewalld lists the application port. The application uses
  host networking and listens on the configured port, normally 8510.
- **Quota exceeded:** request quota or reduce the test sizing before retrying.

## Handoff checklist

- [ ] Teammate has repository access.
- [ ] Target compartment is selected.
- [ ] Vault and KMS key are ready and active.
- [ ] Region-specific Oracle Linux image is selected.
- [ ] SSH public key is available.
- [ ] Required IAM permissions and quotas are confirmed.
- [ ] No passwords, private keys, wallets, or secret values are in the zip.
- [ ] Plan was reviewed before Apply.
- [ ] Health endpoint was verified after Apply.
