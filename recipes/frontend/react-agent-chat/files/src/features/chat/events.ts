/**
 * Events of the agent stream: the frontend side of the contract in the `langgraph-graph` recipe
 * (agentic/graph/events.py). Change both at once.
 */

export type ChatEvent =
  | { type: 'token'; text: string }
  | { type: 'tool_start'; tool: string }
  | { type: 'tool_end'; tool: string }
  | { type: 'routing'; data: Record<string, unknown> }
  | { type: 'error'; errorId?: string }
  | { type: 'done'; answer: string }

type Raw = Record<string, unknown>

const str = (value: unknown): value is string => typeof value === 'string'

/** Raw SSE `event` + parsed `data` -> typed event. Unknown events or bad payloads -> null (ignored). */
export function toChatEvent(event: string, data: unknown): ChatEvent | null {
  if (typeof data !== 'object' || data === null) return null
  const raw = data as Raw
  switch (event) {
    case 'token':
      return str(raw.text) ? { type: 'token', text: raw.text } : null
    case 'tool_start':
    case 'tool_end':
      return str(raw.tool) ? { type: event, tool: raw.tool } : null
    case 'routing':
      return { type: 'routing', data: raw }
    case 'error':
      return { type: 'error', errorId: str(raw.error_id) ? raw.error_id : undefined }
    case 'done':
      return { type: 'done', answer: str(raw.answer) ? raw.answer : '' }
    default:
      return null
  }
}
