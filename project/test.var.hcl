signature = "From Var File"

variable "base_signature" {
  type = string
  default = "Base Signature"
}

variable "nested_signature" {
  type = string
  default = "${var.base_signature} - Nested"
}

variable "map_var" {
  type = map
  default = {
    key1 = "${var.base_signature} - Map1"
    key2 = "${var.nested_signature} - Map2"
  }
}

variable "list_var" {
  type = list
  default = [
    "${var.base_signature} - List1",
    "${var.nested_signature} - List2"
  ]
}

variable "plugin_settings" {
  type = map
  default = {
    signature = "${var.nested_signature}"
    extra_setting = "test"
  }
}

# Test type constraints
variable "number_var" {
  type = number
  default = 42
}

variable "bool_var" {
  type = bool
  default = true
}

# Test required variables
variable "required_var" {
  type = string
  description = "This variable must be set"
}
