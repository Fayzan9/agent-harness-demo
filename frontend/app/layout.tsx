import type { Metadata } from "next";
import { JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

const ui = Plus_Jakarta_Sans({ variable: "--font-ui", subsets: ["latin"] });
const code = JetBrains_Mono({ variable: "--font-code", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Agent harness playground",
  description: "See how an agent harness works, live",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${ui.variable} ${code.variable} h-full`}>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
