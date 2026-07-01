import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { blogPosts } from '../data/blogPosts'

export default function Blog() {
  const [search, setSearch] = useState('')
  const [activeTag, setActiveTag] = useState<string | null>(null)

  const allTags = useMemo(() => [...new Set(blogPosts.flatMap(p => p.tags))].sort(), [])

  const filtered = useMemo(() => {
    return blogPosts.filter(p => {
      const matchesSearch = !search ||
        p.title.toLowerCase().includes(search.toLowerCase()) ||
        p.excerpt.toLowerCase().includes(search.toLowerCase())
      const matchesTag = !activeTag || p.tags.includes(activeTag)
      return matchesSearch && matchesTag
    })
  }, [search, activeTag])

  return (
    <div className="py-16 px-4" data-testid="blog-page">
      <div className="mx-auto max-w-6xl">
        <h1 className="text-3xl font-bold mb-2">Blog</h1>
        <p className="text-gray-600 mb-8">Insights, guides, and updates from the AnyCompany team.</p>

        {/* Search */}
        <input
          type="text"
          placeholder="Search posts..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full md:w-96 border border-gray-300 rounded-lg px-4 py-2 mb-6"
          data-testid="blog-search"
        />

        {/* Tags */}
        <div className="flex flex-wrap gap-2 mb-8" data-testid="blog-tags">
          <button
            onClick={() => setActiveTag(null)}
            className={`px-3 py-1 rounded-full text-sm ${!activeTag ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
          >
            All
          </button>
          {allTags.map(tag => (
            <button
              key={tag}
              onClick={() => setActiveTag(activeTag === tag ? null : tag)}
              className={`px-3 py-1 rounded-full text-sm ${activeTag === tag ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
            >
              {tag}
            </button>
          ))}
        </div>

        {/* Posts */}
        {filtered.length === 0 ? (
          <p className="text-gray-500" data-testid="no-results">No posts found matching your criteria.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filtered.map(post => (
              <Link
                key={post.id}
                to={`/blog/${post.id}`}
                className="bg-white border rounded-lg p-6 hover:shadow-md transition-shadow"
                data-testid={`blog-card-${post.id}`}
              >
                <div className="flex flex-wrap gap-2 mb-3">
                  {post.tags.map(t => (
                    <span key={t} className="bg-indigo-50 text-indigo-600 text-xs px-2 py-0.5 rounded">{t}</span>
                  ))}
                </div>
                <h2 className="font-semibold text-lg mb-2">{post.title}</h2>
                <p className="text-gray-600 text-sm mb-4">{post.excerpt}</p>
                <div className="flex justify-between text-xs text-gray-400">
                  <span>{post.author}</span>
                  <span>{post.readTime}</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
