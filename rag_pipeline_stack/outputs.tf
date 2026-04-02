output "api_gateway_base_url" {
  description = "Public base URL of the API Gateway."
  value       = local.api_base_url
}

output "chat_endpoint" {
  description = "Public chat endpoint for ODA or other clients."
  value       = "${local.api_base_url}/chat"
}

output "health_endpoint" {
  description = "Public health endpoint."
  value       = var.enable_health_endpoint ? "${local.api_base_url}/health" : ""
}

output "app_vm_ocid" {
  description = "OCID of the private application VM."
  value       = oci_core_instance.app.id
}

output "app_vm_private_ip" {
  description = "Private IP address of the application VM."
  value       = data.oci_core_vnic.app_primary.private_ip_address
}

output "jump_host_ocid" {
  description = "OCID of the public jump host VM."
  value       = var.enable_jump_host ? oci_core_instance.jump_host[0].id : ""
}

output "jump_host_public_ip" {
  description = "Public IP address of the jump host VM."
  value       = var.enable_jump_host ? data.oci_core_vnic.jump_host_primary[0].public_ip_address : ""
}

output "jump_host_private_ip" {
  description = "Private IP address of the jump host VM."
  value       = var.enable_jump_host ? data.oci_core_vnic.jump_host_primary[0].private_ip_address : ""
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

output "deployment_summary" {
  description = "Quick summary of the deployed service."
  value       = <<EOT
RAG service deployed successfully.

API Gateway Base URL: ${local.api_base_url}
Chat Endpoint: ${local.api_base_url}/chat
Health Endpoint: ${var.enable_health_endpoint ? "${local.api_base_url}/health" : "disabled"}
App VM Private IP: ${data.oci_core_vnic.app_primary.private_ip_address}
Jump Host Public IP: ${var.enable_jump_host ? data.oci_core_vnic.jump_host_primary[0].public_ip_address : "disabled"}
ADB Name: ${oci_database_autonomous_database.rag_adb.display_name}
App Schema: ${local.resolved_app_schema_name}
App Schema Secret: ${oci_vault_secret.app_schema_password.secret_name}
EOT
}
