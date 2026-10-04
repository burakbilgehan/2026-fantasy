import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { useMemo, type MouseEvent } from 'react'

// External links open in a new tab. In-app links (#player/<id>) stay as they are.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A' && /^https?:/.test(node.getAttribute('href') ?? '')) {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

/** Renders a knowledge page (GitHub style markdown with tables, <details> and <sub>). */
export function Markdown({ text, onOpenPlayer }: { text: string; onOpenPlayer?: (id: number) => void }) {
  const html = useMemo(
    () => DOMPurify.sanitize(marked.parse(text, { async: false, gfm: true }), { ADD_ATTR: ['target'] }),
    [text],
  )
  const onClick = (e: MouseEvent<HTMLDivElement>) => {
    const a = (e.target as HTMLElement).closest('a')
    const href = a?.getAttribute('href') ?? ''
    const m = /^#player\/(\d+)$/.exec(href)
    if (m) {
      e.preventDefault()
      onOpenPlayer?.(Number(m[1]))
    } else if (href === '#') {
      e.preventDefault()
    }
  }
  // Content is sanitized above; links are handled by the click handler.
  // eslint-disable-next-line react/no-danger
  return <div className="md" onClick={onClick} dangerouslySetInnerHTML={{ __html: html }} />
}
