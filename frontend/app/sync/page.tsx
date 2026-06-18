'use client'
import { useEffect, useState } from 'react'
import { fetchAPI } from '@/lib/api'
import { RefreshCw, CheckCircle, AlertCircle } from 'lucide-react'

export default function SyncPage() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [lastDate, setLastDate] = useState('2026-06-17')
  useEffect(() => {
    fetch('/api/v1/dashboard').then(r => r.json()).then(d => {
      if (d.last_data_date) setLastDate(d.last_data_date)
    }).catch(() => {})
  }, [])

  const sync = async () => {
    setLoading(true)
    setResult(null)
    try {
      const res = await fetchAPI('/sync', 0)
      setResult({ ok: true, msg: res.message || 'Đã kích hoạt đồng bộ' })
    } catch (e: any) {
      setResult({ ok: false, msg: e.message })
    }
    setLoading(false)
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Đồng bộ dữ liệu</h1>

      <div className="card max-w-lg">
        <p className="text-sm text-muted-foreground mb-4">
          Nhấn nút bên dưới để kích hoạt đồng bộ dữ liệu mới nhất từ VCI/DNSE.
          Quá trình này chạy trên GitHub Actions và mất khoảng 1-3 phút.
        </p>
        <button onClick={sync} disabled={loading} className="btn btn-primary flex items-center gap-2">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Đang đồng bộ...' : 'Đồng bộ dữ liệu'}
        </button>
        {result && (
          <div className={`mt-4 flex items-center gap-2 text-sm ${result.ok ? 'text-buy' : 'text-sell'}`}>
            {result.ok ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
            {result.msg}
          </div>
        )}
      </div>

      <div className="card max-w-lg">
        <h3 className="font-semibold mb-2">Lịch sử đồng bộ</h3>
        <p className="text-xs text-muted-foreground">
          Lần cuối: {lastDate} 15:30 (GitHub Actions).<br />
          Dữ liệu hiện tại: 122 cổ phiếu VN100, ~173k bar OHLCV.
        </p>
      </div>
    </div>
  )
}
