model "gpt4" {
  provider = "openai"
  name     = "gpt-4"
}

model "gpt4o" {
  provider = "openai"
  name     = "gpt-4o"
}

model "llama3" {
  provider = "ollama"
  name     = "llama3.2:latest"
  settings {
    temperature = 0.5
  }
}
