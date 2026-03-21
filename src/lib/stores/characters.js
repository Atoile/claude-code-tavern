import { writable } from 'svelte/store'

export const repackedCharacters = writable([])
export const rawCharacters = writable([])
export const selectedCharacters = writable([]) // max 2

export async function loadCharacters() {
  try {
    const [charsRes, rawRes] = await Promise.all([
      fetch('/api/characters'),
      fetch('/api/raw')
    ])
    const chars = await charsRes.json()
    const raws = await rawRes.json()
    repackedCharacters.set(chars)
    rawCharacters.set(raws)
  } catch (err) {
    console.error('Failed to load characters:', err)
  }
}

export function clearSelection() {
  selectedCharacters.set([])
}

export function toggleCharacterSelection(char, isRaw = false) {
  selectedCharacters.update(sel => {
    const key = isRaw ? `raw:${char.filename}` : `repacked:${char.id}`
    const exists = sel.find(s => s._key === key)
    if (exists) {
      return sel.filter(s => s._key !== key)
    }
    if (sel.length >= 2) return sel
    return [...sel, { ...char, _key: key, _isRaw: isRaw }]
  })
}
