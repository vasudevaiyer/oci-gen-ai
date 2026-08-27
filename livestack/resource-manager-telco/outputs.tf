output "app_vm_ocid" {
  description = "OCID of the private application VM."
  value       = oci_core_instance.app.id
}

output "app_vm_private_ip" {
  description = "Private IP address of the application VM."
  value       = data.oci_core_vnic.app_primary.private_ip_address
}

output "autonomous_database_ocid" {
  description = "OCID of the Autonomous Database."
  value       = oci_database_autonomous_database.rag_adb.id
}

output "autonomous_database_name" {
  description = "Display name of the Autonomous Database."
  value       = oci_database_autonomous_database.rag_adb.display_name
}

output "adb_private_endpoint_ip" {
  description = "Private endpoint IP address of the Autonomous Database."
  value       = oci_database_autonomous_database.rag_adb.private_endpoint_ip
}

output "adb_private_endpoint_label" {
  description = "Private endpoint label of the Autonomous Database."
  value       = oci_database_autonomous_database.rag_adb.private_endpoint_label
}

output "adb_service_name_used" {
  description = "Database service name used by the application."
  value       = var.adb_service_name
}

output "app_schema_name" {
  description = "Application schema created for the RAG service."
  value       = local.resolved_app_schema_name
}

output "app_schema_password_secret_name" {
  description = "Vault secret name storing the application schema password."
  value       = oci_vault_secret.app_schema_password.secret_name
}

output "app_schema_password_secret_ocid" {
  description = "Vault secret OCID storing the application schema password."
  value       = oci_vault_secret.app_schema_password.id
}

output "vcn_ocid" {
  description = "OCID of the VCN."
  value       = oci_core_vcn.main.id
}

output "public_api_subnet_ocid" {
  description = "OCID of the public subnet used by API Gateway."
  value       = oci_core_subnet.api_public.id
}

output "private_app_subnet_ocid" {
  description = "OCID of the private subnet used by the app VM."
  value       = oci_core_subnet.app_private.id
}

output "private_db_subnet_ocid" {
  description = "OCID of the private subnet used by the ADB private endpoint."
  value       = oci_core_subnet.db_private.id
}

output "wallet_bucket_name" {
  description = "Private Object Storage bucket containing the generated ADB wallet."
  value       = oci_objectstorage_bucket.adb_wallet.name
}

output "wallet_object_name" {
  description = "Object containing the base64-encoded ADB wallet."
  value       = oci_objectstorage_object.adb_wallet.object
}
