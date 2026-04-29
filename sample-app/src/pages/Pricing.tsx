import { useState } from 'react'
import { pricingTiers, featureMatrix } from '../data/pricing'
import Modal from '../components/Modal'

export default function Pricing() {
  const [annual, setAnnual] = useState(false)
  const [modal, setModal] = useState(false)

  return (
    <div className="py-16 px-4" data-testid="pricing-page">
      <div className="mx-auto max-w-6xl text-center">
        <h1 className="text-3xl font-bold mb-2">Simple, transparent pricing</h1>
        <p className="text-gray-600 mb-8">Choose the plan that fits your team. No hidden fees.</p>

        {/* Toggle */}
        <div className="flex items-center justify-center gap-3 mb-12" data-testid="pricing-toggle">
          <span className={annual ? 'text-gray-400' : 'font-semibold'}>Monthly</span>
          <button
            onClick={() => setAnnual(!annual)}
            className={`relative w-14 h-7 rounded-full transition-colors ${annual ? 'bg-indigo-600' : 'bg-gray-300'}`}
            aria-label="Toggle annual pricing"
            data-testid="toggle-button"
          >
            <span className={`absolute top-0.5 w-6 h-6 bg-white rounded-full shadow transition-transform ${annual ? 'translate-x-7' : 'translate-x-0.5'}`} />
          </button>
          <span className={annual ? 'font-semibold' : 'text-gray-400'}>
            Annual <span className="text-green-600 text-sm">(Save ~17%)</span>
          </span>
        </div>

        {/* Tier cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-16">
          {pricingTiers.map(tier => (
            <div
              key={tier.name}
              className={`rounded-lg p-8 text-left ${tier.highlighted ? 'border-2 border-indigo-600 shadow-lg relative' : 'border shadow-sm'}`}
              data-testid={`tier-${tier.name.toLowerCase()}`}
            >
              {tier.highlighted && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-indigo-600 text-white text-xs px-3 py-1 rounded-full" data-testid="popular-badge">
                  Most Popular
                </span>
              )}
              <h2 className="text-xl font-bold mb-1">{tier.name}</h2>
              <p className="text-gray-500 text-sm mb-4">{tier.description}</p>
              <div className="mb-6">
                <span className="text-4xl font-bold" data-testid={`price-${tier.name.toLowerCase()}`}>
                  ${annual ? tier.annualPrice : tier.monthlyPrice}
                </span>
                <span className="text-gray-500">/{annual ? 'yr' : 'mo'}</span>
              </div>
              <ul className="space-y-2 mb-8">
                {tier.features.map(f => (
                  <li key={f} className="flex items-center gap-2 text-sm text-gray-600">
                    <span className="text-green-500">✓</span> {f}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => setModal(true)}
                className={`w-full py-3 rounded-lg font-semibold ${tier.highlighted ? 'bg-indigo-600 text-white hover:bg-indigo-700' : 'border border-indigo-600 text-indigo-600 hover:bg-indigo-50'}`}
                data-testid={`cta-${tier.name.toLowerCase()}`}
              >
                Get Started
              </button>
            </div>
          ))}
        </div>

        {/* Feature comparison table */}
        <h2 className="text-2xl font-bold mb-6">Feature Comparison</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left border" data-testid="feature-table">
            <thead>
              <tr className="bg-gray-50">
                <th className="px-4 py-3 font-semibold">Feature</th>
                <th className="px-4 py-3 font-semibold text-center">Starter</th>
                <th className="px-4 py-3 font-semibold text-center">Professional</th>
                <th className="px-4 py-3 font-semibold text-center">Enterprise</th>
              </tr>
            </thead>
            <tbody>
              {featureMatrix.map(row => (
                <tr key={row.feature} className="border-t">
                  <td className="px-4 py-3 text-sm">{row.feature}</td>
                  <td className="px-4 py-3 text-sm text-center">{row.starter}</td>
                  <td className="px-4 py-3 text-sm text-center">{row.professional}</td>
                  <td className="px-4 py-3 text-sm text-center">{row.enterprise}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Modal open={modal} onClose={() => setModal(false)} title="Demo Application">
        <p className="text-gray-600 mb-4">
          This is a demo application for QA Studio. In a real application, this would start the sign-up process.
        </p>
        <button
          onClick={() => setModal(false)}
          className="w-full bg-indigo-600 text-white py-2 rounded-lg font-semibold hover:bg-indigo-700"
          data-testid="modal-close-button"
        >
          Got it
        </button>
      </Modal>
    </div>
  )
}
