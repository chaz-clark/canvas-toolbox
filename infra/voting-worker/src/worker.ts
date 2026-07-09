/**
 * canvas-toolbox voting worker
 *
 * Handles voting for roadmap features. Stores votes in D1, deduplicates by
 * (user_hash, feature_id), returns current vote counts.
 *
 * Endpoints:
 *   GET  /        - Info page
 *   GET  /votes   - Fetch all vote counts (JSON)
 *   POST /vote    - Submit a vote (JSON body)
 */

// Valid feature IDs from docs/ROADMAP.md
const VALID_FEATURES = new Set([
  // Phase 1: High-Value, Low-Complexity
  'grade-forecast',
  'engagement-early-warning',
  'bulk-reminder',
  'group-override-manager',

  // Phase 2: Medium-Value, Moderate-Complexity
  'assignment-performance-analyzer',
  'accommodation-notifier',
  'weekly-announcements',
  'ta-grading-status',

  // Phase 3: Nice-to-Have
  'module-scheduler',
  'rubric-library',
  'grade-audit-trail',
  'random-groups',
]);

interface Env {
  VOTES_DB: D1Database;
  RATE_LIMIT_KV?: KVNamespace; // Optional: rate limiting
}

interface VoteRequest {
  feature_id: string;
  user_hash: string;
  source?: string; // 'cli' | 'web' | 'agent'
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // CORS headers (future web voting)
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };

    // Handle OPTIONS (preflight)
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // Route: GET / — info page
    if (url.pathname === '/' && request.method === 'GET') {
      return new Response(
        'canvas-toolbox voting worker — POST /vote with JSON, GET /votes for counts.',
        {
          headers: { ...corsHeaders, 'Content-Type': 'text/plain' },
        }
      );
    }

    // Route: GET /votes — fetch all vote counts
    if (url.pathname === '/votes' && request.method === 'GET') {
      try {
        const results = await env.VOTES_DB.prepare(`
          SELECT feature_id, COUNT(*) as count
          FROM votes
          GROUP BY feature_id
          ORDER BY count DESC
        `).all();

        const votes: Record<string, number> = {};
        for (const row of results.results) {
          votes[row.feature_id as string] = row.count as number;
        }

        return new Response(JSON.stringify(votes), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
      } catch (err) {
        console.error('Error fetching votes:', err);
        return new Response(
          JSON.stringify({ error: 'Database query failed' }),
          {
            status: 500,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          }
        );
      }
    }

    // Route: POST /vote — submit a vote
    if (url.pathname === '/vote' && request.method === 'POST') {
      // Rate limiting (if KV is configured)
      if (env.RATE_LIMIT_KV) {
        const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';
        const rateLimitKey = `rate_limit:\${clientIP}`;

        const currentCount = await env.RATE_LIMIT_KV.get(rateLimitKey);
        const count = currentCount ? parseInt(currentCount, 10) : 0;

        if (count >= 10) {
          return new Response(
            JSON.stringify({
              error: 'Rate limit: max 10 votes per IP per hour',
            }),
            {
              status: 429,
              headers: { ...corsHeaders, 'Content-Type': 'application/json' },
            }
          );
        }

        // Increment rate limit counter (1 hour TTL)
        await env.RATE_LIMIT_KV.put(rateLimitKey, (count + 1).toString(), {
          expirationTtl: 3600,
        });
      }

      // Parse request body
      let body: VoteRequest;
      try {
        body = await request.json() as VoteRequest;
      } catch {
        return new Response(
          JSON.stringify({ error: 'Invalid JSON body' }),
          {
            status: 400,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          }
        );
      }

      // Validate feature_id
      if (!body.feature_id || !VALID_FEATURES.has(body.feature_id)) {
        return new Response(
          JSON.stringify({
            error: 'Invalid feature_id',
            valid_features: Array.from(VALID_FEATURES),
          }),
          {
            status: 400,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          }
        );
      }

      // Validate user_hash
      if (!body.user_hash || body.user_hash.length < 10) {
        return new Response(
          JSON.stringify({ error: 'Invalid user_hash' }),
          {
            status: 400,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          }
        );
      }

      // Validate User-Agent (anti-spam)
      const userAgent = request.headers.get('User-Agent');
      if (!userAgent || userAgent.length < 5) {
        return new Response(
          JSON.stringify({
            error: 'Invalid User-Agent (spam prevention)',
          }),
          {
            status: 400,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          }
        );
      }

      // Insert vote (idempotent: ON CONFLICT DO NOTHING)
      try {
        const timestamp = new Date().toISOString();
        await env.VOTES_DB.prepare(`
          INSERT INTO votes (feature_id, user_hash, source, voted_at)
          VALUES (?, ?, ?, ?)
          ON CONFLICT (feature_id, user_hash) DO NOTHING
        `).bind(
          body.feature_id,
          body.user_hash,
          body.source || 'cli',
          timestamp
        ).run();

        // Fetch updated count for this feature
        const result = await env.VOTES_DB.prepare(`
          SELECT COUNT(*) as count
          FROM votes
          WHERE feature_id = ?
        `).bind(body.feature_id).first<{ count: number }>();

        const count = result?.count || 0;

        return new Response(
          JSON.stringify({
            success: true,
            feature_id: body.feature_id,
            count,
          }),
          {
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          }
        );
      } catch (err) {
        console.error('Error recording vote:', err);
        return new Response(
          JSON.stringify({ error: 'Database write failed' }),
          {
            status: 500,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          }
        );
      }
    }

    // 404 for unknown routes
    return new Response(
      JSON.stringify({ error: 'Not found' }),
      {
        status: 404,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );
  },
};
