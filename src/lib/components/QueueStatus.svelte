<script>
  import { onMount, onDestroy } from 'svelte'
  import { queueItems, readQueue } from '../stores/queue.js'

  let { standalone = false, polling = false, onQueueEmpty } = $props()

  let interval = null

  $effect(() => {
    if (polling) {
      startPolling()
    } else {
      stopPolling()
    }
  })

  onMount(() => {
    readQueue()
  })

  onDestroy(() => {
    stopPolling()
  })

  function startPolling() {
    if (interval) return
    interval = setInterval(async () => {
      const q = await readQueue()
      const active = q.filter(i => i.status !== 'done' && i.status !== 'error')
      if (active.length === 0 && onQueueEmpty) {
        onQueueEmpty(q)
      }
    }, 2000)
  }

  function stopPolling() {
    if (interval) {
      clearInterval(interval)
      interval = null
    }
  }

  const statusColor = {
    pending: 'badge-ghost',
    processing: 'badge-warning',
    done: 'badge-success',
    error: 'badge-error'
  }
</script>

{#if standalone}
  <div class="flex flex-col h-full p-4">
    <div class="flex items-center gap-2 mb-4">
      <h2 class="text-lg font-bold">Queue</h2>
      <button class="btn btn-xs btn-ghost" onclick={() => readQueue()}>
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="23 4 23 10 17 10"/>
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg>
        Refresh
      </button>
    </div>

    {#if $queueItems.length === 0}
      <div class="text-base-content/40 text-sm">Queue is empty.</div>
    {:else}
      <div class="flex flex-col gap-2 overflow-y-auto">
        {#each $queueItems as item (item.id)}
          <div class="card bg-base-200 p-3 text-xs font-mono">
            <div class="flex items-center gap-2 mb-1">
              <span class="badge {statusColor[item.status] || 'badge-ghost'} badge-sm">{item.status}</span>
              <span class="font-semibold">{item.type}</span>
            </div>
            <div class="text-base-content/40 truncate">{item.id}</div>
            {#if item.depends_on?.length}
              <div class="text-base-content/30 mt-1">depends: {item.depends_on.join(', ')}</div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>
{:else}
  <!-- Compact inline status for use inside other panels -->
  <div class="flex flex-col gap-1">
    {#each $queueItems as item (item.id)}
      <div class="flex items-center gap-2 text-xs">
        <span class="badge {statusColor[item.status] || 'badge-ghost'} badge-xs">{item.status}</span>
        <span class="text-base-content/60">{item.type}</span>
      </div>
    {/each}
    {#if $queueItems.length === 0}
      <span class="text-xs text-success">Queue empty</span>
    {/if}
  </div>
{/if}
