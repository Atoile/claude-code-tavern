<script>
  let { character, isRaw = false, selected = false, onSelect } = $props()

  const name = $derived(isRaw
    ? character.filename.replace(/\.png$/i, '').replace(/_/g, ' ').split('-').slice(0, 3).join(' ')
    : (character.data?.meta?.name || character.name || character.id))

  const tagline = $derived(isRaw
    ? 'Raw card — needs repacking'
    : (character.data?.personality?.core_traits?.[0] || character.data?.identity?.occupation?.[0] || ''))

  const avatarSrc = $derived(isRaw
    ? `/raw/${character.filename}`
    : character.avatarPath ? `/${character.avatarPath}` : null)
</script>

<div
  role="button"
  tabindex="0"
  class="card card-compact bg-base-200 hover:bg-base-100 cursor-pointer transition-all border-2
    {selected ? 'border-primary shadow-lg shadow-primary/20' : 'border-transparent'}
    w-full text-left"
  onclick={onSelect}
  onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect()}
  aria-pressed={selected}
>
  <div class="card-body flex-row items-center gap-3 p-3">
    <!-- Avatar 4:3 -->
    <div class="shrink-0 w-12 rounded-lg overflow-hidden bg-base-300" style="aspect-ratio: 3/4;">
      {#if avatarSrc}
        <img src={avatarSrc} alt={name} class="object-cover w-full h-full" />
      {:else}
        <div class="w-full h-full flex items-center justify-center text-base-content/30">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6" viewBox="0 0 24 24" style="fill: none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
        </div>
      {/if}
    </div>

    <!-- Info -->
    <div class="flex-1 min-w-0">
      <div class="font-semibold text-sm truncate">{name}</div>
      {#if tagline}
        <div class="text-xs text-base-content/50 truncate mt-0.5">{tagline}</div>
      {/if}
      {#if isRaw}
        <div class="badge badge-warning badge-xs mt-1">raw</div>
      {:else}
        <div class="badge badge-success badge-xs mt-1">repacked</div>
      {/if}
    </div>

    <!-- Selection indicator -->
    {#if selected}
      <div class="text-primary shrink-0">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" style="fill: none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
      </div>
    {/if}
  </div>
</div>
