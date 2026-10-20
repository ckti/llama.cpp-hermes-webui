import TestWrapper from './components/TestWrapper.svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';

describe('/+page.svelte', () => {
	const createdSessionBodies: Record<string, unknown>[] = [];
	const chatRequestBodies: Record<string, unknown>[] = [];

	beforeEach(() => {
		createdSessionBodies.length = 0;
		chatRequestBodies.length = 0;
		localStorage.clear();

		vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
			const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;

			if (url === '/v1/capabilities') {
				return Response.json({ features: { session_chat_streaming: true } });
			}

			if (url === '/api/model/options?include_unconfigured=false') {
				return Response.json({ providers: [] });
			}

			if (url === '/api/sessions?limit=100') {
				return Response.json({ data: [] });
			}

			if (url === '/api/sessions/session-1/messages?order=oldest') {
				return Response.json({ data: [] });
			}

			if (url === '/api/sessions' && init?.method === 'POST') {
				const body = JSON.parse(String(init.body)) as Record<string, unknown>;

				createdSessionBodies.push(body);

				return Response.json({ session: { id: `session-${createdSessionBodies.length}` } });
			}

			if (url === '/api/sessions/session-1/chat/stream' && init?.method === 'POST') {
				chatRequestBodies.push(JSON.parse(String(init.body)) as Record<string, unknown>);

				return new Response(
					new ReadableStream<Uint8Array>({
						start(controller) {
							controller.close();
						}
					})
				);
			}

			throw new Error(`Unexpected request: ${init?.method ?? 'GET'} ${url}`);
		});
	});

	it('should render page without throwing', async () => {
		// Basic smoke test - page should render without throwing errors.
		// API calls are mocked in vitest-setup-client.ts.
		await render(TestWrapper);
		expect(true).toBe(true);
	});

	it('creates multiple untitled sessions so Hermes can generate their summaries', async () => {
		const screen = await render(TestWrapper);

		await screen.getByPlaceholder('Hermes API key').fill('test-api-key');
		await screen.getByRole('button', { name: 'Connect' }).click();
		await expect.element(screen.getByRole('button', { name: 'New chat' })).toBeVisible();

		await screen.getByRole('button', { name: 'New chat' }).click();
		await expect.poll(() => createdSessionBodies.length).toBe(1);
		await screen.getByRole('button', { name: 'New chat' }).click();
		await expect.poll(() => createdSessionBodies.length).toBe(2);

		expect(createdSessionBodies).toEqual([
			{ source: 'hermes_gateway_ui' },
			{ source: 'hermes_gateway_ui' }
		]);
	});

	it('sends an attached image as a Gateway image content part', async () => {
		const screen = await render(TestWrapper);

		await screen.getByPlaceholder('Hermes API key').fill('test-api-key');
		await screen.getByRole('button', { name: 'Connect' }).click();
		await expect.element(screen.getByText('Attach', { exact: true })).toBeVisible();

		const input = screen.container.querySelector('input[type="file"]');

		if (!(input instanceof HTMLInputElement)) throw new Error('Attachment input was not rendered.');

		const files = new DataTransfer();

		files.items.add(new File(['image data'], 'reference.png', { type: 'image/png' }));
		Object.defineProperty(input, 'files', { configurable: true, value: files.files });
		input.dispatchEvent(new Event('change', { bubbles: true }));

		await expect.element(screen.getByText('reference.png')).toBeVisible();
		await screen.getByRole('button', { name: 'Send' }).click();
		await expect.poll(() => chatRequestBodies.length).toBe(1);

		expect(chatRequestBodies[0]).toMatchObject({
			input: [
				{
					image_url: { url: expect.stringMatching(/^data:image\/png;base64,/) },
					type: 'image_url'
				}
			]
		});
	});
});
