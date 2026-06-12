# 抽取系统提示 — changjuan Stage 3（cast 世情小说 profile）

> **语言说明：** 规则用中文，技术字段名（YAML 字段、id 格式、枚举值）保留英文，与 `extraction-schema.yaml` 一一对应。
>
> **profile：cast。** 适用于以**人物众多、人物关系密集**为核心的世情小说（红楼梦等），与 history（东周列国志，以事件/列国/纪年为核心）相对。**cast 不抽取历史纪年**——本书无可考朝代年月，任何 date 一律 `inference_kind: unknown` 或直接省略。

---

## ⓪、cast profile 抽取目标（最重要）

每个 chunk 中，按下列优先级抽取：

1. **persons（人物）** — 命名个体。世情小说人物极多，凡有名/号/称谓且参与情节者皆收。
2. **relations（人物关系）** — 本 profile 的**核心产出**。亲属、婚姻、情爱、主仆、师友、收养、同族等（见 §②）。
3. **groups（家族/世家）** — 四大家族（贾、史、王、薛）及府第宗族；作为 group 抽取（见 §③）。`group_type` 由 loader 按 profile 自动置为 `clan`，**你只需给 group 一个 `type`（如「家族」「世家」「皇族」），不要填 group_type**。
4. **events（情节事件）** — 宴饮、丧仪、婚配、入梦、出家、诉讼、省亲、起诗社等社会性事件（见 §④）。
5. **themes（主题/意象）** — 反复出现的母题与象征（梦/幻、真/假、盛/衰、情、宿命等），并标注其 occurrences（见 §⑤）。本 profile 新增。
6. **places（地点）** — 出现的地名/宅第（大观园、荣国府、葫芦庙等）。多为虚构，**不要**填 lat/lon/modern_equiv。

无 chronology、无跨国 states——不要套用历史/军政词汇。

---

## ①、persons

- **收录范围：** 有专名或固定称谓、且在本 chunk 有叙事行动或被明确指认者。仅一笔带过的群众（"众人""丫鬟们"）不收。
- **canonical_name：** 用最常用的正式名（贾宝玉、林黛玉、王熙凤、贾雨村、甄士隐）。
- **variants（变体）：** 收 `字 / 号 / 乳名 / 小名 / 排行称 / 法名道号 / 尊称绰号`。`kind` 用最贴近的：`本名 / 字 / 谥号 / 封号 / 别名`（schema 限定五值；号/乳名/绰号/法名等一律归 `别名`）。例：宝玉「字」无，但「乳名 宝玉」「号 绛洞花主」→ 都记 `别名`；黛玉「字 颦颦」→ `字`。
- **gender：** male / female（世情小说性别明确，尽量填）。
- **social_category（11 值）：** 红楼梦映射建议——
  - 主子/公侯之家成员（贾母、宝玉、黛玉、凤姐）→ `noble`
  - 任官者（贾政、贾雨村、王子腾）→ `official`
  - 丫鬟、小厮、奶妈、仆役（袭人、平儿、焙茗）→ `servant`
  - 僧、道、尼（一僧一道、空空道人、妙玉）→ `clergy`（神话性神祇/仙真如女娲、警幻仙姑 → `mythic`）
  - 市井平民（甄士隐为乡宦→`noble`/`official`酌情；刘姥姥→`commoner`）→ `commoner`
  - 拿不准 → `unknown`

---

## ②、relations（核心）

关系是有向的：`from_person_id` → `to_person_id`，配一个 `kind`。**只用下表 cast 词表**（loader 按 cast profile 校验，表外词会被拒）：

| 文本中的关系 | kind | 方向约定（from → to） |
|---|---|---|
| 父子/父女、母子/母女 | `parent` | 长辈 → 晚辈（贾政 → 宝玉） |
| （同上的反向，若文本以晚辈为主语） | `child` | 晚辈 → 长辈 |
| 夫妻、嫡配 | `spouse` | 任一方 → 另一方 |
| 兄弟、姊妹、兄妹 | `sibling` | 任一方 → 另一方 |
| 祖孙（祖父母→孙） | `grandparent` | 祖辈 → 孙辈（贾母 → 宝玉） |
| 孙→祖（以孙为主语时） | `grandchild` | 孙辈 → 祖辈 |
| 叔侄、姑侄、舅甥、伯侄 | `uncle_aunt` | 叔伯姑舅 → 侄甥 |
| 堂/表 兄弟姊妹 | `cousin` | 任一方 → 另一方 |
| 翁婿、婆媳、妯娌、连襟、姻亲 | `in_law` | 任一方 → 另一方 |
| 妾、姨娘、通房 | `concubine` | 妾 → 夫（赵姨娘 → 贾政） |
| 主仆（主子↔丫鬟/小厮/奶妈） | `master` / `servant` | 主 → 仆 用 `master`；仆 → 主 用 `servant`（取文本主语方向） |
| 师徒、教引 | `mentor` | 师 → 徒 |
| 朋友、手帕交、相与 | `friend` | 任一方 → 另一方 |
| 情爱、相恋、慕恋（宝黛） | `romantic` | 任一方 → 另一方 |
| 收养、养(母/女)、抚养 | `adopted` | 养方 → 被养方 |
| 同族、本家、一族 | `clan_member` | 任一方 → 另一方 |

- 每条 relation 需 `citation`（文本依据）。`relation_detail` 可记限定语（如 `异母`「庶出」「结拜」「续弦」「通房」）。
- 只记**文本明示或强烈暗示**的关系；不要凭红楼梦常识补全未在本 chunk 出现的关系（跨 chunk 由 linker 处理）。

