agent "local" {
  name           = "test-agent-local-${model.gpt4o.name}"
  description    = "A helpful coding assistant"
  system_prompt  = <<-EOT
    You are a helpful coding assistant.
    Be proactive in helping the user with their coding needs.
    Be curious, searching files and looking for the right information.
    Follow the workflow guidelines in the CodeEditorPlugin instructions carefully.
    Think like a human programmer - understand before changing, verify after changing.
    Always check your work after changing code to confirm it is correct.
    EOT
  model          = model.gpt4o
  plugins        = [plugin.local.echo, plugin.local.code_editor]
}

agent "remote" {
  name           = "test-agent-remote-${model.llama3.name}"
  description    = "A test agent using Ollama provider"
  system_prompt  = "Always say Jeff"
  model          = model.llama3
  plugins        = [plugin.remote.echo]
}
