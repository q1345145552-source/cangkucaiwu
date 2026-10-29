import WarehouseCards from "@/components/WarehouseCards";
import { WarehouseOverviewEntry } from "@/components/WarehouseOverview";

export default function SelectWarehousePage() {
  return (
    <section>
      <div className="relative">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">请选择要进入的仓库</h1>
        <WarehouseOverviewEntry />
      </div>
      <WarehouseCards />
    </section>
  );
}
