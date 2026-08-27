check "compartment_selection" {
  assert {
    condition     = trimspace(var.compartment_ocid) != "" || trimspace(var.compartment_name) != ""
    error_message = "Provide either compartment_ocid or compartment_name."
  }
}