### 关系记录的 YAML 形态（字段名严格，loader 按此读取）

所有关系都放在顶层 `relations` 列表，用 `kind` 区分关系类型；**各类型的"具体关系值"字段名不同**，务必照下表用对，否则 loader 会静默丢弃：

| `kind`（类型判别） | 具体值字段 | 端点字段 |
|---|---|---|
| `person_relation` | **`kind_detail`**（取 §② 词表，如 `spouse`/`parent`/`master`） | `from_person_id` / `to_person_id` |
| `person_group` | `role`（如 `成员`/`主母`，可空串） | `person_id` / `group_id` |
| `event_participant` | `role`（如 `主行`/`受`/`亡`） | `event_id` / `person_id` |
| `event_place` | `role`（如 `发生地`） | `event_id` / `place_id` |
| `event_relation` | **`relation_kind`**（`causes`/`precedes`/`related`） | `from_event_id` / `to_event_id` |

⚠️ **人物关系（person_relation）的关系词放在 `kind_detail`，不是 `relation_kind`**（`relation_kind` 仅用于事件因果 event_relation）。例：
```yaml
relations:
  - kind: person_relation
    from_person_id: p7
    to_person_id: p8
    kind_detail: spouse          # ← 关系词在这里
    relation_detail: 续弦         # ← 可选限定语
    citation: { chunk_id: "chk:hlm:1:5", paragraph: 10, quote: "嫡妻封氏", span: [0,0] }
```

---

## ③、groups（家族 / 世家）

- 抽取**宗族/家族/府第**作为 group：贾（贾府/荣宁二府）、史、王、薛 四大家族，以及皇族等。
- group 字段：`name`（如「贾」「薛」「贾府」）、`type`（叙事赋予的类别，如「家族」「世家」「皇族」「宦门」）、`ruling_clan`（宗姓，若文本点明）。**不要填 group_type**——loader 按 cast profile 置 `clan`。
- person 的 `group_id` 指向其所属家族 group 的 local id（如荣国府中人 → 贾 group 的 `g1`）。仅当本 chunk 明示归属时填。

---

## ④、events

- 抽取社会性/情节性事件：`type` 用自然标签（`宴` `丧` `婚` `梦` `出家` `诉讼` `省亲` `结社` `游园` `赠物` `相会` 等）。
- `summary` 一句话概述；`outcome` 若有结局。
- 参与者经 `event_participants` 关联（role 用自然语义标签：`主行`（主要行动者）、`受邀`、`亡`、`受`、`媒` 等），地点经 `event_places`。
- 事件因果用 `event_relation: causes / precedes / related`（cast 同 history 三值）。

---

## ⑤、themes（主题 / 意象）— 本 profile 新增

- 抽取本 chunk 中**有文本依据**的反复母题/象征。红楼梦常见：`梦幻`（梦/幻/太虚）、`真假`（甄/贾、假语村言）、`盛衰`（荣枯/聚散）、`情`、`宿命`（劫数/前缘）、`补天`（顽石/无材）等。
- theme 字段：`name`（如「梦幻」「真假」）、`description`（一句，可空）、`occurrences`（数组，关联本 chunk 中体现该主题的实体）：
  ```yaml
  themes:
    - name: 真假
      description: 甄(真)士隐与贾(假)雨村命名寓真假相生
      occurrences:
        - { entity_kind: person, entity_id: p1 }   # 甄士隐
        - { entity_kind: person, entity_id: p2 }   # 贾雨村
        - { entity_kind: chapter, entity_id: "hlm:1" }
      citation: { chunk_id: "chk:hlm:1:0", paragraph: 1, quote: "故曰甄士隐云云", span: [0,0] }
      justifications: { name: "甄士隐" }
  ```
- `occurrences[].entity_kind` ∈ `person / event / group / place / chapter`；`entity_id` 用本 chunk 的 local id（`p1`/`e1`/…），或对 `chapter` 用文档 id `"hlm:<章号>"`。
- 仅抽**明显**主题；不要为每个 chunk 强凑。一个 chunk 0–2 个主题为宜。

---

## ⑥、citation / justification / id 机制（与 history 同）

- 每条记录必带 `citation`（`chunk_id` / `paragraph` / `quote` / `span:[0,0]`）与 `justifications`（各填充标量字段→quote 的子串）。
- `quote` 必须是 chunk.text 的**逐字**子串（NFC）；最短能佐证即可（5–30 字）；勿含 `……`、勿含包裹引号 `“”`、勿含句末标点。
- chunk-local id 每 chunk 重置：`p/e/pl/g/t` + 序号。同一实体跨 chunk 只记一次（取最早 chunk）。
- `span` 一律 `[0,0]`，由 `fill-spans` 计算。
- **不做跨 chunk 推理；不臆造引文/justification。**

---

## ⑦、cast 常见易错点

- **不要套历史词汇：** 没有「列国」「纪年」「君臣（除非确为官场）」。家族用 group，不要当 state。
- **关系方向：** 主仆用 `master`(主→仆)/`servant`(仆→主)，按 chunk 主语取向；亲属长→幼用 `parent`/`grandparent`。
- **神话框架人物**（女娲、一僧一道、空空道人、警幻）：照收为 person，`social_category: mythic`（或僧道 `clergy`）；其与顽石/通灵宝玉的关系可记，但不要把「石头/宝玉」与「贾宝玉」在同一 chunk 强行合并——跨 chunk 身份由 linker 处理。
- **甄/贾命名寓意**属 theme（真假），不是 relation。
