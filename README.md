# Hermes Gateway UI

This is a standalone Hermes UI derived from the SvelteKit Web UI in llama.cpp.
It retains the upstream chat, conversation, attachment, markdown, responsive,
and PWA features while Hermes Gateway owns agent execution, tools, approvals,
and durable session history.

## Requirements

- Node.js 20 or newer
- A running Hermes Gateway API Server, normally at `http://127.0.0.1:8642`
- Its API key, which must be configured in Gateway and then entered into the
  UI's Settings panel (the UI stores its copy only in browser local storage)

Start Hermes Gateway with its API Server enabled and a strong `API_SERVER_KEY`.
For example:

```bash
hermes config set API_SERVER_ENABLED true
hermes config set API_SERVER_KEY your-strong-secret
hermes gateway stop && hermes gateway
```

The same `API_SERVER_KEY` value belongs in the UI Settings API-key field.
Gateway must be restarted after changing it: the durable session and memory
headers used by this UI are deliberately rejected when Gateway has no key.
See `hermes-agent/website/docs/user-guide/features/api-server.md` for details.

## Development

```bash
cd new-webui
npm ci
cp .env.example .env.local
npm run dev
```

Open `http://127.0.0.1:5173`, then enter the Gateway API key in Settings.
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

## Integration model

Each local browser conversation receives deterministic `X-Hermes-Session-Id`
and `X-Hermes-Session-Key` headers. Hermes therefore owns the agent transcript
and memory scope for that conversation; the browser stores its presentation copy
in IndexedDB. The UI's native browser/MCP agent loop is disabled to avoid two
independent owners executing tools for one chat. The upstream branching controls
remain browser-local and do not fork the Hermes session.

`hermes_bridge.py` supplies only the small llama.cpp compatibility surface the
upstream frontend requires (`/props`, `/slots`, and inactive stream discovery)
and proxies `/v1/*` requests unchanged to Hermes Gateway. It does not keep or
log the API key.

See [UPSTREAM.md](UPSTREAM.md) for the imported source revision.
