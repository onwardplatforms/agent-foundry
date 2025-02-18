plugin "local" "echo" {
  source = "./local_plugins/echo"
  variables = {
    "signature" = var.signature
  }
}

plugin "local" "code_editor" {
  source = "./local_plugins/code_editor_v2"
}

plugin "remote" "echo" {
  source = "https://github.com/onwardplatforms/agentruntime-plugin-echo"
  version = "0.0.1"
}
