export interface BlogPost {
  id: string
  title: string
  excerpt: string
  content: string
  author: string
  date: string
  tags: string[]
  readTime: string
}

export const blogPosts: BlogPost[] = [
  {
    id: 'getting-started-cloud',
    title: 'Getting Started with Cloud Migration',
    excerpt: 'Learn the fundamentals of moving your infrastructure to the cloud with our step-by-step guide.',
    content: `<p>Cloud migration is one of the most impactful decisions a company can make. Whether you're moving from on-premises servers or switching cloud providers, the process requires careful planning.</p>
<h3>Step 1: Assess Your Current Infrastructure</h3>
<p>Before migrating, take inventory of all your applications, databases, and services. Identify dependencies and potential bottlenecks.</p>
<h3>Step 2: Choose Your Migration Strategy</h3>
<p>The six common strategies are: Rehost, Replatform, Repurchase, Refactor, Retire, and Retain. Each has its own trade-offs.</p>
<h3>Step 3: Plan Your Timeline</h3>
<p>A phased approach reduces risk. Start with non-critical workloads and gradually move mission-critical systems.</p>`,
    author: 'Sarah Chen',
    date: '2026-03-15',
    tags: ['Cloud', 'Migration', 'Infrastructure'],
    readTime: '5 min read',
  },
  {
    id: 'automated-testing-best-practices',
    title: 'Automated Testing Best Practices for 2026',
    excerpt: 'Discover the latest strategies for building reliable automated test suites that scale with your team.',
    content: `<p>Automated testing has evolved significantly. Modern tools powered by AI can now understand natural language instructions and interact with web applications like a human would.</p>
<h3>Write Tests That Read Like User Stories</h3>
<p>The best tests describe what a user does, not how the code works. Natural language test steps make tests accessible to everyone on the team.</p>
<h3>Prioritize Critical User Journeys</h3>
<p>Focus your automation efforts on the paths that matter most: login flows, checkout processes, and core feature interactions.</p>
<h3>Run Tests in CI/CD</h3>
<p>Integrate your test suite into your deployment pipeline. Run smoke tests on every commit and full regression suites nightly.</p>`,
    author: 'Marcus Johnson',
    date: '2026-03-08',
    tags: ['Testing', 'Automation', 'DevOps'],
    readTime: '4 min read',
  },
  {
    id: 'scaling-microservices',
    title: 'Scaling Microservices: Lessons from Production',
    excerpt: 'Real-world lessons learned from scaling a microservices architecture to handle millions of requests.',
    content: `<p>After running microservices in production for three years, we've learned some hard lessons about what works and what doesn't.</p>
<h3>Service Discovery Matters</h3>
<p>As your service count grows, manual configuration becomes impossible. Invest in proper service discovery early.</p>
<h3>Distributed Tracing is Non-Negotiable</h3>
<p>When a request touches 12 services, you need to trace it end-to-end. Tools like OpenTelemetry make this manageable.</p>
<h3>Circuit Breakers Save Lives</h3>
<p>One failing service shouldn't cascade across your entire system. Implement circuit breakers at every service boundary.</p>`,
    author: 'Priya Patel',
    date: '2026-02-20',
    tags: ['Microservices', 'Architecture', 'DevOps'],
    readTime: '6 min read',
  },
  {
    id: 'security-zero-trust',
    title: 'Implementing Zero Trust Security',
    excerpt: 'A practical guide to adopting zero trust principles in your organization without disrupting workflows.',
    content: `<p>Zero trust isn't a product you buy — it's a philosophy. "Never trust, always verify" applies to every request, regardless of where it originates.</p>
<h3>Start with Identity</h3>
<p>Strong authentication is the foundation. Multi-factor authentication should be mandatory for all users and services.</p>
<h3>Micro-Segmentation</h3>
<p>Don't rely on network perimeters. Segment your network so that compromising one service doesn't expose everything.</p>
<h3>Continuous Monitoring</h3>
<p>Log everything, analyze patterns, and alert on anomalies. Zero trust requires ongoing vigilance, not a one-time setup.</p>`,
    author: 'Alex Rivera',
    date: '2026-02-10',
    tags: ['Security', 'Infrastructure', 'Cloud'],
    readTime: '5 min read',
  },
  {
    id: 'developer-productivity',
    title: 'Boosting Developer Productivity with AI Tools',
    excerpt: 'How AI-powered development tools are changing the way teams write, test, and deploy code.',
    content: `<p>AI coding assistants have moved from novelty to necessity. Teams using AI tools report significant productivity gains across the development lifecycle.</p>
<h3>Code Generation</h3>
<p>AI can generate boilerplate, suggest implementations, and even write tests. The key is reviewing and understanding what it produces.</p>
<h3>Automated Code Review</h3>
<p>AI-powered review tools catch bugs, security issues, and style violations before human reviewers see the code.</p>
<h3>Intelligent Testing</h3>
<p>AI can generate test cases from user stories, identify untested code paths, and prioritize which tests to run.</p>`,
    author: 'Sarah Chen',
    date: '2026-01-25',
    tags: ['AI', 'Productivity', 'Testing'],
    readTime: '4 min read',
  },
  {
    id: 'serverless-patterns',
    title: 'Serverless Architecture Patterns That Work',
    excerpt: 'Battle-tested serverless patterns for building scalable, cost-effective applications.',
    content: `<p>Serverless computing removes the burden of infrastructure management, but it introduces its own set of patterns and anti-patterns.</p>
<h3>Event-Driven Processing</h3>
<p>Decouple your services with event queues. This pattern handles variable load gracefully and improves resilience.</p>
<h3>API Gateway + Lambda</h3>
<p>The classic serverless API pattern. Keep functions focused on a single responsibility for easier debugging and scaling.</p>
<h3>Fan-Out / Fan-In</h3>
<p>For parallel processing workloads, fan out to multiple functions and aggregate results. Great for data processing pipelines.</p>`,
    author: 'Marcus Johnson',
    date: '2026-01-12',
    tags: ['Serverless', 'Architecture', 'Cloud'],
    readTime: '5 min read',
  },
  {
    id: 'observability-guide',
    title: 'The Complete Guide to Observability',
    excerpt: 'Metrics, logs, and traces — how to build a comprehensive observability strategy for modern applications.',
    content: `<p>Observability goes beyond monitoring. It's about understanding the internal state of your system from its external outputs.</p>
<h3>The Three Pillars</h3>
<p>Metrics tell you what's happening, logs tell you why, and traces show you the journey. You need all three.</p>
<h3>Structured Logging</h3>
<p>Unstructured log messages are nearly useless at scale. Use structured formats (JSON) with consistent field names.</p>
<h3>SLOs and Error Budgets</h3>
<p>Define service level objectives and track error budgets. This gives you a data-driven framework for reliability decisions.</p>`,
    author: 'Priya Patel',
    date: '2025-12-28',
    tags: ['Observability', 'DevOps', 'Infrastructure'],
    readTime: '7 min read',
  },
]
