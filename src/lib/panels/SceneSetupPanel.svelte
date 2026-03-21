<script>
  import { onMount, onDestroy } from 'svelte'
  import { readQueue, appendToQueue } from '../stores/queue.js'

  let { charA, charB, onBack, onDialogueReady, resumeDialogueId = null } = $props()

  // stage: 'review' | 'waiting-setup' | 'scenario' | 'waiting-init'
  let stage = $state('review')
  let error = $state(null)
  let dialogueId = $state(null)
  let scenario = $state(null)
  let selectedLeading = $state(null)
  let selectedOpening = $state(null)
  let pollInterval = $state(null)
  let setupTaskIds = $state([])
  let initTaskIds = $state([])

  const charAName = $derived(charA?._isRaw
    ? charA.filename?.replace(/\.png$/i, '').replace(/_/g, ' ')
    : (charA?.data?.meta?.name || charA?.name || charA?.id || 'Character A'))

  const charBName = $derived(charB?._isRaw
    ? charB.filename?.replace(/\.png$/i, '').replace(/_/g, ' ')
    : (charB?.data?.meta?.name || charB?.name || charB?.id || 'Character B'))

  const charAAvatarSrc = $derived(charA?._isRaw
    ? `/raw/${charA.filename}`
    : (charA?.avatarPath ? `/${charA.avatarPath}` : null))

  const charBAvatarSrc = $derived(charB?._isRaw
    ? `/raw/${charB.filename}`
    : (charB?.avatarPath ? `/${charB.avatarPath}` : null))

  const charAIsRaw = $derived(charA?._isRaw === true)
  const charBIsRaw = $derived(charB?._isRaw === true)

  const charASummary = $derived(charA?._isRaw ? null
    : (charA?.data?.identity?.background_summary || charA?.data?.personality?.core_traits?.slice(0, 2).join(' · ') || null))

  const charBSummary = $derived(charB?._isRaw ? null
    : (charB?.data?.identity?.background_summary || charB?.data?.personality?.core_traits?.slice(0, 2).join(' · ') || null))

  onMount(async () => {
    if (!resumeDialogueId) return
    dialogueId = resumeDialogueId
    const res = await fetch(`/api/dialogue/${resumeDialogueId}/scenario`)
    if (res.ok) {
      scenario = await res.json()
      selectedLeading = 'A'
      selectedOpening = 0
      stage = 'scenario'
    } else {
      stage = 'waiting-setup'
      // Poll until scenario.json appears (queue task may still be processing)
      pollInterval = setInterval(async () => {
        const r = await fetch(`/api/dialogue/${dialogueId}/scenario`)
        if (r.ok) {
          stopPolling()
          scenario = await r.json()
          selectedLeading = 'A'
          selectedOpening = 0
          stage = 'scenario'
        }
      }, 2000)
    }
  })

  onDestroy(() => stopPolling())

  function stopPolling() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null }
  }

  function startPolling(taskIds, onEmpty) {
    stopPolling()
    pollInterval = setInterval(async () => {
      const q = await readQueue()
      const ourTasks = q.filter(item => taskIds.includes(item.id))
      if (ourTasks.length === 0 || ourTasks.every(i => i.status === 'done' || i.status === 'error')) {
        stopPolling()
        onEmpty(q)
      }
    }, 2000)
  }

  function sanitizeName(name) {
    return name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
  }

  function persistScene(id) {
    try {
      localStorage.setItem('tavern:active_scene', JSON.stringify({
        dialogueId: id,
        charA, charB,
        savedAt: Date.now()
      }))
    } catch {}
  }

  async function beginSetup() {
    error = null
    const id = crypto.randomUUID()
    dialogueId = id
    persistScene(id)

    const tasks = []
    let repackAId = null
    let repackBId = null

    if (charAIsRaw) {
      repackAId = crypto.randomUUID()
      tasks.push({
        id: repackAId, type: 'repack_character', parallel: true, depends_on: [],
        model: 'claude-sonnet-4-6',
        input: { raw_path: `infrastructure/raw/${charA.filename}`, character_name: charAName },
        output_path: `infrastructure/characters/${sanitizeName(charAName)}/data.json`,
        status: 'pending'
      })
    }
    if (charBIsRaw) {
      repackBId = crypto.randomUUID()
      tasks.push({
        id: repackBId, type: 'repack_character', parallel: true, depends_on: [],
        model: 'claude-sonnet-4-6',
        input: { raw_path: `infrastructure/raw/${charB.filename}`, character_name: charBName },
        output_path: `infrastructure/characters/${sanitizeName(charBName)}/data.json`,
        status: 'pending'
      })
    }

    const optimizeId = crypto.randomUUID()
    tasks.push({
      id: optimizeId, type: 'optimize_scenario', parallel: false,
      depends_on: [repackAId, repackBId].filter(Boolean),
      model: 'claude-sonnet-4-6',
      input: {
        dialogue_id: id,
        char_a: charAIsRaw
          ? { name: charAName, raw_path: `infrastructure/raw/${charA.filename}`, needs_repack: true }
          : { name: charAName, data_path: charA.dataPath, id: charA.id },
        char_b: charBIsRaw
          ? { name: charBName, raw_path: `infrastructure/raw/${charB.filename}`, needs_repack: true }
          : { name: charBName, data_path: charB.dataPath, id: charB.id }
      },
      output_path: `infrastructure/dialogues/${id}/scenario.json`,
      status: 'pending'
    })

    // Create initial dialogue state so Claude Code can find characters
    await fetch(`/api/dialogue/${id}/characters`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        charA: charAIsRaw
          ? { name: charAName, raw_path: `infrastructure/raw/${charA.filename}`, needs_repack: true }
          : { id: charA.id, name: charAName, data_path: charA.dataPath },
        charB: charBIsRaw
          ? { name: charBName, raw_path: `infrastructure/raw/${charB.filename}`, needs_repack: true }
          : { id: charB.id, name: charBName, data_path: charB.dataPath }
      })
    })

    setupTaskIds = tasks.map(t => t.id)
    await appendToQueue(tasks)
    stage = 'waiting-setup'
    startPolling(setupTaskIds, onSetupComplete)
  }

  async function onSetupComplete() {
    try {
      const res = await fetch(`/api/dialogue/${dialogueId}/scenario`)
      if (res.ok) {
        scenario = await res.json()
        selectedLeading = 'A'
        selectedOpening = 0
        stage = 'scenario'
      } else {
        error = `Scenario not found after processing. (dialogue id: ${dialogueId})`
        stage = 'review'
      }
    } catch (err) {
      error = `Failed to load scenario: ${err.message}`
      stage = 'review'
    }
  }

  async function initializeDialogue() {
    if (!selectedLeading || selectedOpening === null) return
    error = null
    stage = 'waiting-init'

    try {
    const leadingCharId = selectedLeading === 'A'
      ? (charAIsRaw ? sanitizeName(charAName) : charA.id)
      : (charBIsRaw ? sanitizeName(charBName) : charB.id)
    const replyingCharId = selectedLeading === 'A'
      ? (charBIsRaw ? sanitizeName(charBName) : charB.id)
      : (charAIsRaw ? sanitizeName(charAName) : charA.id)

    const selectedGreeting =
      scenario[selectedLeading === 'A' ? 'char_a' : 'char_b']?.openings?.[selectedOpening]
      ?? scenario.opening_options?.[selectedOpening]

    // Write the opening line directly — no need to queue optimize_opening / write_opening_line
    const openingMessage = { speaker: leadingCharId, text: selectedGreeting }
    const chatInit = [openingMessage]
    await fetch(`/api/dialogue/${dialogueId}/full_chat`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(chatInit)
    })
    await fetch(`/api/dialogue/${dialogueId}/recent_chat`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(chatInit)
    })

    // Update characters.json with resolved leading/replying
    await fetch(`/api/dialogue/${dialogueId}/characters`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        charA: charAIsRaw ? { name: charAName, raw_path: `raw/${charA.filename}`, needs_repack: true } : { id: charA.id, name: charAName, data_path: charA.dataPath },
        charB: charBIsRaw ? { name: charBName, raw_path: `raw/${charB.filename}`, needs_repack: true } : { id: charB.id, name: charBName, data_path: charB.dataPath },
        leading: { id: leadingCharId, name: selectedLeading === 'A' ? charAName : charBName },
        replying: { id: replyingCharId, name: selectedLeading === 'A' ? charBName : charAName }
      })
    })

    // Queue only the first reply
    const generateReplyId = crypto.randomUUID()
    const tasks = [{
      id: generateReplyId, type: 'generate_reply', parallel: false, depends_on: [],
      model: 'claude-sonnet-4-6',
      input: { dialogue_id: dialogueId, replying_char_id: replyingCharId },
      output_path: `infrastructure/dialogues/${dialogueId}/recent_chat.json`,
      status: 'pending'
    }]

    initTaskIds = [generateReplyId]
    await appendToQueue(tasks)

    startPolling([generateReplyId], async () => {
      const leadingCharObj = selectedLeading === 'A' ? charA : charB
      const otherCharObj = selectedLeading === 'A' ? charB : charA
      onDialogueReady({ dialogueId, charA: leadingCharObj, charB: otherCharObj, leadingChar: leadingCharObj, initialTaskIds: [] })
    })
    } catch (err) {
      error = `Failed to start dialogue: ${err.message}`
      stage = 'scenario'
    }
  }
