resource "oci_core_instance" "app" {
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  compartment_id      = local.resolved_compartment_ocid
  display_name        = local.names.app_vm
  shape               = var.vm_shape
  depends_on = [
    oci_database_autonomous_database.rag_adb,
    oci_vault_secret.app_schema_password,
  ]

  shape_config {
    ocpus         = var.vm_ocpus
    memory_in_gbs = var.vm_memory_gbs
  }

  source_details {
    source_type             = "image"
    source_id               = var.instance_image_ocid
    boot_volume_size_in_gbs = var.vm_boot_volume_gbs
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.app_private.id
    assign_public_ip = false
    nsg_ids          = [oci_core_network_security_group.app.id]
    display_name     = "${local.names.app_vm}-vnic"
    hostname_label   = local.hostname_label
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(templatefile("${path.module}/templates/cloud-init.yaml.tftpl", {
      bootstrap_script = templatefile("${path.module}/templates/bootstrap_app.sh.tftpl", {
        app_source_type                = var.app_source_type
        app_source_url                 = var.app_source_url
        app_source_ref                 = var.app_source_ref
        app_dir                        = "/opt/${local.name_prefix}"
        app_listen_port                = var.app_listen_port
        adb_admin_password_secret_ocid = var.adb_admin_password_secret_ocid
        adb_connect_string             = local.app_db_connect_string
        app_schema_name                = local.resolved_app_schema_name
        app_schema_password            = local.app_schema_password
        compartment_ocid               = local.resolved_compartment_ocid
        region                         = var.region
        genai_endpoint                 = var.genai_endpoint
        embed_model_id                 = var.embed_model_id
        chat_model_id                  = var.chat_model_id
        vision_model_id                = var.vision_model_id
      })
    }))
  }

  lifecycle {
    ignore_changes = [
      metadata["user_data"],
    ]
  }

  freeform_tags = local.common_tags
}

resource "oci_core_instance" "jump_host" {
  count               = var.enable_jump_host ? 1 : 0
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  compartment_id      = local.resolved_compartment_ocid
  display_name        = local.names.jump_vm
  shape               = var.jump_host_shape

  shape_config {
    ocpus         = var.jump_host_ocpus
    memory_in_gbs = var.jump_host_memory_gbs
  }

  source_details {
    source_type             = "image"
    source_id               = var.instance_image_ocid
    boot_volume_size_in_gbs = var.jump_host_boot_volume_gbs
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.api_public.id
    assign_public_ip = true
    nsg_ids          = [oci_core_network_security_group.jump_host[0].id]
    display_name     = "${local.names.jump_vm}-vnic"
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
  }

  freeform_tags = local.common_tags
}

data "oci_core_vnic_attachments" "app" {
  compartment_id      = local.resolved_compartment_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  instance_id         = oci_core_instance.app.id
}

data "oci_core_vnic" "app_primary" {
  vnic_id = data.oci_core_vnic_attachments.app.vnic_attachments[0].vnic_id
}

data "oci_core_vnic_attachments" "jump_host" {
  count               = var.enable_jump_host ? 1 : 0
  compartment_id      = local.resolved_compartment_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  instance_id         = oci_core_instance.jump_host[0].id
}

data "oci_core_vnic" "jump_host_primary" {
  count   = var.enable_jump_host ? 1 : 0
  vnic_id = data.oci_core_vnic_attachments.jump_host[0].vnic_attachments[0].vnic_id
}
