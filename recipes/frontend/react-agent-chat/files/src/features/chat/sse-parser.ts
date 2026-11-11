/**
 * Server-Sent Events over `fetch` (not EventSource: it only does GET and cannot send Authorization).
 *
 * - Chunks may cut a line or a JSON payload in half: the partial line stays in the buffer.
 * - CRLF and LF line endings (sse-starlette sends CRLF).
 * - `data:` with or without a space; several `data:` lines are joined with "\n" (SSE spec).
 * - Comments (`: ping`), `id:` and `retry:` are ignored. Bad JSON and unknown events are ignored.
 * - `error` and `done` are terminal: the reader is cancelled after them.
 */

import { toChatEvent, type ChatEvent } from './events'

export class SseParser {
  private buffer = ''
  private event = ''
  private data: string[] = []

  /** Feed a decoded chunk; returns the events it completed. */
  push(chunk: string): ChatEvent[] {
    this.buffer += chunk
    const lines = this.buffer.split(/\r\n|\n|\r/)
    this.buffer = lines.pop() ?? ''
    const events: ChatEvent[] = []
    for (const line of lines) {
      const event = this.line(line)
      if (event) events.push(event)
    }
    return events
  }

  /** End of stream: a last event without the trailing blank line still counts. */
  flush(): ChatEvent[] {
    const pending = this.buffer
    this.buffer = ''
    const events = pending ? this.push(`${pending}\n`) : []
    const last = this.dispatch()
    return last ? [...events, last] : events
  }

  private line(line: string): ChatEvent | null {
    if (line === '') return this.dispatch()
    if (line.startsWith(':')) return null
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') this.event = value
    else if (field === 'data') this.data.push(value)
    return null
  }

  private dispatch(): ChatEvent | null {
    const event = this.event || 'message'
    const data = this.data.join('\n')
    this.event = ''
    this.data = []
    if (!data) return null
    try {
      return toChatEvent(event, JSON.parse(data))
    } catch {
      return null
    }
  }
}

const isTerminal = (event: ChatEvent) => event.type === 'error' || event.type === 'done'

export async function* readSse(stream: ReadableStream<Uint8Array>): AsyncGenerator<ChatEvent> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  const parser = new SseParser()
  try {
    while (true) {
      const { value, done } = await reader.read()
      const events = done ? [...parser.push(decoder.decode()), ...parser.flush()] : parser.push(decoder.decode(value, { stream: true }))
      for (const event of events) {
        yield event
        if (isTerminal(event)) return
      }
      if (done) return
    }
  } finally {
    await reader.cancel().catch(() => undefined)
  }
}
