export interface PricingTier {
  name: string
  monthlyPrice: number
  annualPrice: number
  description: string
  features: string[]
  highlighted: boolean
}

export const pricingTiers: PricingTier[] = [
  {
    name: 'Starter',
    monthlyPrice: 29,
    annualPrice: 290,
    description: 'Perfect for small teams getting started.',
    features: ['5 team members', '10 projects', '5 GB storage', 'Email support', 'Basic analytics'],
    highlighted: false,
  },
  {
    name: 'Professional',
    monthlyPrice: 79,
    annualPrice: 790,
    description: 'For growing teams that need more power.',
    features: ['25 team members', 'Unlimited projects', '100 GB storage', 'Priority support', 'Advanced analytics', 'Custom integrations', 'API access'],
    highlighted: true,
  },
  {
    name: 'Enterprise',
    monthlyPrice: 199,
    annualPrice: 1990,
    description: 'For organizations with advanced needs.',
    features: ['Unlimited team members', 'Unlimited projects', '1 TB storage', '24/7 dedicated support', 'Advanced analytics', 'Custom integrations', 'API access', 'SSO & SAML', 'Audit logs', 'SLA guarantee'],
    highlighted: false,
  },
]

export const featureMatrix = [
  { feature: 'Team Members', starter: '5', professional: '25', enterprise: 'Unlimited' },
  { feature: 'Projects', starter: '10', professional: 'Unlimited', enterprise: 'Unlimited' },
  { feature: 'Storage', starter: '5 GB', professional: '100 GB', enterprise: '1 TB' },
  { feature: 'API Access', starter: '✗', professional: '✓', enterprise: '✓' },
  { feature: 'Custom Integrations', starter: '✗', professional: '✓', enterprise: '✓' },
  { feature: 'SSO & SAML', starter: '✗', professional: '✗', enterprise: '✓' },
  { feature: 'Audit Logs', starter: '✗', professional: '✗', enterprise: '✓' },
  { feature: 'SLA Guarantee', starter: '✗', professional: '✗', enterprise: '✓' },
  { feature: 'Support', starter: 'Email', professional: 'Priority', enterprise: '24/7 Dedicated' },
]
