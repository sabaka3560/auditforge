# Semantic renames where the ideal config name differs from the actual column header.
# Derived from Oracle Fusion INV export naming conventions and sample output analysis.
# Extend this dict when a new client export uses a different column name.
MANUAL_ALIASES: dict[str, str] = {
    "AllowItemSubstitutionsFlag": "AllowItemSubstitutions",
    "BusinessUnitId": "BusinessUnitName",
    "MasterOrganizationId": "MasterOrgCode",
    "ProfitCenterBuId": "ProfitCenterBuName",
    "SupplierId": "SupplierName",
    "SupplierSiteId": "SupplierSiteName",
}
