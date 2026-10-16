"use client";
import OvertimePage from "../overtime/page";
import { EmployeeViewContext } from "@/hooks/useEmployeeView";
export default function Page() {
  return <EmployeeViewContext.Provider value={{ employeeView: true, initialLeave: false }}><OvertimePage /></EmployeeViewContext.Provider>;
}
