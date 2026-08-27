resource "oci_core_vcn" "main" {
  compartment_id = local.resolved_compartment_ocid
  cidr_blocks    = [var.vcn_cidr]
  display_name   = local.names.vcn
  dns_label      = local.dns_label
  freeform_tags  = local.common_tags
}

resource "oci_core_internet_gateway" "igw" {
  compartment_id = local.resolved_compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = local.names.igw
  enabled        = true
  freeform_tags  = local.common_tags
}

resource "oci_core_nat_gateway" "nat" {
  compartment_id = local.resolved_compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = local.names.nat
  freeform_tags  = local.common_tags
}

resource "oci_core_service_gateway" "sgw" {
  compartment_id = local.resolved_compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = local.names.sgw
  services {
    service_id = data.oci_core_services.all.services[0].id
  }
  freeform_tags = local.common_tags
}

resource "oci_core_route_table" "api_public" {
  compartment_id = local.resolved_compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = local.names.api_route_table

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.igw.id
  }

  freeform_tags = local.common_tags
}

resource "oci_core_route_table" "app_private" {
  compartment_id = local.resolved_compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = local.names.app_route_table

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_nat_gateway.nat.id
  }

  route_rules {
    destination       = data.oci_core_services.all.services[0].cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.sgw.id
  }

  freeform_tags = local.common_tags
}

resource "oci_core_route_table" "db_private" {
  compartment_id = local.resolved_compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = local.names.db_route_table

  route_rules {
    destination       = data.oci_core_services.all.services[0].cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.sgw.id
  }

  freeform_tags = local.common_tags
}

resource "oci_core_subnet" "api_public" {
  compartment_id             = local.resolved_compartment_ocid
  vcn_id                     = oci_core_vcn.main.id
  cidr_block                 = var.api_public_subnet_cidr
  display_name               = local.names.api_public_subnet
  dns_label                  = local.api_subnet_dns_label
  route_table_id             = oci_core_route_table.api_public.id
  prohibit_public_ip_on_vnic = false
  freeform_tags              = local.common_tags
}

resource "oci_core_subnet" "app_private" {
  compartment_id             = local.resolved_compartment_ocid
  vcn_id                     = oci_core_vcn.main.id
  cidr_block                 = var.app_private_subnet_cidr
  display_name               = local.names.app_private_subnet
  dns_label                  = local.app_subnet_dns_label
  route_table_id             = oci_core_route_table.app_private.id
  prohibit_public_ip_on_vnic = true
  freeform_tags              = local.common_tags
}

resource "oci_core_subnet" "db_private" {
  compartment_id             = local.resolved_compartment_ocid
  vcn_id                     = oci_core_vcn.main.id
  cidr_block                 = var.db_private_subnet_cidr
  display_name               = local.names.db_private_subnet
  dns_label                  = local.db_subnet_dns_label
  route_table_id             = oci_core_route_table.db_private.id
  prohibit_public_ip_on_vnic = true
  freeform_tags              = local.common_tags
}
