# Few-Shot Example — chunk `chk:dzl:1:14` (Ch.1, paragraphs 14–19)

This example shows the expected YAML output for one chunk of 东周列国志 Chapter 1.
All values are drawn from the hand-annotated golden files in `tests/golden/ch01/`.

---

## Chunk text excerpt

The chunk covers paragraphs 14–19 of Chapter 1. The key passages cited below:

**Paragraph 17 (the 43-year sacrifice, dream, and executions):**

> ……到四十三年，时当大祭，宣王宿于斋宫。忽见一美貌女子，自西方冉冉而来，直至宫廷……走入太庙之中，大笑三声，又大哭三声；不慌不忙，将七庙神主，做一束儿捆著，望东而去。……宣王惊觉，乃是一梦……召太史伯阳父圆梦。伯阳父曰："此梦……三年前童谣之语，王岂忘之耶……"……忽然想起三年前，曾命上大夫杜伯督率司市，查访妖女，全无下落。宣王大怒曰："既然如此，何不明白奏闻？分明是怠弃朕命"……武士将杜伯推出朝门斩了。左儒回到家中，自刎而死。乃下大夫左儒，是杜伯的好友，举荐同朝的……

**Paragraph 19 (隰叔 flees to 晋):**

> 杜伯之子隰叔，奔晋。后仕晋为士师之官，子孙遂为士氏。食邑于范，又为范氏。后人哀杜伯之忠，立祠于杜陵，号为杜主，又曰右将军庙，至今尚存。

---

## Expected YAML output

