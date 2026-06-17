'use client'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Rectangle
} from 'recharts'

interface Candle {
  date: string
  open: number
  high: number
  low: number
  close: number
}

interface Props {
  data: Candle[]
  height?: number
}

function CandlestickShape(props: any) {
  const { x, y, width, height, payload } = props
  if (!payload) return null
  const { open, close, high, low } = payload
  const isUp = close >= open
  const color = isUp ? '#22c55e' : '#ef4444'
  const scaleMin = props.domain?.[0] ?? Math.min(low, open, close)
  const scaleMax = props.domain?.[1] ?? Math.max(high, open, close)
  const range = scaleMax - scaleMin || 1
  const yScale = (v: number) => y + height - ((v - scaleMin) / range) * height

  const bodyTop = yScale(Math.max(open, close))
  const bodyBottom = yScale(Math.min(open, close))
  const bodyH = Math.max(bodyBottom - bodyTop, 1)
  const wickTop = yScale(high)
  const wickBottom = yScale(low)
  const barW = Math.max(width * 0.6, 2)
  const cx = x + width / 2

  return (
    <g>
      <line x1={cx} y1={wickTop} x2={cx} y2={wickBottom} stroke={color} strokeWidth={1.5} />
      <rect x={cx - barW / 2} y={bodyTop} width={barW} height={bodyH} fill={color} rx={1} />
    </g>
  )
}

function CandleTooltip({ active, payload }: any) {
  if (!active || !payload?.[0]) return null
  const d = payload[0].payload
  return (
    <div className="card text-xs space-y-1" style={{ padding: '8px 12px' }}>
      <p className="font-medium">{d.date}</p>
      <p>O: {d.open.toFixed(1)}</p>
      <p>H: {d.high.toFixed(1)}</p>
      <p>L: {d.low.toFixed(1)}</p>
      <p>C: {d.close.toFixed(1)}</p>
    </div>
  )
}

export default function CandlestickChart({ data, height = 300 }: Props) {
  if (!data?.length) return <div className="text-muted-foreground text-sm">No data</div>

  const low = Math.min(...data.map(d => d.low))
  const high = Math.max(...data.map(d => d.high))
  const padding = (high - low) * 0.05 || 1

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
        <XAxis
          dataKey="date"
          tick={{ fill: '#94a3b8', fontSize: 10 }}
          tickFormatter={(v: string) => v.slice(5)}
          axisLine={{ stroke: '#334155' }}
          tickLine={false}
          interval="preserveStartEnd"
          minTickGap={40}
        />
        <YAxis
          domain={[low - padding, high + padding]}
          tick={{ fill: '#94a3b8', fontSize: 10 }}
          axisLine={{ stroke: '#334155' }}
          tickLine={false}
          tickFormatter={(v: number) => v.toFixed(0)}
          width={50}
        />
        <Tooltip content={<CandleTooltip />} />
        <Bar dataKey="close" shape={<CandlestickShape domain={[low - padding, high + padding]} />} isAnimationActive={false}>
          {data.map((_, i) => (
            <rect key={i} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
