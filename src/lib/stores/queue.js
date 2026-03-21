import { writable } from 'svelte/store'

export const queueItems = writable([])

export async function readQueue() {
  try {
    const res = await fetch('/api/queue')
    const data = await res.json()
    queueItems.set(Array.isArray(data) ? data : [])
    return data
  } catch (err) {
    console.error('Failed to read queue:', err)
    return []
  }
}

export async function writeQueue(items) {
  try {
    await fetch('/api/queue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(items)
    })
    queueItems.set(items)
  } catch (err) {
    console.error('Failed to write queue:', err)
  }
}

export async function appendToQueue(newItems) {
  const current = await readQueue()
  const updated = [...current, ...newItems]
  await writeQueue(updated)
  return updated
}
