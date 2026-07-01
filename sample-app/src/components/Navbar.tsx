import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

const links = [
  { to: '/', label: 'Home' },
  { to: '/blog', label: 'Blog' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/contact', label: 'Contact' },
]

export default function Navbar() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()

  const isActive = (to: string) =>
    to === '/' ? pathname === '/' : pathname.startsWith(to)

  return (
    <nav className="bg-white shadow" data-testid="navbar">
      <div className="mx-auto max-w-6xl px-4 flex items-center justify-between h-16">
        <Link to="/" className="text-xl font-bold text-indigo-600">AnyCompany</Link>

        {/* Desktop */}
        <div className="hidden md:flex gap-6">
          {links.map(l => (
            <Link
              key={l.to}
              to={l.to}
              className={`text-sm font-medium ${isActive(l.to) ? 'text-indigo-600 border-b-2 border-indigo-600' : 'text-gray-600 hover:text-indigo-600'}`}
            >
              {l.label}
            </Link>
          ))}
        </div>

        {/* Hamburger */}
        <button
          className="md:hidden p-2"
          onClick={() => setOpen(!open)}
          aria-label="Toggle menu"
          data-testid="hamburger"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {open
              ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />}
          </svg>
        </button>
      </div>

      {/* Mobile menu */}
      {open && (
        <div className="md:hidden border-t" data-testid="mobile-menu">
          {links.map(l => (
            <Link
              key={l.to}
              to={l.to}
              onClick={() => setOpen(false)}
              className={`block px-4 py-3 text-sm ${isActive(l.to) ? 'text-indigo-600 bg-indigo-50' : 'text-gray-600'}`}
            >
              {l.label}
            </Link>
          ))}
        </div>
      )}
    </nav>
  )
}
