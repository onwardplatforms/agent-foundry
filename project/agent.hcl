runtime {
  required_version = "0.0.1"
}

variable "model_temperature" {
  description = "Temperature setting for the model"
  type        = number
  default     = 0.7
}

variable "model_max_tokens" {
  description = "Maximum tokens for model response"
  type        = number
  default     = 1000
}

variable "signature" {
  description = "Signature to use for messages"
  type        = string
  default     = "From Variable"
}

variable "provider" {
  description = "Provider to use for the model"
  type = string
  default = "ollama"
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
