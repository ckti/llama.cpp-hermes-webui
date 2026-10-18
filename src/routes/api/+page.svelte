<script lang="ts">
	import { onMount } from 'svelte';

	type OpenApiDocument = {
		components?: {
			parameters?: Record<string, OpenApiParameter>;
			schemas?: Record<string, OpenApiSchema>;
		};
		info?: { title?: string; version?: string };
		paths?: Record<string, OpenApiPathItem>;
	};

	type OpenApiPathItem = {
		parameters?: OpenApiParameter[];
		[key: string]: OpenApiOperation | OpenApiParameter[] | undefined;
	};

	type OpenApiOperation = {
		description?: string;
		operationId?: string;
		parameters?: OpenApiParameter[];
		requestBody?: {
			content?: Record<string, { schema?: OpenApiSchema }>;
			required?: boolean;
		};
		summary?: string;
		tags?: string[];
	};

	type OpenApiParameter = {
		description?: string;
		example?: unknown;
		in?: 'cookie' | 'header' | 'path' | 'query';
		name?: string;
		required?: boolean;
		schema?: OpenApiSchema;
	};

	type OpenApiSchema = {
		$ref?: string;
		default?: unknown;
		description?: string;
		enum?: unknown[];
		example?: unknown;
		format?: string;
		items?: OpenApiSchema;
		oneOf?: OpenApiSchema[];
		properties?: Record<string, OpenApiSchema>;
		type?: string;
	};

	type ApiOperation = {
		bodyContentType?: string;
		bodyExample?: unknown;
		bodySchema?: OpenApiSchema;
		description?: string;
		id: string;
		method: string;
		parameters: OpenApiParameter[];
		path: string;
		summary: string;
		tags: string[];
		transport?: 'http' | 'websocket';
	};

	const apiKeyStorageKey = 'hermes-gateway-ui.api-key';
	const methods = new Set(['delete', 'get', 'head', 'options', 'patch', 'post', 'put']);

	function documentedParameter(
		name: string,
		location: OpenApiParameter['in'],
		example = '',
		required = true,
		description?: string
	): OpenApiParameter {
		return { description, example, in: location, name, required, schema: { type: 'string' } };
	}

	function documentedOperation(
		method: string,
		path: string,
		summary: string,
		options: {
			bodyExample?: unknown;
			description?: string;
			parameters?: OpenApiParameter[];
			tags?: string[];
			transport?: 'http' | 'websocket';
		} = {}
	): ApiOperation {
		return {
			bodyContentType: options.bodyExample === undefined ? undefined : 'application/json',
			bodyExample: options.bodyExample,
			description: options.description,
			id: `official:${method}:${path}`,
			method,
			parameters: options.parameters ?? [],
			path,
			summary,
			tags: options.tags ?? ['Official API'],
			transport: options.transport ?? 'http'
		};
	}

	// The official API-server documentation is a usable fallback for Gateway
	// releases that do not publish an OpenAPI document (including the current
	// aiohttp implementation). The live capability document adds version-specific
	// extension routes after this documented baseline.
	const officialHermesOperations: ApiOperation[] = [
		documentedOperation('get', '/health', 'Gateway liveness', {
			description: 'Cheap public liveness probe.',
			tags: ['Health']
		}),
		documentedOperation('get', '/v1/health', 'OpenAI-compatible liveness', {
			tags: ['Health']
		}),
		documentedOperation('get', '/health/detailed', 'Gateway readiness', {
			description: 'Authenticated readiness and dependency status.',
			tags: ['Health']
		}),
		documentedOperation('post', '/v1/chat/completions', 'Chat completion', {
			bodyExample: {
				messages: [{ content: 'Hello from Hermes.', role: 'user' }],
				model: 'hermes-agent',
				stream: false
			},
			parameters: [
				documentedParameter('Idempotency-Key', 'header', '', false),
				documentedParameter('X-Hermes-Session-Id', 'header', '', false),
				documentedParameter('X-Hermes-Session-Key', 'header', '', false)
			],
			tags: ['OpenAI compatibility']
		}),
		documentedOperation('post', '/v1/responses', 'Response API turn', {
			bodyExample: { input: 'Hello from Hermes.', model: 'hermes-agent' },
			parameters: [
				documentedParameter('Idempotency-Key', 'header', '', false),
				documentedParameter('X-Hermes-Session-Id', 'header', '', false),
				documentedParameter('X-Hermes-Session-Key', 'header', '', false)
			],
			tags: ['OpenAI compatibility']
		}),
		documentedOperation('get', '/v1/responses/{response_id}', 'Get stored response', {
			parameters: [documentedParameter('response_id', 'path', 'resp_example')],
			tags: ['OpenAI compatibility']
		}),
		documentedOperation('delete', '/v1/responses/{response_id}', 'Delete stored response', {
			parameters: [documentedParameter('response_id', 'path', 'resp_example')],
			tags: ['OpenAI compatibility']
		}),
		documentedOperation('get', '/v1/models', 'List OpenAI-compatible models', {
			tags: ['OpenAI compatibility']
		}),
		documentedOperation('get', '/api/model/options', 'List Hermes model options', {
			description: 'Provider-aware model picker inventory. refresh=1 re-probes saved providers.',
			parameters: [
				documentedParameter('refresh', 'query', 'false', false),
				documentedParameter('include_unconfigured', 'query', 'false', false)
			],
			tags: ['Discovery']
		}),
		documentedOperation('get', '/v1/capabilities', 'Discover Gateway capabilities', {
			tags: ['Discovery']
		}),
		documentedOperation('get', '/v1/skills', 'List skills', { tags: ['Discovery'] }),
		documentedOperation('get', '/v1/toolsets', 'List toolsets', { tags: ['Discovery'] }),
		documentedOperation('post', '/v1/browser-control/register', 'Register browser controller', {
			bodyExample: {
				browser_profile_id: 'default',
				capabilities: ['browser_navigate'],
				controller_id: 'browser-controller-1',
				protocol_version: 1,
				session_id: 'session_id'
			},
			tags: ['Browser control']
		}),
		documentedOperation('get', '/v1/browser-control/ws', 'Browser controller WebSocket', {
			description:
				'WebSocket upgrade using the hermes-browser-control-v1 and one-time ticket subprotocols.',
			tags: ['Browser control'],
			transport: 'websocket'
		}),
		documentedOperation('post', '/v1/runs', 'Start agent run', {
			bodyExample: { input: 'Hello from Hermes.' },
			parameters: [
				documentedParameter('Idempotency-Key', 'header', '', false),
				documentedParameter('X-Hermes-Session-Key', 'header', '', false)
			],
			tags: ['Runs']
		}),
		documentedOperation('get', '/v1/runs/{run_id}', 'Get run status', {
			parameters: [documentedParameter('run_id', 'path', 'run_example')],
			tags: ['Runs']
		}),
		documentedOperation('get', '/v1/runs/{run_id}/events', 'Stream run events', {
			description: 'Server-Sent Event stream.',
			parameters: [documentedParameter('run_id', 'path', 'run_example')],
			tags: ['Runs']
		}),
		documentedOperation('post', '/v1/runs/{run_id}/resolve-unknown', 'Resolve unknown run', {
			bodyExample: { admission_id: 'adm_example', execution_generation: 1 },
			parameters: [documentedParameter('run_id', 'path', 'run_example')],
			tags: ['Runs']
		}),
		documentedOperation('post', '/v1/runs/{run_id}/stop', 'Stop run', {
			parameters: [documentedParameter('run_id', 'path', 'run_example')],
			tags: ['Runs']
		}),
		documentedOperation('post', '/v1/runs/{run_id}/approval', 'Respond to approval', {
			bodyExample: { choice: 'once', execution_generation: 1, request_id: 'request_id' },
			parameters: [documentedParameter('run_id', 'path', 'run_example')],
			tags: ['Runs']
		}),
		documentedOperation('post', '/v1/runs/{run_id}/clarify', 'Respond to clarification', {
			bodyExample: {
				answer: 'The requested clarification.',
				execution_generation: 1,
				request_id: 'request_id'
			},
			parameters: [documentedParameter('run_id', 'path', 'run_example')],
			tags: ['Runs']
		}),
		documentedOperation('post', '/v1/runs/{run_id}/steer', 'Steer active run', {
			bodyExample: { input: 'Focus on the tests first.' },
			parameters: [documentedParameter('run_id', 'path', 'run_example')],
			tags: ['Runs']
		}),
		documentedOperation('get', '/api/jobs', 'List scheduled jobs', { tags: ['Jobs'] }),
		documentedOperation('post', '/api/jobs', 'Create scheduled job', {
			bodyExample: {
				name: 'Example job',
				prompt: 'Summarize the latest project activity.',
				schedule: '0 9 * * *'
			},
			tags: ['Jobs']
		}),
		documentedOperation('get', '/api/jobs/{job_id}', 'Get scheduled job', {
			parameters: [documentedParameter('job_id', 'path', 'job_id')],
			tags: ['Jobs']
		}),
		documentedOperation('patch', '/api/jobs/{job_id}', 'Update scheduled job', {
			bodyExample: { schedule: '0 10 * * *' },
			parameters: [documentedParameter('job_id', 'path', 'job_id')],
			tags: ['Jobs']
		}),
		documentedOperation('delete', '/api/jobs/{job_id}', 'Delete scheduled job', {
			parameters: [documentedParameter('job_id', 'path', 'job_id')],
			tags: ['Jobs']
		}),
		documentedOperation('post', '/api/jobs/{job_id}/pause', 'Pause scheduled job', {
			parameters: [documentedParameter('job_id', 'path', 'job_id')],
			tags: ['Jobs']
		}),
		documentedOperation('post', '/api/jobs/{job_id}/resume', 'Resume scheduled job', {
			parameters: [documentedParameter('job_id', 'path', 'job_id')],
			tags: ['Jobs']
		}),
		documentedOperation('post', '/api/jobs/{job_id}/run', 'Run scheduled job', {
			bodyExample: { prompt: 'Use this optional one-off context.' },
			parameters: [documentedParameter('job_id', 'path', 'job_id')],
			tags: ['Jobs']
		}),
		documentedOperation('get', '/api/sessions', 'List sessions', {
			parameters: [
				documentedParameter('limit', 'query', '50', false),
				documentedParameter('offset', 'query', '0', false),
				documentedParameter('source', 'query', '', false),
				documentedParameter('include_children', 'query', 'false', false)
			],
			tags: ['Sessions']
		}),
		documentedOperation('post', '/api/sessions', 'Create session', {
			bodyExample: { source: 'hermes_gateway_ui', title: 'New session' },
			tags: ['Sessions']
		}),
		documentedOperation('get', '/api/sessions/{session_id}', 'Get session', {
			parameters: [documentedParameter('session_id', 'path', 'session_id')],
			tags: ['Sessions']
		}),
		documentedOperation('patch', '/api/sessions/{session_id}', 'Update session', {
			bodyExample: { title: 'Renamed session' },
			parameters: [documentedParameter('session_id', 'path', 'session_id')],
			tags: ['Sessions']
		}),
		documentedOperation('delete', '/api/sessions/{session_id}', 'Delete session', {
			parameters: [documentedParameter('session_id', 'path', 'session_id')],
			tags: ['Sessions']
		}),
		documentedOperation('get', '/api/sessions/{session_id}/messages', 'Get session messages', {
			parameters: [
				documentedParameter('session_id', 'path', 'session_id'),
				documentedParameter('limit', 'query', '50', false),
				documentedParameter('offset', 'query', '0', false),
				documentedParameter('order', 'query', 'oldest', false),
				documentedParameter('include_compacted', 'query', 'false', false)
			],
			tags: ['Sessions']
		}),
		documentedOperation('post', '/api/sessions/{session_id}/fork', 'Fork session', {
			bodyExample: { title: 'Branch' },
			parameters: [documentedParameter('session_id', 'path', 'session_id')],
			tags: ['Sessions']
		}),
		documentedOperation('post', '/api/sessions/{session_id}/chat', 'Run session chat', {
			bodyExample: { input: 'Hello from Hermes.' },
			parameters: [documentedParameter('session_id', 'path', 'session_id')],
			tags: ['Sessions']
		}),
		documentedOperation('post', '/api/sessions/{session_id}/chat/stream', 'Stream session chat', {
			bodyExample: { input: 'Hello from Hermes.' },
			parameters: [documentedParameter('session_id', 'path', 'session_id')],
			tags: ['Sessions']
		})
	];

	let apiKey = $state('');
	let document = $state<OpenApiDocument | null>(null);
	let operations = $state<ApiOperation[]>([]);
	let selectedOperationId = $state('');
	let parameterValues = $state<Record<string, string>>({});
	let requestBody = $state('');
	let responseBody = $state('');
	let responseStatus = $state<number | null>(null);
	let isLoading = $state(false);
	let isSending = $state(false);
	let error = $state('');
	let search = $state('');
	let contractSource = $state('');

	let selectedOperation = $derived(
		operations.find((operation) => operation.id === selectedOperationId) ?? null
	);
	let visibleOperations = $derived(
		operations.filter((operation) => {
			const haystack = [operation.method, operation.path, operation.summary, ...operation.tags]
				.join(' ')
				.toLowerCase();

			return haystack.includes(search.trim().toLowerCase());
		})
	);

	function operationLabel(operation: ApiOperation): string {
		return `${operation.method.toUpperCase()} ${operation.path}`;
	}

	function endpoint(path: string): string {
		return `/__hermes_api${path.startsWith('/') ? path : `/${path}`}`;
	}

	function apiHeaders(): Headers {
		if (!apiKey.trim()) throw new Error('Enter the Hermes Gateway API key first.');

		return new Headers({
			Accept: 'application/json',
			Authorization: `Bearer ${apiKey.trim()}`
		});
	}

	function resolveSchema(schema: OpenApiSchema | undefined): OpenApiSchema | undefined {
		if (!schema?.$ref || !document?.components?.schemas) return schema;

		const name = schema.$ref.split('/').at(-1);

		return name ? (document.components.schemas[name] ?? schema) : schema;
	}

	function resolveParameter(parameter: OpenApiParameter): OpenApiParameter {
		const unknownParameter = parameter as OpenApiParameter & { $ref?: string };

		if (!unknownParameter.$ref || !document?.components?.parameters) return parameter;

		const name = unknownParameter.$ref.split('/').at(-1);

		return name ? (document.components.parameters[name] ?? parameter) : parameter;
	}

	function sampleForSchema(schema: OpenApiSchema | undefined, depth = 0): unknown {
		const resolved = resolveSchema(schema);

		if (!resolved || depth > 4) return '';

		if (resolved.example !== undefined) return resolved.example;

		if (resolved.default !== undefined) return resolved.default;

		if (resolved.enum?.length) return resolved.enum[0];

		if (resolved.oneOf?.length) return sampleForSchema(resolved.oneOf[0], depth + 1);

		if (resolved.type === 'array') return [sampleForSchema(resolved.items, depth + 1)];

		if (resolved.type === 'object' || resolved.properties) {
			return Object.fromEntries(
				Object.entries(resolved.properties ?? {}).map(([name, property]) => [
					name,
					sampleForSchema(property, depth + 1)
				])
			);
		}

		if (resolved.type === 'boolean') return false;

		if (resolved.type === 'integer' || resolved.type === 'number') return 0;

		return '';
	}

	function operationsFromDocument(openApiDocument: OpenApiDocument): ApiOperation[] {
		return Object.entries(openApiDocument.paths ?? {}).flatMap(([path, pathItem]) => {
			const pathParameters = (pathItem.parameters ?? []).map(resolveParameter);

			return Object.entries(pathItem).flatMap(([candidateMethod, operation]) => {
				const method = candidateMethod.toLowerCase();

				if (!methods.has(method) || !operation || Array.isArray(operation)) return [];

				const typedOperation = operation as OpenApiOperation;
				const bodyContent =
					Object.entries(typedOperation.requestBody?.content ?? {}).find(([type]) =>
						type.includes('json')
					) ?? Object.entries(typedOperation.requestBody?.content ?? {})[0];
				const parameters = [
					...pathParameters,
					...(typedOperation.parameters ?? []).map(resolveParameter)
				];

				return [
					{
						bodyContentType: bodyContent?.[0],
						bodySchema: bodyContent?.[1].schema,
						description: typedOperation.description,
						id: `${method}:${path}:${typedOperation.operationId ?? ''}`,
						method,
						parameters,
						path,
						summary:
							typedOperation.summary ||
							typedOperation.operationId ||
							`${method.toUpperCase()} ${path}`,
						tags: typedOperation.tags ?? ['Other']
					}
				];
			});
		});
	}

	function operationsFromCapabilities(payload: unknown): ApiOperation[] {
		if (!payload || typeof payload !== 'object') return [];

		const endpoints = (payload as { endpoints?: unknown }).endpoints;

		if (!endpoints || typeof endpoints !== 'object') return [];

		return Object.entries(endpoints).flatMap(([name, endpoint]) => {
			if (!endpoint || typeof endpoint !== 'object') return [];

			const { method, path } = endpoint as { method?: unknown; path?: unknown };

			if (typeof method !== 'string' || typeof path !== 'string') return [];

			const normalizedMethod = method.toLowerCase();

			if (!methods.has(normalizedMethod)) return [];

			const parameters = [...path.matchAll(/\{([^}]+)\}/g)].map((match) =>
				documentedParameter(match[1], 'path', match[1])
			);

			return [
				{
					id: `capability:${normalizedMethod}:${path}`,
					method: normalizedMethod,
					parameters,
					path,
					summary: name.replaceAll('_', ' '),
					tags: ['Connected Gateway']
				}
			];
		});
	}

	function mergeOperations(...operationLists: ApiOperation[][]): ApiOperation[] {
		const seen: Record<string, true> = {};

		return operationLists.flat().filter((operation) => {
			const key = `${operation.method}:${operation.path}`;

			if (seen[key]) return false;

			seen[key] = true;

			return true;
		});
	}

	function selectOperation(operation: ApiOperation): void {
		selectedOperationId = operation.id;
		responseBody = '';
		responseStatus = null;
		error = '';
		parameterValues = Object.fromEntries(
			operation.parameters
				.filter((parameter) => parameter.name)
				.map((parameter) => [
					`${parameter.in ?? 'query'}:${parameter.name}`,
					String(parameter.example ?? sampleForSchema(parameter.schema) ?? '')
				])
		);

		if (operation.bodyExample !== undefined) {
			requestBody = JSON.stringify(operation.bodyExample, null, 2);
		} else if (operation.bodySchema) {
			requestBody = JSON.stringify(sampleForSchema(operation.bodySchema), null, 2);
		} else {
			requestBody = '';
		}
	}

	async function loadSpecification(): Promise<void> {
		isLoading = true;
		error = '';
		try {
			const response = await fetch(endpoint('/openapi.json'), { headers: apiHeaders() });

			if (response.ok) {
				document = (await response.json()) as OpenApiDocument;
				operations = operationsFromDocument(document);
				contractSource = 'Loaded from the connected Gateway OpenAPI contract.';
			} else if (response.status === 404) {
				const capabilitiesResponse = await fetch(endpoint('/v1/capabilities'), {
					headers: apiHeaders()
				});

				if (!capabilitiesResponse.ok) {
					throw new Error(
						`Could not load Gateway capabilities (${capabilitiesResponse.status}) after OpenAPI was unavailable.`
					);
				}

				const capabilities = await capabilitiesResponse.json();

				document = { info: { title: 'Hermes API Server', version: 'built-in contract' } };
				operations = mergeOperations(
					officialHermesOperations,
					operationsFromCapabilities(capabilities)
				);
				contractSource =
					'OpenAPI is not exposed by this Gateway; using the official Hermes contract plus its live capabilities.';
			} else {
				throw new Error(`Could not load OpenAPI specification (${response.status}).`);
			}

			if (!operations.length)
				throw new Error('The server OpenAPI specification did not declare any operations.');

			selectOperation(operations[0]);
			localStorage.setItem(apiKeyStorageKey, apiKey.trim());
		} catch (cause) {
			document = null;
			operations = [];
			contractSource = '';
			error = cause instanceof Error ? cause.message : 'Could not load the OpenAPI specification.';
		} finally {
			isLoading = false;
		}
	}

	function buildRequestPath(operation: ApiOperation): string {
		let path = operation.path;

		const query: string[] = [];

		for (const parameter of operation.parameters) {
			if (!parameter.name) continue;

			const value = parameterValues[`${parameter.in ?? 'query'}:${parameter.name}`]?.trim();

			if (!value && parameter.required) {
				throw new Error(
					`Enter a value for required ${parameter.in ?? 'query'} parameter “${parameter.name}”.`
				);
			}

			if (!value) continue;

			if (parameter.in === 'path') {
				path = path.replace(`{${parameter.name}}`, encodeURIComponent(value));
			} else if (parameter.in === 'query') {
				query.push(`${encodeURIComponent(parameter.name)}=${encodeURIComponent(value)}`);
			}
		}

		return query.length ? `${path}?${query.join('&')}` : path;
	}

	async function readResponse(response: Response): Promise<string> {
		const contentType = response.headers.get('content-type') ?? '';

		if (!contentType.includes('text/event-stream') || !response.body) {
			const text = await response.text();

			if (!text) return '';

			try {
				return JSON.stringify(JSON.parse(text), null, 2);
			} catch {
				return text;
			}
		}

		const reader = response.body.getReader();
		const decoder = new TextDecoder();

		let output = '';

		while (true) {
			const { done, value } = await reader.read();

			if (done) return output;

			output += decoder.decode(value, { stream: true });
			responseBody = output;
		}
	}

	async function sendRequest(): Promise<void> {
		if (!selectedOperation) return;

		if (selectedOperation.transport === 'websocket') {
			error =
				'This operation is a WebSocket controller endpoint. Register a controller first, then connect with its one-time ticket in Sec-WebSocket-Protocol.';

			return;
		}

		isSending = true;
		error = '';
		responseBody = '';
		responseStatus = null;
		try {
			const requestHeaders = apiHeaders();
			const cookies: string[] = [];

			for (const parameter of selectedOperation.parameters) {
				if (!parameter.name) continue;

				const value = parameterValues[`${parameter.in ?? 'query'}:${parameter.name}`]?.trim();

				if (parameter.in === 'header' && value) requestHeaders.set(parameter.name, value);

				if (parameter.in === 'cookie' && value) {
					cookies.push(`${encodeURIComponent(parameter.name)}=${encodeURIComponent(value)}`);
				}
			}

			if (cookies.length) requestHeaders.set('Cookie', cookies.join('; '));

			const init: RequestInit = {
				headers: requestHeaders,
				method: selectedOperation.method.toUpperCase()
			};

			if (selectedOperation.bodyContentType && requestBody.trim()) {
				if (selectedOperation.bodyContentType.includes('json')) JSON.parse(requestBody);

				requestHeaders.set('Content-Type', selectedOperation.bodyContentType);
				init.body = requestBody;
			}

			const response = await fetch(endpoint(buildRequestPath(selectedOperation)), init);

			responseStatus = response.status;
			responseBody = await readResponse(response);

			if (!response.ok) error = `Hermes returned HTTP ${response.status}.`;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'The API request failed.';
		} finally {
			isSending = false;
		}
	}

	onMount(() => {
		apiKey = localStorage.getItem(apiKeyStorageKey) ?? '';
	});
