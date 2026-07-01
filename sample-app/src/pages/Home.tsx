import { Link } from 'react-router-dom'

const features = [
  { title: 'Cloud Native', desc: 'Built for the cloud from day one with auto-scaling and high availability.' },
  { title: 'Secure by Default', desc: 'Enterprise-grade security with encryption at rest and in transit.' },
  { title: 'Developer Friendly', desc: 'Comprehensive APIs and SDKs for seamless integration.' },
  { title: 'Global Scale', desc: 'Deploy to any region with single-click global distribution.' },
]

const testimonials = [
  { quote: 'AnyCompany transformed how we manage our infrastructure. Deployment time dropped by 80%.', author: 'Jamie L.', role: 'CTO, TechStart Inc.' },
  { quote: 'The best developer experience we\'ve ever had. Our team productivity doubled in three months.', author: 'Morgan K.', role: 'VP Engineering, DataFlow' },
  { quote: 'Reliable, scalable, and the support team is incredible. Couldn\'t ask for more.', author: 'Taylor R.', role: 'Lead Architect, CloudOps' },
]

export default function Home() {
  return (
    <div data-testid="home-page">
      {/* Hero */}
      <section className="bg-gradient-to-br from-indigo-600 to-purple-700 text-white py-24 px-4">
        <div className="mx-auto max-w-4xl text-center">
          <h1 className="text-4xl md:text-5xl font-bold mb-6">Build faster. Scale smarter.</h1>
          <p className="text-lg md:text-xl text-indigo-100 mb-8">
            AnyCompany provides the cloud platform your team needs to ship with confidence.
          </p>
          <div className="flex gap-4 justify-center flex-wrap">
            <Link to="/pricing" className="bg-white text-indigo-600 px-6 py-3 rounded-lg font-semibold hover:bg-indigo-50" data-testid="cta-pricing">
              View Pricing
            </Link>
            <Link to="/contact" className="border-2 border-white text-white px-6 py-3 rounded-lg font-semibold hover:bg-white/10" data-testid="cta-contact">
              Contact Us
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-20 px-4" data-testid="features-section">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-3xl font-bold text-center mb-12">Why teams choose AnyCompany</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
            {features.map(f => (
              <div key={f.title} className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow">
                <h3 className="font-semibold text-lg mb-2">{f.title}</h3>
                <p className="text-gray-600 text-sm">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="bg-gray-50 py-20 px-4" data-testid="testimonials-section">
        <div className="mx-auto max-w-6xl">
          <h2 className="text-3xl font-bold text-center mb-12">What our customers say</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {testimonials.map(t => (
              <div key={t.author} className="bg-white p-6 rounded-lg shadow-sm border">
                <p className="text-gray-600 italic mb-4">"{t.quote}"</p>
                <p className="font-semibold">{t.author}</p>
                <p className="text-sm text-gray-500">{t.role}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}
