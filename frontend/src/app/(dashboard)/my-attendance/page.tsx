"use client";
import AttendancePage from "../attendance/page";
import { EmployeeViewContext } from "@/hooks/useEmployeeView";
export default function Page() {
  return <EmployeeViewContext.Provider value={{ employeeView: true, initialLeave: false }}><AttendancePage /></EmployeeViewContext.Provider>;
}
