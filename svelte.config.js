import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import { mdsvex } from 'mdsvex';

// HERMES_UI_OUT_DIR lets an embedding build choose a staging directory; a
// normal `npm run build` writes to ./dist.
const outDir = process.env.HERMES_UI_OUT_DIR ?? './dist';
/** @type {import('@sveltejs/kit').Config} */
const config = {
	extensions: ['.svelte', '.svx'],

	kit: {
		adapter: adapter({
			assets: outDir,
			fallback: 'index.html',
			pages: outDir,
			precompress: false,
			strict: true
		}),
		output: {
			bundleStrategy: 'single'
		},
		paths: {
			relative: true
		},
		router: { type: 'hash' }
	},

	// Consult https://svelte.dev/docs/kit/integrations
	// for more information about preprocessors
	preprocess: [vitePreprocess(), mdsvex()]
};

export default config;
