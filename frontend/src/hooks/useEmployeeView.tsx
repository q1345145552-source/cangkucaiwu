"use client";
import { createContext, useContext } from "react";

// Personal routes reuse the labor pages without changing the supervisor's account role.
export const EmployeeViewContext = createContext({ employeeView: false, initialLeave: false });
export const useEmployeeView = () => useContext(EmployeeViewContext);
