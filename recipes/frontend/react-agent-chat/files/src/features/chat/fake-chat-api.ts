/** Fake agent: emits the same events as the real stream (routing, a tool, tokens, done). No backend needed. */

import type { ChatApi } from './chat-api'
import type { ChatEvent } from './events'

export type FakeChatOptions = {
  /** Delay between events in ms. 0 in tests. */
  stepMs?: number
  reply?: (question: string) => string
  /** Tool to show as a step, or null for none. */
  tool?: string | null
}

export function createFakeChatApi(options: FakeChatOptions = {}): ChatApi {
  const { stepMs = 40, reply = (q) => `Has preguntado: **${q}**`, tool = 'search_documents' } = options

  const sleep = (signal?: AbortSignal) =>
    new Promise<void>((resolve, reject) => {
      if (signal?.aborted) return reject(new DOMException('aborted', 'AbortError'))
      const timer = setTimeout(resolve, stepMs)
      signal?.addEventListener('abort', () => {
        clearTimeout(timer)
        reject(new DOMException('aborted', 'AbortError'))
      })
    })

  return {
    async *streamAnswer({ question }, signal): AsyncGenerator<ChatEvent> {
      const answer = reply(question)
      yield { type: 'routing', data: { category: 'technical' } }
      if (tool) {
        await sleep(signal)
        yield { type: 'tool_start', tool }
        await sleep(signal)
        yield { type: 'tool_end', tool }
      }
      for (const word of answer.split(/(?<= )/)) {
        await sleep(signal)
        yield { type: 'token', text: word }
      }
      yield { type: 'done', answer }
    },
  }
}
