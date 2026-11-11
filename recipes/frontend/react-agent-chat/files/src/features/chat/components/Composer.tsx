import type { FormEvent, KeyboardEvent } from 'react'

type Props = {
  draft: string
  onDraft: (text: string) => void
  onSend: () => void
  onCancel: () => void
  sending: boolean
}

/** Enter sends, Shift+Enter is a new line. While streaming, the button cancels. */
export function Composer({ draft, onDraft, onSend, onCancel, sending }: Props) {
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (sending) onCancel()
    else onSend()
  }
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (!sending) onSend()
    }
  }

  return (
    <form className="chat-composer" onSubmit={submit}>
      <textarea
        aria-label="Mensaje"
        rows={2}
        value={draft}
        onChange={(event) => onDraft(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Escribe tu pregunta…"
      />
      <button className="button" type="submit" disabled={!sending && !draft.trim()}>
        {sending ? 'Detener' : 'Enviar'}
      </button>
    </form>
  )
}
