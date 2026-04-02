provider "oci" {
  region = var.region
}

provider "oci" {
  alias  = "home"
  region = local.resolved_home_region
}
