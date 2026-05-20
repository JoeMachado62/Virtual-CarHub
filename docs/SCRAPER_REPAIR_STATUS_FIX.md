# Scraper Fix: Repaired Damage Items Being Sent as Active Damage

**For:** Claude Code agent maintaining the OVE scraper
**Priority:** High — this bug caused a consumer report to overstate vehicle damage,
diminishing perceived value in the client's eyes.

---

## The Problem

When scraping Manheim Insight condition reports, the scraper is sending
**repaired damage items** as if they were **active damage**. The VPS
consumer-facing condition report then shows damage that no longer exists.

### Real-world example: VIN KM8R2DGE1PU586345 (listing 442858513)

The Manheim CR page body text clearly shows two sections:

```
Cosmetic Conventional Paint and Body Not Required-[1 Items]
IMAGE   DESCRIPTION     CONDITION       SEVERITY
        LF Door Dent/No Paint Dmg       PDR/1           ← ACTIVE (real damage)

        Repaired
IMAGE   DESCRIPTION     CONDITION       SEVERITY        REPAIR STATUS
        LF Bumper Cover Scratch Heavy   1/2" to 1"      Completed  ← REPAIRED
        RF Bumper Cover Scratch Heavy   2" to 3"        Completed  ← REPAIRED
```

But the scraper sent **all three items** in `damage_items[]` with
`section_label: "Cosmetic Conventional Paint and Body Not Required"` —
including the two bumper scratches that were under the **"Repaired"**
section on the actual page. The scraper mislabeled them.

Additionally, the `conditionEnrichment.damages` from the listing JSON
contributed **three more duplicate items** (same panels, same conditions),
bringing the total to 6 damage items when only 1 is real.

---

## What the VPS Received (actual stored data)

```json
[
  // From CR HTML scrape — section_label is WRONG for items 2-3
  {"panel": "LF Door", "condition": "Dent/No Paint Dmg", "section_label": "Cosmetic Conventional Paint and Body Not Required", "reported_severity": "PDR/1"},
  {"panel": "LF Bumper Cover", "condition": "Scratch Heavy", "section_label": "Cosmetic Conventional Paint and Body Not Required"},
  {"panel": "RF Bumper Cover", "condition": "Scratch Heavy", "section_label": "Cosmetic Conventional Paint and Body Not Required"},

  // From listing JSON conditionEnrichment.damages — duplicates
  {"panel": "LF Bumper Cover", "condition": "Scratch Heavy", "section_label": "Paint and Body Requires Conventional Repair", "raw": {"displayRepaired": false}},
  {"panel": "RF Bumper Cover", "condition": "Scratch Heavy", "section_label": "Paint and Body Requires Conventional Repair", "raw": {"displayRepaired": false}},
  {"panel": "LF Door", "condition": "Dent/No Paint Dmg", "section_label": "Cosmetic Conventional Paint and Body Not Required", "raw": {"displayRepaired": false}}
]
```

---

## What the VPS Has Done on Its Side

We have deployed a backend fix that adds **three layers of defense**:

1. **Body-text cross-referencing:** The VPS now parses the `body_text` for
   a "Repaired" section and excludes matching (panel, condition) pairs from
   the consumer report — even when `section_label` is wrong.

2. **`repair_status` field support:** The VPS now checks for an explicit
   `repair_status` field on each damage item. If the value is `"repaired"`
   or `"completed"`, the item is filtered out.

3. **Deduplication:** Same (panel, condition) from different sources only
   produces one issue entry, eliminating the CR-HTML + listing-JSON
   doubling.

These are **defensive fallbacks**. The right fix is at the source — the
scraper should either **not send repaired items at all**, or **tag them
with `repair_status: "repaired"`**.

---

## What Needs to Change in the Scraper

You know your own code far better than I do, so treat this as a problem
statement and directional guidance — **audit against the reality of your
codebase** before implementing. The actual parsing logic, selectors, and
data flow may differ from what I describe below.

### Issue 1: CR HTML parser is not detecting the "Repaired" section

