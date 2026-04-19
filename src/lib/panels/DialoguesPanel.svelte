<script>
  import { onMount } from 'svelte'

  let { onOpenDialogue, onNewScene } = $props()

  let dialogues = $state([])
  let loading = $state(true)

  onMount(() => load())

  async function load() {
    loading = true
    try {
      const res = await fetch('/api/dialogues')
      dialogues = await res.json()
    } catch {}
    loading = false
  }
</script>

<div class="flex flex-col h-full p-4 overflow-y-auto">
  <div class="flex items-center justify-between mb-4">
    <h1 class="text-xl font-bold">Dialogues</h1>
    <div class="flex gap-2">
      <button class="btn btn-xs btn-ghost" onclick={load}>
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" style="fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round">
          <polyline points="23 4 23 10 17 10"/>
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg>
        Refresh
      </button>
      <button class="btn btn-xs btn-primary" onclick={onNewScene}>
        + New Scene
      </button>
    </div>
  </div>

  {#if loading}
    <div class="flex justify-center mt-16">
      <span class="loading loading-ring loading-md text-primary"></span>
    </div>
  {:else if dialogues.length === 0}
    <div class="text-sm text-base-content/40 mt-16 text-center">
      No dialogues yet.<br/>
      <button class="btn btn-primary btn-sm mt-4" onclick={onNewScene}>Start your first scene</button>
    </div>
  {:else}
    <div class="flex flex-col gap-3">
      {#each dialogues as d (d.id)}
        {@const participants = d.characters?.participants || {}}
        {@const leadingId = d.characters?.leading_id}
        {@const leading = leadingId ? participants[leadingId] : null}
        {@const others = Object.values(participants).filter(p => p.id !== leadingId)}
        <div
          class="card bg-base-200 hover:bg-base-100 text-left transition-colors border-2 border-transparent hover:border-base-100 w-full cursor-pointer"
          role="button"
          tabindex="0"
          onclick={() => onOpenDialogue(d.id, d.characters)}
          onkeydown={(e) => e.key === 'Enter' && onOpenDialogue(d.id, d.characters)}
        >
          <div class="card-body p-4 gap-2">
            <div class="flex items-center gap-2 flex-wrap">
              {#each others as o, i (o.id || i)}
                {#if i > 0}<span class="text-base-content/30 text-xs">·</span>{/if}
                <span class="font-semibold text-sm">{o?.name || '?'}</span>
              {/each}
              {#if leading && others.length > 0}
                <span class="text-base-content/30 text-xs">×</span>
              {/if}
              {#if leading}
                <span class="font-semibold text-sm">{leading?.name || '?'}</span>
              {:else if others.length === 0}
                <span class="font-semibold text-sm text-base-content/40">no participants</span>
              {/if}
              <span class="ml-auto text-xs text-base-content/30">{d.message_count} msg</span>
            </div>
            {#if d.scenario_text}
              <p class="text-xs text-base-content/50 leading-relaxed line-clamp-3">{d.scenario_text}</p>
            {/if}
            <div class="text-xs text-base-content/30">{new Date(d.last_updated).toLocaleString()}</div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
