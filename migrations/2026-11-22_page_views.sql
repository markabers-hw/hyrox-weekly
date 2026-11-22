-- First-party website traffic tracking (replaces relying on Netlify's 7-day analytics window).
-- Written by the Netlify function hyroxweekly-site/netlify/functions/track.mjs, read by the dashboard's
-- Analytics page via the traffic_* functions below.
--
-- Privacy: no cookies, no IP addresses stored. visitor_hash is an HMAC of IP + user agent keyed by a secret
-- that rotates daily, so it can count unique visitors within a day but cannot follow anyone across days.
--
-- Undo with:
--   DROP FUNCTION public.traffic_daily(int, text);
--   DROP FUNCTION public.traffic_breakdown(text, int, int);
--   DROP FUNCTION public.traffic_signups_daily(int, text);
--   DROP TABLE public.page_views;

CREATE TABLE IF NOT EXISTS public.page_views (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    viewed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    path          TEXT NOT NULL CHECK (char_length(path) <= 300),
    referrer_host TEXT CHECK (char_length(referrer_host) <= 100),   -- NULL = direct / internal navigation
    utm_source    TEXT CHECK (char_length(utm_source) <= 100),
    utm_medium    TEXT CHECK (char_length(utm_medium) <= 100),
    utm_campaign  TEXT CHECK (char_length(utm_campaign) <= 100),
    country       TEXT CHECK (char_length(country) = 2),            -- ISO 3166-1 alpha-2
    device        TEXT CHECK (device IN ('mobile', 'tablet', 'desktop')),
    visitor_hash  TEXT                                              -- rotates daily; see header comment
);

CREATE INDEX IF NOT EXISTS page_views_viewed_at_idx ON public.page_views (viewed_at DESC);
CREATE INDEX IF NOT EXISTS page_views_path_idx ON public.page_views (path, viewed_at);

-- RLS on with no policies: the public anon key can neither read nor write this table.
-- The Netlify function and the dashboard use the service key, which bypasses RLS.
ALTER TABLE public.page_views ENABLE ROW LEVEL SECURITY;


-- One row per local day: total views and unique visitors (unique per day, since the hash rotates daily).
CREATE OR REPLACE FUNCTION public.traffic_daily(p_days int DEFAULT 90, p_tz text DEFAULT 'Australia/Sydney')
RETURNS TABLE (day date, views bigint, visitors bigint)
LANGUAGE sql STABLE AS $$
    SELECT (viewed_at AT TIME ZONE p_tz)::date AS day,
           count(*) AS views,
           count(DISTINCT visitor_hash) AS visitors
    FROM public.page_views
    WHERE viewed_at >= now() - make_interval(days => p_days)
    GROUP BY 1
    ORDER BY 1;
$$;

-- Top values for one dimension: path, referrer, country, device, utm_source, utm_medium or utm_campaign.
-- Unknown dimensions return a single "(none)" row.
CREATE OR REPLACE FUNCTION public.traffic_breakdown(p_dimension text, p_days int DEFAULT 30, p_limit int DEFAULT 20)
RETURNS TABLE (label text, views bigint, visitors bigint)
LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
               CASE p_dimension
                   WHEN 'path'         THEN path
                   WHEN 'referrer'     THEN referrer_host
                   WHEN 'country'      THEN country
                   WHEN 'device'       THEN device
                   WHEN 'utm_source'   THEN utm_source
                   WHEN 'utm_medium'   THEN utm_medium
                   WHEN 'utm_campaign' THEN utm_campaign
               END,
               '(none)') AS label,
           count(*) AS views,
           count(DISTINCT visitor_hash) AS visitors
    FROM public.page_views
    WHERE viewed_at >= now() - make_interval(days => p_days)
    GROUP BY 1
    ORDER BY 2 DESC, 1
    LIMIT p_limit;
$$;

-- New newsletter signups per local day, for lining up against traffic.
CREATE OR REPLACE FUNCTION public.traffic_signups_daily(p_days int DEFAULT 90, p_tz text DEFAULT 'Australia/Sydney')
RETURNS TABLE (day date, signups bigint)
LANGUAGE sql STABLE AS $$
    SELECT (subscribed_at AT TIME ZONE p_tz)::date AS day,
           count(*) AS signups
    FROM public.newsletter_subscribers
    WHERE subscribed_at >= now() - make_interval(days => p_days)
    GROUP BY 1
    ORDER BY 1;
$$;

-- Postgres grants EXECUTE to everyone by default, and Supabase exposes public functions over the REST API.
-- Lock these down to the service key only.
REVOKE EXECUTE ON FUNCTION public.traffic_daily(int, text)             FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.traffic_breakdown(text, int, int)    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.traffic_signups_daily(int, text)     FROM PUBLIC, anon, authenticated;
GRANT  EXECUTE ON FUNCTION public.traffic_daily(int, text)             TO service_role;
GRANT  EXECUTE ON FUNCTION public.traffic_breakdown(text, int, int)    TO service_role;
GRANT  EXECUTE ON FUNCTION public.traffic_signups_daily(int, text)     TO service_role;
