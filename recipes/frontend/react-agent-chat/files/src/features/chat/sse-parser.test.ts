import { describe, expect, it } from 'vitest'

import { readSse, SseParser } from './sse-parser'

const enc = new TextEncoder()

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(enc.encode(chunk))
      controller.close()
    },
  })
}

async function collect(chunks: string[]) {
  const events = []
  for await (const event of readSse(streamOf(chunks))) events.push(event)
  return events
}

describe('SseParser', () => {
  it('parses event + data framed by a blank line', () => {
    const parser = new SseParser()
    expect(parser.push('event: token\ndata: {"text": "Hola"}\n\n')).toEqual([{ type: 'token', text: 'Hola' }])
  })

  it('keeps a line cut between chunks, even inside the JSON', () => {
    const parser = new SseParser()
    expect(parser.push('event: tok')).toEqual([])
    expect(parser.push('en\ndata: {"te')).toEqual([])
    expect(parser.push('xt": "a b"}\n\n')).toEqual([{ type: 'token', text: 'a b' }])
  })

  it('accepts CRLF (sse-starlette) and data without a space', () => {
    const parser = new SseParser()
    expect(parser.push('event: tool_start\r\ndata:{"tool":"search"}\r\n\r\n')).toEqual([
      { type: 'tool_start', tool: 'search' },
    ])
  })

  it('joins multi-line data with \\n', () => {
    const parser = new SseParser()
    expect(parser.push('event: done\ndata: {"answer":\ndata: "x"}\n\n')).toEqual([{ type: 'done', answer: 'x' }])
  })

  it('ignores comments, pings, id/retry, unknown events and bad JSON', () => {
    const parser = new SseParser()
    const events = parser.push(
      ': ping\n\nid: 1\nretry: 100\n\nevent: weird\ndata: {"a":1}\n\nevent: token\ndata: {not json\n\nevent: token\ndata: {"text":"ok"}\n\n',
    )
    expect(events).toEqual([{ type: 'token', text: 'ok' }])
  })

  it('maps error and done payloads', () => {
    const parser = new SseParser()
    expect(parser.push('event: error\ndata: {"error_id":"e-1"}\n\nevent: done\ndata: {"answer":"fin"}\n\n')).toEqual([
      { type: 'error', errorId: 'e-1' },
      { type: 'done', answer: 'fin' },
    ])
  })

  it('flushes a last event without trailing blank line', () => {
    const parser = new SseParser()
    expect(parser.push('event: done\ndata: {"answer":"x"}')).toEqual([])
    expect(parser.flush()).toEqual([{ type: 'done', answer: 'x' }])
  })
})

describe('readSse', () => {
  it('reads a stream split at arbitrary byte boundaries', async () => {
    const body = 'event: routing\ndata: {"category":"billing"}\n\nevent: token\ndata: {"text":"ñandú "}\n\nevent: done\ndata: {"answer":"ñandú"}\n\n'
    const bytes = enc.encode(body)
    const chunks: Uint8Array[] = []
    for (let i = 0; i < bytes.length; i += 3) chunks.push(bytes.slice(i, i + 3)) // splits the ñ in half
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        chunks.forEach((c) => controller.enqueue(c))
        controller.close()
      },
    })

    const events = []
    for await (const event of readSse(stream)) events.push(event)

    expect(events).toEqual([
      { type: 'routing', data: { category: 'billing' } },
      { type: 'token', text: 'ñandú ' },
      { type: 'done', answer: 'ñandú' },
    ])
  })

  it('stops after a terminal event', async () => {
    const events = await collect(['event: error\ndata: {}\n\nevent: token\ndata: {"text":"late"}\n\n'])
    expect(events).toEqual([{ type: 'error', errorId: undefined }])
  })
})
