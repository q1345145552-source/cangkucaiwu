export default function CashAdvanceLink({ id, number }: { id?: number | null; number?: string | null }) {
  if (!Number.isSafeInteger(id) || !id || id < 1 || !number) return null;
  return <a href={`/cash-advances/${id}`} onClick={event => event.stopPropagation()}
    aria-label={`查看垫款单 ${number}`} className="inline-flex items-center min-h-[32px] px-2 py-1 rounded bg-amber-50 text-amber-700 text-xs whitespace-nowrap hover:underline">
    垫款单 {number}
  </a>;
}
