resource "oci_identity_dynamic_group" "app" {
  provider       = oci.home
  count          = var.app_dynamic_group_enabled ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = local.names.app_dynamic_group
  description    = "Dynamic group for the private RAG app VM."
  matching_rule  = "ANY {instance.compartment.id = '${local.resolved_compartment_ocid}'}"
}

resource "oci_identity_policy" "app" {
  provider       = oci.home
  count          = var.app_dynamic_group_enabled ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = local.names.app_policy
  description    = "Policy allowing the app VM to call OCI Generative AI using instance principals."

  statements = [
    "Allow dynamic-group 'Default'/'${local.names.app_dynamic_group}' to use generative-ai-family in compartment id ${local.resolved_compartment_ocid}",
    "Allow dynamic-group 'Default'/'${local.names.app_dynamic_group}' to read secret-bundles in compartment id ${local.resolved_compartment_ocid}",
    "Allow dynamic-group 'Default'/'${local.names.app_dynamic_group}' to use vaults in compartment id ${local.resolved_compartment_ocid}",
    "Allow dynamic-group 'Default'/'${local.names.app_dynamic_group}' to use keys in compartment id ${local.resolved_compartment_ocid}",
    "Allow dynamic-group 'Default'/'${local.names.app_dynamic_group}' to use tag-namespaces in compartment id ${local.resolved_compartment_ocid}",
  ]
}
