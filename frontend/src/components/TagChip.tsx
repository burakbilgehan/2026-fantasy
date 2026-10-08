import type { PlayerTag } from '../api/client'

/** Hover text: why the player has the tag (detail, then each source note with its quote). */
function why(t: PlayerTag): string {
  const lines = [t.detail, t.until ? `Until ${t.until}` : null]
  for (const s of t.sources ?? []) {
    if (!s.text) continue
    lines.push(`${s.date ? `${s.date}, ` : ''}${s.video ?? 'source'}: ${s.text}${s.quote ? `\n  "${s.quote}"` : ''}`)
  }
  return lines.filter(Boolean).join('\n')
}

/** A profile tag (T-022). Hover shows the reason and sources; a click opens the first source video at its timestamp. */
export function TagChip({ t, className }: { t: PlayerTag; className?: string }) {
  const url = t.sources?.find((s) => s.url)?.url
  const cls = ['tag', t.channel, url && 'linked', className].filter(Boolean).join(' ')
  const label = <>{t.tag}{t.until ? ` (until ${t.until})` : ''}</>
  return url
    ? <a className={cls} href={url} target="_blank" rel="noreferrer" title={`${why(t)}\n\nClick: open the source video`}
      onClick={(e) => e.stopPropagation()}>{label}</a>
    : <span className={cls} title={why(t) || undefined}>{label}</span>
}
