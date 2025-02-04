1. Purpose & High-Level Overview
We want a system (the Agent Foundry) that can:

Create new AI agents based on user requests.
Run these agents in an interactive or automated mode.
Manage plugins, environment variables, and local storage for each agent.
Key points:

The Foundry is itself an agent that a user can interact with through a CLI (via Python’s Click library) and possibly chat-based interactions.
Each agent has its own local directory, virtual environment, and plugins.
Agents are stateless between sessions but hold conversation/memory during a session.
Agents can create or modify code and plugins (with user approval) to adapt to the user’s needs.
Configurations and environment variables are stored locally (e.g., agent.config.json, .env).
2. Folder & File Structure
We will keep agents/ and foundry/ at the same level in the project, for clarity and separation:

bash
Copy
Edit
my_project/
  ├── foundry/
  │    ├── foundry_cli.py          # Main entry point for the CLI (Click)
  │    ├── plugins/                # Plugins folder for the Foundry
  │    │    ├── foundry_core/      # The Foundry's own core tools (treated as a plugin)
  │    │    │   ├── __init__.py
  │    │    │   ├── create_agent.py
  │    │    │   ├── run_agent.py
  │    │    │   ├── list_agents.py
  │    │    │   └── ...
  │    │    └── standard_lib/      # Standard library plugin with common tools
  │    │        ├── __init__.py
  │    │        ├── read_write_code.py
  │    │        ├── grep_codebase.py
  │    │        └── web_search.py
  │    └── ...
  └── agents/
       └── {agent_name}/
           ├── agent.config.json
           ├── .env
           ├── plugins/
           │   └── (custom plugins unique to this agent)
           ├── venv/
           ├── main.py
           └── ...
foundry/

Contains the CLI and core logic for the Foundry.
Has a plugins/ directory where:
foundry_core/ holds the Foundry’s essential functionalities (create/run/list agents, etc.) in plugin form.
standard_lib/ is a standard library plugin, providing tools (e.g., code manipulation, search) commonly useful for new agents.
agents/

Each subdirectory is one agent.
Includes:
agent.config.json with the agent’s settings (e.g., name, description, dependencies).
.env for environment variables (e.g., API keys).
plugins/ folder for any custom or dynamically generated plugins.
venv/ for the agent’s Python environment.
A main entry script (e.g., main.py) to run the agent.
3. The Foundry
The Foundry is both a CLI tool and an agent. Its responsibilities:

Create New Agents

Scaffold a folder under agents/{agent_name}.
Generate default config files (agent.config.json, .env, etc.).
Optionally copy or reference the standard_lib tools if desired.
Set up a Python virtual environment and install necessary packages (like semantic-kernel, python-dotenv, and any user-specified dependencies).
Run Existing Agents

Activate that agent’s virtual environment.
Start an interactive session (chat) with the agent or run it in a “headless” way.
Keep track of conversation context while running (stateful), but discard after the session ends.
Manage Agents

List available agents by scanning the agents/ folder.
(Optionally) delete an agent by removing its folder.
Provide a --debug flag in every command for verbose logs.
Interact with the User

Explain environment variables if needed.
Prompt for user approval when an agent wants to create or modify a plugin.
Validate system requirements (Python version, presence of API keys) using a function like validate_environment().
4. Core Tools as a Plugin
Foundry Core Plugin (foundry_core/)
create_agent.py: Logic to create a new agent folder, config files, .env, venv, etc.
run_agent.py: Logic to load an agent’s agent.config.json, activate its venv, and launch interactive or run mode.
list_agents.py: Lists subdirectories under agents/.
Since these are structured as a plugin, the Foundry CLI can import them just like any other plugin code, ensuring consistency in how “tools” are handled.

5. Standard Library Plugin
standard_lib/
read_write_code.py: Tools to read/modify the agent’s code files (with user confirmation).
grep_codebase.py: Tools for searching keywords within the agent’s file tree.
web_search.py: A function or class enabling internet queries, if desired.
Additional common logic (e.g., environment variable or dev tool helpers).
Agents can use these standard tools by referencing them in agent.config.json or by copying them into their own plugins/ folder if isolation is preferred.

