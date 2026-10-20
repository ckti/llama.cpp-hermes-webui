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

### Remote access and file dialogs

When running the browser itself remotely with SSH X forwarding, Linux desktop
portals can send the native file dialog to the remote desktop instead of the
forwarded display. The webpage cannot choose that display.

- **LibreWolf/Firefox:** open `about:config` and set
  `widget.use-xdg-desktop-portal.file-picker` to `0` to use the GTK picker
  (see [Mozilla's guidance](https://bugzilla.mozilla.org/show_bug.cgi?id=2026210#c2)).
  Reset this preference when returning to a normal desktop session if desired.
- **Chrome:** from the SSH shell with X forwarding, start a separate browser
  profile with no desktop-portal bus. This makes Chrome use its native picker
  on the forwarded display and avoids temporary portal paths that disappear
  before Chrome can read them:

  ```bash
  hermes_chrome_profile=$(mktemp -d -t hermes-chrome-x11.XXXXXX)
  DBUS_SESSION_BUS_ADDRESS="unix:path=$hermes_chrome_profile/no-session-bus" \
    google-chrome --user-data-dir="$hermes_chrome_profile" http://localhost:8788
  ```

  The separate profile prevents Chrome from reusing a browser process attached
  to another desktop session. Enter the Gateway API key again in this profile.

Both approaches still select files on the machine running the remote browser.
Alternatively, to select files from your own computer, forward the UI port with
`ssh -N -L 18788:127.0.0.1:8788 user@remote-host` and open
`http://127.0.0.1:18788` in a local browser.

## Hermes API integration

The browser calls documented Hermes endpoints only:

- `GET /v1/capabilities` and `GET /api/model/options` during connection.
- `GET`, `POST`, `DELETE`, and `POST /fork` under `/api/sessions` for durable
  conversations and their saved transcripts.
- `POST /api/sessions/{id}/chat/stream` for Server-Sent Event chat streaming.
- `/v1/runs/{id}/stop` and `/v1/runs/{id}/approval` for active-run controls.

The composer accepts image and text/code attachments. Images are sent as inline image content and
text files are included in the message with their filename; PDF, audio, video, and other binary
uploads are not offered because Gateway's session-chat API does not support document uploads.
Click **Attach** to open the attachments panel, then use **Choose files** or drag files into
the panel. Selected files appear above the message, where they can be removed before sending.

`hermes_bridge.py` serves the static build and transparently forwards `/api/*`,
`/v1/*`, and `/health` to Gateway on the same origin. It does not translate,
store, or log the API key. Branching uses Hermes's native session fork and
therefore ends the source session, as documented by the Gateway API.

The **API Explorer** (open `#/api`) loads the connected Gateway's
`/openapi.json` contract when it is available. Gateways that do not publish
OpenAPI fall back to the official Hermes API contract—chat, responses, runs,
browser control, jobs, sessions, health, model discovery, and skills/toolsets—
then merge the connected Gateway's `/v1/capabilities` routes. It renders path,
query, and header parameters plus declared request bodies. Its requests are
sent through an isolated `/__hermes_api/*` bridge prefix, which is stripped
before Gateway receives them.

For each native chat session, the UI also creates an opaque local
`X-Hermes-Session-Key`. This is distinct from the transcript session ID and
gives Hermes a stable, isolated scope for long-term memory in that chat.

See [UPSTREAM.md](UPSTREAM.md) for the imported source revision.
