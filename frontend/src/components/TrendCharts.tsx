"use client";
import { useState } from "react";

export interface TrendDataset {
  name: string;
  color: string;
  values: number[];
}

function niceMax(vals: number[]): number {
  const m = Math.max(1, ...vals);
  // 取一个好看的刻度上限
  const step = Math.pow(10, Math.floor(Math.log10(m)));
  const candidates = [1, 2, 5, 10].map(n => n * step);
  for (const c of candidates) {
    if (m <= c) return c;
  }
  return m;
}

export function LineChart({ labels, datasets, valuePrefix = "" }: {
  labels: string[];
  datasets: TrendDataset[];
  valuePrefix?: string;
}) {
  const W = 620, H = 220, padL = 46, padR = 14, padT = 14, padB = 30;
  const [hover, setHover] = useState<number | null>(null);

  const maxVal = niceMax(datasets.flatMap(d => d.values));
  const x = (i: number) => padL + (labels.length <= 1 ? 0 : (i * (W - padL - padR)) / (labels.length - 1));
  const y = (v: number) => padT + (H - padT - padB) * (1 - v / maxVal);
  const path = (values: number[]) => values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    let idx = 0, best = Infinity;
    labels.forEach((_, i) => {
      const d = Math.abs(x(i) - px);
      if (d < best) { best = d; idx = i; }
    });
    setHover(idx);
  }

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {/* 网格线 */}
        {[0, 0.5, 1].map(f => (
          <line key={f} x1={padL} x2={W - padR} y1={y(maxVal * f)} y2={y(maxVal * f)} stroke="#e5e7eb" strokeWidth={1} />
        ))}
        {/* 折线 */}
        {datasets.map(d => (
          <path key={d.name} d={path(d.values)} fill="none" stroke={d.color} strokeWidth={2} />
        ))}
        {/* 数据点 */}
        {labels.map((_, i) => (
          <g key={i}>
            {datasets.map(d => (
              <circle key={d.name} cx={x(i)} cy={y(d.values[i])} r={hover === i ? 4 : 2.2} fill={d.color} />
            ))}
          </g>
        ))}
        {/* 悬停竖线 */}
        {hover !== null && (
          <line x1={x(hover)} x2={x(hover)} y1={padT} y2={H - padB} stroke="#94a3b8" strokeWidth={1} strokeDasharray="3 3" />
        )}
        {/* x 轴标签 */}
        {labels.map((l, i) => {
          const step = Math.ceil(labels.length / 12);
          if (i % step !== 0 && i !== labels.length - 1) return null;
          return (
            <text key={i} x={x(i)} y={H - 8} textAnchor="middle" fontSize={9} fill="#9ca3af">
              {l.length > 5 ? l.slice(5) : l}
            </text>
          );
        })}
        {/* y 轴标签 */}
        {[0, 0.5, 1].map(f => (
          <text key={f} x={padL - 6} y={y(maxVal * f) + 3} textAnchor="end" fontSize={9} fill="#9ca3af">
            {valuePrefix}{Math.round(maxVal * f).toLocaleString()}
          </text>
        ))}
      </svg>

      {/* 图例 */}
      <div className="flex gap-4 mt-1 text-xs text-gray-500">
        {datasets.map(d => (
          <span key={d.name} className="flex items-center gap-1">
            <span className="w-3 h-0.5 rounded" style={{ background: d.color }} />{d.name}
          </span>
        ))}
      </div>

      {/* 悬停提示 */}
      {hover !== null && (
        <div
          className="absolute top-1 bg-white border rounded-lg shadow-lg px-2.5 py-1.5 text-xs pointer-events-none"
          style={{ left: `${Math.min(70, Math.max(0, (x(hover) / W) * 100))}%`, transform: "translateX(-50%)" }}
        >
          <div className="font-medium text-gray-700 mb-0.5">{labels[hover]}</div>
          {datasets.map(d => (
            <div key={d.name} className="flex items-center gap-1 text-gray-600">
              <span className="w-2 h-2 rounded-full" style={{ background: d.color }} />
              {d.name}: {valuePrefix}{d.values[hover]?.toLocaleString() ?? 0}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function BarChart({ labels, datasets, valuePrefix = "" }: {
  labels: string[];
  datasets: TrendDataset[];
  valuePrefix?: string;
}) {
  const W = 620, H = 200, padL = 46, padR = 14, padT = 14, padB = 30;
  const [hover, setHover] = useState<number | null>(null);
  const maxVal = niceMax(datasets.flatMap(d => d.values));
  const bw = (W - padL - padR) / labels.length;
  const y = (v: number) => padT + (H - padT - padB) * (1 - v / maxVal);

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const idx = Math.min(labels.length - 1, Math.max(0, Math.floor((px - padL) / bw)));
    setHover(idx);
  }

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {[0, 0.5, 1].map(f => (
          <line key={f} x1={padL} x2={W - padR} y1={y(maxVal * f)} y2={y(maxVal * f)} stroke="#e5e7eb" strokeWidth={1} />
        ))}
        {labels.map((l, i) => {
          const v = datasets[0]?.values[i] ?? 0;
          return (
            <rect
              key={i}
              x={padL + i * bw + bw * 0.2}
              y={y(v)}
              width={bw * 0.6}
              height={Math.max(0, H - padT - padB - y(v))}
              rx={3}
              fill={datasets[0]?.color ?? "#3b82f6"}
              opacity={hover === i ? 1 : 0.85}
            />
          );
        })}
        {hover !== null && (
          <line x1={padL + hover * bw + bw / 2} x2={padL + hover * bw + bw / 2} y1={padT} y2={H - padB} stroke="#94a3b8" strokeWidth={1} strokeDasharray="3 3" />
        )}
        {labels.map((l, i) => {
          const step = Math.ceil(labels.length / 8);
          if (i % step !== 0 && i !== labels.length - 1) return null;
          return (
            <text key={i} x={padL + i * bw + bw / 2} y={H - 8} textAnchor="middle" fontSize={9} fill="#9ca3af">
              {l.length > 5 ? l.slice(5) : l}
            </text>
          );
        })}
        {[0, 0.5, 1].map(f => (
          <text key={f} x={padL - 6} y={y(maxVal * f) + 3} textAnchor="end" fontSize={9} fill="#9ca3af">
            {valuePrefix}{Math.round(maxVal * f)}
          </text>
        ))}
      </svg>

      {hover !== null && (
        <div
          className="absolute top-1 bg-white border rounded-lg shadow-lg px-2.5 py-1.5 text-xs pointer-events-none"
          style={{ left: `${Math.min(80, Math.max(10, ((padL + hover * bw + bw / 2) / W) * 100))}%`, transform: "translateX(-50%)" }}
        >
          <div className="font-medium text-gray-700">{labels[hover]}</div>
          {datasets.map(d => (
            <div key={d.name} className="text-gray-600">{d.name}: {valuePrefix}{d.values[hover] ?? 0}</div>
          ))}
        </div>
      )}
    </div>
  );
}
