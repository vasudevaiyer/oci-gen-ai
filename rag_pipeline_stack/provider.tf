provider "oci" {
  region = var.region
}

provider "oci" {
  alias  = "home"
  region = var.home_region != "" ? var.home_region : var.region
}
