import { expect, test } from '@playwright/test';

// Exercise the built page without creating real Gateway sessions or model requests.
test.beforeEach(async ({ page }) => {
	await page.route('**/v1/capabilities', (route) =>
		route.fulfill({ json: { features: { session_chat_streaming: true } } })
	);
	await page.route('**/api/**', (route) => {
		const request = route.request();
		const path = new URL(request.url()).pathname;

		if (path === '/api/model/options') return route.fulfill({ json: { providers: [] } });

		if (path === '/api/sessions' && request.method() === 'POST') {
			return route.fulfill({ json: { session: { id: 'attachment-test' } }, status: 201 });
		}

		if (path.endsWith('/chat/stream')) {
			return route.fulfill({ body: '', contentType: 'text/event-stream' });
		}

		return route.fulfill({ json: { data: [] } });
	});
	await page.goto('/');
	await page.getByPlaceholder('Hermes API key').fill('attachment-browser-test');
	await page.getByRole('button', { exact: true, name: 'Connect' }).click();
});

for (const width of [1280, 390]) {
	test(`opens the attachment panel and sends chosen files at ${width}px`, async ({ page }) => {
		await page.setViewportSize({ height: 900, width });
		const errors: string[] = [];

		page.on('pageerror', (error) => errors.push(error.message));

		const attach = page.getByRole('button', { exact: true, name: 'Attach files' });
		const panel = page.getByRole('region', { name: 'Add attachments' });

		await expect(panel).toBeHidden();
		await attach.click();
		await expect(attach).toHaveAttribute('aria-expanded', 'true');
		await expect(panel).toBeVisible();
		await expect(attach).toHaveCSS('border-top-width', '1px');

		const chooserPromise = page.waitForEvent('filechooser');

		await page.getByLabel('Choose files or drop them here').click();
		const chooser = await chooserPromise;

		expect(chooser.isMultiple()).toBe(true);
		await chooser.setFiles([
			{ buffer: Buffer.from('Review this attachment.'), mimeType: 'text/plain', name: 'notes.txt' },
			{
				buffer: Buffer.from(
					'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7S8AAAAASUVORK5CYII=',
					'base64'
				),
				mimeType: 'image/png',
				name: 'reference.png'
			}
		]);
		await expect(page.getByRole('button', { name: 'Remove notes.txt' })).toBeVisible();
		await expect(page.getByRole('img', { name: 'Preview of reference.png' })).toBeVisible();

		const sent = page.waitForRequest((request) => request.url().endsWith('/chat/stream'));

		await page.getByRole('button', { exact: true, name: 'Send' }).click();
		expect((await sent).postDataJSON()).toEqual({
			input: [
				{ text: 'Attached file: notes.txt\n\nReview this attachment.', type: 'text' },
				{ image_url: { url: expect.stringMatching(/^data:image\/png;base64,/) }, type: 'image_url' }
			]
		});
		await expect(page.getByRole('button', { name: 'Remove notes.txt' })).toHaveCount(0);
		expect(errors).toEqual([]);
	});
}

test('accepts dropped files and allows removing and reselecting them', async ({ page }) => {
	const attach = page.getByRole('button', { name: 'Attach files' });

	await attach.focus();
	await page.keyboard.press('Enter');

	const panel = page.getByRole('region', { name: 'Add attachments' });

	await expect(panel).toBeVisible();
	const files = await page.evaluateHandle(() => {
		const transfer = new DataTransfer();

		transfer.items.add(
			new File(['Dropped file contents'], 'dropped.md', { type: 'text/markdown' })
		);

		return transfer;
	});

	try {
		await panel.dispatchEvent('drop', { dataTransfer: files });
	} finally {
		await files.dispose();
	}
	await page.getByRole('button', { name: 'Remove dropped.md' }).click();
	await expect(page.getByRole('button', { exact: true, name: 'Send' })).toBeDisabled();

	const chooserPromise = page.waitForEvent('filechooser');

	await page.getByLabel('Choose files or drop them here').click();
	await (
		await chooserPromise
	).setFiles({
		buffer: Buffer.from('Dropped file contents'),
		mimeType: 'text/markdown',
		name: 'dropped.md'
	});
	await expect(page.getByRole('button', { name: 'Remove dropped.md' })).toBeVisible();

	await attach.click();
	await expect(panel).toBeHidden();
	await expect(page.getByRole('button', { name: 'Remove dropped.md' })).toBeVisible();
});
