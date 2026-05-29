# Actual Config File Analysis — INV_ORGANIZATION_PARAMETER.xlsx

> Agent findings from structural analysis of the client-uploaded file.

## File Overview

| Property | Value |
|---|---|
| Sheets | `INV_ORGANIZATION_PARAMETER`, `summary` |
| Data rows | 300 (1 header + 300 org records) |
| Total columns | 126 |

## Key Structure

- **Column A (`Name`)** = Organization name — the BU identifier used as the primary key for comparison
- **Column B (`Status`)** = A (Active) / I (Inactive) / B
- Remaining 124 columns = configuration parameter names and their values per org

## Column Groups

| Domain | Columns | Type |
|---|---|---|
| Lot control flags | `AllocateSerialFlag`, `AllowNegOnhandCcTxns`, `CopyLotAttributeFlag`… | Y/N string or null |
| Numeric lookup codes | `LotNumberGeneration`, `NegativeInvReceiptCode`, `SerialNumberGeneration`… | int |
| Business unit/legal entity | `BusinessUnitName`, `LegalEntityIdentifier`, `ProfitCenterBuName` | string |
| Oracle DFF attributes | `Attribute1`–`Attribute15`, `AttributeDate1`–`AttributeDate5`… | Almost entirely null |
| Manufacturing flags | `MfgPlantFlag`, `ContractMfgFlag`, `EamEnabledFlag` | Y/N or null |
| Effective dates | `LocationEffectiveStartDate`, `LocationEffectiveEndDate`, `EffectiveStartDate` | datetime / string |

## Oracle Date Sentinels

- `4712-12-31` = Oracle "end of time" (open-ended) — treat as no end date
- `0001/01/01` = stored as string, Oracle epoch start

## Data Quality Notes

- Most DFF attribute columns (`Attribute1`–`Attribute15`) are entirely null across all 300 orgs
- `PartyName` has a leading space (` Apple Inc`) — raw data quality issue, strip on ingest
- `ContractMfgFlag` + `SupplierName` + `SupplierSiteName` only populated for contract manufacturer orgs
- `IntegratedSystemCode` discriminates WMS orgs (`ORA_RCS_IS_WMS`) from standard inventory (`ORA_RCS_IS_INVMGMT`)

## BU Name Column

The first column (`Name`) is the BU identifier. Values are plain strings like `Atlanta`, `Shanghai`, `Tokyo`, `Berlin`. This is the join key for all output sheets.
