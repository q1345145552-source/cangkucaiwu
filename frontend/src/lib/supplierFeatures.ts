// UI entry switch only. APIs, models, quotation handlers and historical records remain intact.
export const SUPPLIER_LOGISTICS_ENABLED = false;
const logisticsActions = new Set([
  'suppliers.download_logistics_template', 'suppliers.import_logistics',
  'suppliers.import_logistics_for_supplier', 'suppliers.compare_logistics',
  'suppliers.list_logistics_prices', 'suppliers.add_logistics_price', 'suppliers.delete_logistics_price',
]);
export function supplierActionEntryVisible(action: string): boolean {
  return SUPPLIER_LOGISTICS_ENABLED || !logisticsActions.has(action);
}
export function supplierCategoryChoiceVisible(entity: string, id: unknown): boolean {
  return SUPPLIER_LOGISTICS_ENABLED || entity !== 'SupplierCategory' || String(id) === '1';
}
