-- Grouped content counts for the dashboard sidebar and Dashboard page.
-- Replaces fetching every content_items row (Supabase caps a response at 1000 rows, so the counts were wrong).
-- Undo with: DROP VIEW public.content_status_counts;
CREATE OR REPLACE VIEW public.content_status_counts
WITH (security_invoker = true) AS
SELECT platform, status, COUNT(*)::int AS count
FROM public.content_items
GROUP BY platform, status;
