import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Renders an assistant reply.
 *
 * Models emit markdown constantly, so showing it raw would mean reading `##`
 * and backticks all session. Streaming text is frequently mid syntax (an
 * unclosed code fence, half a bold marker), which react-markdown handles
 * without throwing, so it can be rendered while it is still arriving.
 */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Links from a model go to who knows where; open them safely.
          a: ({ node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
