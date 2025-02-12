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

model "llama2_instance" {
  provider = "ollama"
  name     = "llama2"
  settings {
    temperature = var.model_temperature
    max_tokens  = var.model_max_tokens
  }
}

plugin "local" "echo" {
  source = "./local_plugins/echo"
  variables = {}
}

plugin "remote" "echo" {
  source = "onwardplatforms/echo"
  version = "0.0.1"
  variables = {}
}

agent "local" {
  name           = "test-agent-local"
  description    = "A test agent using Ollama provider (Local Development)"
  system_prompt  = "You are a helpful AI assistant."
  model          = model.llama2_instance
  plugins        = [plugin.local.echo]
}

# agent "remote" {
#   name           = "test-agent"
#   description    = "A test agent using Ollama provider"
#   system_prompt  = "Always say Jeff"
#   model          = model.llama2_instance
#   plugins        = [plugin.remote.echo]
# }
