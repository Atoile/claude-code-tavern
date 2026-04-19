<script>
  import { onMount } from 'svelte'
  import { SvelteSet } from 'svelte/reactivity'
  import { repackedCharacters, rawCharacters, selectedCharacters, loadCharacters, toggleCharacterSelection, clearSelection, updateCharacterColor, MIN_PARTICIPANTS, MAX_PARTICIPANTS } from '../stores/characters.js'
  import CharacterCard from '../components/CharacterCard.svelte'

  let { onStartScene } = $props()

  let searchQuery = $state('')
  let selectedTags = new SvelteSet()

  onMount(() => loadCharacters())

  function handleSelect(char, isRaw) {
    toggleCharacterSelection(char, isRaw)
  }

  function isSelected(char, isRaw) {
    const key = isRaw ? `raw:${char.filename}` : `repacked:${char.id}`
    return $selectedCharacters.some(s => s._key === key)
  }

  function displayName(c) {
    return c?.data?.meta?.name || c?.name || c?.filename?.replace(/\.png$/i, '') || c?.id || '?'
  }

  function handleColorChange(char, color) {
    updateCharacterColor(char.id, color)
  }

  function handleStartScene() {
    onStartScene({ characters: [...$selectedCharacters] })
  }

  function toggleTag(tag) {
    selectedTags.has(tag) ? selectedTags.delete(tag) : selectedTags.add(tag)
  }

  const allTags = $derived(
    [...new Set($repackedCharacters.flatMap(c => c.data?.filter_tags || []))].sort()
  )

  const q = $derived(searchQuery.trim().toLowerCase())

  const filteredRepacked = $derived(
    $repackedCharacters.filter(c => {
      const name = (c.data?.meta?.name || c.name || c.id || '').toLowerCase()
      if (q && !name.includes(q)) return false
      if (selectedTags.size > 0) {
        const charTags = new Set(c.data?.filter_tags || [])
        for (const t of selectedTags) if (!charTags.has(t)) return false
      }
      return true
    })
  )

  const filteredRaw = $derived(
    q ? $rawCharacters.filter(c => {
      const name = c.filename.replace(/\.png$/i, '').replace(/[_-]/g, ' ').toLowerCase()
      return name.includes(q)
    }) : $rawCharacters
  )
</script>

<div class="flex flex-col h-full p-4 overflow-y-auto">
  <div class="flex items-center justify-between mb-3">
    <h1 class="text-xl font-bold">Characters</h1>
    <button class="btn btn-xs btn-ghost" onclick={loadCharacters}>
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" style="fill: none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="23 4 23 10 17 10"/>
        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
      </svg>
      Refresh
    </button>
  </div>

  <label class="input input-sm w-full flex items-center gap-2" class:mb-2={allTags.length > 0} class:mb-4={allTags.length === 0}>
    <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-base-content/40 shrink-0" viewBox="0 0 24 24" style="fill: none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>
    <input type="text" placeholder="Search characters…" class="grow bg-transparent outline-none text-sm" bind:value={searchQuery} />
    {#if searchQuery}
      <button class="text-base-content/30 hover:text-base-content/60" onclick={() => searchQuery = ''}>✕</button>
    {/if}
  </label>

  {#if allTags.length > 0}
    <div class="flex flex-wrap gap-1 mb-4">
      {#each allTags as tag (tag)}
        <button
          class="badge badge-sm cursor-pointer select-none transition-colors"
          class:badge-success={selectedTags.has(tag)}
          class:badge-ghost={!selectedTags.has(tag)}
          onclick={() => toggleTag(tag)}
        >{tag}</button>
      {/each}
      {#if selectedTags.size > 0}
        <button class="badge badge-sm badge-ghost opacity-50 hover:opacity-80 cursor-pointer" onclick={() => selectedTags.clear()}>clear</button>
      {/if}
    </div>
  {/if}

  <!-- Selection status -->
  <div class="mb-4">
    {#if $selectedCharacters.length === 0}
      <div class="text-sm text-base-content/40">Select {MIN_PARTICIPANTS}–{MAX_PARTICIPANTS} characters to start a scene.</div>
    {:else if $selectedCharacters.length < MIN_PARTICIPANTS}
      <div class="flex items-center gap-3 flex-wrap">
        <div class="text-sm text-base-content/60">
          {#each $selectedCharacters as c, i (c._key)}<span class="font-medium text-base-content">{displayName(c)}</span>{#if i < $selectedCharacters.length - 1} &amp; {/if}{/each}
          selected — pick {MIN_PARTICIPANTS - $selectedCharacters.length} more.
        </div>
        <button class="btn btn-ghost btn-sm text-base-content/40" onclick={clearSelection}>Clear</button>
      </div>
    {:else}
      <div class="flex items-center gap-3 flex-wrap">
        <div class="text-sm text-base-content/60">
          {#each $selectedCharacters as c, i (c._key)}<span class="font-medium text-base-content">{displayName(c)}</span>{#if i < $selectedCharacters.length - 1} &amp; {/if}{/each}
          {#if $selectedCharacters.length < MAX_PARTICIPANTS}
            <span class="text-base-content/30">— add {MAX_PARTICIPANTS - $selectedCharacters.length} more or start now</span>
          {/if}
        </div>
        <button class="btn btn-primary btn-sm" onclick={handleStartScene}>Start Scene →</button>
        <button class="btn btn-ghost btn-sm text-base-content/40" onclick={clearSelection}>Clear</button>
      </div>
    {/if}
  </div>

  <!-- Repacked characters -->
  {#if filteredRepacked.length > 0}
    <div class="mb-4">
      <div class="text-xs font-semibold text-success uppercase tracking-wider mb-2">Repacked</div>
      <div class="flex flex-col gap-2">
        {#each filteredRepacked as char (char.id)}
          <CharacterCard character={char} isRaw={false} selected={isSelected(char, false)} onSelect={() => handleSelect(char, false)} onColorChange={handleColorChange} />
        {/each}
      </div>
    </div>
  {/if}

  <!-- Raw characters -->
  {#if filteredRaw.length > 0}
    <div class="mb-4">
      <div class="text-xs font-semibold text-warning uppercase tracking-wider mb-2">Raw (unrepacked)</div>
      <div class="flex flex-col gap-2">
        {#each filteredRaw as char (char.filename)}
          <CharacterCard character={char} isRaw={true} selected={isSelected(char, true)} onSelect={() => handleSelect(char, true)} />
        {/each}
      </div>
    </div>
  {/if}

  {#if $repackedCharacters.length === 0 && $rawCharacters.length === 0}
    <div class="text-sm text-base-content/40 mt-8 text-center">
      No characters found.<br/>
      <span class="text-xs">Place SillyTavern PNGs in <code class="bg-base-300 px-1 rounded">infrastructure/raw/</code> or repacked data in <code class="bg-base-300 px-1 rounded">infrastructure/characters/</code></span>
    </div>
  {:else if filteredRepacked.length === 0 && filteredRaw.length === 0}
    <div class="text-sm text-base-content/40 mt-8 text-center">No characters match{searchQuery ? ` "${searchQuery}"` : ''}{selectedTags.size > 0 ? ` [${[...selectedTags].join(', ')}]` : ''}</div>
  {/if}
</div>
