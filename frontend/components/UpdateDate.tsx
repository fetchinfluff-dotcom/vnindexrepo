'use client'
import { useEffect, useState } from 'react'

export default function UpdateDate() {
  const [date, setDate] = useState<string | null>(null)
  const [err, setErr] = useState(false)
  useEffect(() => {
    fetch('/api/v1/dashboard')
      .then(r => r.json())
      .then(d => { if (d.last_data_date) setDate(d.last_data_date) })
      .catch(() => setErr(true))
  }, [])
  if (err) return null
  if (!date) return <span className="opacity-50">Đang tải...</span>
  return <span>Dữ liệu cập nhật: {date}</span>
}
