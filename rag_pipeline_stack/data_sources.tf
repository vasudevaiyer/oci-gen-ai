data "oci_identity_tenancy" "current" {
  tenancy_id = var.tenancy_ocid
}

data "oci_identity_regions" "all" {}

data "oci_identity_compartments" "target" {
  count                     = var.compartment_ocid == "" ? 1 : 0
  compartment_id            = var.tenancy_ocid
  compartment_id_in_subtree = true
  access_level              = "ACCESSIBLE"
  name                      = var.compartment_name
  state                     = "ACTIVE"
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

data "oci_core_services" "all" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}

data "oci_secrets_secretbundle" "adb_admin_password" {
  secret_id = var.adb_admin_password_secret_ocid
}
