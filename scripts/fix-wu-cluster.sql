-- ============================================================================
-- DATA FIX: 吴 royal-family cluster — 3 duplicate merges + kin-edge repair
-- ============================================================================
-- Problem (verified against data/changjuan.sqlite 2026-06-01):
--   Duplicates (near-empty record folds into the full one):
--     per:吴公子光  (1 ev, 0 rel)  -> per:吴王阖闾 (32 ev, 7 rel)   [光=阖闾]
--     per:公子夷昧  (1 ev, 0 rel)  -> per:吴王夷昧 (3 ev, 1 rel)    [余眛=夷昧]
--     per:公子夫概  (1 ev, 1 rel)  -> per:夫概     (7 ev, 2 rel)    [夫概]
--   Each doomed record's variant set is IDENTICAL to its survivor's, so no
--   variant is lost (collisions are ignored then deleted).
--
--   Missing kin edges (source-grounded, see citations below):
--     诸樊 parent 吴王阖闾   — "诸樊之子名光，善于用兵，王僚用之为将。"
--     寿梦 parent 诸樊       — "寿梦病笃，召其四子诸樊、馀祭、夷昧、季札至床前"
--     寿梦 parent 吴王夷昧   —  (same line; 寿梦 already linked to 余祭 + 季札)
--
--   Wrong edge:
--     per:吴王阖闾 sibling per:季札  — 季札 is 阖闾's UNCLE (寿梦's 4th son),
--       not his sibling. The uncle/cousin relations aren't representable as a
--       direct edge (no 'uncle'/'cousin' kind) and aren't drawn by the reader
--       chart; they live implicitly in the 寿梦→{诸樊,夷昧}→{阖闾,僚} tree.
--       Remove the incorrect sibling edge.
--
-- 吴王僚 (阖闾's cousin) is unchanged: it already surfaces on 阖闾's card via the
-- existing `rival` political edge (the 专诸 assassination). Cousin kinship is
-- not chartable; no kin edge is added between them.
--
-- Added edges are provenance='curated', confidence=1.0; the source quote backing
-- each is recorded in audit_log.after_json (citation_id left NULL — matches the
-- manual-fix precedent in fix-jin-duplicates.sql).
--
-- Fully reversible: snapshot first, every change logged to audit_log.
-- ============================================================================
--
-- PRE-FLIGHT (run in the shell BEFORE this script — NOT part of the SQL):
--   cp data/changjuan.sqlite data/changjuan.sqlite.bak-wufix
--   rm -f data/changjuan.sqlite-shm data/changjuan.sqlite-wal
-- ============================================================================

PRAGMA foreign_keys = OFF;   -- we re-point FK columns by hand; avoid mid-statement trips
BEGIN;

-- ---------- audit: merges -----------
INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, before_json, after_json, actor, at)
VALUES
 ('aud:wufix-merge-guang', 'person', 'per:吴公子光', NULL, 'merge',
  json_object('canonical_name','吴王阖闾','events',1,'reason','duplicate of 吴王阖闾 (光=阖闾); identical variant set'),
  json_object('merged_into','per:吴王阖闾'), 'manual-fix', datetime('now')),
 ('aud:wufix-merge-yimei', 'person', 'per:公子夷昧', NULL, 'merge',
  json_object('canonical_name','吴王夷昧','events',1,'reason','duplicate of 吴王夷昧 (余眛=夷昧); identical variant set'),
  json_object('merged_into','per:吴王夷昧'), 'manual-fix', datetime('now')),
 ('aud:wufix-merge-fugai', 'person', 'per:公子夫概', NULL, 'merge',
  json_object('canonical_name','夫概','events',1,'reason','duplicate of 夫概; identical variant set'),
  json_object('merged_into','per:夫概'), 'manual-fix', datetime('now'));

-- ============================================================================
-- MERGE A:  per:吴公子光  ->  per:吴王阖闾
-- ============================================================================
UPDATE OR IGNORE person_variants    SET person_id='per:吴王阖闾'      WHERE person_id='per:吴公子光';
DELETE FROM person_variants                                          WHERE person_id='per:吴公子光';

UPDATE OR IGNORE event_participants  SET person_id='per:吴王阖闾'      WHERE person_id='per:吴公子光';
DELETE FROM event_participants                                       WHERE person_id='per:吴公子光';

