import type { ChatApi } from '../chat-api'
import { useChat } from '../use-chat'
import { Composer } from './Composer'
import { MessageList } from './MessageList'
import '../chat.css'

/** The whole chat. Receives its `ChatApi` from outside (real or fake), like every screen. */
export function ChatView({ chat }: { chat: ChatApi }) {
  const { messages, draft, setDraft, sending, send, cancel, newConversation } = useChat(chat)

  return (
    <section className="chat">
      <header className="chat-header">
        <button className="button button--ghost" onClick={newConversation} disabled={messages.length === 0}>
          Nueva conversación
        </button>
      </header>
      <MessageList messages={messages} />
      <Composer draft={draft} onDraft={setDraft} onSend={() => void send()} onCancel={cancel} sending={sending} />
    </section>
  )
}