</script>

<svelte:head>
	<title>Hermes API Explorer</title>

	<meta content="OpenAPI explorer for Hermes Gateway" name="description" />
</svelte:head>

<main class="min-h-screen bg-base-200 text-base-content">
	<div class="mx-auto flex min-h-screen max-w-7xl flex-col p-3 sm:p-6">
		<header
			class="mb-3 flex flex-col gap-3 rounded-box border border-base-300 bg-base-100 p-4 shadow-sm lg:flex-row lg:items-center"
		>
			<div class="mr-auto">
				<h1 class="text-xl font-semibold">Hermes API Explorer</h1>

				<p class="text-sm opacity-65">
					Official Hermes operations plus the connected Gateway’s live capabilities.
				</p>
			</div>

			<a class="btn btn-ghost" href="#/">Chat</a>

			<input
				bind:value={apiKey}
				autocomplete="current-password"
				class="input input-bordered w-full sm:w-72"
				placeholder="Hermes API key"
				type="password"
			/>

			<button
				class="btn btn-primary"
				disabled={isLoading || !apiKey.trim()}
				onclick={loadSpecification}>{isLoading ? 'Loading…' : 'Load API'}</button
			>
		</header>

		{#if error}
			<div class="alert alert-error mb-3 text-sm">
				<span>{error}</span><button class="btn btn-ghost btn-xs" onclick={() => (error = '')}
					>Dismiss</button
				>
			</div>
		{/if}

		{#if !document}
			<section class="mx-auto flex w-full max-w-2xl flex-1 items-center">
				<div class="w-full rounded-box border border-base-300 bg-base-100 p-8 shadow-sm">
					<h2 class="text-lg font-semibold">Load the Gateway contract</h2>

					<p class="mt-2 leading-6 opacity-75">
						Enter the same API-server key used for chat. The explorer loads <code
							>/openapi.json</code
						>
						when the Gateway provides it; otherwise it uses the official Hermes API contract and merges
						in this Gateway’s <code>/v1/capabilities</code> routes.
					</p>
				</div>
			</section>
		{:else}
			<section class="grid flex-1 gap-3 lg:grid-cols-[20rem_minmax(0,1fr)]">
				<aside
					class="flex min-h-0 flex-col rounded-box border border-base-300 bg-base-100 p-3 shadow-sm"
				>
					<p class="mb-2 text-xs opacity-60">
						{document.info?.title || 'OpenAPI'}
						{document.info?.version ? `· ${document.info.version}` : ''} · {operations.length} operations
					</p>

					<p class="mb-2 text-xs opacity-60">{contractSource}</p>

					<input
						bind:value={search}
						class="input input-bordered input-sm mb-2"
						placeholder="Filter endpoints"
					/>

					<div class="min-h-0 space-y-1 overflow-y-auto">
						{#each visibleOperations as operation (operation.id)}
							<button
								class:btn-active={operation.id === selectedOperationId}
								class="btn btn-ghost h-auto w-full justify-start px-2 py-2 text-left normal-case"
								onclick={() => selectOperation(operation)}
							>
								<span class="min-w-0"
									><span class="mr-2 font-mono text-xs opacity-65"
										>{operation.method.toUpperCase()}</span
									><span class="text-sm">{operation.summary}</span><span
										class="block truncate font-mono text-xs opacity-55">{operation.path}</span
									></span
								>
							</button>
						{/each}
					</div>
				</aside>

				{#if selectedOperation}
					<section
						class="flex min-w-0 flex-col rounded-box border border-base-300 bg-base-100 shadow-sm"
					>
						<div class="border-b border-base-300 p-4">
							<p class="font-mono text-sm opacity-65">{operationLabel(selectedOperation)}</p>

							<h2 class="text-lg font-semibold">{selectedOperation.summary}</h2>

							{#if selectedOperation.description}<p class="mt-1 text-sm opacity-70">
									{selectedOperation.description}
								</p>{/if}
						</div>

						<div class="grid gap-4 p-4 xl:grid-cols-2">
							<div class="space-y-3">
								<h3 class="font-medium">Parameters</h3>

								{#if selectedOperation.parameters.length === 0}<p class="text-sm opacity-60">
										No path, query, or extra header parameters.
									</p>{/if}

								{#each selectedOperation.parameters as parameter (`${parameter.in}:${parameter.name}`)}
									<label class="form-control w-full"
										><span class="label-text text-xs"
											>{parameter.in || 'query'} · {parameter.name}{parameter.required
												? ' *'
												: ''}</span
										><input
											bind:value={parameterValues[`${parameter.in ?? 'query'}:${parameter.name}`]}
											class="input input-bordered input-sm"
											placeholder={parameter.description || parameter.schema?.description || ''}
										/></label
									>
								{/each}
							</div>

							<div class="space-y-3">
								<h3 class="font-medium">Request body</h3>

								{#if selectedOperation.bodyContentType}
									<p class="text-xs opacity-60">{selectedOperation.bodyContentType}</p>

									<textarea
										bind:value={requestBody}
										class="textarea textarea-bordered min-h-64 w-full font-mono text-xs"
										spellcheck="false"
									></textarea>
								{:else}
									<p class="text-sm opacity-60">This operation does not declare a request body.</p>
								{/if}
							</div>
						</div>

						<div class="flex items-center gap-3 border-t border-base-300 p-4">
							<button
								class="btn btn-primary"
								disabled={isSending || selectedOperation.transport === 'websocket'}
								onclick={sendRequest}
								>{selectedOperation.transport === 'websocket'
									? 'WebSocket endpoint'
									: isSending
										? 'Sending…'
										: `Send ${selectedOperation.method.toUpperCase()}`}</button
							>

							{#if responseStatus}<span
									class:badge-error={responseStatus >= 400}
									class:badge-success={responseStatus < 400}
									class="badge">HTTP {responseStatus}</span
								>{/if}
						</div>

						{#if responseStatus !== null || responseBody}
							<div class="border-t border-base-300 p-4">
								<h3 class="mb-2 font-medium">Response</h3>

								<pre
									class="max-h-96 overflow-auto rounded-box bg-neutral p-3 text-xs text-neutral-content">{responseBody ||
										'(empty response)'}</pre>
							</div>
						{/if}
					</section>
				{/if}
			</section>
		{/if}
	</div>
</main>