UPDATE OR IGNORE person_relations    SET from_person_id='per:吴王阖闾' WHERE from_person_id='per:吴公子光';
DELETE FROM person_relations                                         WHERE from_person_id='per:吴公子光';
UPDATE OR IGNORE person_relations    SET to_person_id='per:吴王阖闾'   WHERE to_person_id='per:吴公子光';
DELETE FROM person_relations                                         WHERE to_person_id='per:吴公子光';
DELETE FROM person_relations         WHERE from_person_id = to_person_id;   -- drop any self-loop

UPDATE OR IGNORE person_states       SET person_id='per:吴王阖闾'      WHERE person_id='per:吴公子光';
DELETE FROM person_states                                            WHERE person_id='per:吴公子光';

UPDATE OR IGNORE entity_citations    SET entity_id='per:吴王阖闾'
  WHERE entity_kind='person' AND entity_id='per:吴公子光';
DELETE FROM entity_citations         WHERE entity_kind='person' AND entity_id='per:吴公子光';
UPDATE OR IGNORE entity_citations    SET entity_id = REPLACE(entity_id, 'per:吴公子光', 'per:吴王阖闾')
  WHERE entity_id LIKE '%per:吴公子光%';
DELETE FROM entity_citations         WHERE entity_id LIKE '%per:吴公子光%';

UPDATE merge_candidates              SET candidate_a_id='per:吴王阖闾' WHERE candidate_a_id='per:吴公子光';
UPDATE merge_candidates              SET candidate_b_id='per:吴王阖闾' WHERE candidate_b_id='per:吴公子光';

DELETE FROM persons                  WHERE id='per:吴公子光';

-- ============================================================================
-- MERGE B:  per:公子夷昧  ->  per:吴王夷昧
-- ============================================================================
UPDATE OR IGNORE person_variants    SET person_id='per:吴王夷昧'      WHERE person_id='per:公子夷昧';
DELETE FROM person_variants                                          WHERE person_id='per:公子夷昧';

UPDATE OR IGNORE event_participants  SET person_id='per:吴王夷昧'      WHERE person_id='per:公子夷昧';
DELETE FROM event_participants                                       WHERE person_id='per:公子夷昧';

UPDATE OR IGNORE person_relations    SET from_person_id='per:吴王夷昧' WHERE from_person_id='per:公子夷昧';
DELETE FROM person_relations                                         WHERE from_person_id='per:公子夷昧';
UPDATE OR IGNORE person_relations    SET to_person_id='per:吴王夷昧'   WHERE to_person_id='per:公子夷昧';
DELETE FROM person_relations                                         WHERE to_person_id='per:公子夷昧';
DELETE FROM person_relations         WHERE from_person_id = to_person_id;

UPDATE OR IGNORE person_states       SET person_id='per:吴王夷昧'      WHERE person_id='per:公子夷昧';
DELETE FROM person_states                                            WHERE person_id='per:公子夷昧';

UPDATE OR IGNORE entity_citations    SET entity_id='per:吴王夷昧'
  WHERE entity_kind='person' AND entity_id='per:公子夷昧';
DELETE FROM entity_citations         WHERE entity_kind='person' AND entity_id='per:公子夷昧';
UPDATE OR IGNORE entity_citations    SET entity_id = REPLACE(entity_id, 'per:公子夷昧', 'per:吴王夷昧')
  WHERE entity_id LIKE '%per:公子夷昧%';
DELETE FROM entity_citations         WHERE entity_id LIKE '%per:公子夷昧%';

UPDATE merge_candidates              SET candidate_a_id='per:吴王夷昧' WHERE candidate_a_id='per:公子夷昧';
UPDATE merge_candidates              SET candidate_b_id='per:吴王夷昧' WHERE candidate_b_id='per:公子夷昧';

DELETE FROM persons                  WHERE id='per:公子夷昧';

-- ============================================================================
-- MERGE C:  per:公子夫概  ->  per:夫概
-- ============================================================================
UPDATE OR IGNORE person_variants    SET person_id='per:夫概'          WHERE person_id='per:公子夫概';
DELETE FROM person_variants                                          WHERE person_id='per:公子夫概';

