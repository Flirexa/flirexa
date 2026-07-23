// Chart helper — the designer's charts are hand-built inline <svg>, no library.
// Feed a number array; get { line, area } path `d` strings over a 300×120 box.
// (Verbatim from his data-contracts.md.)
export function linePath(values, w = 300, h = 120, pad = 8) {
  const vals = (values && values.length) ? values : [0, 0]
  const max = Math.max(1, ...vals)
  const min = Math.min(0, ...vals)
  const x = i => (i / (vals.length - 1 || 1)) * w
  const y = v => h - pad - ((v - min) / (max - min || 1)) * (h - 2 * pad)
  const line = vals.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  const area = `${line} L${w} ${h} L0 ${h} Z`
  return { line, area }
}

// Bar geometry for column charts (returns [{x,y,w,h}] over a box).
export function bars(values, w = 300, h = 120, pad = 8, gap = 0.35) {
  const vals = (values && values.length) ? values : [0]
  const max = Math.max(1, ...vals)
  const bw = w / vals.length
  const iw = bw * (1 - gap)
  return vals.map((v, i) => {
    const bh = (v / max) * (h - 2 * pad)
    return { x: i * bw + (bw - iw) / 2, y: h - pad - bh, w: iw, h: bh }
  })
}
