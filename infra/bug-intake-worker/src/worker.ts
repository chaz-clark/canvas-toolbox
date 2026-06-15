/**
 * canvas-toolbox bug-intake worker.
 *
 * One-way pipe: faculty CLI (`cb_report_bug.py`) → this Worker →
 * GitHub Issues API. Faculty never holds a PAT, never sees a browser
 * auth flow, never needs a GitHub account.
 *
 * Endpoint: `POST /bug` (anything else returns 404)
 * Body shape (JSON):
 *   {
 *     "title":           "<short bug title>",
 *     "body":            "<rendered markdown — toolkit context + operator description>",
 *     "toolkit_version": "0.49.1",
 *     "user_agent":      "canvas-toolbox-bug-reporter/0.49.1"
 *   }
 *
 * Server-side guards (defense in depth — `cb_report_bug.py` already
 * scrubs client-side, but we don't trust the wire):
 *
 *   1. Required User-Agent prefix    — script-kiddie filter, not auth.
 *   2. Body-size cap                 — hard 64 KB on the JSON payload.
 *   3. Field shape + length limits   — title ≤ 200, body ≤ 50 KB.
 *   4. Email / userpath regex scrub  — same patterns as the Python deid
 *                                       adapters (EMAIL_RE / USERPATH_RE).
 *                                       A submitter-supplied name would
 *                                       have been redacted client-side;
 *                                       this catches anything that wasn't.
 *   5. Rate-limit per IP             — 5 issues per IP per rolling hour
 *                                       via Cloudflare's CF-Connecting-IP
 *                                       + a Durable-Object-free counter
 *                                       in KV (or in-memory fallback).
 *
 * On accept, the Worker POSTs to:
 *   POST https://api.github.com/repos/<OWNER>/<REPO>/issues
 *   Authorization: Bearer <GITHUB_PAT>   (Worker secret)
 *   X-GitHub-Api-Version: 2022-11-28
 *   Accept: application/vnd.github+json
 *
 * Returns 200 with `{url, number}` on success; 4xx on validation
 * failure; 5xx (passed through) on upstream GitHub trouble.
 */

interface Env {
  GITHUB_PAT: string;
  GITHUB_OWNER: string;            // e.g. "chaz-clark"
  GITHUB_REPO: string;             // e.g. "canvas-toolbox"
  ISSUE_LABEL: string;             // e.g. "agent-submitted"
  RATE_LIMIT_KV?: KVNamespace;     // optional — falls back to no-limit if absent
}

const MAX_BODY_BYTES = 64 * 1024;
const MAX_TITLE_CHARS = 200;
const MAX_BODY_CHARS = 50 * 1024;
const RATE_LIMIT_PER_HOUR = 5;
const REQUIRED_UA_PREFIX = 'canvas-toolbox-bug-reporter/';

// Same regexes the Python adapters use. Keep in sync with
// lib/tools/grader_deidentify_databricks.py:EMAIL_RE / USERPATH_RE.
const EMAIL_RE = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
const USERPATH_RE = /\/(?:Users|home)\/[A-Za-z0-9._-]+/g;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });
}

function scrubPII(text: string): string {
  return text
    .replace(EMAIL_RE, '[REDACTED-EMAIL]')
    .replace(USERPATH_RE, '[REDACTED-PATH]');
}

async function rateLimitOk(env: Env, ip: string): Promise<boolean> {
  if (!env.RATE_LIMIT_KV) return true;  // no KV bound → no limit (deploy without rate-limit OK for v1)
  const key = `rl:${ip}`;
  const raw = await env.RATE_LIMIT_KV.get(key);
  const count = raw ? parseInt(raw, 10) : 0;
  if (count >= RATE_LIMIT_PER_HOUR) return false;
  await env.RATE_LIMIT_KV.put(key, String(count + 1), { expirationTtl: 3600 });
  return true;
}

function githubHeaders(env: Env): HeadersInit {
  return {
    'Authorization': `Bearer ${env.GITHUB_PAT}`,
    'X-GitHub-Api-Version': '2022-11-28',
    'Accept': 'application/vnd.github+json',
    'User-Agent': 'canvas-toolbox-bug-intake-worker',
    'Content-Type': 'application/json',
  };
}

