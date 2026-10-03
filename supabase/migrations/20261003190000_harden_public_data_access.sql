-- The public site is read-only. Keep display data selectable through the API,
-- but do not allow clients holding the publishable key to modify it.
REVOKE INSERT, UPDATE, DELETE ON TABLE
  public.players,
  public.performance_stats,
  public.social_media,
  public.valuations,
  public.public_valuations
FROM PUBLIC, anon, authenticated;

-- These internal/test tables are not used by the public application.
REVOKE SELECT ON TABLE
  public.nil_training_labels,
  public.players_test
FROM PUBLIC, anon, authenticated;

DROP POLICY IF EXISTS allow_all ON public.players;
DROP POLICY IF EXISTS authenticated_delete_players ON public.players;
DROP POLICY IF EXISTS authenticated_insert_players ON public.players;
DROP POLICY IF EXISTS authenticated_select_all_players ON public.players;
DROP POLICY IF EXISTS authenticated_update_players ON public.players;
CREATE POLICY public_read_players ON public.players
  FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS allow_all ON public.performance_stats;
DROP POLICY IF EXISTS authenticated_delete_performance_stats ON public.performance_stats;
DROP POLICY IF EXISTS authenticated_insert_performance_stats ON public.performance_stats;
DROP POLICY IF EXISTS authenticated_select_all_performance_stats ON public.performance_stats;
DROP POLICY IF EXISTS authenticated_update_performance_stats ON public.performance_stats;
CREATE POLICY public_read_performance_stats ON public.performance_stats
  FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS allow_all ON public.social_media;
CREATE POLICY public_read_social_media ON public.social_media
  FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS allow_all ON public.valuations;
CREATE POLICY public_read_valuations ON public.valuations
  FOR SELECT TO anon, authenticated USING (true);

CREATE POLICY public_read_public_valuations ON public.public_valuations
  FOR SELECT TO anon, authenticated USING (true);

-- This is an internal DDL event-trigger helper; it must never be callable as
-- a public REST RPC endpoint.
REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC, anon, authenticated;

-- Pin the lookup path for the public stats RPC.
ALTER FUNCTION public.get_season_stats(integer)
  SET search_path = pg_catalog, public;
