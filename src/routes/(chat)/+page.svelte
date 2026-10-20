<script lang="ts">
	import { onMount } from 'svelte';

	type HermesSession = {
		id: string;
		title?: string | null;
		preview?: string | null;
		model?: string | null;
		last_active?: string | number | null;
		parent_session_id?: string | null;
	};

	type HermesMessage = {
		id: string;
		role: string;
		content: unknown;
		timestamp?: string | number | null;
		reasoning?: string | null;
		reasoning_content?: string | null;
	};

	type DisplayMessage = {
		id: string;
		role: string;
		content: string;
		timestamp?: string | number | null;
		pending?: boolean;
	};

	type PendingApproval = {
		runId: string;
		requestId?: string;
		executionGeneration?: number;
		toolName?: string;
		message?: string;
	};

	type ModelChoice = {
		id: string;
		model: string;
		provider: string;
		providerName: string;
	};

	type HermesModelProvider = {
		authenticated?: boolean;
		is_current?: boolean;
		models?: unknown[];
		name?: string;
		slug?: string;
	};

	const apiKeyStorageKey = 'hermes-gateway-ui.api-key';
	const sessionKeyStorageKey = 'hermes-gateway-ui.session-keys';

	let apiKey = $state('');
	let isConnected = $state(false);
	let isConnecting = $state(false);
	let error = $state('');
	let sessions = $state<HermesSession[]>([]);
	let activeSessionId = $state<string | null>(null);
	let messages = $state<DisplayMessage[]>([]);
	let modelChoices = $state<ModelChoice[]>([]);
	let selectedModelId = $state('');
	let prompt = $state('');
	let isStreaming = $state(false);
	let activeRunId = $state<string | null>(null);
	let activity = $state<string[]>([]);
	let pendingApproval = $state<PendingApproval | null>(null);
	let sessionKeys = $state<Record<string, string>>({});
	let streamController: AbortController | null = null;

	let activeSession = $derived(sessions.find((session) => session.id === activeSessionId) ?? null);
	let selectedModel = $derived(
		modelChoices.find((choice) => choice.id === selectedModelId) ?? null
	);

	function contentText(content: unknown): string {
		if (typeof content === 'string') return content;

		if (Array.isArray(content)) {
			return content
				.map((part) => {
					if (typeof part === 'string') return part;

					if (part && typeof part === 'object' && 'text' in part) {
						const text = (part as { text?: unknown }).text;

						return typeof text === 'string' ? text : '';
					}

					return '';
				})
				.join('');
		}

		if (content == null) return '';

		return JSON.stringify(content);
	}

	function errorMessage(payload: unknown, status: number): string {
		if (payload && typeof payload === 'object') {
			const result = payload as { error?: { message?: unknown } | unknown; message?: unknown };

			if (typeof result.message === 'string') return result.message;

			if (result.error && typeof result.error === 'object' && 'message' in result.error) {
				const message = (result.error as { message?: unknown }).message;

				if (typeof message === 'string') return message;
			}

			if (typeof result.error === 'string') return result.error;
		}

		return `Hermes Gateway request failed (${status}).`;
	}

	function createSessionKey(): string {
		return `hermes-webui:${crypto.randomUUID()}`;
	}

	function sessionKeyFor(sessionId: string): string {
		const existing = sessionKeys[sessionId];

		if (existing) return existing;

		const sessionKey = createSessionKey();

		sessionKeys = { ...sessionKeys, [sessionId]: sessionKey };
		localStorage.setItem(sessionKeyStorageKey, JSON.stringify(sessionKeys));

		return sessionKey;
	}

	function headers(extra?: HeadersInit, sessionId?: string): Headers {
		if (!apiKey.trim()) throw new Error('Enter the Hermes Gateway API key first.');

		const result = new Headers(extra);

		result.set('Authorization', `Bearer ${apiKey.trim()}`);
		result.set('Accept', 'application/json');

		if (sessionId) result.set('X-Hermes-Session-Key', sessionKeyFor(sessionId));

		return result;
	}

	async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
		const requestHeaders = headers(init.headers);

		if (init.body && !requestHeaders.has('Content-Type')) {
			requestHeaders.set('Content-Type', 'application/json');
		}

		const response = await fetch(path, { ...init, headers: requestHeaders });

		if (!response.ok) {
			const payload = await response.json().catch(() => null);

			throw new Error(errorMessage(payload, response.status));
		}

		return response.json() as Promise<T>;
	}

	function sessionFromResponse(response: unknown): HermesSession {
		if (response && typeof response === 'object' && 'session' in response) {
			return (response as { session: HermesSession }).session;
		}

		return response as HermesSession;
	}

	function sessionList(response: unknown): HermesSession[] {
		if (
			response &&
			typeof response === 'object' &&
			Array.isArray((response as { data?: unknown }).data)
		) {
			return (response as { data: HermesSession[] }).data;
		}

		return [];
	}

	function messagesFromResponse(response: unknown): DisplayMessage[] {
		if (
			!response ||
			typeof response !== 'object' ||
			!Array.isArray((response as { data?: unknown }).data)
		) {
			return [];
		}

		return (response as { data: HermesMessage[] }).data.map((message) => ({
			content: contentText(message.content),
			id: message.id,
			role: message.role,
			timestamp: message.timestamp
		}));
	}

	function sortSessions(items: HermesSession[]): HermesSession[] {
		return [...items].sort((left, right) => {
			const leftTime = left.last_active ? new Date(left.last_active).getTime() : 0;
			const rightTime = right.last_active ? new Date(right.last_active).getTime() : 0;

			return rightTime - leftTime;
		});
	}

	function modelChoicesFromResponse(response: {
		providers?: HermesModelProvider[];
	}): ModelChoice[] {
		const currentProviderFirst = [...(response.providers ?? [])].sort(
			(left, right) => Number(Boolean(right.is_current)) - Number(Boolean(left.is_current))
		);

		return currentProviderFirst.flatMap((provider) => {
			const providerSlug = provider.slug;

			if (!providerSlug || provider.authenticated === false || !Array.isArray(provider.models)) {
				return [];
			}

			return provider.models.flatMap((entry) => {
				const model =
					typeof entry === 'string'
						? entry
						: entry &&
							  typeof entry === 'object' &&
							  typeof (entry as { id?: unknown }).id === 'string'
							? (entry as { id: string }).id
							: '';

				if (!model) return [];

				return [
					{
						id: `${providerSlug}::${model}`,
						model,
						provider: providerSlug,
						providerName: provider.name || providerSlug
					}
				];
			});
		});
	}

	async function loadModelOptions(refresh = false): Promise<void> {
		const suffix = refresh
			? '?include_unconfigured=false&refresh=1'
			: '?include_unconfigured=false';
		const response = await api<{ providers?: HermesModelProvider[] }>(
			`/api/model/options${suffix}`
		);

		modelChoices = modelChoicesFromResponse(response);

		if (!modelChoices.some((choice) => choice.id === selectedModelId)) {
			selectedModelId = modelChoices[0]?.id ?? '';
		}
	}

	async function refreshSessions(): Promise<void> {
		const response = await api<unknown>('/api/sessions?limit=100');

		sessions = sortSessions(sessionList(response));
	}

	async function loadMessages(sessionId: string): Promise<void> {
		const response = await api<unknown>(
			`/api/sessions/${encodeURIComponent(sessionId)}/messages?order=oldest`
		);

		if (activeSessionId === sessionId) messages = messagesFromResponse(response);
	}

	async function connect(): Promise<void> {
		isConnecting = true;
		error = '';
		try {
			const capabilities = await api<{ features?: Record<string, boolean> }>('/v1/capabilities');

			if (capabilities.features?.session_chat_streaming === false) {
				throw new Error(
					'This Hermes Gateway does not expose session chat streaming. Update Hermes Gateway and restart its API server.'
				);
			}

			await Promise.all([loadModelOptions(), refreshSessions()]);
			isConnected = true;
			localStorage.setItem(apiKeyStorageKey, apiKey.trim());
		} catch (cause) {
			isConnected = false;
			error = cause instanceof Error ? cause.message : 'Could not connect to Hermes Gateway.';
		} finally {
			isConnecting = false;
		}
	}

	async function createSession(): Promise<HermesSession | null> {
		error = '';
		try {
			// "New chat" is only a UI placeholder. Sending it as a stored title makes
			// each new session collide with the Gateway's unique-title constraint and
			// prevents Hermes from replacing it with an automatic summary.
			const body: Record<string, string> = { source: 'hermes_gateway_ui' };

			if (selectedModel) {
				body.model = selectedModel.model;
				body.provider = selectedModel.provider;
			}

			const created = sessionFromResponse(
				await api<unknown>('/api/sessions', {
					body: JSON.stringify(body),
					method: 'POST'
				})
			);

			sessions = [created, ...sessions.filter((session) => session.id !== created.id)];
			activeSessionId = created.id;
			messages = [];
			activity = [];
			sessionKeyFor(created.id);

			return created;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not create a Hermes session.';

			return null;
		}
	}

	async function openSession(sessionId: string): Promise<void> {
		if (isStreaming || sessionId === activeSessionId) return;

		error = '';
		activeSessionId = sessionId;
		messages = [];
		activity = [];
		try {
			await loadMessages(sessionId);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not load this Hermes session.';
		}
	}

	function appendActivity(text: string): void {
		activity = [...activity.slice(-5), text];
	}

	function applyStreamEvent(
		eventName: string,
		payload: Record<string, unknown>,
		assistantId: string
	): void {
		const runId = typeof payload.run_id === 'string' ? payload.run_id : undefined;

		if (runId) activeRunId = runId;

		if (eventName === 'assistant.delta') {
			const delta = typeof payload.delta === 'string' ? payload.delta : '';

			messages = messages.map((message) =>
				message.id === assistantId ? { ...message, content: message.content + delta } : message
			);

			return;
		}

		if (eventName === 'assistant.completed') {
			const content = contentText(payload.content);

			messages = messages.map((message) =>
				message.id === assistantId
					? { ...message, content: content || message.content, pending: false }
					: message
			);

			return;
		}

		if (eventName === 'assistant.commentary') {
			const commentary = typeof payload.text === 'string' ? payload.text : '';

			if (commentary) appendActivity(commentary);

			return;
		}

		if (eventName === 'tool.started') {
			appendActivity(
				`Running ${typeof payload.tool_name === 'string' ? payload.tool_name : 'tool'}…`
			);

			return;
		}

		if (eventName === 'tool.completed' || eventName === 'tool.failed') {
			const tool = typeof payload.tool_name === 'string' ? payload.tool_name : 'Tool';

			appendActivity(`${tool} ${eventName === 'tool.completed' ? 'completed' : 'failed'}.`);

			return;
		}

		if (eventName === 'approval.request') {
			pendingApproval = {
				executionGeneration:
					typeof payload.execution_generation === 'number'
						? payload.execution_generation
						: undefined,
				message: typeof payload.message === 'string' ? payload.message : undefined,
				requestId: typeof payload.request_id === 'string' ? payload.request_id : undefined,
				runId: runId ?? activeRunId ?? '',
				toolName: typeof payload.tool_name === 'string' ? payload.tool_name : undefined
			};
			appendActivity('Hermes is waiting for tool approval.');

			return;
		}

		if (
			eventName === 'run.completed' ||
			eventName === 'run.failed' ||
			eventName === 'run.cancelled' ||
			eventName === 'run.interrupted'
		) {
			activeRunId = null;

			if (eventName !== 'run.completed') appendActivity(`Run ${eventName.slice(4)}.`);

			return;
		}

		if (eventName === 'error' && typeof payload.message === 'string') {
			error = payload.message;
		}
	}

	function consumeSseBlock(block: string, assistantId: string): void {
		const lines = block.replaceAll('\r\n', '\n').split('\n');

		let eventName = 'message';

		const data: string[] = [];

		for (const line of lines) {
			if (line.startsWith('event:')) eventName = line.slice(6).trim();

			if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
		}

		if (!data.length || data.join('\n') === '[DONE]' || eventName === 'done') return;

		try {
			const payload = JSON.parse(data.join('\n')) as Record<string, unknown>;

			applyStreamEvent(eventName, payload, assistantId);
		} catch {
			appendActivity('Received an unreadable event from Hermes Gateway.');
		}
	}

	async function sendMessage(): Promise<void> {
		const input = prompt.trim();

		if (!input || isStreaming) return;

		error = '';
		let sessionId = activeSessionId;

		if (!sessionId) {
			const session = await createSession();

			if (!session) return;

			sessionId = session.id;
		}

		const assistantId = `pending-${crypto.randomUUID()}`;

		messages = [
			...messages,
			{ content: input, id: `local-${crypto.randomUUID()}`, role: 'user' },
			{ content: '', id: assistantId, pending: true, role: 'assistant' }
		];
		prompt = '';
		isStreaming = true;
		activity = [];
		streamController = new AbortController();

		try {
			const body: Record<string, string> = { input };

			if (selectedModel) {
				body.model = selectedModel.model;
				body.provider = selectedModel.provider;
			}

			const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/chat/stream`, {
				body: JSON.stringify(body),
				headers: {
					...Object.fromEntries(headers(undefined, sessionId)),
					'Content-Type': 'application/json'
				},
				method: 'POST',
				signal: streamController.signal
			});

			if (!response.ok || !response.body) {
				const payload = await response.json().catch(() => null);

				throw new Error(errorMessage(payload, response.status));
			}

			const reader = response.body.getReader();
			const decoder = new TextDecoder();

			let remainder = '';

			while (true) {
				const { done, value } = await reader.read();

				if (done) break;

				remainder += decoder.decode(value, { stream: true }).replaceAll('\r\n', '\n');
				let boundary = remainder.indexOf('\n\n');

				while (boundary >= 0) {
					consumeSseBlock(remainder.slice(0, boundary), assistantId);
					remainder = remainder.slice(boundary + 2);
					boundary = remainder.indexOf('\n\n');
				}
			}

			if (remainder.trim()) consumeSseBlock(remainder, assistantId);
		} catch (cause) {
			if (!(cause instanceof DOMException && cause.name === 'AbortError')) {
				error = cause instanceof Error ? cause.message : 'Hermes Gateway streaming failed.';
			}
		} finally {
			isStreaming = false;
			streamController = null;
			activeRunId = null;
			messages = messages.map((message) =>
				message.id === assistantId ? { ...message, pending: false } : message
			);

			if (activeSessionId === sessionId) {
				try {
					await Promise.all([loadMessages(sessionId), refreshSessions()]);
				} catch {
					// The completed stream is still visible; a later refresh can reconcile history.
				}
			}
		}
	}

	async function stopRun(): Promise<void> {
		if (!activeRunId) {
			streamController?.abort();

			return;
		}

		try {
			await api(`/v1/runs/${encodeURIComponent(activeRunId)}/stop`, { method: 'POST' });
			appendActivity('Stop requested.');
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not stop this run.';
		}
	}

	async function answerApproval(choice: 'once' | 'session' | 'always' | 'deny'): Promise<void> {
		if (!pendingApproval?.runId) return;

		try {
			const body: { choice: string; execution_generation?: number; request_id?: string } = {
				choice
			};

			if (pendingApproval.requestId) body.request_id = pendingApproval.requestId;

			if (pendingApproval.executionGeneration !== undefined) {
				body.execution_generation = pendingApproval.executionGeneration;
			}

			await api(`/v1/runs/${encodeURIComponent(pendingApproval.runId)}/approval`, {
				body: JSON.stringify(body),
				method: 'POST'
			});
			pendingApproval = null;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not submit the approval choice.';
		}
	}

	async function forkSession(): Promise<void> {
		if (!activeSessionId || isStreaming) return;

		if (!confirm('Branch this session? Hermes will end the current session and open the branch.'))
			return;

		try {
			const forked = sessionFromResponse(
				await api<unknown>(`/api/sessions/${encodeURIComponent(activeSessionId)}/fork`, {
					body: JSON.stringify({}),
					method: 'POST'
				})
			);

			await refreshSessions();
			activeSessionId = forked.id;
			await loadMessages(forked.id);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not branch this Hermes session.';
		}
	}

	async function deleteSession(): Promise<void> {
		if (!activeSessionId || isStreaming) return;

		if (!confirm('Delete this Hermes session and its saved transcript?')) return;

		const deletingId = activeSessionId;

		try {
			await api(`/api/sessions/${encodeURIComponent(deletingId)}`, { method: 'DELETE' });
			sessions = sessions.filter((session) => session.id !== deletingId);
			const { [deletingId]: _removed, ...remainingSessionKeys } = sessionKeys;

			sessionKeys = remainingSessionKeys;
			localStorage.setItem(sessionKeyStorageKey, JSON.stringify(sessionKeys));
			activeSessionId = null;
			messages = [];
			activity = [];
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not delete this Hermes session.';
		}
	}

	onMount(() => {
		apiKey = localStorage.getItem(apiKeyStorageKey) ?? '';
		try {
			const stored = JSON.parse(localStorage.getItem(sessionKeyStorageKey) ?? '{}');

			if (stored && typeof stored === 'object' && !Array.isArray(stored)) {
				const validEntries = Object.entries(stored).filter(
					(entry): entry is [string, string] => typeof entry[1] === 'string' && entry[1].length > 0
				);

				sessionKeys = Object.fromEntries(validEntries);
			}
		} catch {
			localStorage.removeItem(sessionKeyStorageKey);
		}
	});
</script>

<svelte:head>
	<title>Hermes Gateway UI</title>

	<meta content="Native Hermes Gateway session UI" name="description" />
</svelte:head>

<main class="min-h-screen bg-base-200 text-base-content">
	<div class="mx-auto flex min-h-screen max-w-7xl flex-col p-3 sm:p-6">
		<header
			class="mb-3 flex flex-col gap-3 rounded-box border border-base-300 bg-base-100 p-4 shadow-sm lg:flex-row lg:items-center lg:justify-between"
		>
			<div>
				<h1 class="text-xl font-semibold">Hermes Gateway</h1>

				<p class="text-sm opacity-65">Native sessions, streaming runs, tools, and approvals.</p>
			</div>

			<a class="btn btn-ghost" href="#/api">API Explorer</a>

			<form
				class="flex w-full flex-col gap-2 sm:flex-row lg:w-auto"
				onsubmit={(event) => {
					event.preventDefault();
					connect();
				}}
			>
				<input
					bind:value={apiKey}
					autocomplete="current-password"
					class="input input-bordered w-full sm:w-80"
					placeholder="Hermes API key"
					type="password"
				/>

				<button class="btn btn-primary" disabled={isConnecting || !apiKey.trim()} type="submit">
					{isConnecting ? 'Connecting…' : isConnected ? 'Reconnect' : 'Connect'}
				</button>
			</form>
		</header>

		{#if error}
			<div class="alert alert-error mb-3 text-sm">
				<span>{error}</span><button class="btn btn-ghost btn-xs" onclick={() => (error = '')}
					>Dismiss</button
				>
			</div>
		{/if}

		{#if !isConnected}
			<section class="mx-auto flex w-full max-w-2xl flex-1 items-center">
				<div class="w-full rounded-box border border-base-300 bg-base-100 p-8 shadow-sm">
					<h2 class="text-lg font-semibold">Connect to Hermes API</h2>

					<p class="mt-2 leading-6 opacity-75">
						Enter the API-server key configured in Hermes Gateway. The browser stores it locally
						only after a successful capability check.
					</p>

					<p class="mt-4 text-sm opacity-60">
						This UI calls Hermes endpoints directly: <code>/v1/capabilities</code>,
						<code>/api/model/options</code>, and <code>/api/sessions</code>.
					</p>
				</div>
			</section>
		{:else}
			<section class="grid flex-1 gap-3 lg:grid-cols-[18rem_minmax(0,1fr)]">
				<aside
					class="flex min-h-0 flex-col rounded-box border border-base-300 bg-base-100 p-3 shadow-sm"
				>
					<div class="mb-3 flex gap-2">
						<button class="btn btn-primary btn-sm flex-1" onclick={createSession}>New chat</button>

						<button
							aria-label="Refresh sessions"
							class="btn btn-ghost btn-sm"
							onclick={() => refreshSessions().catch((cause) => (error = cause.message))}
							>Refresh</button
						>
					</div>

					<div class="min-h-0 space-y-1 overflow-y-auto">
						{#if sessions.length === 0}
							<p class="p-3 text-sm opacity-60">No Hermes sessions yet.</p>
						{/if}

						{#each sessions as session (session.id)}
							<button
								class:btn-active={session.id === activeSessionId}
								class="btn btn-ghost h-auto w-full justify-start px-3 py-2 text-left normal-case"
								onclick={() => openSession(session.id)}
							>
								<span class="min-w-0">
									<span class="block truncate font-medium"
										>{session.title || session.preview || 'New chat'}</span
									>

									<span class="block truncate text-xs opacity-60"
										>{session.model || 'Hermes default model'}</span
									>
								</span>
							</button>
						{/each}
					</div>
				</aside>

				<section
					class="flex min-h-[32rem] min-w-0 flex-col rounded-box border border-base-300 bg-base-100 shadow-sm"
				>
					<div class="flex flex-wrap items-center gap-2 border-b border-base-300 p-3">
						<div class="mr-auto min-w-0">
							<h2 class="truncate font-semibold">
								{activeSession?.title || activeSession?.preview || 'New chat'}
							</h2>

							<p class="text-xs opacity-60">
								{activeSession
									? `Session ${activeSession.id}`
									: 'Create a session or send your first message.'}
							</p>
						</div>

						<select
							bind:value={selectedModelId}
							aria-label="Model"
							class="select select-bordered select-sm max-w-56"
						>
							<option value="">Hermes default model</option>

							{#each modelChoices as choice (choice.id)}
								<option value={choice.id}>{choice.providerName} · {choice.model}</option>
							{/each}
						</select>

						<button
							aria-label="Refresh model options"
							class="btn btn-ghost btn-sm"
							disabled={isStreaming}
							onclick={() => loadModelOptions(true).catch((cause) => (error = cause.message))}
							>Models</button
						>

						{#if activeSession}
							<button class="btn btn-ghost btn-sm" disabled={isStreaming} onclick={forkSession}
								>Branch</button
							>

							<button
								class="btn btn-ghost btn-sm text-error"
								disabled={isStreaming}
								onclick={deleteSession}>Delete</button
							>
						{/if}
					</div>

					<div class="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
						{#if messages.length === 0}
							<p class="py-16 text-center opacity-60">
								Start a Hermes session to keep its transcript and run history on Gateway.
							</p>
						{/if}

						{#each messages as message (message.id)}
							<div
								class:chat-end={message.role === 'user'}
								class:chat-start={message.role !== 'user'}
								class="chat"
							>
								<div class="chat-header text-xs opacity-55">
									{message.role === 'user' ? 'You' : 'Hermes'}
								</div>

								<div
									class:chat-bubble-primary={message.role === 'user'}
									class="chat-bubble max-w-3xl whitespace-pre-wrap"
								>
									{message.content || (message.pending ? 'Thinking…' : '')}
								</div>
							</div>
						{/each}
					</div>

					{#if activity.length || pendingApproval}
						<div class="border-t border-base-300 bg-base-200/50 p-3 text-sm">
							{#each activity as item (item)}<p class="py-0.5 opacity-75">{item}</p>{/each}

							{#if pendingApproval}
								<div class="mt-2 rounded-box border border-warning/30 bg-warning/10 p-3">
									<p class="mb-2">
										{pendingApproval.message ||
											`${pendingApproval.toolName || 'A tool'} needs approval.`}
									</p>

									<div class="flex flex-wrap gap-2">
										<button class="btn btn-primary btn-xs" onclick={() => answerApproval('once')}
											>Allow once</button
										>

										<button class="btn btn-ghost btn-xs" onclick={() => answerApproval('session')}
											>This session</button
										>

										<button class="btn btn-ghost btn-xs" onclick={() => answerApproval('always')}
											>Always</button
										>

										<button
											class="btn btn-ghost btn-xs text-error"
											onclick={() => answerApproval('deny')}>Deny</button
										>
									</div>
								</div>
							{/if}
						</div>
					{/if}

					<form
						class="flex gap-2 border-t border-base-300 p-3"
						onsubmit={(event) => {
							event.preventDefault();
							sendMessage();
						}}
					>
						<textarea
							bind:value={prompt}
							class="textarea textarea-bordered min-h-12 flex-1"
							disabled={isStreaming}
							onkeydown={(event) => {
								if (event.key === 'Enter' && !event.shiftKey) {
									event.preventDefault();
									sendMessage();
								}
							}}
							placeholder="Message Hermes…"
						></textarea>

						{#if isStreaming}
							<button class="btn btn-warning self-end" onclick={stopRun} type="button">Stop</button>
						{:else}
							<button class="btn btn-primary self-end" disabled={!prompt.trim()} type="submit"
								>Send</button
							>
						{/if}
					</form>
				</section>
			</section>
		{/if}
	</div>
</main>