UPDATE OR IGNORE event_participants  SET person_id='per:夫概'          WHERE person_id='per:公子夫概';
DELETE FROM event_participants                                       WHERE person_id='per:公子夫概';

UPDATE OR IGNORE person_relations    SET from_person_id='per:夫概'     WHERE from_person_id='per:公子夫概';
DELETE FROM person_relations                                         WHERE from_person_id='per:公子夫概';
UPDATE OR IGNORE person_relations    SET to_person_id='per:夫概'       WHERE to_person_id='per:公子夫概';
DELETE FROM person_relations                                         WHERE to_person_id='per:公子夫概';
DELETE FROM person_relations         WHERE from_person_id = to_person_id;

UPDATE OR IGNORE person_states       SET person_id='per:夫概'          WHERE person_id='per:公子夫概';
DELETE FROM person_states                                            WHERE person_id='per:公子夫概';

UPDATE OR IGNORE entity_citations    SET entity_id='per:夫概'
  WHERE entity_kind='person' AND entity_id='per:公子夫概';
DELETE FROM entity_citations         WHERE entity_kind='person' AND entity_id='per:公子夫概';
UPDATE OR IGNORE entity_citations    SET entity_id = REPLACE(entity_id, 'per:公子夫概', 'per:夫概')
  WHERE entity_id LIKE '%per:公子夫概%';
DELETE FROM entity_citations         WHERE entity_id LIKE '%per:公子夫概%';

UPDATE merge_candidates              SET candidate_a_id='per:夫概'     WHERE candidate_a_id='per:公子夫概';
UPDATE merge_candidates              SET candidate_b_id='per:夫概'     WHERE candidate_b_id='per:公子夫概';

DELETE FROM persons                  WHERE id='per:公子夫概';

-- ============================================================================
-- REMOVE wrong edge: 吴王阖闾 sibling 季札  (季札 is the uncle, not a sibling)
-- ============================================================================
INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, before_json, after_json, actor, at)
VALUES
 ('aud:wufix-del-helu-jizha-sibling', 'person_relation',
  'per:吴王阖闾:per:季札:sibling', NULL, 'delete',
  json_object('kind','sibling','reason','季札 is 阖闾 uncle (寿梦 4th son), not sibling; remove mis-extracted edge'),
  NULL, 'manual-fix', datetime('now'));

DELETE FROM entity_citations
 WHERE entity_kind='person_relation'
   AND entity_id LIKE '%per:吴王阖闾%' AND entity_id LIKE '%per:季札%';
DELETE FROM person_relations
 WHERE from_person_id='per:吴王阖闾' AND to_person_id='per:季札' AND kind='sibling';

-- ============================================================================
-- ADD missing kin edges (curated, source-grounded)
-- ============================================================================
INSERT INTO audit_log (id, entity_kind, entity_id, field, change_kind, before_json, after_json, actor, at)
VALUES
 ('aud:wufix-add-zhufan-helu', 'person_relation', 'per:诸樊:per:吴王阖闾:parent', NULL, 'create',
  NULL,
  json_object('kind','parent','provenance','curated','source','诸樊之子名光，善于用兵，王僚用之为将。'),
  'manual-fix', datetime('now')),
 ('aud:wufix-add-shoumeng-zhufan', 'person_relation', 'per:寿梦:per:诸樊:parent', NULL, 'create',
  NULL,
  json_object('kind','parent','provenance','curated','source','寿梦病笃，召其四子诸樊、馀祭、夷昧、季札至床前'),
  'manual-fix', datetime('now')),
 ('aud:wufix-add-shoumeng-yimei', 'person_relation', 'per:寿梦:per:吴王夷昧:parent', NULL, 'create',
  NULL,
  json_object('kind','parent','provenance','curated','source','寿梦病笃，召其四子诸樊、馀祭、夷昧、季札至床前'),
  'manual-fix', datetime('now'));

INSERT OR IGNORE INTO person_relations
  (from_person_id, to_person_id, kind, confidence, provenance)
VALUES
 ('per:诸樊', 'per:吴王阖闾', 'parent', 1.0, 'curated'),
 ('per:寿梦', 'per:诸樊',     'parent', 1.0, 'curated'),
 ('per:寿梦', 'per:吴王夷昧', 'parent', 1.0, 'curated');

COMMIT;
PRAGMA foreign_keys = ON;
