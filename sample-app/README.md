# AnyCompany Sample Application

A demo web application for the fictional "AnyCompany" — a SaaS/cloud services company. This app serves as a **test target** for QA Studio, providing realistic pages and interactive elements for automated testing with Nova Act.

## Quick Start

```bash
cd sample-app
npm install
npm run dev
```

The app runs at `http://localhost:5174`.

## Pages

| Page | Route | Description |
|------|-------|-------------|
| Home | `/` | Hero section, feature highlights, testimonials |
| Blog | `/blog` | Blog post list with search and tag filtering |
| Blog Post | `/blog/:id` | Full blog post with related posts |
| Pricing | `/pricing` | Three pricing tiers with monthly/annual toggle, feature comparison table |
| Contact | `/contact` | Contact form with client-side validation |

## Interactive Elements (Test Targets)

- **Navigation**: Top nav with active link highlighting, mobile hamburger menu
- **Contact form**: Required field validation, email format check, success toast on submit
- **Blog search**: Real-time filtering by title and excerpt
- **Blog tag filter**: Filter posts by tag category
- **Pricing toggle**: Switch between monthly and annual pricing
- **Modal**: Appears when clicking "Get Started" on pricing tiers
- **Toast notifications**: Auto-dismissing success messages

## Tech Stack

| Technology | Purpose |
|------------|---------|
| React 18 | UI framework |
| TypeScript | Type safety |
| Vite | Build tool and dev server |
| Tailwind CSS | Styling |
| React Router v6 | Client-side routing (browser router) |

## Deployment (AWS)

The sample app has its own CDK stack that deploys to S3 + CloudFront.

```bash
cd sample-app
npm install
npm run deploy
```

This builds the Vite app and deploys the `SampleApp` CloudFormation stack. The CloudFront URL is printed after deployment.

To tear down:

```bash
npm run destroy
```

### Infrastructure

- S3 bucket (private, encrypted, enforce SSL)
- CloudFront distribution with OAC
- CloudFront Function for SPA routing
- Access logging to separate S3 bucket

## Test Cases

Pre-built QA Studio test cases are in `testcases/sample-app/`:

| Test Case | File | What it tests |
|-----------|------|---------------|
| Validate Home Page | `validate_home_page.json` | All home page elements render |
| Home to Pricing | `home_to_pricing.json` | CTA navigation from home to pricing |
| Pricing Toggle | `pricing_toggle.json` | Monthly/annual toggle + modal |
| Contact Form Submit | `contact_form_submit.json` | Happy path form submission |
| Contact Form Validation | `contact_form_validation.json` | Validation error messages |
| Blog Search | `blog_search.json` | Search filtering |
| Blog Filter Tag | `blog_filter_tag.json` | Tag-based filtering |
| Blog Read Post | `blog_read_post.json` | Post detail + back navigation |
| Validate Navigation | `validate_navigation.json` | Nav links + active state |

Import these test cases into QA Studio and set the `starting_url` to your deployment URL (or `http://localhost:5174` for local testing).

## Project Structure

```
sample-app/
├── src/
│   ├── components/     # Navbar, Footer, Modal, Toast
│   ├── pages/          # Home, Contact, Blog, BlogPost, Pricing
│   ├── data/           # Hardcoded blog posts and pricing tiers
│   ├── App.tsx         # Router setup
│   ├── main.tsx        # Entry point
│   └── index.css       # Tailwind imports
├── package.json
├── vite.config.ts
└── README.md
```