```yaml
persons:
  - id: p1
    canonical_name: 周宣王
    variants:
      - { variant: 宣王, kind: 谥号 }
      - { variant: 靖, kind: 本名 }
    gender: male
    social_category: royalty
    state_id: s1
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "到四十三年，时当大祭，宣王宿于斋宫"
      span: [0, 0]
    justifications:
      canonical_name: "宣王宿于斋宫"
      social_category: "宣王宿于斋宫"
      gender: "宣王宿于斋宫"

  - id: p2
    canonical_name: 伯阳父
    gender: male
    social_category: official
    state_id: s1
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "三年前童谣之语，王岂忘之耶"
      span: [0, 0]
    justifications:
      canonical_name: "三年前童谣之语，王岂忘之耶"
      # justification for canonical_name would need the name itself to appear in quote;
      # use the citation that actually names him in paragraph 17:
      # quote: "召太史伯阳父圆梦" → justifications.canonical_name: "伯阳父"

  - id: p3
    canonical_name: 杜伯
    gender: male
    social_category: official
    state_id: s1
    death_date:
      year_bce: 785
      uncertainty: point
      original: "宣王四十三年"
      inference_kind: explicit_reign_zhou
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "忽然想起三年前，曾命上大夫杜伯督率司市，查访妖女，全无下落"
      span: [0, 0]
    justifications:
      canonical_name: "上大夫杜伯"
      social_category: "上大夫杜伯"

  - id: p4
    canonical_name: 左儒
    gender: male
    social_category: official
    state_id: s1
    death_date:
      year_bce: 785
      uncertainty: point
      original: "(杜伯死同日)"
      inference_kind: relative_to_prior_event
      relative_anchor_event_id: e3
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "乃下大夫左儒，是杜伯的好友，举荐同朝的"
      span: [0, 0]
    justifications:
      canonical_name: "下大夫左儒"
      social_category: "下大夫左儒"

  - id: p5
    canonical_name: 隰叔
    gender: male
    social_category: noble
    state_id: s1
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 19
      quote: "杜伯之子隰叔，奔晋"
      span: [0, 0]
    justifications:
      canonical_name: "隰叔"
      social_category: "杜伯之子隰叔"

events:
  - id: e1
    type: 异梦
    date:
      year_bce: 785
      uncertainty: point
      original: "宣王四十三年"
      inference_kind: explicit_reign_zhou
    outcome: 伯阳父言梦应童谣之谶
    summary: 宣王四十三年大祭宿斋宫，夜梦美貌女子自西来，入太庙大笑大哭，捆七庙神主东去；告伯阳父，言女祸应童谣谶
    primary_place_id: pl1
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "到四十三年，时当大祭，宣王宿于斋宫"
      span: [0, 0]
    justifications:
      type: "忽见一美貌女子，自西方冉冉而来"
      outcome: "三年前童谣之语，王岂忘之耶"
      summary: "到四十三年，时当大祭，宣王宿于斋宫"

  - id: e2
    type: 处死
    date:
      year_bce: 785
      uncertainty: point
      original: "(颁胙之后)"
      inference_kind: relative_to_prior_event
      relative_anchor_event_id: e1
    outcome: 杜伯斩
    summary: 宣王问杜伯访妖女何无回话，杜伯奏中止；宣王怒，斥为不忠，命武士推出朝门斩之
    primary_place_id: pl1
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "武士将杜伯推出朝门斩了"
      span: [0, 0]
    justifications:
      type: "武士将杜伯推出朝门斩了"
      outcome: "推出朝门斩了"

  - id: e3
    type: 自刎
    date:
      year_bce: 785
      uncertainty: point
      original: "(杜伯死同日)"
      inference_kind: relative_to_prior_event
      relative_anchor_event_id: e2
    outcome: 左儒自刎
    summary: 左儒先谏宣王勿杀杜伯不听，杜伯被斩后回家自刎
    primary_place_id: pl1
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "左儒回到家中，自刎而死"
      span: [0, 0]
    justifications:
      type: "自刎而死"
      outcome: "自刎而死"

  - id: e4
    type: 出奔
    date:
      year_bce: 785
      uncertainty: circa
      original: "(杜伯死后)"
      inference_kind: relative_to_prior_event
      relative_anchor_event_id: e2
    outcome: 隰叔仕晋为士师；子孙为士氏、范氏
    summary: 杜伯之子隰叔奔晋，后仕晋为士师之官；子孙食邑于范，遂为士氏、范氏
    primary_place_id: null
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 19
      quote: "杜伯之子隰叔，奔晋"
      span: [0, 0]
    justifications:
      type: "奔晋"
      outcome: "后仕晋为士师之官"

places:
  - id: pl1
    name: 镐京
    type: 都城
    lat: null
    lon: null
    coord_confidence: null
    modern_equiv: 西安市西南
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "宣王宿于斋宫"
      span: [0, 0]
    justifications:
      name: "宣王宿于斋宫"
      # 镐京 is implied as the capital where the royal palace/ancestral hall is;
      # use a longer attestation if the name 镐京 appears explicitly in this chunk.

  - id: pl2
    name: 杜陵
    type: 邑
    lat: null
    lon: null
    coord_confidence: null
    modern_equiv: null
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 19
      quote: "立祠于杜陵，号为杜主"
      span: [0, 0]
    justifications:
      name: "于杜陵"
      type: "立祠于杜陵"

  - id: pl3
    name: 范
    type: 邑
    lat: null
    lon: null
    coord_confidence: null
    modern_equiv: null
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 19
      quote: "食邑于范，又为范氏"
      span: [0, 0]
    justifications:
      name: "食邑于范"
      type: "食邑于范"

states:
  - id: s1
    name: 周
    type: 王朝
    ruling_clan: 姬
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "宣王宿于斋宫"
      span: [0, 0]
    justifications:
      name: "宣王宿于斋宫"
      # 周 is the implied polity throughout; cite the strongest attestation available in this chunk.

  - id: s2
    name: 晋
    type: 诸侯国
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 19
      quote: "杜伯之子隰叔，奔晋"
      span: [0, 0]
    justifications:
      name: "奔晋"

relations:
  # --- event_participant ---
  - kind: event_participant
    event_id: e1
    person_id: p1
    role: 梦者
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "到四十三年，时当大祭，宣王宿于斋宫"
      span: [0, 0]

  - kind: event_participant
    event_id: e1
    person_id: p2
    role: 奏对
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "三年前童谣之语，王岂忘之耶"
      span: [0, 0]

  - kind: event_participant
    event_id: e2
    person_id: p1
    role: 命斩
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "宣王大怒曰"
      span: [0, 0]

  - kind: event_participant
    event_id: e2
    person_id: p3
    role: 死
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "武士将杜伯推出朝门斩了"
      span: [0, 0]

  - kind: event_participant
    event_id: e2
    person_id: p4
    role: 进谏
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "乃下大夫左儒，是杜伯的好友，举荐同朝的"
      span: [0, 0]

  - kind: event_participant
    event_id: e3
    person_id: p4
    role: 自刎
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "左儒回到家中，自刎而死"
      span: [0, 0]

  - kind: event_participant
    event_id: e4
    person_id: p5
    role: 出奔
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 19
      quote: "杜伯之子隰叔，奔晋"
      span: [0, 0]

  # --- person_relation ---
  - kind: person_relation
    from_person_id: p3
    to_person_id: p5
    kind_detail: parent
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 19
      quote: "杜伯之子隰叔"
      span: [0, 0]

  - kind: person_relation
    from_person_id: p4
    to_person_id: p3
    kind_detail: ally
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "乃下大夫左儒，是杜伯的好友"
      span: [0, 0]

  - kind: person_relation
    from_person_id: p3
    to_person_id: p4
    kind_detail: mentor
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "乃下大夫左儒，是杜伯的好友，举荐同朝的"
      span: [0, 0]

  # --- person_state ---
  - kind: person_state
    person_id: p1
    state_id: s1
    role: ruler
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "到四十三年，时当大祭，宣王宿于斋宫"
      span: [0, 0]

  - kind: person_state
    person_id: p3
    state_id: s1
    role: minister
    to_date:
      year_bce: 785
      uncertainty: point
      original: "宣王四十三年"
      inference_kind: explicit_reign_zhou
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "曾命上大夫杜伯督率司市"
      span: [0, 0]

  - kind: person_state
    person_id: p4
    state_id: s1
    role: minister
    to_date:
      year_bce: 785
      uncertainty: point
      original: "(杜伯死同日)"
      inference_kind: relative_to_prior_event
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "乃下大夫左儒"
      span: [0, 0]

  - kind: person_state
    person_id: p5
    state_id: s1
    role: defector
    to_date:
      year_bce: 785
      uncertainty: circa
      original: "(杜伯死后)"
      inference_kind: relative_to_prior_event
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 19
      quote: "杜伯之子隰叔，奔晋"
      span: [0, 0]

  - kind: person_state
    person_id: p5
    state_id: s2
    role: minister
    from_date:
      year_bce: 785
      uncertainty: circa
      original: "(奔晋后)"
      inference_kind: relative_to_prior_event
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 19
      quote: "后仕晋为士师之官"
      span: [0, 0]

  # --- event_relation (explicit causation attested in text) ---
  - kind: event_relation
    from_event_id: e1
    to_event_id: e2
    kind_detail: causes
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "忽然想起三年前，曾命上大夫杜伯督率司市，查访妖女，全无下落"
      span: [0, 0]

  - kind: event_relation
    from_event_id: e2
    to_event_id: e3
    kind_detail: causes
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 17
      quote: "左儒回到家中，自刎而死"
      span: [0, 0]

  - kind: event_relation
    from_event_id: e2
    to_event_id: e4
    kind_detail: causes
    citation:
      chunk_id: "chk:dzl:1:14"
      paragraph: 19
      quote: "杜伯之子隰叔，奔晋"
      span: [0, 0]
```

---

## Annotation notes for this chunk

- **p1 (周宣王):** Appears in multiple chunks. In a full extraction this record would be
  defined once (citing its earliest appearance), and all other chunks would reference it
  only in `relations`. Within a single-chunk extraction, it is defined here.

- **p2 (伯阳父):** `social_category: official` not `religious` — see system-prompt §六.
  太史 is an administrative court role, not a ritual specialist.

- **`relative_anchor_event_id` on e3 and e4:** Set explicitly here even though Stage 4
  walkback would infer them, because the within-chunk chain is complex enough that
  spelling out the link improves readability. The golden documents this as a
  "documentation aid, not functional necessity."

- **`primary_place_id: null` on e4 (出奔):** The flight destination 晋 is a polity
  (`state_id`), not a typed place. Representing it via `person_state` (role: defector)
  is the correct encoding — not an `event_place` pointing to a state entity.

- **`span: [0, 0]` on all citations:** Always leave as placeholder. The
  `scripts/fill-spans` script computes real offsets from `data/corpus.sqlite`.
