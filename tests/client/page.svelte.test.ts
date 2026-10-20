import TestWrapper from './components/TestWrapper.svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';

describe('/+page.svelte', () => {
	const createdSessionBodies: Record<string, unknown>[] = [];

	beforeEach(() => {
		createdSessionBodies.length = 0;
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

			if (url === '/api/sessions' && init?.method === 'POST') {
				const body = JSON.parse(String(init.body)) as Record<string, unknown>;

				createdSessionBodies.push(body);

				return Response.json({ session: { id: `session-${createdSessionBodies.length}` } });
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
});
