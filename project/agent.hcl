runtime {
  required_version = "0.0.1"
}

variable "model_temperature" {
  type = "number"
  description = "Temperature setting for the model (0.0 to 1.0)"
  default = 0.7
}

variable "model_max_tokens" {
  type = "number"
  description = "Maximum number of tokens for model responses"
  default = 1000
}

variable "signature" {
  description = "Signature to use for messages"
  type        = string
  default     = "From Variable"
}

variable "model_provider" {
  type = "string"
  description = "Model provider to use (e.g. ollama, openai)"
  default = "openai"
}

variable "model_name" {
  type = "string"
  description = "Model name to use (e.g. gpt-4, gpt-3.5-turbo)"
  default = "gpt-4"
}

variable "debug_mode" {
  type = "bool"
  description = "Enable debug logging"
  default = false
}

variable "allowed_models" {
  type = "list"
  description = "List of allowed model names"
  default = ["gpt-4", "gpt-3.5-turbo"]
}

variable "model_settings" {
  type = "map"
  description = "Additional model settings"
  default = {
    context_window = 4096
    top_p = 0.9
  }
}

model "llama2_instance" {
  provider = var.model_provider
  name     = var.model_name
  settings {
    temperature = var.model_temperature
    max_tokens  = var.model_max_tokens
  }
}

plugin "local" "echo" {
  source = "./local_plugins/echo"
  variables = {
    "signature" = var.signature
  }
}

plugin "local" "code_editor" {
  source = "./local_plugins/code_editor_v2"
  variables = {
    workspace_root = "."
  }
}

plugin "remote" "echo" {
  source = "onwardplatforms/echo"
  version = "0.0.1"
  variables = {}
}

agent "local" {
  name           = "test-agent-local-${model.llama2_instance.name}"
  description    = "A helpful coding assistant"
  system_prompt  = <<-EOT
    You are a helpful coding assistant.
    Be proactive in helping the user with their coding needs.
    Be curious, searching files and looking for the right information.
    Follow the workflow guidelines in the CodeEditorPlugin instructions carefully.
    Think like a human programmer - understand before changing, verify after changing.
    Always check your work after changing code to confirm it is correct.
    EOT
  model          = model.llama2_instance
  plugins        = [plugin.local.echo, plugin.local.code_editor]
}

agent "remote" {
  name           = "test-agent"
  description    = "A test agent using Ollama provider"
  system_prompt  = "Always say Jeff"
  model          = model.llama2_instance
  plugins        = [plugin.remote.echo]
}
