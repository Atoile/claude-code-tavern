import { writable } from 'svelte/store'

export const repackedCharacters = writable([])
export const rawCharacters = writable([])
export const selectedCharacters = writable([]) // 2-4 participants per scene

export const MAX_PARTICIPANTS = 4
export const MIN_PARTICIPANTS = 2

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

export async function updateCharacterColor(charId, color) {
  try {
    await fetch(`/api/characters/${charId}/color`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ color })
    })
    repackedCharacters.update(chars =>
      chars.map(c => c.id === charId
        ? { ...c, data: { ...c.data, meta: { ...c.data?.meta, color } } }
        : c
      )
    )
    selectedCharacters.update(sel =>
      sel.map(c => (!c._isRaw && c.id === charId)
        ? { ...c, data: { ...c.data, meta: { ...c.data?.meta, color } } }
        : c
      )
    )
  } catch (err) {
    console.error('Failed to update character color:', err)
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
    if (sel.length >= MAX_PARTICIPANTS) return sel
    return [...sel, { ...char, _key: key, _isRaw: isRaw }]
  })
}