6. Agent Architecture & Workflow
Agent Directory

agent.config.json:
json
Copy
Edit
{
  "name": "ExampleAgent",
  "description": "An agent that does X, Y, Z",
  "dependencies": ["semantic-kernel", "python-dotenv"],
  "entry_module": "main.py",
  "tools": ["read_write_code", "grep_codebase"],
  "plugins": ["my_custom_plugin"]
}
.env: Contains environment variables (e.g., OPENAI_API_KEY=).
plugins/: Each plugin subfolder has a __init__.py plus any other Python files.
venv/: Created by the Foundry.
main.py: Entry point for the agent’s run logic (interactive shell, conversation loop, etc.).
Stateful Execution

During a session, the agent can remember conversation context.
The memory resets after the session ends (no persistent conversation logs by default).
If the agent wants to add or modify plugins, it must ask the user to confirm.
Edit vs. Run Mode

Run Mode: Responds to user queries with its current set of tools and plugins.
Edit Mode: Allows the agent (and user) to collaborate on adding or updating code, typically for new functionalities or debugging.
7. CLI Commands (Using Click)
Below is a recommended approach for foundry_cli.py:

foundry create [AGENT_NAME]

Purpose: Create a new agent directory under agents/{agent_name}.
Flow:
Check if AGENT_NAME exists. If not, create the folder.
Write a default agent.config.json.
Create a placeholder .env (optionally prompt the user to fill it).
Copy or link standard library plugins if the user requests them.
Create a virtual environment (venv/) and install dependencies.
(Optional) run the agent immediately if a --run flag is provided.
Common Options:
--description: Add a quick summary in the config.
--dependencies: A comma-separated list of extra PyPI packages.
--debug: Print verbose logs.
foundry run [AGENT_NAME]

Purpose: Activate the chosen agent’s environment and start a chat session.
Flow:
Validate environment (check Python version, keys, etc.).
Load the agent’s config + .env.
Launch an interactive shell (with streaming responses if integrated with OpenAI).
Options:
--edit: Enter edit mode (agent can propose plugin edits).
--debug: Verbose logs.
foundry list

Purpose: Scan the agents/ folder for subdirectories.
Flow:
Print each agent’s name and possibly a one-line description from agent.config.json.
(Optional) foundry delete [AGENT_NAME]

Purpose: Remove an agent folder if no longer needed.
Flow: Confirms with the user, then deletes the agents/{agent_name} directory.
8. Interactive Agent Sessions
Startup
foundry run MyAgent → Foundry loads the config and environment, then calls the agent’s main.py.
Conversation
The agent uses its listed tools/plugins plus any local memory.
If the user’s query requires new functionality, the agent can propose generating or editing plugins (edit mode).
User Confirmation
When the agent wants to write new code or alter existing code, it must prompt the user.
Exit
The user types exit or presses Ctrl+C.
The session ends, memory is cleared, but any newly added files remain for future sessions.
9. Environment Variables Management
Whenever an agent or the Foundry requires new environment variables (e.g., an API key), it should:
Explain what is needed and why.
Prompt the user to provide initial values if desired.
Write or update the agent’s .env.
This keeps sensitive data localized to each agent’s environment, with no centralized registry necessary.

10. Security & Deployment (Deferred)
For now, we are not focusing on advanced security or deployment solutions.
Future iterations might include sandboxing, plugin versioning, rate limiting, or containerization.
11. Summary
Local Storage: All agents live under agents/, each with its own config and venv/.
Foundry as an Agent: Implemented via a CLI plus a “foundry_core” plugin.
Plugins: Each agent has local plugins, can also copy from the Foundry’s standard_lib.
Modes: Run mode (regular chat) vs. Edit mode (co-develop or debug).
Minimal Dependencies: semantic-kernel and python-dotenv as a baseline, plus any new ones specified by the user or agent’s purpose.
Conversation Lifecycle: Agents are stateless between runs but hold memory during each session.
Debugging: A --debug flag for verbose output at every CLI command.