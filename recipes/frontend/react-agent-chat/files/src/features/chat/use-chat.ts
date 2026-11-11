/**
 * Chat state machine over a `ChatApi`. The UI only renders what this hook returns.
 *
 * - The user message and an EMPTY assistant message are added up front (`tool_start` may arrive
 *   before any token); tokens are appended to it.
 * - Tools are steps with a status (running -> done). Steps still open when the turn ends -> error.
 * - One AbortController per send. Cancelling is not an error: the turn is marked `cancelled`.
 * - On failure the question goes back to the draft so the user can resend it.
 * - A stream that closes without `done` is a failure (the backend died mid-answer).
 * - `conversationId` is generated here, one per conversation; `newConversation()` starts another.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import type { ChatApi } from './chat-api'

export type StepStatus = 'running' | 'done' | 'error'
export type Step = { id: string; tool: string; status: StepStatus }
export type MessageStatus = 'streaming' | 'done' | 'error' | 'cancelled'

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  steps: Step[]
  status: MessageStatus
  /** Backend error id to quote to support (never the error detail). */
  errorId?: string
}

const newId = () => crypto.randomUUID()

export function useChat(chat: ChatApi) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [conversationId, setConversationId] = useState(newId)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  const patchAssistant = (id: string, patch: (m: ChatMessage) => ChatMessage) =>
    setMessages((all) => all.map((m) => (m.id === id ? patch(m) : m)))

  const send = useCallback(
    async (text: string = draft) => {
      const question = text.trim()
      if (!question || sending) return
      const assistantId = newId()
      const abort = new AbortController()
      controller.current = abort
      setDraft('')
      setSending(true)
      setMessages((all) => [
        ...all,
        { id: newId(), role: 'user', content: question, steps: [], status: 'done' },
        { id: assistantId, role: 'assistant', content: '', steps: [], status: 'streaming' },
      ])

      let finished = false
      try {
        for await (const event of chat.streamAnswer({ question, conversationId }, abort.signal)) {
          switch (event.type) {
            case 'token':
              patchAssistant(assistantId, (m) => ({ ...m, content: m.content + event.text }))
              break
            case 'tool_start':
              patchAssistant(assistantId, (m) => ({
                ...m,
                steps: [...m.steps, { id: newId(), tool: event.tool, status: 'running' }],
              }))
              break
            case 'tool_end':
              patchAssistant(assistantId, (m) => ({ ...m, steps: closeStep(m.steps, event.tool) }))
              break
            case 'error':
              throw new ChatStreamError(event.errorId)
            case 'done':
              finished = true
              patchAssistant(assistantId, (m) => ({
                ...m,
                content: m.content || event.answer,
                steps: failOpenSteps(m.steps),
                status: 'done',
              }))
              break
            case 'routing':
              break
          }
        }
        if (!finished) throw new ChatStreamError()
      } catch (error) {
        if (abort.signal.aborted) {
          patchAssistant(assistantId, (m) => ({ ...m, steps: failOpenSteps(m.steps), status: 'cancelled' }))
        } else {
          const errorId = error instanceof ChatStreamError ? error.errorId : undefined
          patchAssistant(assistantId, (m) => ({ ...m, steps: failOpenSteps(m.steps), status: 'error', errorId }))
          setDraft((current) => current || question)
        }
      } finally {
        if (controller.current === abort) controller.current = null
        setSending(false)
      }
    },
    [chat, conversationId, draft, sending],
  )

  const cancel = useCallback(() => controller.current?.abort(), [])

  const newConversation = useCallback(() => {
    controller.current?.abort()
    setMessages([])
    setDraft('')
    setConversationId(newId())
  }, [])

  return { messages, draft, setDraft, sending, conversationId, send, cancel, newConversation }
}

export class ChatStreamError extends Error {
  constructor(readonly errorId?: string) {
    super(errorId ? `Agent error ${errorId}` : 'The answer was interrupted')
    this.name = 'ChatStreamError'
  }
}

/** Close the oldest running step of that tool. */
export function closeStep(steps: Step[], tool: string): Step[] {
  const index = steps.findIndex((s) => s.tool === tool && s.status === 'running')
  if (index === -1) return steps
  return steps.map((s, i) => (i === index ? { ...s, status: 'done' } : s))
}

export function failOpenSteps(steps: Step[]): Step[] {
  return steps.map((s) => (s.status === 'running' ? { ...s, status: 'error' } : s))
}
