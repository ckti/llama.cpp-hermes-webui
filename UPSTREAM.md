# Upstream source

The UI source in this directory was initialized from
`/home/ckti/github/llama.cpp.all/consolidated/tools/ui` at llama.cpp commit
`781dbc5ac`.

The imported sources remain under their upstream [MIT License](LICENSE).

The Hermes-specific application layer replaces the imported runtime wiring:

- `src/routes/(chat)/+page.svelte` uses Gateway's native session lifecycle,
  session-stream SSE endpoint, and run-control endpoints.
- `hermes_bridge.py` and `vite.config.ts` pass `/api/*`, `/v1/*`, and
  `/health` through to Gateway on the same origin.
- No llama.cpp endpoint, model-loader endpoint, or compatibility shim is used
  at runtime. The remaining imported source files are retained only as the
  visual/source foundation under their upstream license.
