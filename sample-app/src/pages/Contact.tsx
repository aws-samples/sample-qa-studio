import { useState, useCallback } from 'react'
import Toast from '../components/Toast'

const subjects = ['General Inquiry', 'Sales', 'Support', 'Partnership']

interface FormData {
  name: string
  email: string
  subject: string
  message: string
  subscribe: boolean
}

interface FormErrors {
  name?: string
  email?: string
  subject?: string
  message?: string
}

const initialForm: FormData = { name: '', email: '', subject: '', message: '', subscribe: false }

function validate(form: FormData): FormErrors {
  const errors: FormErrors = {}
  if (form.name.trim().length < 2) errors.name = 'Name must be at least 2 characters'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errors.email = 'Please enter a valid email'
  if (!form.subject) errors.subject = 'Please select a subject'
  if (form.message.trim().length < 10) errors.message = 'Message must be at least 10 characters'
  return errors
}

export default function Contact() {
  const [form, setForm] = useState<FormData>(initialForm)
  const [errors, setErrors] = useState<FormErrors>({})
  const [submitted, setSubmitted] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value, type } = e.target
    const checked = (e.target as HTMLInputElement).checked
    setForm(prev => ({ ...prev, [name]: type === 'checkbox' ? checked : value }))
    if (errors[name as keyof FormErrors]) {
      setErrors(prev => ({ ...prev, [name]: undefined }))
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const errs = validate(form)
    setErrors(errs)
    setSubmitted(true)
    if (Object.keys(errs).length === 0) {
      setToast('Message sent successfully! We\'ll get back to you soon.')
      setForm(initialForm)
      setSubmitted(false)
    }
  }

  const dismissToast = useCallback(() => setToast(null), [])

  const hasErrors = submitted && Object.keys(validate(form)).length > 0

  return (
    <div className="py-16 px-4" data-testid="contact-page">
      <div className="mx-auto max-w-2xl">
        <h1 className="text-3xl font-bold mb-2">Contact Us</h1>
        <p className="text-gray-600 mb-8">Have a question? We'd love to hear from you.</p>

        <form onSubmit={handleSubmit} noValidate data-testid="contact-form">
          {/* Name */}
          <div className="mb-5">
            <label htmlFor="name" className="block text-sm font-medium mb-1">Full Name</label>
            <input
              id="name" name="name" value={form.name} onChange={handleChange}
              className={`w-full border rounded-lg px-4 py-2 ${errors.name ? 'border-red-500' : 'border-gray-300'}`}
              data-testid="input-name"
            />
            {errors.name && <p className="text-red-500 text-sm mt-1" data-testid="error-name">{errors.name}</p>}
          </div>

          {/* Email */}
          <div className="mb-5">
            <label htmlFor="email" className="block text-sm font-medium mb-1">Email</label>
            <input
              id="email" name="email" type="email" value={form.email} onChange={handleChange}
              className={`w-full border rounded-lg px-4 py-2 ${errors.email ? 'border-red-500' : 'border-gray-300'}`}
              data-testid="input-email"
            />
            {errors.email && <p className="text-red-500 text-sm mt-1" data-testid="error-email">{errors.email}</p>}
          </div>

          {/* Subject */}
          <div className="mb-5">
            <label htmlFor="subject" className="block text-sm font-medium mb-1">Subject</label>
            <select
              id="subject" name="subject" value={form.subject} onChange={handleChange}
              className={`w-full border rounded-lg px-4 py-2 ${errors.subject ? 'border-red-500' : 'border-gray-300'}`}
              data-testid="input-subject"
            >
              <option value="">Select a subject</option>
              {subjects.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            {errors.subject && <p className="text-red-500 text-sm mt-1" data-testid="error-subject">{errors.subject}</p>}
          </div>

          {/* Message */}
          <div className="mb-5">
            <label htmlFor="message" className="block text-sm font-medium mb-1">Message</label>
            <textarea
              id="message" name="message" rows={5} value={form.message} onChange={handleChange}
              className={`w-full border rounded-lg px-4 py-2 ${errors.message ? 'border-red-500' : 'border-gray-300'}`}
              data-testid="input-message"
            />
            {errors.message && <p className="text-red-500 text-sm mt-1" data-testid="error-message">{errors.message}</p>}
          </div>

          {/* Subscribe */}
          <div className="mb-6 flex items-center gap-2">
            <input id="subscribe" name="subscribe" type="checkbox" checked={form.subscribe} onChange={handleChange} data-testid="input-subscribe" />
            <label htmlFor="subscribe" className="text-sm text-gray-600">Subscribe to our newsletter</label>
          </div>

          <button
            type="submit"
            disabled={hasErrors}
            className="w-full bg-indigo-600 text-white py-3 rounded-lg font-semibold hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
            data-testid="submit-button"
          >
            Send Message
          </button>
        </form>
      </div>

      {toast && <Toast message={toast} onClose={dismissToast} />}
    </div>
  )
}
