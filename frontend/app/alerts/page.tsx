'use client'
import { useEffect, useState } from 'react'
import { fetchAPI, putAPI, postAPI } from '@/lib/api'
import { Bell, Send, Save } from 'lucide-react'

export default function AlertsPage() {
  const [config, setConfig] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetchAPI('/alerts/config')
      .then(d => { setConfig(d); setLoading(false) })
      .catch(e => { setErr(e.message); setLoading(false) })
  }, [])

  const save = async () => {
    setSaving(true)
    await putAPI('/alerts/config', config)
    setSaving(false)
  }
  const testAlert = async () => {
    await postAPI('/alerts/test', {})
    alert('Test alert sent!')
  }

  if (err) return <div className="card text-sell">{err}</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Cảnh báo</h1>
      <p className="text-muted-foreground text-sm">Cấu hình kênh nhận thông báo tín hiệu giao dịch</p>

      {loading ? (
        <div className="animate-pulse space-y-4">
          <div className="card h-32" />
          <div className="card h-32" />
          <div className="card h-48" />
        </div>
      ) : config ? (
        <>
          <div className="card">
            <h2 className="text-lg font-semibold mb-4">Telegram</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Bot Token</label>
                <input value={config.telegram_token || ''} onChange={e => setConfig({...config, telegram_token: e.target.value})}
                  className="input-field w-full" placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Chat ID</label>
                <input value={config.telegram_chat_id || ''} onChange={e => setConfig({...config, telegram_chat_id: e.target.value})}
                  className="input-field w-full" placeholder="-1001234567890" />
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="text-lg font-semibold mb-4">Email</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">SMTP Host</label>
                <input value={config.email_host || ''} onChange={e => setConfig({...config, email_host: e.target.value})}
                  className="input-field w-full" placeholder="smtp.gmail.com" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Email</label>
                <input value={config.email_user || ''} onChange={e => setConfig({...config, email_user: e.target.value})}
                  className="input-field w-full" placeholder="you@gmail.com" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Password / App Password</label>
                <input type="password" value={config.email_pass || ''} onChange={e => setConfig({...config, email_pass: e.target.value})}
                  className="input-field w-full" placeholder="****" />
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="text-lg font-semibold mb-4">Loại cảnh báo</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {[
                {k:'alert_daily_signal',l:'Tín hiệu ngày'},
                {k:'alert_position_open',l:'Mở vị thế'},
                {k:'alert_position_close',l:'Đóng vị thế'},
                {k:'alert_stop_loss',l:'Stop Loss'},
                {k:'alert_drawdown_warning',l:'Drawdown > 10%'},
                {k:'alert_drawdown_stop',l:'Drawdown > 15%'},
              ].map(item => (
                <label key={item.k} className="flex items-center gap-2 p-3 rounded-lg bg-secondary/30 cursor-pointer">
                  <input type="checkbox" checked={(config as any)[item.k] ?? true}
                    onChange={e => setConfig({...config, [item.k]: e.target.checked})}
                    className="rounded accent-primary" />
                  <span className="text-sm">{item.l}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="flex gap-3">
            <button onClick={save} disabled={saving} className="btn btn-primary flex items-center gap-2">
              <Save size={16} /> {saving ? 'Đang lưu...' : 'Lưu cấu hình'}
            </button>
            <button onClick={testAlert} className="btn btn-secondary flex items-center gap-2">
              <Send size={16} /> Gửi test alert
            </button>
          </div>
        </>
      ) : null}
    </div>
  )
}
