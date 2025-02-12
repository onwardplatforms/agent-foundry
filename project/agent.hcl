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

variable "provider" {
  type = "string"
  description = "Model provider to use (e.g. ollama, openai)"
  default = "ollama"
}

variable "debug_mode" {
  type = "bool"
  description = "Enable debug logging"
  default = false
}

variable "allowed_models" {
  type = "list"
  description = "List of allowed model names"
  default = ["llama2", "mistral", "codellama"]
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
  provider = var.provider
  name     = "llama2"
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

plugin "remote" "echo" {
  source = "onwardplatforms/echo"
  version = "0.0.1"
  variables = {}
}

agent "local" {
  name           = "test-agent-local-${model.llama2_instance.name}"
  description    = "A test agent using Ollama provider (Local Development)"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2_instance
  plugins        = [plugin.local.echo]
}

agent "remote" {
  name           = "test-agent"
  description    = "A test agent using Ollama provider"
  system_prompt  = "Always say Jeff"
  model          = model.llama2_instance
  plugins        = [plugin.remote.echo]
}
