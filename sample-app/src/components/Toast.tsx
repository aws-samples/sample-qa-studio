import { useEffect } from 'react'

interface ToastProps {
  message: string
  type?: 'success' | 'error'
  onClose: () => void
}

export default function Toast({ message, type = 'success', onClose }: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(onClose, 4000)
    return () => clearTimeout(timer)
  }, [onClose])

  const bg = type === 'success' ? 'bg-green-500' : 'bg-red-500'

  return (
    <div className={`fixed top-20 right-4 z-50 ${bg} text-white px-6 py-3 rounded-lg shadow-lg flex items-center gap-3`} data-testid="toast">
      <span>{message}</span>
      <button onClick={onClose} className="hover:opacity-80" aria-label="Dismiss">✕</button>
    </div>
  )
}
