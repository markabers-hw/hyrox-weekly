/**
 * Page View Tracker
 * POST /api/track
 * Body (JSON, sent as text/plain by /hw.js): { path: string, referrer?: string, search?: string }
 *
 * Writes one row to Supabase `page_views` per real browser page load. Cookieless, and no IP address is stored:
 * the visitor hash is an HMAC of IP + user agent keyed by a secret that rotates daily, so it counts unique
 * visitors within a day but cannot follow anyone across days. Always answers 204 so tracking never affects a page.
 *
 * Optional env var ANALYTICS_SALT; falls back to JWT_SECRET (domain-separated, so the two never collide).
 */

import { createClient } from '@supabase/supabase-js';
import { createHmac } from 'node:crypto';

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY
);

// Only count traffic from the real site. Deploy previews and other origins are ignored.
// `netlify dev` sets NETLIFY_DEV, which additionally allows localhost so the tracker can be tested.
const SITE_HOSTS = new Set(['hyroxweekly.com', 'www.hyroxweekly.com']);
const IS_DEV = Boolean(process.env.NETLIFY_DEV);

const MAX_BODY_BYTES = 2000;
const BOT_UA = /bot|crawl|spider|slurp|headless|lighthouse|pingdom|uptime|monitor|facebookexternalhit|curl|wget|python-requests|httpclient|go-http-client|java\//i;

function hostOf(value) {
  try {
    return new URL(value).hostname.toLowerCase();
  } catch {
    return null;
  }
}

function isAllowedOrigin(req) {
  const host = hostOf(req.headers.get('origin') || req.headers.get('referer') || '');
  if (!host) return false;
  if (SITE_HOSTS.has(host)) return true;
  return IS_DEV && (host === 'localhost' || host === '127.0.0.1');
}

/** "/archive/edition-34/index.html?x=1" -> "/archive/edition-34" (query string never reaches the database). */
function normalizePath(raw) {
  if (typeof raw !== 'string' || !raw.startsWith('/')) return null;
  let path = raw.split(/[?#]/)[0].replace(/\/index\.html$/, '/').replace(/\.html$/, '');
  if (path.length > 1) path = path.replace(/\/+$/, '');
  return path.slice(0, 300) || '/';
}

/** Referrer hostname without "www.", or null for direct visits and our own pages. */
function referrerHost(raw) {
  if (typeof raw !== 'string' || !/^https?:\/\//i.test(raw)) return null;
  const host = hostOf(raw);
  if (!host) return null;
  const bare = host.replace(/^www\./, '');
  if (SITE_HOSTS.has(host) || SITE_HOSTS.has(bare)) return null;
  return bare.slice(0, 100);
}

function utmParams(search) {
  const params = new URLSearchParams(typeof search === 'string' ? search : '');
  const clean = (key) => (params.get(key) || '').trim().slice(0, 100) || null;
  return {
    utm_source: clean('utm_source'),
    utm_medium: clean('utm_medium'),
    utm_campaign: clean('utm_campaign'),
  };
}

function deviceClass(ua) {
  if (/iPad|Tablet|Android(?!.*Mobile)/i.test(ua)) return 'tablet';
  if (/Mobi|iPhone|Android/i.test(ua)) return 'mobile';
  return 'desktop';
}

let warnedNoSecret = false;

function visitorHash(ip, ua) {
  const secret = process.env.ANALYTICS_SALT || process.env.JWT_SECRET;
  if (!secret) {
    // Without a secret, views are still recorded but unique-visitor counts will be empty.
    // `netlify dev` hits this: JWT_SECRET is flagged secret in Netlify, so the CLI can't pull its value.
    // Set ANALYTICS_SALT to any string when running locally.
    if (!warnedNoSecret) {
      console.warn('track: no ANALYTICS_SALT or JWT_SECRET set; visitor_hash will be NULL');
      warnedNoSecret = true;
    }
    return null;
  }
  if (!ip) return null;
  const today = new Date().toISOString().slice(0, 10);
  const dailyKey = createHmac('sha256', secret).update(`pageviews:${today}`).digest();
  return createHmac('sha256', dailyKey).update(`${ip}|${ua}`).digest('hex').slice(0, 32);
}

export default async (req, context) => {
  if (req.method !== 'POST') {
    return new Response(null, { status: 405, headers: { Allow: 'POST' } });
  }

  const done = new Response(null, { status: 204 });

  try {
    const ua = req.headers.get('user-agent') || '';
    if (!ua || BOT_UA.test(ua) || !isAllowedOrigin(req)) return done;

    const text = await req.text();
    if (text.length > MAX_BODY_BYTES) return done;

    const body = JSON.parse(text);
    const path = normalizePath(body.path);
    if (!path) return done;

    const countryCode = context?.geo?.country?.code;

    const { error } = await supabase.from('page_views').insert({
      path,
      referrer_host: referrerHost(body.referrer),
      ...utmParams(body.search),
      country: typeof countryCode === 'string' && countryCode.length === 2 ? countryCode.toUpperCase() : null,
      device: deviceClass(ua),
      visitor_hash: visitorHash(context?.ip || req.headers.get('x-nf-client-connection-ip'), ua),
    });

    if (error) console.error('page_views insert failed:', error.message);
  } catch (err) {
    console.error('track error:', err.message);
  }

  return done;
};
