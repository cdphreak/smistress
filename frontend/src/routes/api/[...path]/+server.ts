import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';
import { proxyRequest } from '$lib/server/proxy';

const API_ORIGIN = env.API_ORIGIN ?? 'http://localhost:8000';

const handler: RequestHandler = ({ request, params }) =>
  proxyRequest(request, params.path, API_ORIGIN);

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
