import { useParams, Link } from 'react-router-dom'
import { blogPosts } from '../data/blogPosts'

export default function BlogPost() {
  const { id } = useParams<{ id: string }>()
  const post = blogPosts.find(p => p.id === id)

  if (!post) {
    return (
      <div className="py-16 px-4 text-center">
        <h1 className="text-2xl font-bold mb-4">Post not found</h1>
        <Link to="/blog" className="text-indigo-600 hover:underline">← Back to Blog</Link>
      </div>
    )
  }

  const related = blogPosts
    .filter(p => p.id !== post.id && p.tags.some(t => post.tags.includes(t)))
    .slice(0, 3)

  return (
    <div className="py-16 px-4" data-testid="blogpost-page">
      <div className="mx-auto max-w-3xl">
        <Link to="/blog" className="text-indigo-600 hover:underline text-sm" data-testid="back-to-blog">← Back to Blog</Link>

        <div className="flex flex-wrap gap-2 mt-6 mb-4">
          {post.tags.map(t => (
            <span key={t} className="bg-indigo-50 text-indigo-600 text-xs px-2 py-0.5 rounded">{t}</span>
          ))}
        </div>

        <h1 className="text-3xl font-bold mb-2">{post.title}</h1>
        <div className="flex gap-4 text-sm text-gray-500 mb-8">
          <span>{post.author}</span>
          <span>{new Date(post.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}</span>
          <span>{post.readTime}</span>
        </div>

        <div
          className="prose max-w-none [&_h3]:text-xl [&_h3]:font-semibold [&_h3]:mt-6 [&_h3]:mb-3 [&_p]:text-gray-600 [&_p]:mb-4 [&_p]:leading-relaxed"
          dangerouslySetInnerHTML={{ __html: post.content }}
        />

        {/* Related posts */}
        {related.length > 0 && (
          <div className="mt-16 pt-8 border-t" data-testid="related-posts">
            <h2 className="text-xl font-bold mb-6">Related Posts</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {related.map(r => (
                <Link key={r.id} to={`/blog/${r.id}`} className="border rounded-lg p-4 hover:shadow-md transition-shadow">
                  <h3 className="font-semibold mb-1">{r.title}</h3>
                  <p className="text-sm text-gray-500">{r.readTime}</p>
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
