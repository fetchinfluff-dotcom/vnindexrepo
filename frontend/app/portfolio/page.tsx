'use client'
import { useEffect, useState } from 'react'
import { fetchAPI, postAPI, deleteAPI, fmt, fmtPct } from '@/lib/api'
import { Plus, Trash2, TrendingUp, TrendingDown } from 'lucide-react'

export default function PortfolioPage() {
  const [positions, setPositions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ ticker: '', entry_price: 0, quantity: 0, entry_date: new Date().toISOString().split('T')[0] })

  const load = async () => {
    setLoading(true)
    try {
      const res = await fetchAPI('/portfolio')
      setPositions(Array.isArray(res) ? res : [])
    } catch (e: any) { setErr(e.message) }
    setLoading(false)
  }
  useEffect(() => { load() }, [])

  const addPosition = async () => {
    await postAPI('/portfolio/positions', form)
    setShowForm(false)
    setForm({ ticker: '', entry_price: 0, quantity: 0, entry_date: new Date().toISOString().split('T')[0] })
    load()
  }

  const removePosition = async (id: string) => {
    await deleteAPI(`/portfolio/positions/${id}`)
    load()
  }

  const totalValue = positions.reduce((s, p) => s + (p.current_price || p.entry_price) * p.quantity, 0)
  const totalCost = positions.reduce((s, p) => s + p.entry_price * p.quantity, 0)
  const totalPnl = totalValue - totalCost

  if (err) return <div className="card text-sell">{err}</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Danh mục đầu tư</h1>
        <button onClick={() => setShowForm(true)} className="btn btn-primary flex items-center gap-2"><Plus size={16} /> Thêm vị thế</button>
      </div>

      {loading ? <LoadingSkeleton /> : <>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="card"><div className="text-xs text-muted-foreground">Tổng giá trị</div><div className="text-xl font-bold">{fmt(totalValue)}</div></div>
          <div className="card"><div className="text-xs text-muted-foreground">Tổng vốn</div><div className="text-xl font-bold">{fmt(totalCost)}</div></div>
          <div className="card"><div className="text-xs text-muted-foreground">PnL</div><div className={`text-xl font-bold ${totalPnl >= 0 ? 'text-buy' : 'text-sell'}`}>{fmtPct((totalValue/totalCost-1)*100)}</div></div>
          <div className="card"><div className="text-xs text-muted-foreground">Số vị thế</div><div className="text-xl font-bold">{positions.length}</div></div>
        </div>

        {showForm && (
          <div className="card">
            <h3 className="font-semibold mb-3">Thêm vị thế mới</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <input placeholder="Mã CK" value={form.ticker} onChange={e => setForm({...form, ticker: e.target.value.toUpperCase()})} className="input-field" />
              <input type="number" placeholder="Giá vào" value={form.entry_price} onChange={e => setForm({...form, entry_price: Number(e.target.value)})} className="input-field" />
              <input type="number" placeholder="Số lượng" value={form.quantity} onChange={e => setForm({...form, quantity: Number(e.target.value)})} className="input-field" />
              <input type="date" value={form.entry_date} onChange={e => setForm({...form, entry_date: e.target.value})} className="input-field" />
            </div>
            <div className="flex gap-2">
              <button onClick={addPosition} className="btn btn-primary">Lưu</button>
              <button onClick={() => setShowForm(false)} className="btn btn-secondary">Hủy</button>
            </div>
          </div>
        )}

        <div className="card">
          {positions.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted-foreground border-b border-border">
                    <th className="text-left py-2">Mã</th>
                    <th className="text-right py-2">Giá vào</th>
                    <th className="text-right py-2">Giá hiện tại</th>
                    <th className="text-right py-2">SL</th>
                    <th className="text-right py-2">Số lượng</th>
                    <th className="text-right py-2">Giá trị</th>
                    <th className="text-right py-2">PnL</th>
                    <th className="text-center py-2">Ngày</th>
                    <th className="text-center py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p: any) => {
                    const curPrice = p.current_price || p.entry_price
                    const pnl = (curPrice - p.entry_price) * p.quantity
                    const pnlPct = (curPrice / p.entry_price - 1) * 100
                    return (
                      <tr key={p.id} className="border-b border-border/50 hover:bg-secondary/30">
                        <td className="py-2 font-medium">{p.ticker}</td>
                        <td className="py-2 text-right">{fmt(p.entry_price)}</td>
                        <td className="py-2 text-right">{fmt(curPrice)}</td>
                        <td className="py-2 text-right text-sell">{p.stop_loss ? fmt(p.stop_loss) : '-'}</td>
                        <td className="py-2 text-right">{p.quantity}</td>
                        <td className="py-2 text-right">{fmt(curPrice * p.quantity)}</td>
                        <td className={`py-2 text-right ${pnl >= 0 ? 'text-buy' : 'text-sell'}`}>{fmtPct(pnlPct)}</td>
                        <td className="py-2 text-center text-xs text-muted-foreground">{p.entry_date}</td>
                        <td className="py-2 text-center">
                          <button onClick={() => removePosition(p.id)} className="text-sell hover:brightness-125"><Trash2 size={16} /></button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : <p className="text-muted-foreground">Chưa có vị thế nào. Thêm vị thế đầu tiên!</p>}
        </div>
      </>}
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="grid grid-cols-4 gap-4">{[...Array(4)].map((_,i) => <div key={i} className="card h-20" />)}</div>
      <div className="card h-64" />
    </div>
  )
}
