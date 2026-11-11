/**
 * Load data for a screen: `{data, loading, error, reload}`.
 * Stale answers are dropped (if `deps` change mid-request, only the last request wins) and the
 * request is aborted on unmount.
 */

import { useCallback, useEffect, useRef, useState, type DependencyList } from 'react'

export type LoadState<T> = {
  data: T | undefined
  loading: boolean
  error: unknown
  reload: () => void
}

export function useLoad<T>(load: (signal: AbortSignal) => Promise<T>, deps: DependencyList): LoadState<T> {
  const [data, setData] = useState<T>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>()
  const [attempt, setAttempt] = useState(0)
  const loadRef = useRef(load)
  loadRef.current = load

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(undefined)
    loadRef.current(controller.signal).then(
      (value) => {
        if (controller.signal.aborted) return
        setData(value)
        setLoading(false)
      },
      (reason: unknown) => {
        if (controller.signal.aborted) return
        setError(reason)
        setLoading(false)
      },
    )
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt])

  const reload = useCallback(() => setAttempt((n) => n + 1), [])
  return { data, loading, error, reload }
}