</script>

<div class="flex flex-col h-full overflow-y-auto p-4 gap-6">
  <!-- Header -->
  <div class="flex items-center gap-3">
    <button class="btn btn-ghost btn-sm" onclick={onBack}>
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="15 18 9 12 15 6"/>
      </svg>
      Back
    </button>
    <h1 class="text-xl font-bold">Scene Setup</h1>
  </div>

  {#if error}
    <div class="alert alert-error text-sm">
      <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
      </svg>
      {error}
    </div>
  {/if}

  <!-- Character pair — always visible -->
  <div class="grid grid-cols-2 gap-4">
    {#each [
      { name: charAName, avatarSrc: charAAvatarSrc, isRaw: charAIsRaw, summary: charASummary },
      { name: charBName, avatarSrc: charBAvatarSrc, isRaw: charBIsRaw, summary: charBSummary }
    ] as char}
      <div class="card bg-base-200 overflow-hidden">
        <!-- Avatar fills card top, 4:3 -->
        <div class="overflow-hidden bg-base-300 mx-auto" style="aspect-ratio: 3/4; width: min(100%, calc(400px * 3 / 4));">
          {#if char.avatarSrc}
            <img src={char.avatarSrc} alt={char.name} class="object-cover w-full h-full" />
          {:else}
            <div class="w-full h-full flex items-center justify-center text-base-content/20">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-12 h-12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
            </div>
          {/if}
        </div>
        <!-- Info -->
        <div class="p-3 flex flex-col gap-1">
          <div class="font-semibold">{char.name}</div>
          {#if char.summary}
            <div class="text-xs text-base-content/50 leading-relaxed line-clamp-3">{char.summary}</div>
          {/if}
          {#if char.isRaw}
            <div class="badge badge-warning badge-xs mt-1">raw — will repack</div>
          {:else}
            <div class="badge badge-success badge-xs mt-1">repacked</div>
          {/if}
        </div>
      </div>
    {/each}
  </div>

  <!-- Begin / pending state -->
  {#if stage === 'review' || stage === 'waiting-setup'}
    <div class="flex flex-col gap-3">
      <div class="text-sm text-base-content/60 bg-base-200 rounded-xl p-4">
        {#if charAIsRaw || charBIsRaw}
          <p class="mb-2">
            <span class="text-warning font-medium">
              {[charAIsRaw && charAName, charBIsRaw && charBName].filter(Boolean).join(' and ')}
            </span>
            {(charAIsRaw && charBIsRaw) ? ' need' : ' needs'} to be repacked first.
          </p>
        {/if}
        <p>Claude will generate an optimized scenario tailored to these two characters.</p>
      </div>
      <button class="btn btn-primary" onclick={beginSetup} disabled={stage === 'waiting-setup'}>
        {#if stage === 'waiting-setup'}
          <span class="loading loading-spinner loading-xs"></span>
        {/if}
        Begin
        {#if stage === 'review'}
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
        {/if}
      </button>
    </div>
  {/if}

  <!-- Scenario ready: pick leading char + opening -->
  {#if (stage === 'scenario' || stage === 'waiting-init') && scenario}
    {@const leadingScenario = scenario[selectedLeading === 'A' ? 'char_a' : 'char_b']}
    {@const openings = leadingScenario?.openings ?? []}

    <div class="flex flex-col gap-4">
      <!-- Scenario description -->
      <div class="bg-base-200 rounded-xl p-4 text-sm text-base-content/70 leading-relaxed">
        {leadingScenario?.scenario ?? ''}
      </div>

      <!-- Leading character selector -->
      <div class="flex flex-col gap-2">
        <div class="text-xs font-semibold text-base-content/50 uppercase tracking-wide">Leading character</div>
        <div class="grid grid-cols-2 gap-2">
          {#each [{ key: 'A', name: charAName }, { key: 'B', name: charBName }] as opt}
            <button
              class="btn btn-sm {selectedLeading === opt.key ? 'btn-primary' : 'btn-ghost border border-base-100'}"
              onclick={() => { selectedLeading = opt.key; selectedOpening = 0 }}
            >
              {opt.name}
            </button>
          {/each}
        </div>
      </div>

      <!-- Opening options -->
      <div class="flex flex-col gap-2">
        <div class="text-xs font-semibold text-base-content/50 uppercase tracking-wide">Opening line</div>
        {#each openings as opening, i}
          <button
            class="text-left rounded-xl p-3 text-sm leading-relaxed transition-colors border-2 {selectedOpening === i ? 'border-primary bg-primary/10' : 'border-transparent bg-base-200 hover:bg-base-100'}"
            onclick={() => selectedOpening = i}
          >
            {opening}
          </button>
        {/each}
      </div>

      <button
        class="btn btn-primary"
        onclick={initializeDialogue}
        disabled={selectedOpening === null || stage === 'waiting-init'}
      >
        {#if stage === 'waiting-init'}
          <span class="loading loading-spinner loading-xs"></span>
        {:else}
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
        {/if}
        Start Dialogue
      </button>
    </div>
  {/if}

</div>
