'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, Signal, Filter, Briefcase, Eye, Bell, History, Menu, X } from 'lucide-react'
import { useState } from 'react'

const NAV_ITEMS = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/signals', label: 'Tín hiệu', icon: Signal },
  { href: '/screener', label: 'Bộ lọc', icon: Filter },
  { href: '/portfolio', label: 'Danh mục', icon: Briefcase },
  { href: '/watchlist', label: 'Theo dõi', icon: Eye },
  { href: '/alerts', label: 'Cảnh báo', icon: Bell },
  { href: '/trades', label: 'Lịch sử', icon: History },
]

export default function Sidebar() {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)
  return (
    <>
      <button onClick={() => setOpen(!open)} className="lg:hidden fixed top-4 left-4 z-50 p-2 rounded-lg bg-card border border-border">
        {open ? <X size={20} /> : <Menu size={20} />}
      </button>
      <aside className={`fixed inset-y-0 left-0 z-40 w-64 bg-card border-r border-border transform transition-transform duration-200 ${open ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0`}>
        <div className="p-6 border-b border-border">
          <h1 className="text-lg font-bold text-primary">VN100</h1>
          <p className="text-xs text-muted-foreground mt-1">Trading Dashboard</p>
        </div>
        <nav className="p-4 space-y-1">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href)
            return (
              <Link key={href} href={href} onClick={() => setOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all ${active ? 'bg-primary/20 text-primary font-medium' : 'text-muted-foreground hover:text-foreground hover:bg-secondary'}`}>
                <Icon size={18} />
                {label}
              </Link>
            )
          })}
        </nav>
        <div className="absolute bottom-4 left-4 right-4 p-4 rounded-lg bg-secondary/50">
          <p className="text-xs text-muted-foreground">Dữ liệu từ vnstock VCI</p>
          <p className="text-xs text-muted-foreground mt-1">Cập nhật: 15:30 VN</p>
        </div>
      </aside>
    </>
  )
}
