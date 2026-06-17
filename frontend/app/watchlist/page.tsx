'use client'
import { useEffect, useState } from 'react'
import { fetchAPI, postAPI, deleteAPI, fmt } from '@/lib/api'
import { Plus, Trash2 } from 'lucide-react'

export default function WatchlistPage() {
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [newTicker, setNewTicker] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const res = await fetchAPI('/watchlist')
      setItems(Array.isArray(res) ? res : [])
    } catch (e: any) { setErr(e.message) }
    setLoading(false)
  }
  useEffect(() => { load() }, [])

  const add = async () => {
    if (!newTicker) return
    await postAPI('/watchlist', { ticker: newTicker.toUpperCase() })
    setNewTicker('')
    load()
  }

  const remove = async (ticker: string) => {
    await deleteAPI(`/watchlist/${ticker}`)
    load()
  }

  if (err) return <div className="card text-sell">{err}</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Danh sách theo dõi</h1>
        <span className="text-sm text-muted-foreground">{items.length} mã</span>
      </div>

      <div className="card flex gap-2">
        <input value={newTicker} onChange={e => setNewTicker(e.target.value.toUpperCase())}
          placeholder="Nhập mã chứng khoán..." className="input-field flex-1"
          onKeyDown={e => e.key === 'Enter' && add()} />
        <button onClick={add} className="btn btn-primary"><Plus size={16} /></button>
      </div>

      <div className="card">
        {loading ? (
          <div className="animate-pulse space-y-3">
            {[...Array(5)].map((_,i) => <div key={i} className="h-10 rounded-lg bg-secondary/30" />)}
          </div>
        ) : items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted-foreground border-b border-border">
                  <th className="text-left py-2">Mã</th>
                  <th className="text-right py-2">Giá</th>
                  <th className="text-right py-2">O/H/L</th>
                  <th className="text-right py-2">KL</th>
                  <th className="text-center py-2">Ghi chú</th>
                  <th className="text-center py-2"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((item: any) => (
                  <tr key={item.id} className="border-b border-border/50 hover:bg-secondary/30">
                    <td className="py-2 font-medium">{item.ticker}</td>
                    <td className="py-2 text-right">{item.current_price ? fmt(item.current_price) : '-'}</td>
                    <td className="py-2 text-right text-xs text-muted-foreground">
                      {item.open ? `${fmt(item.open)}/${fmt(item.high)}/${fmt(item.low)}` : '-'}
                    </td>
                    <td className="py-2 text-right">{item.volume ? fmt(item.volume) : '-'}</td>
                    <td className="py-2 text-center text-xs text-muted-foreground">{item.note || '-'}</td>
                    <td className="py-2 text-center">
                      <button onClick={() => remove(item.ticker)} className="text-sell hover:brightness-125"><Trash2 size={16} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="text-muted-foreground">Chưa có mã nào trong danh sách theo dõi</p>}
      </div>
    </div>
  )
}