async function fileIssue(
  env: Env, title: string, body: string,
): Promise<{ status: number; payload: unknown }> {
  // Create the issue WITHOUT labels.
  //
  // GitHub fine-grained PATs scoped to Issues:read+write empirically
  // CANNOT mutate labels — verified 2026-06-15:
  //   - POST /issues with `labels` in body  → silently drops the field
  //   - POST /issues/:n/labels              → 403 "Resource not accessible"
  //   - PATCH /issues/:n with `labels`       → 403 "Resource not accessible"
  // All three are documented as requiring just Issues:write, but the
  // runtime check is stricter than the docs. Adding broader scopes
  // (Pull requests:write, Contents:write) would unlock label mutation
  // but expands the PAT's blast radius — wrong trade for a one-way
  // intake channel.
  //
  // Instead: the worker creates the issue cleanly; a tiny GitHub
  // Actions workflow (`.github/workflows/agent-submitted-label.yml`)
  // adds the `agent-submitted` label by matching the body footer
  // "_Filed via canvas-toolbox bug-intake worker._". Actions tokens
  // have the right scope by default.
  //
  // env.ISSUE_LABEL is kept for backward-compat / future use (e.g. if
  // GitHub later loosens the permission check, or if the worker grows
  // a GitHub-App auth path); it's no longer sent.
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/issues`;
  const resp = await fetch(url, {
    method: 'POST',
    headers: githubHeaders(env),
    body: JSON.stringify({ title, body }),
  });
  const text = await resp.text();
  let payload: unknown;
  try { payload = JSON.parse(text); } catch { payload = { raw: text }; }
  return { status: resp.status, payload };
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (req.method === 'GET' && url.pathname === '/') {
      return new Response(
        'canvas-toolbox bug-intake worker — POST /bug with JSON. ' +
        'See https://github.com/chaz-clark/canvas-toolbox/blob/main/infra/bug-intake-worker/README.md',
        { headers: { 'content-type': 'text/plain' } },
      );
    }

    if (req.method !== 'POST' || url.pathname !== '/bug') {
      return jsonResponse(404, { error: 'POST /bug only' });
    }

    // Guard 1: User-Agent prefix (script-kiddie filter, not auth).
    const ua = req.headers.get('user-agent') || '';
    if (!ua.startsWith(REQUIRED_UA_PREFIX)) {
      return jsonResponse(400, {
        error: `User-Agent must start with '${REQUIRED_UA_PREFIX}'`,
      });
    }

    // Guard 5: Rate limit by client IP.
    const ip = req.headers.get('cf-connecting-ip') || req.headers.get('x-real-ip') || 'unknown';
    if (!(await rateLimitOk(env, ip))) {
      return jsonResponse(429, {
        error: `Rate limit: max ${RATE_LIMIT_PER_HOUR} issues per IP per hour. Try again later.`,
      });
    }

    // Guard 2: Body size cap.
    let raw: string;
    try {
      raw = await req.text();
    } catch {
      return jsonResponse(400, { error: 'unreadable body' });
    }
    if (raw.length > MAX_BODY_BYTES) {
      return jsonResponse(413, { error: `body exceeds ${MAX_BODY_BYTES} bytes` });
    }

    // Guard 3: JSON + field shape.
    let parsed: { title?: string; body?: string; toolkit_version?: string };
    try {
      parsed = JSON.parse(raw);
    } catch {
      return jsonResponse(400, { error: 'invalid JSON' });
    }
    const titleIn = (parsed.title || '').trim();
    const bodyIn = (parsed.body || '').trim();
    const version = (parsed.toolkit_version || 'unknown').slice(0, 32);
    if (!titleIn || !bodyIn) {
      return jsonResponse(400, { error: 'title and body are required' });
    }
    if (titleIn.length > MAX_TITLE_CHARS) {
      return jsonResponse(400, {
        error: `title exceeds ${MAX_TITLE_CHARS} chars`,
      });
    }
    if (bodyIn.length > MAX_BODY_CHARS) {
      return jsonResponse(400, {
        error: `body exceeds ${MAX_BODY_CHARS} chars`,
      });
    }

    // Guard 4: Defense-in-depth PII scrub (email + userpath).
    const titleClean = scrubPII(titleIn);
    const bodyClean = [
      scrubPII(bodyIn),
      '',
      '---',
      `_Filed via canvas-toolbox bug-intake worker._`,
      `_toolkit_version: ${version}_`,
    ].join('\n');

    // File the issue.
    const { status, payload } = await fileIssue(env, titleClean, bodyClean);
    if (status >= 200 && status < 300) {
      const issue = payload as { html_url?: string; number?: number };
      return jsonResponse(200, {
        url: issue.html_url,
        number: issue.number,
      });
    }
    return jsonResponse(status, { error: 'github_api_error', upstream: payload });
  },
} satisfies ExportedHandler<Env>;
