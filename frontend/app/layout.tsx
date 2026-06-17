import type { Metadata } from 'next'
import './globals.css'
import Sidebar from '@/components/Sidebar'

export const metadata: Metadata = {
  title: 'VN100 Trading Dashboard',
  description: 'Hệ thống giao dịch VN100 - tín hiệu, lọc cổ phiếu, quản lý danh mục',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className="flex flex-col min-h-screen">
        <Sidebar />
        <main className="lg:ml-64 flex-1 p-4 lg:p-8 pt-16 lg:pt-8">
          {children}
        </main>
        <footer className="lg:ml-64 border-t border-border/50 px-4 lg:px-8 py-2 text-xs text-muted-foreground flex justify-between">
          <span>Dữ liệu cập nhật: <span id="update-date">2026-06-17</span></span>
          <span>VN100 Trading Dashboard v1.0</span>
        </footer>
      </body>
    </html>
  )
}
