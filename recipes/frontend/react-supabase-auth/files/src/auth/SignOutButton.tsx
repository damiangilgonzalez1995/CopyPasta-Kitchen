import { useSession } from './session-context'

/** Shows who is signed in and signs out. Put it wherever the layout has room (header, menu). */
export function SignOutButton() {
  const { session, signOut } = useSession()
  if (!session) return null
  return (
    <button className="button" onClick={() => void signOut()}>
      Salir ({session.user.email})
    </button>
  )
}
