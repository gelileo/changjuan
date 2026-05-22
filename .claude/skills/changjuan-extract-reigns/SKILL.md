---
name: changjuan-extract-reigns
description: Produce a draft YAML reign table for one Eastern-Zhou state, using training knowledge of the chronology. Output requires human review before commit. Use when the user asks to extract reigns for a state, e.g. "extract reigns for 晋" or "/changjuan-extract-reigns state:sta:jin".
---

# changjuan-extract-reigns — Phase 4 reign-table production

This skill produces a draft `data/reigns/<state>.yaml` file from the LLM's training
knowledge of Eastern-Zhou chronology. The output is a DRAFT — the user must review
the YAML and correct any date errors before committing.

## Invocation

```
/changjuan-extract-reigns state:sta:jin
```

`state` is the canonical state id (e.g. `sta:jin`, `sta:qi`, `sta:chu`). The output
is written to `/tmp/changjuan-reigns-<state_slug>.yaml`.

## Steps

### 1. Load skill context

Read `.claude/skills/changjuan-extract-reigns/system-prompt.md` for the full
extraction rules.

### 2. Parse the state argument

Accept `state:<state_id>` from the invocation. The state_id is the canonical form
(e.g. `sta:jin`). Convert to the filename slug: replace `:` with `_` and append
`.yaml` (e.g. `sta:jin` → `sta_jin.yaml`).

### 3. Produce the draft YAML

Following the rules in `system-prompt.md`, emit the YAML for ALL rulers of the
state during the Eastern-Zhou period (770-221 BCE). Cover the Spring-and-Autumn
period AND the Warring-States period. Required fields per ruler:
`id`, `posthumous_name`, `given_name`, `reign_start_bce`, `reign_end_bce`,
`sources`, `confidence`, `notes`. See `system-prompt.md` for definitions.

### 4. Write to the output file

Write the YAML to `/tmp/changjuan-reigns-<state_slug>.yaml`. Print the path on
completion so the user can find it.

### 5. Notify the user

Print a summary:

```
Draft reign YAML written to /tmp/changjuan-reigns-<state_slug>.yaml
Rulers: N
Date span: <earliest>-<latest> BCE
Low-confidence entries: M (review priority)

Review the file, correct any errors, then:
  git mv /tmp/changjuan-reigns-<state_slug>.yaml data/reigns/<state_slug>.yaml
  git add data/reigns/<state_slug>.yaml
  git commit -m "feat(reigns): add <state> reign table (Phase 4)"
```

## What this skill does NOT do

- It does NOT write to any database.
- It does NOT commit the YAML.
- It does NOT validate the dates against any external source. The user does.
- It does NOT modify any other files.
