const vnd = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 })

export function formatVND(value) {
  if (value === null || value === undefined || value === '') return '—'
  return vnd.format(Number(value))
}