The Manheim Insight CR page has a collapsible section titled **"Repaired"**
that lists damage items with a **"REPAIR STATUS"** column (value:
"Completed"). The scraper's CR HTML parser appears to be extracting items
from this section but assigning them the wrong `section_label` (it gives
them the label of the preceding section like "Cosmetic Conventional Paint
and Body Not Required" instead of "Repaired").

**Suggested fix direction:**
- When parsing the damage sections from the CR HTML, look for the section
  header that says "Repaired" (it's a distinct collapsible group, similar
  to "Paint and Body Requires Conventional Repair" and "Cosmetic
  Conventional Paint and Body Not Required").
- Items under that section should either:
  - **(Preferred)** Be excluded from `damage_items[]` entirely, OR
  - Be included but tagged with `repair_status: "repaired"` and
    `section_label: "Repaired"`

### Issue 2: Listing JSON `conditionEnrichment.damages` duplicates

The scraper is sending damage items from **both** the CR HTML page **and**
the `conditionEnrichment.damages` array from the listing JSON. This
creates duplicates. The listing JSON items have a `raw` object with fields
like `displayRepaired`, `displayItem`, `category`, and `gradeItem`.

**Observations from the stored data:**
- `raw.displayRepaired: false` on all items — even the ones that the CR
  HTML page shows as "Repaired / Completed". This field may not be
  reliable, or it may reflect a different concept than what appears on the
  CR page.
- `raw.displayItem: false` on all listing JSON items.
- The listing JSON `category` field (e.g., "Paint and Body Requires
  Conventional Repair") does not match the CR HTML section for the same
  item in some cases.

**Suggested fix direction:**
- Decide which is the authoritative source for damage items: the CR HTML
  page or the listing JSON. The CR HTML is the rendered inspection report
  and reflects the **current state** (including repairs). The listing JSON
  `conditionEnrichment` may reflect the **original inspection** before
  repairs were approved.
- If you include items from both sources, deduplicate by (panel, condition)
  before sending to the VPS.
- If you keep the listing JSON items, check whether `displayRepaired` or
  any other field reliably indicates repair completion and use that to set
  `repair_status`.

### Issue 3: Different CR types may handle repairs differently

The scraper deals with three CR formats:
- **Manheim Insight** (like this VIN) — has the "Repaired" dropdown section
- **Liquidmotors CR pages** — may have a different structure for repairs
- **Conventional Manheim / Manheim Express** — may be similar to Insight

Each format's parser needs to handle repair detection appropriately. The
normalized payload that gets sent to the VPS should use the same mechanism
regardless of source format.

---

## Updated Contract: `repair_status` Field

The VPS now supports an optional `repair_status` field on damage items
(see `docs/CONDITION_REPORT_CONTRACT.md` section 3.6):

```jsonc
{
  "panel": "LF Bumper Cover",
  "condition": "Scratch Heavy",
  "section_label": "Repaired",
  "repair_status": "repaired",   // null | "active" | "repaired"
  // ... other fields
}
```

- `null` or `"active"` → treated as current damage (shown to consumer)
- `"repaired"` → excluded from consumer report

If the scraper cannot confidently determine repair status, omit the field
(`null`) and the VPS will fall back to body-text cross-referencing.

---

## How to Verify

After making your fix, re-scrape VIN **KM8R2DGE1PU586345** (listing
442858513, Manheim Orlando) and POST to the VPS. The expected result:

- `damage_items` should contain **only 1 item**: LF Door, Dent/No Paint
  Dmg, PDR/1
- OR it should contain all 3 items but the bumper items tagged with
  `repair_status: "repaired"` and `section_label: "Repaired"`
- No duplicate items from both CR HTML and listing JSON for the same
  panel + condition
- `problem_highlights` should only mention the LF Door PDR/1

The VPS consumer report should then show:
- **Driver Front Door**: issue — PDR/1 dent
- **Front Bumper / Rear Bumper**: Normal — No Damage Reported
- **Further Disclosures / Other**: empty
- **Inspection Questionnaire**: only LF Door

---

## Summary

| What | Current (broken) | Expected (fixed) |
|---|---|---|
| Repaired items | Sent as active damage with wrong section_label | Excluded or tagged `repair_status: "repaired"` |
| CR HTML + listing JSON | Both sent, creating duplicates | One authoritative source, or deduped |
| Consumer sees | 3+ damage items, diminished value | 1 real damage item (LF Door PDR/1) |
