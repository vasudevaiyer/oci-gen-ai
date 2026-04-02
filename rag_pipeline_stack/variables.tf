variable "tenancy_ocid" {
  description = "Tenancy OCID. Resource Manager can prepopulate this."
  type        = string
}

variable "region" {
  description = "OCI region."
  type        = string
}

variable "home_region" {
  description = "OCI tenancy home region used for IAM resources such as dynamic groups and policies."
  type        = string
  default     = ""
}

variable "compartment_ocid" {
  description = "Target compartment OCID. Prefer this over compartment_name."
  type        = string
  default     = ""
}

variable "compartment_name" {
  description = "Optional target compartment name if compartment_ocid is not supplied."
  type        = string
  default     = ""
}

variable "prefix" {
  description = "Short naming prefix."
  type        = string
  default     = "oci"
}

variable "app_name" {
  description = "Application short name used in naming."
  type        = string
  default     = "rag"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "test", "uat", "prod"], var.environment)
    error_message = "environment must be one of: dev, test, uat, prod."
  }
}

variable "region_code" {
  description = "Short region code used in naming, for example iad or phx."
  type        = string
  default     = "iad"
}

variable "ssh_public_key" {
  description = "SSH public key for the jump host and private application VM."
  type        = string
}

variable "instance_image_ocid" {
  description = "Oracle Linux image OCID for the application VM."
  type        = string
}

variable "vcn_cidr" {
  description = "VCN CIDR block."
  type        = string
  default     = "10.0.0.0/16"
}

variable "api_public_subnet_cidr" {
  description = "Public subnet CIDR for API Gateway."
  type        = string
  default     = "10.0.1.0/24"
}

variable "app_private_subnet_cidr" {
  description = "Private subnet CIDR for the app VM."
  type        = string
  default     = "10.0.2.0/24"
}

variable "db_private_subnet_cidr" {
  description = "Private subnet CIDR for the Autonomous Database private endpoint."
  type        = string
  default     = "10.0.3.0/24"
}

variable "allowed_api_cidrs" {
  description = "Allowed ingress CIDRs for the public API path."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "allowed_ssh_cidrs" {
  description = "Allowed CIDRs for SSH access to the public jump host."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "vm_shape" {
  description = "Application VM shape."
  type        = string
  default     = "VM.Standard.E4.Flex"
}

variable "vm_ocpus" {
  description = "Application VM OCPU count."
  type        = number
  default     = 2
}

variable "vm_memory_gbs" {
  description = "Application VM memory in GB."
  type        = number
  default     = 16
}

variable "vm_boot_volume_gbs" {
  description = "Application VM boot volume size."
  type        = number
  default     = 100
}

variable "enable_jump_host" {
  description = "Create a public jump host VM for SSH access into the private VCN."
  type        = bool
  default     = true
}

variable "jump_host_shape" {
  description = "Jump host VM shape."
  type        = string
  default     = "VM.Standard.E4.Flex"
}

variable "jump_host_ocpus" {
  description = "Jump host VM OCPU count."
  type        = number
  default     = 1
}

variable "jump_host_memory_gbs" {
  description = "Jump host VM memory in GB."
  type        = number
  default     = 8
}

variable "jump_host_boot_volume_gbs" {
  description = "Jump host boot volume size."
  type        = number
  default     = 50
}

variable "app_listen_port" {
  description = "Internal application listen port."
  type        = number
  default     = 8045
}

variable "app_source_type" {
  description = "How the application source should be fetched on the VM."
  type        = string
  default     = "git"

  validation {
    condition     = contains(["git", "archive"], var.app_source_type)
    error_message = "app_source_type must be either git or archive."
  }
}

variable "app_source_url" {
  description = "Git clone URL or archive download URL for the application source."
  type        = string
}

variable "app_source_ref" {
  description = "Git branch/tag/ref when app_source_type is git."
  type        = string
  default     = "main"
}

variable "vault_ocid" {
  description = "Existing OCI Vault OCID used to store the generated app schema password."
  type        = string
}

variable "kms_key_ocid" {
  description = "Existing OCI KMS key OCID used for the generated app schema password secret."
  type        = string
}

variable "adb_admin_password_secret_ocid" {
  description = "Vault secret OCID containing the Autonomous Database admin password used both for ADB creation and VM-side schema bootstrap."
  type        = string
}

variable "adb_compute_model" {
  description = "ADB compute model."
  type        = string
  default     = "ECPU"
}

variable "adb_compute_count" {
  description = "ADB compute units."
  type        = number
  default     = 2
}

variable "adb_storage_size_gb" {
  description = "ADB storage size in GB."
  type        = number
  default     = 50
}

variable "adb_auto_scaling_enabled" {
  description = "Enable ADB auto scaling."
  type        = bool
  default     = true
}

variable "adb_license_model" {
  description = "ADB license model."
  type        = string
  default     = "LICENSE_INCLUDED"
}

variable "adb_db_version" {
  description = "Autonomous Database version. Use a vector-capable AI Database version for this RAG stack."
  type        = string
  default     = "26ai"
}

variable "adb_service_name" {
  description = "ADB service connection name used by the application."
  type        = string
  default     = "LOW"

  validation {
    condition     = contains(["LOW", "MEDIUM", "HIGH", "TP", "TPURGENT"], var.adb_service_name)
    error_message = "adb_service_name must be one of LOW, MEDIUM, HIGH, TP, TPURGENT."
  }
}

variable "app_schema_name" {
  description = "Optional override for the application schema."
  type        = string
  default     = ""
}

variable "genai_endpoint" {
  description = "OCI Generative AI inference endpoint."
  type        = string
  default     = "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com"
}

variable "embed_model_id" {
  description = "OCI embedding model ID."
  type        = string
  default     = "cohere.embed-v4.0"
}

variable "chat_model_id" {
  description = "OCI chat model ID."
  type        = string
  default     = "cohere.command-a-03-2025"
}

variable "vision_model_id" {
  description = "OCI vision model ID."
  type        = string
  default     = "cohere.command-a-vision"
}

variable "top_k_default" {
  description = "Default top_k for chat/search."
  type        = number
  default     = 6
}

variable "include_images_default" {
  description = "Default image inclusion setting."
  type        = bool
  default     = false
}

variable "enable_health_endpoint" {
  description = "Expose the health endpoint through API Gateway."
  type        = bool
  default     = true
}

variable "app_dynamic_group_enabled" {
  description = "Create the dynamic group and policy required for the VM to use instance principals for OCI Generative AI and Vault secret bundle reads."
  type        = bool
  default     = true
}

variable "freeform_tags" {
  description = "Additional freeform tags."
  type        = map(string)
  default     = {}
}
