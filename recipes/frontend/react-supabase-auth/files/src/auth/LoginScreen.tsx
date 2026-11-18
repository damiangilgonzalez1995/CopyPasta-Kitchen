/** Email + password. Messages by `AuthError.code`, never the provider's text. */

import { useState, type FormEvent } from 'react'

import { AuthError, type AuthErrorCode } from './auth'
import { useSession } from './session-context'
import './auth.css'

const MESSAGES: Record<AuthErrorCode, string> = {
  invalid_credentials: 'No coinciden el correo y la contraseña',
  email_not_confirmed: 'Confirma tu correo antes de entrar',
  rate_limited: 'Demasiados intentos. Espera un momento',
  unavailable: 'No se pudo iniciar sesión. Inténtalo de nuevo',
}

export function LoginScreen() {
  const { signIn, expired } = useSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSending(true)
    setError(null)
    try {
      await signIn({ email, password })
    } catch (reason) {
      setError(reason instanceof AuthError ? MESSAGES[reason.code] : MESSAGES.unavailable)
      setSending(false)
    }
  }

  return (
    <form className="card login" onSubmit={(event) => void submit(event)} aria-labelledby="login-title">
      <h1 id="login-title">Entrar</h1>
      {expired && <p className="muted">Tu sesión ha caducado</p>}
      <label className="field">
        Correo
        <input type="email" name="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label className="field">
        Contraseña
        <input
          type="password"
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      {error && (
        <p role="alert" className="login-error">
          {error}
        </p>
      )}
      <button className="button" type="submit" disabled={sending}>
        {sending ? 'Entrando…' : 'Entrar'}
      </button>
    </form>
  )
}
