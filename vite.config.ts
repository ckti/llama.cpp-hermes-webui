import { buildInfoPlugin } from './scripts/vite-plugin-build-info';
import { nerdamerPlugin } from './scripts/vite-plugin-nerdamer';
import { relativizeBasePlugin } from './scripts/vite-plugin-relativize-base';
import { splashScreenPlugin } from './scripts/vite-plugin-splash-screen';
import { SVELTEKIT_PWA_OPTIONS } from './src/lib/constants/pwa.constants';
import { storybookTest } from '@storybook/addon-vitest/vitest-plugin';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { SvelteKitPWA } from '@vite-pwa/sveltekit';
import { playwright } from '@vitest/browser-playwright';
import type { ServerResponse } from 'node:http';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import type { Plugin } from 'vite';
import { defineConfig, loadEnv, searchForWorkspaceRoot } from 'vite';

const __dirname = dirname(fileURLToPath(import.meta.url));
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const browserBaseConfig: any = {
	enabled: true,
	instances: [{ browser: 'chromium' }],
	provider: playwright({
		launchOptions: {
			args: ['--no-sandbox']
		}
	})
};

function hermesGatewayProps() {
	return {
		bos_token: '',
		build_info: 'Hermes Gateway compatibility bridge',
		chat_template: '',
		default_generation_settings: {
			id: 0,
			id_task: 0,
			is_processing: false,
			n_ctx: 128000,
			next_token: {
				has_new_line: false,
				has_next_token: false,
				n_decoded: 0,
				n_remain: 0,
				stopping_word: ''
			},
			params: {
				backend_sampling: false,
				chat_format: '',
				dry_allowed_length: 2,
				dry_base: 1.75,
				dry_multiplier: 0,
				dry_penalty_last_n: -1,
				dry_sequence_breakers: [],
				dynatemp_exponent: 1,
				dynatemp_range: 0,
				frequency_penalty: 0,
				generation_prompt: '',
				grammar: '',
				grammar_lazy: false,
				grammar_triggers: [],
				ignore_eos: false,
				logit_bias: [],
				lora: [],
				max_tokens: -1,
				min_keep: 0,
				min_p: 0,
				mirostat: 0,
				mirostat_eta: 0.1,
				mirostat_tau: 5,
				n_discard: 0,
				n_keep: 0,
				n_predict: -1,
				n_probs: 0,
				post_sampling_probs: false,
				presence_penalty: 0,
				preserved_tokens: [],
				reasoning_format: 'auto',
				reasoning_in_content: false,
				repeat_last_n: 64,
				repeat_penalty: 1,
				samplers: [],
				seed: -1,
				'speculative.n_max': 16,
				'speculative.n_min': 0,
				'speculative.p_min': 0.75,
				stop: [],
				stream: true,
				temperature: 0.8,
				timings_per_token: false,
				top_k: 40,
				top_n_sigma: -1,
				top_p: 0.95,
				typ_p: 1,
				xtc_probability: 0,
				xtc_threshold: 0.1
			},
			prompt: '',
			speculative: false
		},
		eos_token: '',
		modalities: { audio: false, video: false, vision: true },
		model_path: 'Hermes Gateway',
		role: 'model',
		total_slots: 1
	};
}

function hermesGatewayCompatPlugin(): Plugin {
	const json = (res: ServerResponse, body: unknown, statusCode = 200) => {
		res.setHeader('Cache-Control', 'no-store');
		res.setHeader('Content-Type', 'application/json; charset=utf-8');
		res.statusCode = statusCode;
		res.end(JSON.stringify(body));
	};

	return {
		configureServer(server) {
			server.middlewares.use((req, res, next) => {
				const pathname = new URL(req.url ?? '/', 'http://localhost').pathname;

				if (req.method === 'GET' && pathname === '/props') {
					json(res, hermesGatewayProps());

					return;
				}

				if (req.method === 'GET' && pathname === '/slots') {
					json(res, []);

					return;
				}

				if (pathname === '/tools') {
					req.resume();
					json(
						res,
						{ error: { message: 'Tools are provided by Hermes Gateway, not this UI bridge.' } },
						403
					);

					return;
				}

				if (req.method === 'POST' && pathname === '/v1/streams/lookup') {
					req.resume();
					json(res, []);

					return;
				}

				if (pathname === '/models/load' || pathname === '/models/unload') {
					req.resume();
					json(
						res,
						{ error: { message: 'Model loading is not provided by Hermes Gateway UI.' } },
						405
					);

					return;
				}

				next();
			});
		},
		name: 'hermes-gateway-compat'
	};
}

export default defineConfig(({ mode }) => {
	const env = loadEnv(mode, process.cwd(), 'VITE_PUBLIC_');
	const SERVER_ORIGIN = env.VITE_PUBLIC_HERMES_GATEWAY_ORIGIN || 'http://127.0.0.1:8642';

	return {
		build: {
			assetsInlineLimit: 32000,
			chunkSizeWarningLimit: 3072,
			minify: true
		},

		plugins: [
			hermesGatewayCompatPlugin(),
			tailwindcss(),
			sveltekit(),
			SvelteKitPWA(SVELTEKIT_PWA_OPTIONS),
			splashScreenPlugin(),
			buildInfoPlugin(),
			nerdamerPlugin(),
			relativizeBasePlugin()
		],

		resolve: {
			alias: {
				'katex-fonts': resolve('node_modules/katex/dist/fonts')
			}
		},

		server: {
			fs: {
				allow: [searchForWorkspaceRoot(process.cwd()), resolve(__dirname, 'tests')]
			},
			headers: {
				'Cross-Origin-Embedder-Policy': 'require-corp',
				'Cross-Origin-Opener-Policy': 'same-origin'
			},
			proxy: {
				'/v1/chat/completions': SERVER_ORIGIN,
				'/v1/health': SERVER_ORIGIN,
				'/v1/models': SERVER_ORIGIN
			}
		},

		test: {
			projects: [
				{
					extends: './vite.config.ts',
					test: {
						browser: browserBaseConfig,
						include: ['tests/client/**/*.svelte.{test,spec}.{js,ts}'],
						name: 'client',
						setupFiles: ['./vitest-setup-client.ts']
					}
				},

				{
					extends: './vite.config.ts',
					test: {
						environment: 'node',
						include: ['tests/unit/**/*.{test,spec}.{js,ts}'],
						name: 'unit'
					}
				},

				{
					extends: './vite.config.ts',
					plugins: [
						storybookTest({
							storybookScript: 'pnpm run storybook --no-open'
						})
					],
					test: {
						browser: { ...browserBaseConfig, instances: [{ browser: 'chromium', headless: true }] },
						name: 'ui'
					}
				}
			]
		}
	};
});
