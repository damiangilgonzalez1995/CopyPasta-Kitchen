/** Text/background pairs in tokens.css must reach WCAG AA (4.5:1), in light and dark. */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// Read from disk: Vitest does not process CSS by default, so a ?raw import comes back empty.
const css = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8')

const [light, dark] = css.split('@media (prefers-color-scheme: dark)')

const PAIRS: [text: string, background: string][] = [
  ['--color-text', '--color-bg'],
  ['--color-text', '--color-surface'],
  ['--color-muted', '--color-bg'],
  ['--color-muted', '--color-surface'],
  ['--color-on-primary', '--color-primary'],
  ['--color-danger', '--color-bg'],
]

function tokens(block: string): Record<string, string> {
  return Object.fromEntries([...block.matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]))
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

describe.each([
  ['light', tokens(light)],
  ['dark', tokens(dark)],
])('%s theme', (_, theme) => {
  it.each(PAIRS)('%s on %s reaches 4.5:1', (text, background) => {
    expect(contrast(theme[text], theme[background])).toBeGreaterThanOrEqual(4.5)
  })
})
