import { useEffect, useRef } from 'react'

import type { ChatMessage, Step } from '../use-chat'
import { Markdown } from './Markdown'

const STEP_LABEL: Record<Step['status'], string> = { running: '…', done: '✓', error: '✕' }

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  const bottom = useRef<HTMLDivElement>(null)

  // Follow the answer while it streams. (jsdom has no scrollIntoView, hence the ?.)
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: 'end' })
  }, [messages])

  return (
    <ol className="chat-messages" aria-live="polite">
      {messages.map((message) => (
        <li key={message.id} className={`chat-message chat-message--${message.role}`} data-status={message.status}>
          {message.steps.length > 0 && (
            <ul className="chat-steps" aria-label="Herramientas">
              {message.steps.map((step) => (
                <li key={step.id} data-status={step.status}>
                  {STEP_LABEL[step.status]} {step.tool}
                </li>
              ))}
            </ul>
          )}
          {message.role === 'assistant' ? <Markdown text={message.content} /> : <p>{message.content}</p>}
          {message.status === 'streaming' && !message.content && <p className="muted">Pensando…</p>}
          {message.status === 'cancelled' && <p className="muted">Respuesta cancelada.</p>}
          {message.status === 'error' && (
            <p role="alert" className="chat-error">
              No se ha podido responder.{message.errorId && ` Referencia: ${message.errorId}`}
            </p>
          )}
        </li>
      ))}
      <div ref={bottom} />
    </ol>
  )
}
