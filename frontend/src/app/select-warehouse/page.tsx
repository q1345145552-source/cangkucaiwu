import WarehouseCards from "@/components/WarehouseCards";

export default function SelectWarehousePage() {
  return (
    <section>
      <h1 className="mb-6 text-2xl font-bold text-gray-900">请选择要进入的仓库</h1>
      <WarehouseCards />
    </section>
  );
}
