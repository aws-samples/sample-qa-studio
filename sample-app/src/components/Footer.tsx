import { Link } from 'react-router-dom'

export default function Footer() {
  return (
    <footer className="bg-gray-900 text-gray-400 mt-auto">
      <div className="mx-auto max-w-6xl px-4 py-12 grid grid-cols-1 md:grid-cols-3 gap-8">
        <div>
          <h3 className="text-white font-bold text-lg mb-2">AnyCompany</h3>
          <p className="text-sm">Building the future of cloud services, one solution at a time.</p>
        </div>
        <div>
          <h4 className="text-white font-semibold mb-2">Quick Links</h4>
          <ul className="space-y-1 text-sm">
            <li><Link to="/" className="hover:text-white">Home</Link></li>
            <li><Link to="/blog" className="hover:text-white">Blog</Link></li>
            <li><Link to="/pricing" className="hover:text-white">Pricing</Link></li>
            <li><Link to="/contact" className="hover:text-white">Contact</Link></li>
          </ul>
        </div>
        <div>
          <h4 className="text-white font-semibold mb-2">Connect</h4>
          <div className="flex gap-4">
            {['Twitter', 'LinkedIn', 'GitHub'].map(name => (
              <a key={name} href="#" className="hover:text-white text-sm">{name}</a>
            ))}
          </div>
        </div>
      </div>
      <div className="border-t border-gray-800 text-center py-4 text-xs">
        © {new Date().getFullYear()} AnyCompany. All rights reserved. This is a demo application.
      </div>
    </footer>
  )
}
