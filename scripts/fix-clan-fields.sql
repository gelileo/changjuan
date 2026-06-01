-- ============================================================================
-- DATA FIX: 4 rows where 姓/氏 landed in the wrong field
-- ============================================================================
-- Field semantics (confirmed against data 2026-05-31):
--   Person.clan_name  = 氏 (lineage/branch: 赵 魏 韩 田 栾 崔 …)
--   State.ruling_clan = 姓 (ancestral surname: 姬 姜 嬴 芈 子 妫 …)
--
-- Mis-categorized rows:
--   per:公子职 (卫)  clan_name='姬'  -> NULL   (姬 is 卫's 姓, not an 氏; a 公子 has no 氏)
--   per:公子华 (郑)  clan_name='嬴'  -> NULL   (嬴 is wrong姓 for 郑[姬姓]; also a 公子 has no 氏)
--   sta:赵          ruling_clan='赵' -> '嬴'  (赵 is the 氏; the house姓 is 嬴 — 嬴姓赵氏)
--   sta:齐          ruling_clan='田' -> '妫'  (田 is the 氏; 田齐姓 is 妫. SEE CAVEAT)
--
-- CAVEAT on sta:齐: the single 齐 state entity conflates 姜齐 (姜姓, Ch.1-~84) and
-- 田齐 (妫姓, after 田氏代齐 ~386 BCE). The stored value '田' signals the 田齐 house,
-- whose 姓 is 妫 — so this fix uses 妫. If you instead consider 齐 primarily 姜齐
-- (the dominant era in the novel), change the value below to '姜'.
--
-- Reversible: snapshot first; every change logged to audit_log with before/after.
-- ============================================================================
--
-- PRE-FLIGHT (run in the shell BEFORE this script — checkpoint, then snapshot):
--   uv run python -c "import sqlite3; sqlite3.connect('data/changjuan.sqlite').execute('PRAGMA wal_checkpoint(TRUNCATE)')"
--   cp data/changjuan.sqlite data/changjuan.sqlite.bak-clanfix
-- (Do NOT rm the live -wal file — checkpoint handles it.)
-- ============================================================================

BEGIN;

-- ---------- audit: capture before-state ----------
INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, before_json, after_json, actor, at)
VALUES
 ('aud:clanfix-gongzizhi', 'person', 'per:公子职', 'clan_name', 'set',
  json_object('value','姬'), json_object('value', NULL, 'reason','姬 is 姓 not 氏; 公子 has no established 氏'),
  'manual-fix', datetime('now')),
 ('aud:clanfix-gongzihua', 'person', 'per:公子华', 'clan_name', 'set',
  json_object('value','嬴'), json_object('value', NULL, 'reason','嬴 is wrong 姓 for 郑(姬姓); 公子 has no 氏'),
  'manual-fix', datetime('now')),
 ('aud:clanfix-zhao', 'state', 'sta:赵', 'ruling_clan', 'set',
  json_object('value','赵'), json_object('value','嬴','reason','赵 is the 氏; house 姓 is 嬴 (嬴姓赵氏)'),
  'manual-fix', datetime('now')),
 ('aud:clanfix-qi', 'state', 'sta:齐', 'ruling_clan', 'set',
  json_object('value','田'), json_object('value','妫','reason','田 is the 氏; 田齐 姓 is 妫'),
  'manual-fix', datetime('now'));

-- ---------- apply the corrections ----------
UPDATE persons SET clan_name = NULL, updated_at = datetime('now') WHERE id='per:公子职' AND clan_name='姬';
UPDATE persons SET clan_name = NULL, updated_at = datetime('now') WHERE id='per:公子华' AND clan_name='嬴';

UPDATE states  SET ruling_clan = '嬴' WHERE id='sta:赵' AND ruling_clan='赵';
UPDATE states  SET ruling_clan = '妫' WHERE id='sta:齐' AND ruling_clan='田';

COMMIT;
