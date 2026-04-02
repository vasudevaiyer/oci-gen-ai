locals {
  resolved_compartment_ocid = var.compartment_ocid != "" ? var.compartment_ocid : one(data.oci_identity_compartments.target[0].compartments).id

  name_prefix = "${var.prefix}-${var.app_name}-${var.environment}-${var.region_code}"

  dns_label      = substr(replace(lower("v${var.app_name}${var.environment}${var.region_code}"), "/[^a-z0-9]/", ""), 0, 15)
  hostname_label = substr(replace(lower("h${var.app_name}${var.environment}${var.region_code}app"), "/[^a-z0-9]/", ""), 0, 15)
  api_subnet_dns_label = substr(replace(lower("a${var.app_name}${var.environment}${var.region_code}"), "/[^a-z0-9]/", ""), 0, 15)
  app_subnet_dns_label = substr(replace(lower("p${var.app_name}${var.environment}${var.region_code}"), "/[^a-z0-9]/", ""), 0, 15)
  db_subnet_dns_label  = substr(replace(lower("d${var.app_name}${var.environment}${var.region_code}"), "/[^a-z0-9]/", ""), 0, 15)

  names = {
    vcn                = "${local.name_prefix}-vcn"
    api_public_subnet  = "${local.name_prefix}-api-pub-sn"
    app_private_subnet = "${local.name_prefix}-app-prv-sn"
    db_private_subnet  = "${local.name_prefix}-db-prv-sn"
    api_route_table    = "${local.name_prefix}-api-rt"
    app_route_table    = "${local.name_prefix}-app-rt"
    db_route_table     = "${local.name_prefix}-db-rt"
    igw                = "${local.name_prefix}-igw"
    nat                = "${local.name_prefix}-nat"
    sgw                = "${local.name_prefix}-sgw"
    api_nsg            = "${local.name_prefix}-api-gw-nsg"
    jump_nsg           = "${local.name_prefix}-jump-nsg"
    app_nsg            = "${local.name_prefix}-app-nsg"
    adb_nsg            = "${local.name_prefix}-adb-nsg"
    jump_vm            = "${local.name_prefix}-jump-vm"
    app_vm             = "${local.name_prefix}-app-vm"
    adb                = "${local.name_prefix}-adb"
    api_gateway        = "${local.name_prefix}-api-gw"
    api_deployment     = "${local.name_prefix}-api-deploy"
    app_secret         = "${local.name_prefix}-app-schema-secret"
    app_dynamic_group  = "${local.name_prefix}-app-dg"
    app_policy         = "${local.name_prefix}-app-policy"
  }

  adb_db_name_seed           = replace(upper("${var.app_name}${var.environment}${var.region_code}"), "/[^A-Z0-9]/", "")
  adb_db_name                = substr(length(regexall("^[A-Z]", local.adb_db_name_seed)) > 0 ? local.adb_db_name_seed : "A${local.adb_db_name_seed}", 0, 14)
  adb_private_endpoint_label = substr(replace(lower("adb${local.names.adb}"), "/[^a-z0-9]/", ""), 0, 20)
  app_schema_name_seed       = upper(var.app_schema_name != "" ? var.app_schema_name : "APP_${var.app_name}_${var.environment}")
  app_schema_name_sanitized  = replace(local.app_schema_name_seed, "/[^A-Z0-9_]/", "_")
  resolved_app_schema_name   = substr(length(regexall("^[A-Z]", local.app_schema_name_sanitized)) > 0 ? local.app_schema_name_sanitized : "APP_${local.app_schema_name_sanitized}", 0, 30)

  common_tags = merge(
    {
      Application = var.app_name
      Environment = var.environment
      ManagedBy   = "ResourceManager"
      Stack       = "rag-pipeline-stack"
    },
    var.freeform_tags,
  )

  adb_admin_password  = trimspace(base64decode(one(data.oci_secrets_secretbundle.adb_admin_password.secret_bundle_content).content))
  app_schema_password = random_password.app_schema_password.result
  adb_connection_info = one(oci_database_autonomous_database.rag_adb.connection_strings)
  adb_server_tls_profiles = [
    for profile in local.adb_connection_info.profiles : profile
    if upper(profile.consumer_group) == upper(var.adb_service_name)
    && upper(profile.tls_authentication) == "SERVER"
    && upper(profile.session_mode) == "DIRECT"
    && upper(profile.protocol) == "TCPS"
    && upper(profile.syntax_format) == "LONG"
  ]
  app_db_connect_string = length(local.adb_server_tls_profiles) > 0 ? local.adb_server_tls_profiles[0].value : lookup(
    local.adb_connection_info.all_connection_strings,
    lower(var.adb_service_name),
    local.adb_connection_info.low,
  )
  api_base_url = trimsuffix(oci_apigateway_deployment.public.endpoint, "/")
}
