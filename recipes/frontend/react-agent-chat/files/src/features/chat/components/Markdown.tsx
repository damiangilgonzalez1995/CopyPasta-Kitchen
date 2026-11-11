/**
 * Agent answers are Markdown. react-markdown builds React elements (no innerHTML): raw HTML in the
 * answer is shown as text, so a prompt-injected <script> cannot run. Links open in a new tab.
 */

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{ a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer noopener" /> }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}
