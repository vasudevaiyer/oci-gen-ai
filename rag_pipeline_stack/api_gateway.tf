resource "oci_apigateway_gateway" "public" {
  compartment_id             = local.resolved_compartment_ocid
  display_name               = local.names.api_gateway
  endpoint_type              = "PUBLIC"
  subnet_id                  = oci_core_subnet.api_public.id
  network_security_group_ids = [oci_core_network_security_group.api_gateway.id]
  freeform_tags              = local.common_tags
}

resource "oci_apigateway_deployment" "public" {
  compartment_id = local.resolved_compartment_ocid
  display_name   = local.names.api_deployment
  gateway_id     = oci_apigateway_gateway.public.id
  path_prefix    = "/"
  freeform_tags  = local.common_tags

  specification {
    routes {
      path    = "/"
      methods = ["GET"]

      backend {
        type                       = "HTTP_BACKEND"
        url                        = "http://${data.oci_core_vnic.app_primary.private_ip_address}:${var.app_listen_port}/"
        connect_timeout_in_seconds = 30
        read_timeout_in_seconds    = 60
        send_timeout_in_seconds    = 60
      }
    }

    routes {
      path    = "/governance"
      methods = ["GET"]

      backend {
        type                       = "HTTP_BACKEND"
        url                        = "http://${data.oci_core_vnic.app_primary.private_ip_address}:${var.app_listen_port}/governance"
        connect_timeout_in_seconds = 30
        read_timeout_in_seconds    = 60
        send_timeout_in_seconds    = 60
      }
    }

    routes {
      path    = "/ui/{asset_path*}"
      methods = ["GET"]

      backend {
        type                       = "HTTP_BACKEND"
        url                        = "http://${data.oci_core_vnic.app_primary.private_ip_address}:${var.app_listen_port}/ui/$${request.path[asset_path]}"
        connect_timeout_in_seconds = 30
        read_timeout_in_seconds    = 60
        send_timeout_in_seconds    = 60
      }
    }

    routes {
      path    = "/assets/{asset_path*}"
      methods = ["GET"]

      backend {
        type                       = "HTTP_BACKEND"
        url                        = "http://${data.oci_core_vnic.app_primary.private_ip_address}:${var.app_listen_port}/assets/$${request.path[asset_path]}"
        connect_timeout_in_seconds = 30
        read_timeout_in_seconds    = 120
        send_timeout_in_seconds    = 120
      }
    }

    routes {
      path    = "/api/{api_path*}"
      methods = ["ANY"]

      backend {
        type                       = "HTTP_BACKEND"
        url                        = "http://${data.oci_core_vnic.app_primary.private_ip_address}:${var.app_listen_port}/api/$${request.path[api_path]}"
        connect_timeout_in_seconds = 60
        read_timeout_in_seconds    = 120
        send_timeout_in_seconds    = 120
      }
    }

    routes {
      path    = "/chat"
      methods = ["ANY"]

      backend {
        type                       = "HTTP_BACKEND"
        url                        = "http://${data.oci_core_vnic.app_primary.private_ip_address}:${var.app_listen_port}/api/chat"
        connect_timeout_in_seconds = 60
        read_timeout_in_seconds    = 120
        send_timeout_in_seconds    = 120
      }
    }

    dynamic "routes" {
      for_each = var.enable_health_endpoint ? [1] : []
      content {
        path    = "/health"
        methods = ["GET"]

        backend {
          type                       = "HTTP_BACKEND"
          url                        = "http://${data.oci_core_vnic.app_primary.private_ip_address}:${var.app_listen_port}/api/health"
          connect_timeout_in_seconds = 15
          read_timeout_in_seconds    = 30
          send_timeout_in_seconds    = 30
        }
      }
    }
  }
}
