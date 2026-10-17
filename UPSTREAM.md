# Upstream source

The UI source in this directory was initialized from
`/home/ckti/github/llama.cpp.all/consolidated/tools/ui` at llama.cpp commit
`781dbc5ac`.

The imported sources remain under their upstream [MIT License](LICENSE).

The Hermes-specific layer is deliberately small:

- `hermes_bridge.py` serves the static build and proxies Gateway's OpenAI API
  on the same origin.
- `vite.config.ts` provides equivalent development-time compatibility routes.
- `ChatService` assigns the browser conversation a durable Hermes session and
  memory key.
- The browser-owned agentic loop is disabled, so Hermes Gateway remains the
  only tool and approval execution owner.
