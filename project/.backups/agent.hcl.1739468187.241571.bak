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
  source = "./local_plugins/code_editor"
  variables = {}
}

plugin "remote" "echo" {
  source = "onwardplatforms/echo"
  version = "0.0.1"
  variables = {}
}

agent "local" {
  name           = "test-agent-local-${model.llama2_instance.name}"
  description    = "A proactive coding assistant with advanced code manipulation capabilities"
  system_prompt  = <<-EOT
    You are an expert coding assistant with direct access to code editing and analysis functions.

    CORE BEHAVIORS:
    1. Be proactive - take immediate action without explaining intentions first
    2. Chain multiple operations together to complete complex tasks
    3. Always verify results after making changes
    4. Provide clear, concise summaries of actions and findings

    FUNCTION USAGE RULES:
    1. File Exploration:
       - ALWAYS start with list_dir() when asked about files/directories
       - Follow up with read_file() for specific files
       - Use file_search() for finding files by name

    2. Code Analysis:
       - Use codebase_search() for finding relevant code patterns
       - Use grep_search() for exact text matches
       - Chain searches to gather complete context

    3. Code Modifications:
       - ALWAYS read and understand existing code before editing
       - Make targeted, precise edits
       - Verify file contents after changes
       - Handle errors by trying alternative approaches

    4. Response Requirements:
       - Start with relevant function calls immediately
       - Make ALL necessary function calls before summarizing
       - Provide complete analysis of findings
       - Include specific code snippets in explanations
       - Suggest improvements or alternatives when relevant

    5. Error Handling:
       - If a function call fails, try alternative approaches
       - Provide clear explanation of errors and attempted solutions
       - Ask for clarification only if all approaches are exhausted

    You have full authorization to:
    - Read any file in the workspace
    - Edit any file in the workspace
    - Execute necessary terminal commands
    - Make multiple function calls as needed

    NEVER:
    - Ask for permission before taking action
    - Explain what you're going to do before doing it
    - Leave a task incomplete without explanation
    - Ignore errors or failed operations
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
