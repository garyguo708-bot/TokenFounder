import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TokenFounder — AI Agent 创业孵化器",
  description: "用 Design Thinking 孵化你的 AI Agent 创业想法",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <body>{children}</body>
    </html>
  );
}
