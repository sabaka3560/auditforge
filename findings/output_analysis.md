# Sample Output File Analysis — Inventory_ITAC_Master_Output.xlsx

> Agent findings from reverse-engineering the expected output structure.

## Sheet Overview

| Sheet | Rows (excl. header) | Purpose |
|---|---|---|
| Controls in place | 441 | BU-config pairs where actual = ideal |
| Control gaps | 4,059 | BU-config pairs where actual ≠ ideal (or null) |
| Controls additional data | 3,900 | Capture-only configs — no comparison, just extract |
| Header Mapping and Exc | 43 | How each ideal config was matched to an actual column |
| Audit Summary | 14 | Aggregate counts and metadata |

## Data Sheet Schema (all 3 main sheets)

All three data sheets use the same 4-column structure:

| Column | Contents |
|---|---|
| A — BU Name | Organization name from Column A of actual file |
| B — Configuration Name | Ideal config name (not the actual header) |
| C — Actual Configuration Value | Raw value from the actual file |
| D — Comment | "Controls in place" / "Controls gaps" / "Actual config captured" |

## Header Mapping Log — Key Findings

28 of 33 ideal configs matched. 5 unmatched:
- `LastUpdateDate` — best score 0.6429 (below threshold)
- `LastUpdateLogin` — best score 0.4828
- `LastUpdatedBy` — best score 0.5185
- `SourceOrganizationId` — best score 0.7222
- `SourceSubinventory` — best score 0.7000

**Known manual aliases used in sample output:**

| Ideal Config Name | Actual Column Header | Match Type |
|---|---|---|
| AllowItemSubstitutionsFlag | AllowItemSubstitutions | Manual Alias |
| BusinessUnitId | BusinessUnitName | Manual Alias |
| MasterOrganizationId | MasterOrgCode | Manual Alias |
| ProfitCenterBuId | ProfitCenterBuName | Manual Alias |
| SupplierId | SupplierName | Manual Alias |
| SupplierSiteId | SupplierSiteName | Manual Alias |
| OrganizationId | OrganizationCode | Fuzzy (score 0.8667) |
| FaBookTypeCode | FABookTypeCode | Normalized (case) |

## Audit Summary Data Points

From the sample output Audit Summary sheet:

| Metric | Value |
|---|---|
| Total BU rows | 300 |
| Total ideal configs | 33 |
| Matched | 28 |
| Unmatched | 5 |
| Compared (non-capture) | 15 |
| Capture-only | 13 |
| Controls in place | 441 |
| Control gaps | 4,059 |
| Additional data | 3,900 |
| Fuzzy threshold used | 0.85 |

## Insight: ~90% Gap Rate

300 BUs × 15 compared configs = 4,500 possible cells.
441 passing + 4,059 failing = 4,500. Most gap rows have `None` as actual value — the config simply wasn't populated in the source, not necessarily misconfigured.
