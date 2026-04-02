resource "random_password" "app_schema_password" {
  length           = 24
  special          = true
  override_special = "!@#%^*-_=+"
}

resource "random_string" "app_schema_secret_suffix" {
  length  = 6
  upper   = false
  special = false
  numeric = true
}

resource "oci_vault_secret" "app_schema_password" {
  compartment_id = local.resolved_compartment_ocid
  vault_id       = var.vault_ocid
  key_id         = var.kms_key_ocid
  secret_name    = "${local.names.app_secret}-${random_string.app_schema_secret_suffix.result}"

  secret_content {
    content      = base64encode(random_password.app_schema_password.result)
    content_type = "BASE64"
    name         = "initial"
    stage        = "CURRENT"
  }

  freeform_tags = local.common_tags
}

resource "oci_database_autonomous_database" "rag_adb" {
  compartment_id              = local.resolved_compartment_ocid
  db_name                     = local.adb_db_name
  display_name                = local.names.adb
  admin_password              = local.adb_admin_password
  db_version                  = var.adb_db_version
  db_workload                 = "OLTP"
  compute_model               = var.adb_compute_model
  compute_count               = var.adb_compute_count
  data_storage_size_in_gb     = var.adb_storage_size_gb
  is_auto_scaling_enabled     = var.adb_auto_scaling_enabled
  license_model               = var.adb_license_model
  subnet_id                   = oci_core_subnet.db_private.id
  nsg_ids                     = [oci_core_network_security_group.adb.id]
  private_endpoint_label      = local.adb_private_endpoint_label
  is_mtls_connection_required = false
  freeform_tags               = local.common_tags
}
