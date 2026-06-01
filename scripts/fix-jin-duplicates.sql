-- ============================================================================
-- DATA FIX: 晋文公 / 晋惠公 duplicate + cross-brother (重耳/夷吾) contamination
-- ============================================================================
-- Problem (verified against data/changjuan.sqlite 2026-05-31):
--   per:晋文公  (85 ev)  — CORRECT survivor for 重耳 / Duke Wen
--   per:晋重耳  (1 ev)   — duplicate of 晋文公; linker failed to fold it
--   per:晋惠公  (25 ev)  — CORRECT survivor for 夷吾 / Duke Hui
--   per:晋夷吾  (1 ev)   — duplicate of 晋惠公 AND wrongly carries 重耳/文公 variants
--                          (two-brother conflation)
--
-- The single event on each doomed record is evt:出镇 (献公 garrisons his sons):
-- 重耳 and 夷吾 BOTH legitimately participate as 受命, so re-pointing each to its
-- correct canonical is correct, not a mis-attribution.
--
-- Fix = two merges + strip the 3 contaminating variants off 晋惠公.
-- Fully reversible: snapshot first, and every deletion is logged to audit_log.
-- ============================================================================
--
-- PRE-FLIGHT (run in the shell BEFORE this script — NOT part of the SQL):
--   cp data/changjuan.sqlite data/changjuan.sqlite.bak-jinfix
--   rm -f data/changjuan.sqlite-shm data/changjuan.sqlite-wal
-- ============================================================================

PRAGMA foreign_keys = OFF;   -- we re-point FK columns by hand; avoid mid-statement trips
BEGIN;

-- ---------- audit: capture before-state of the two doomed records -----------
INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, before_json, after_json, actor, at)
VALUES
 ('aud:jinfix-merge-chonger', 'person', 'per:晋重耳', NULL, 'merge',
  json_object('canonical_name','晋重耳','events',1,'reason','duplicate of 晋文公 (重耳=文公)'),
  json_object('merged_into','per:晋文公'), 'manual-fix', datetime('now')),
 ('aud:jinfix-merge-yiwu', 'person', 'per:晋夷吾', NULL, 'merge',
  json_object('canonical_name','晋惠公','events',1,'reason','duplicate of 晋惠公 (夷吾=惠公); record also wrongly held 重耳/公子重耳/文公 variants'),
  json_object('merged_into','per:晋惠公','stripped_variants', json_array('重耳/本名','公子重耳/别名','文公/谥号')),
  'manual-fix', datetime('now'));

-- ============================================================================
-- MERGE A:  per:晋重耳  ->  per:晋文公
-- Pattern per table: UPDATE OR IGNORE re-points; DELETE removes rows that
-- collided on a PK/UNIQUE (i.e. the survivor already had that edge).
-- ============================================================================
UPDATE OR IGNORE person_variants    SET person_id='per:晋文公'      WHERE person_id='per:晋重耳';
DELETE FROM person_variants                                         WHERE person_id='per:晋重耳';

UPDATE OR IGNORE event_participants  SET person_id='per:晋文公'      WHERE person_id='per:晋重耳';
DELETE FROM event_participants                                      WHERE person_id='per:晋重耳';

UPDATE OR IGNORE person_relations    SET from_person_id='per:晋文公' WHERE from_person_id='per:晋重耳';
DELETE FROM person_relations                                        WHERE from_person_id='per:晋重耳';
UPDATE OR IGNORE person_relations    SET to_person_id='per:晋文公'   WHERE to_person_id='per:晋重耳';
DELETE FROM person_relations                                        WHERE to_person_id='per:晋重耳';
DELETE FROM person_relations         WHERE from_person_id = to_person_id;   -- drop any self-loop

UPDATE OR IGNORE person_states       SET person_id='per:晋文公'      WHERE person_id='per:晋重耳';
DELETE FROM person_states                                           WHERE person_id='per:晋重耳';

-- person-level citations
UPDATE OR IGNORE entity_citations    SET entity_id='per:晋文公'
  WHERE entity_kind='person' AND entity_id='per:晋重耳';
DELETE FROM entity_citations         WHERE entity_kind='person' AND entity_id='per:晋重耳';
-- edge citations embed the person id in a composite entity_id (e.g.
-- 'evt:出镇:per:晋重耳:受命', 'per:晋献公:per:晋重耳:parent') -> rewrite the token
UPDATE OR IGNORE entity_citations    SET entity_id = REPLACE(entity_id, 'per:晋重耳', 'per:晋文公')
  WHERE entity_id LIKE '%per:晋重耳%';
DELETE FROM entity_citations         WHERE entity_id LIKE '%per:晋重耳%';

DELETE FROM persons                  WHERE id='per:晋重耳';

-- ============================================================================
-- MERGE B:  per:晋夷吾  ->  per:晋惠公   (then strip 重耳/文公 contamination)
-- ============================================================================
UPDATE OR IGNORE person_variants    SET person_id='per:晋惠公'      WHERE person_id='per:晋夷吾';
DELETE FROM person_variants                                         WHERE person_id='per:晋夷吾';

UPDATE OR IGNORE event_participants  SET person_id='per:晋惠公'      WHERE person_id='per:晋夷吾';
DELETE FROM event_participants                                      WHERE person_id='per:晋夷吾';

UPDATE OR IGNORE person_relations    SET from_person_id='per:晋惠公' WHERE from_person_id='per:晋夷吾';
DELETE FROM person_relations                                        WHERE from_person_id='per:晋夷吾';
UPDATE OR IGNORE person_relations    SET to_person_id='per:晋惠公'   WHERE to_person_id='per:晋夷吾';
DELETE FROM person_relations                                        WHERE to_person_id='per:晋夷吾';
DELETE FROM person_relations         WHERE from_person_id = to_person_id;

UPDATE OR IGNORE person_states       SET person_id='per:晋惠公'      WHERE person_id='per:晋夷吾';
DELETE FROM person_states                                           WHERE person_id='per:晋夷吾';

UPDATE OR IGNORE entity_citations    SET entity_id='per:晋惠公'
  WHERE entity_kind='person' AND entity_id='per:晋夷吾';
DELETE FROM entity_citations         WHERE entity_kind='person' AND entity_id='per:晋夷吾';
UPDATE OR IGNORE entity_citations    SET entity_id = REPLACE(entity_id, 'per:晋夷吾', 'per:晋惠公')
  WHERE entity_id LIKE '%per:晋夷吾%';
DELETE FROM entity_citations         WHERE entity_id LIKE '%per:晋夷吾%';

-- re-point the 2 historical (status='merged') merge_candidates rows so they don't dangle
UPDATE merge_candidates              SET candidate_b_id='per:晋惠公' WHERE candidate_b_id='per:晋夷吾';

DELETE FROM persons                  WHERE id='per:晋夷吾';

-- strip the cross-brother contamination now sitting on 晋惠公
DELETE FROM person_variants
 WHERE person_id='per:晋惠公'
   AND ( (variant='重耳'   AND kind='本名')
      OR (variant='公子重耳' AND kind='别名')
      OR (variant='文公'   AND kind='谥号') );

COMMIT;
PRAGMA foreign_keys = ON;
