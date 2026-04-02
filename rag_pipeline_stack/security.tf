resource "oci_core_network_security_group" "api_gateway" {
  compartment_id = local.resolved_compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = local.names.api_nsg
  freeform_tags  = local.common_tags
}

resource "oci_core_network_security_group" "jump_host" {
  count          = var.enable_jump_host ? 1 : 0
  compartment_id = local.resolved_compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = local.names.jump_nsg
  freeform_tags  = local.common_tags
}

resource "oci_core_network_security_group" "app" {
  compartment_id = local.resolved_compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = local.names.app_nsg
  freeform_tags  = local.common_tags
}

resource "oci_core_network_security_group" "adb" {
  compartment_id = local.resolved_compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = local.names.adb_nsg
  freeform_tags  = local.common_tags
}

resource "oci_core_network_security_group_security_rule" "app_ingress_from_api" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "NETWORK_SECURITY_GROUP"
  source                    = oci_core_network_security_group.api_gateway.id

  tcp_options {
    destination_port_range {
      min = var.app_listen_port
      max = var.app_listen_port
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_ingress_from_api_subnet" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "CIDR_BLOCK"
  source                    = var.api_public_subnet_cidr

  tcp_options {
    destination_port_range {
      min = var.app_listen_port
      max = var.app_listen_port
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_ssh_from_jump_host" {
  count                     = var.enable_jump_host ? 1 : 0
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "NETWORK_SECURITY_GROUP"
  source                    = oci_core_network_security_group.jump_host[0].id

  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_network_security_group_security_rule" "app_egress_any" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination_type          = "CIDR_BLOCK"
  destination               = "0.0.0.0/0"
}

resource "oci_core_network_security_group_security_rule" "api_gateway_ingress_https" {
  for_each                  = toset(var.allowed_api_cidrs)
  network_security_group_id = oci_core_network_security_group.api_gateway.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "CIDR_BLOCK"
  source                    = each.value

  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_network_security_group_security_rule" "api_gateway_egress_to_app" {
  network_security_group_id = oci_core_network_security_group.api_gateway.id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination_type          = "NETWORK_SECURITY_GROUP"
  destination               = oci_core_network_security_group.app.id

  tcp_options {
    destination_port_range {
      min = var.app_listen_port
      max = var.app_listen_port
    }
  }
}

resource "oci_core_network_security_group_security_rule" "jump_host_ingress_ssh" {
  for_each                  = var.enable_jump_host ? toset(var.allowed_ssh_cidrs) : []
  network_security_group_id = oci_core_network_security_group.jump_host[0].id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "CIDR_BLOCK"
  source                    = each.value

  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_network_security_group_security_rule" "jump_host_egress_ssh_to_app" {
  count                     = var.enable_jump_host ? 1 : 0
  network_security_group_id = oci_core_network_security_group.jump_host[0].id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination_type          = "NETWORK_SECURITY_GROUP"
  destination               = oci_core_network_security_group.app.id

  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_network_security_group_security_rule" "jump_host_egress_any" {
  count                     = var.enable_jump_host ? 1 : 0
  network_security_group_id = oci_core_network_security_group.jump_host[0].id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination_type          = "CIDR_BLOCK"
  destination               = "0.0.0.0/0"
}

resource "oci_core_network_security_group_security_rule" "adb_ingress_from_app" {
  network_security_group_id = oci_core_network_security_group.adb.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "NETWORK_SECURITY_GROUP"
  source                    = oci_core_network_security_group.app.id

  tcp_options {
    destination_port_range {
      min = 1521
      max = 1521
    }
  }
}

resource "oci_core_network_security_group_security_rule" "adb_ingress_from_app_mtls" {
  network_security_group_id = oci_core_network_security_group.adb.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "NETWORK_SECURITY_GROUP"
  source                    = oci_core_network_security_group.app.id

  tcp_options {
    destination_port_range {
      min = 1522
      max = 1522
    }
  }
}

resource "oci_core_network_security_group_security_rule" "adb_egress_any" {
  network_security_group_id = oci_core_network_security_group.adb.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination_type          = "CIDR_BLOCK"
  destination               = "0.0.0.0/0"
}
