# Hermes Gateway UI

This is a standalone UI for Hermes Gateway. Its visual foundation was imported
from the SvelteKit UI in llama.cpp, but it makes no llama.cpp API calls or model
loading requests. Conversations, streaming, tools, approvals, and history use
Hermes Gateway's native API.

## Requirements

- Node.js 20 or newer
- A running Hermes Gateway API Server, normally at `http://127.0.0.1:8642`
- Its API key, configured in Gateway and entered into the UI connection field
  (the UI stores its copy in browser local storage only after connecting)

Start Hermes Gateway with its API Server enabled and a strong `API_SERVER_KEY`.
For example:

```bash
hermes config set API_SERVER_ENABLED true
hermes config set API_SERVER_KEY your-strong-secret
hermes gateway stop && hermes gateway
```

Enter the same `API_SERVER_KEY` value in the UI's API-key field. Gateway must
be restarted after changing it. See
`hermes-agent/website/docs/user-guide/features/api-server.md` for details.

## Development

```bash
cd new-webui
npm ci
cp .env.example .env.local
npm run dev
```

Open `http://127.0.0.1:5173`, then enter the Gateway API key.
`VITE_PUBLIC_HERMES_GATEWAY_ORIGIN` in `.env.local` chooses a different local
Gateway origin for the Vite proxy.

## Production-style local run

```bash
cd new-webui
npm ci
npm run build
HERMES_UI_GATEWAY_URL=http://127.0.0.1:8642 npm run serve
```

The bridge listens on `http://127.0.0.1:8788` by default. Override its bind
address and port with `HERMES_UI_HOST` and `HERMES_UI_PORT`, or use the matching
command-line options. Keep it on loopback unless you deliberately place a
trusted authentication and TLS layer in front of it.

## Hermes API integration

The browser calls documented Hermes endpoints only:

- `GET /v1/capabilities` and `GET /v1/models` during connection.
- `GET`, `POST`, `DELETE`, and `POST /fork` under `/api/sessions` for durable
  conversations and their saved transcripts.
- `POST /api/sessions/{id}/chat/stream` for Server-Sent Event chat streaming.
- `/v1/runs/{id}/stop` and `/v1/runs/{id}/approval` for active-run controls.

`hermes_bridge.py` serves the static build and transparently forwards `/api/*`,
`/v1/*`, and `/health` to Gateway on the same origin. It does not translate,
store, or log the API key. Branching uses Hermes's native session fork and
therefore ends the source session, as documented by the Gateway API.

See [UPSTREAM.md](UPSTREAM.md) for the imported source revision.
