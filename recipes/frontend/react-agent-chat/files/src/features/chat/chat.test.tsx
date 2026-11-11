import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { createHttpClient } from '../../api/http-client'
import { staticToken } from '../../auth/token-provider'
import { createHttpChatApi, type ChatApi } from './chat-api'
import { ChatView } from './components/ChatView'
import type { ChatEvent } from './events'
import { createFakeChatApi } from './fake-chat-api'

/** A ChatApi that plays a fixed list of events. */
function scripted(events: ChatEvent[], options: { hangAfter?: boolean } = {}): ChatApi {
  return {
    async *streamAnswer(_request, signal) {
      for (const event of events) yield event
      if (options.hangAfter) {
        await new Promise((_, reject) =>
          signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))),
        )
      }
    },
  }
}

const typeAndSend = async (text: string) => {
  await userEvent.type(screen.getByLabelText('Mensaje'), text)
  await userEvent.click(screen.getByRole('button', { name: 'Enviar' }))
}

describe('ChatView', () => {
  it('streams tokens into the assistant message and closes tool steps', async () => {
    render(<ChatView chat={createFakeChatApi({ stepMs: 0, reply: () => 'Hola **mundo**' })} />)

    await typeAndSend('hola')

    await waitFor(() => expect(screen.getByText('mundo').tagName).toBe('STRONG'))
    expect(screen.getByText('hola')).toBeTruthy()
    expect(screen.getByLabelText('Herramientas').textContent).toContain('✓ search_documents')
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeTruthy()
  })

  it('sends question and the same conversation id on every turn', async () => {
    const calls: { question: string; conversationId: string }[] = []
    const chat: ChatApi = {
      async *streamAnswer(request) {
        calls.push(request)
        yield { type: 'done', answer: 'ok' }
      },
    }
    render(<ChatView chat={chat} />)

    await typeAndSend('uno')
    await screen.findByText('ok')
    await typeAndSend('dos')
    await waitFor(() => expect(calls).toHaveLength(2))

    expect(calls.map((c) => c.question)).toEqual(['uno', 'dos'])
    expect(calls[0].conversationId).toBe(calls[1].conversationId)
  })

  it('shows the error id and puts the question back in the draft', async () => {
    render(<ChatView chat={scripted([{ type: 'tool_start', tool: 'search' }, { type: 'error', errorId: 'err-42' }])} />)

    await typeAndSend('pregunta')

    expect((await screen.findByRole('alert')).textContent).toContain('err-42')
    expect((screen.getByLabelText('Mensaje') as HTMLTextAreaElement).value).toBe('pregunta')
    expect(screen.getByLabelText('Herramientas').textContent).toContain('✕ search')
  })

  it('treats a stream that ends without done as a failure', async () => {
    render(<ChatView chat={scripted([{ type: 'token', text: 'a medias' }])} />)

    await typeAndSend('x')

    expect(await screen.findByRole('alert')).toBeTruthy()
  })

  it('cancels without showing an error', async () => {
    render(<ChatView chat={scripted([{ type: 'token', text: 'empiezo' }], { hangAfter: true })} />)

    await typeAndSend('x')
    await screen.findByText('empiezo')
    await userEvent.click(screen.getByRole('button', { name: 'Detener' }))

    expect(await screen.findByText('Respuesta cancelada.')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('does not run raw HTML coming from the agent', async () => {
    render(<ChatView chat={scripted([{ type: 'token', text: '<img src=x onerror="alert(1)">' }, { type: 'done', answer: '' }])} />)

    await typeAndSend('x')

    await screen.findByText(/onerror/)
    expect(document.querySelector('img')).toBeNull()
  })

  it('new conversation clears messages and changes the id', async () => {
    const ids: string[] = []
    const chat: ChatApi = {
      async *streamAnswer(request) {
        ids.push(request.conversationId)
        yield { type: 'done', answer: 'ok' }
      },
    }
    render(<ChatView chat={chat} />)
    await typeAndSend('uno')
    await screen.findByText('ok')

    await userEvent.click(screen.getByRole('button', { name: 'Nueva conversación' }))
    expect(screen.queryByText('ok')).toBeNull()
    await typeAndSend('dos')
    await waitFor(() => expect(ids).toHaveLength(2))

    expect(ids[0]).not.toBe(ids[1])
  })
})

describe('createHttpChatApi', () => {
  it('POSTs with bearer and snake_case body and parses the SSE answer', async () => {
    const sse = 'event: token\r\ndata: {"text":"hi"}\r\n\r\nevent: done\r\ndata: {"answer":"hi"}\r\n\r\n'
    const fetcher = vi.fn<typeof fetch>(async () => new Response(sse, { headers: { 'Content-Type': 'text/event-stream' } }))
    const chat = createHttpChatApi(createHttpClient({ baseUrl: '/api', tokens: staticToken('tok'), fetcher }))

    const events = []
    for await (const event of chat.streamAnswer({ question: 'q', conversationId: 'c1' })) events.push(event)

    expect(events).toEqual([
      { type: 'token', text: 'hi' },
      { type: 'done', answer: 'hi' },
    ])
    const [url, init] = fetcher.mock.calls[0]
    expect(url).toBe('/api/agent/stream')
    expect(JSON.parse(init!.body as string)).toEqual({ question: 'q', conversation_id: 'c1' })
    expect((init!.headers as Record<string, string>).Authorization).toBe('Bearer tok')
  })
})
