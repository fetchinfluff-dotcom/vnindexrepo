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
      <body>
        <Sidebar />
        <main className="lg:ml-64 min-h-screen p-4 lg:p-8 pt-16 lg:pt-8">
          {children}
        </main>
      </body>
    </html>
  )
}
