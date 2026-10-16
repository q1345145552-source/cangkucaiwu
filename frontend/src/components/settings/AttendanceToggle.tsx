"use client";
import { api } from "@/lib/api";

export interface AttendanceEmployee {
  id: number;
  name: string;
  employee_no: string;
  user_id: number | null;
  salary_template_id?: number | null;
  deduction_template_id?: number | null;
}

// 只按账号绑定或该账号的历史关联编号识别档案，不按姓名匹配。
export async function findAttendanceEmployee(account: any): Promise<AttendanceEmployee | null> {
  const employees: AttendanceEmployee[] = [];
  for (let page = 1; ; page++) {
    const result = await api.get<{ data: AttendanceEmployee[]; total: number }>(`/employees?page=${page}&page_size=200&include_deleted=true`);
    employees.push(...result.data);
    const found = account.attendance_employee_id != null
      ? result.data.find(item => item.id === account.attendance_employee_id)
      : result.data.find(item => item.user_id === account.id);
    if (found) return found;
    if (!result.data.length || employees.length >= result.total) break;
  }
  if (account.attendance_employee_id != null) throw new Error("关联档案未找到，请检查员工档案");
  let employeeId: number | null = null;
  const records: any[] = [];
  for (let page = 1; ; page++) {
    const history = await api.get<{ data: any[]; total: number }>(`/history?module=user&record_id=${account.id}&page=${page}&page_size=100`);
    records.push(...history.data);
    if (!history.data.length || page * 100 >= history.total) break;
  }
  const previous = records.sort((a, b) => b.id - a.id).find(item => item.after_data?.attendance_employee_id != null || item.before_data?.attendance_employee_id != null);
  if (previous) employeeId = previous.after_data?.attendance_employee_id ?? previous.before_data?.attendance_employee_id;
  if (employeeId == null) return null;
  const employee = employees.find(item => item.id === employeeId);
  if (!employee) throw new Error("原关联档案未找到，请检查员工档案");
  return employee;
}

export default function AttendanceToggle({ id, enabled, onChange, account, employee, loading = false, error = "", onRetry, notice = "" }: {
  id: string;
  enabled: boolean;
  onChange: (value: boolean) => void;
  account?: any;
  employee?: AttendanceEmployee | null;
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
  notice?: string;
}) {
  const linked = account?.attendance_enabled && employee?.user_id === account?.id;
  return (
    <div className="rounded-lg border bg-gray-50 p-3 space-y-2">
      <label htmlFor={id} className="flex items-center gap-3 min-h-[44px] cursor-pointer text-sm font-medium">
        <input id={id} type="checkbox" role="switch" checked={enabled} onChange={e => onChange(e.target.checked)}
          aria-describedby={`${id}-hint`} className="rounded w-5 h-5 shrink-0" />
        纳入考勤
      </label>
      <div id={`${id}-hint`} className="text-xs text-gray-600 space-y-1" aria-live="polite">
        {employee && <p>{linked ? "已关联员工档案" : enabled ? "将绑定到已有的那条档案" : "已有员工档案"}：{employee.name}（工号：{employee.employee_no || account?.username || "—"}）</p>}
        {!enabled && <p>关掉后不纳入考勤，工资不按考勤算，档案和历史记录会保留</p>}
        {loading && <p role="status">正在读取员工档案...</p>}
        {enabled && !employee && !loading && !error && <p>保存后会自动建档案</p>}
        {error && <p className="text-red-600" role="alert">{error}；保存时由后端确认绑定结果。{onRetry && <button type="button" onClick={onRetry} className="underline ml-1">重新读取</button>}</p>}
        {enabled && notice && <p className="text-amber-700">{notice}</p>}
      </div>
    </div>
  );
}
