import "./globals.css";
import ClientShell from "./client-shell";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <body className="min-h-screen bg-gray-50">
        <ClientShell>{children}</ClientShell>
      </body>
    </html>
  );
}
