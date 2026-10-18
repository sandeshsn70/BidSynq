import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'BidSynq | Procurement workspace', description: 'Intelligent B2B procurement and bidding workspace' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
