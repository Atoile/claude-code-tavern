<script>
  import { onMount, onDestroy } from 'svelte'
  import { readQueue, appendToQueue } from '../stores/queue.js'
  import { marked } from 'marked'

  let { characters = [], onBack, onDialogueReady, resumeDialogueId = null } = $props()

  // stage: 'review' | 'waiting-setup' | 'scenario' | 'waiting-init'
  let stage = $state('review')
  let error = $state(null)
  let dialogueId = $state(null)
  let scenario = $state(null)
  let selectedLeadingId = $state(null)
  let selectedOpening = $state(null)
  let customOpeningText = $state('')
  let selectedPlayerId = $state(null)
  const playerModeEnabled = import.meta.env.TAVERN_VERBATIM === 'on'
  const narratorMode = import.meta.env.TAVERN_CHAT_MODE === 'narrator'
  let pollInterval = $state(null)
  let setupTaskIds = $state([])

  // Goals (narrator mode)
  let goalScene = $state('')
  let goalDescription = $state('')
  let goalSuccess = $state('')
  let goalPlayerRefuses = $state('')
  let goalNpcRefuses = $state('')

  function sanitizeName(name) {
    return (name || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
  }

  function rawDisplayName(c) {
    return c.filename?.replace(/\.png$/i, '').replace(/_/g, ' ') || 'Character'
  }

  function displayName(c) {
    if (!c) return 'Character'
    return c._isRaw ? rawDisplayName(c) : (c?.data?.meta?.name || c?.name || c?.id || 'Character')
  }

  function avatarSrcFor(c) {
    if (!c) return null
    return c._isRaw ? `/raw/${c.filename}` : (c?.avatarPath ? `/${c.avatarPath}` : null)
  }

  function summaryFor(c) {
    if (!c || c._isRaw) return null
    return c?.data?.identity?.background_summary || c?.data?.personality?.core_traits?.slice(0, 2).join(' · ') || null
  }

  function resolveCharId(c) {
    if (!c) return null
    return c._isRaw ? sanitizeName(displayName(c)) : c.id
  }

  // Derived per-character views, all driven by the `characters` array
  const charViews = $derived(characters.map(c => ({
    char: c,
    id: resolveCharId(c),
    name: displayName(c),
    avatarSrc: avatarSrcFor(c),
    isRaw: c?._isRaw === true,
    summary: summaryFor(c)
  })))

  const anyRaw = $derived(charViews.some(v => v.isRaw))
  const rawNames = $derived(charViews.filter(v => v.isRaw).map(v => v.name))

  onMount(async () => {
    if (!resumeDialogueId) return
    dialogueId = resumeDialogueId
    const res = await fetch(`/api/dialogue/${resumeDialogueId}/scenario`)
    if (res.ok) {
      scenario = await res.json()
      selectedLeadingId = charViews[0]?.id || null
      selectedOpening = 0
      stage = 'scenario'
    } else {
      stage = 'waiting-setup'
      pollInterval = setInterval(async () => {
        const r = await fetch(`/api/dialogue/${dialogueId}/scenario`)
        if (r.ok) {
          stopPolling()
          scenario = await r.json()
          selectedLeadingId = charViews[0]?.id || null
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

  function persistScene(id) {
    try {
      localStorage.setItem('tavern:active_scene', JSON.stringify({
        dialogueId: id,
        characters,
        savedAt: Date.now()
      }))
    } catch {}
  }

  function buildParticipantInput(view) {
    const c = view.char
    if (view.isRaw) {
      return { id: view.id, name: view.name, raw_path: `infrastructure/raw/${c.filename}`, needs_repack: true }
    }
    return { id: view.id, name: view.name, data_path: c.dataPath }
  }

  function buildParticipantsDict() {
    const out = {}
    for (const v of charViews) {
      out[v.id] = buildParticipantInput(v)
    }
    return out
  }

  async function beginSetup() {
    error = null
    if (charViews.length < 2) {
      error = 'Need at least 2 characters to start a scene.'
      return
    }
    const id = crypto.randomUUID()
    dialogueId = id
    persistScene(id)

    const tasks = []
    const repackIds = []

    for (const v of charViews) {
      if (!v.isRaw) continue
      const repackId = crypto.randomUUID()
      repackIds.push(repackId)
      tasks.push({
        id: repackId,
        type: 'repack_character',
        parallel: true,
        depends_on: [],
        model: 'claude-sonnet-4-6',
        input: { raw_path: `infrastructure/raw/${v.char.filename}`, character_name: v.name },
        output_path: `infrastructure/characters/${v.id}/data.json`,
        status: 'pending'
      })
    }

    // Create initial dialogue state so Claude Code can find characters
    await fetch(`/api/dialogue/${id}/characters`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ participants: buildParticipantsDict() })
    })

    if (narratorMode) {
      // Narrator mode: skip optimize_scenario. If raw chars need repacking, queue those.
      // Then go straight to goals stage.
      if (tasks.length > 0) {
        setupTaskIds = tasks.map(t => t.id)
        await appendToQueue(tasks)
        stage = 'waiting-setup'
        startPolling(setupTaskIds, () => {
          selectedLeadingId = charViews[0]?.id || null
          stage = 'goals'
        })
      } else {
        selectedLeadingId = charViews[0]?.id || null
        stage = 'goals'
      }
    } else {
      // Normal mode: queue optimize_scenario after any repacks
      const optimizeId = crypto.randomUUID()
      tasks.push({
        id: optimizeId,
        type: 'optimize_scenario',
        parallel: false,
        depends_on: repackIds,
        model: 'claude-sonnet-4-6',
        input: {
          dialogue_id: id,
          participants: charViews.map(v => buildParticipantInput(v))
        },
        output_path: `infrastructure/dialogues/${id}/scenario.json`,
        status: 'pending'
      })

      setupTaskIds = tasks.map(t => t.id)
      await appendToQueue(tasks)
      stage = 'waiting-setup'
      startPolling(setupTaskIds, onSetupComplete)
    }
  }

  async function onSetupComplete() {
    try {
      const res = await fetch(`/api/dialogue/${dialogueId}/scenario`)
      if (res.ok) {
        scenario = await res.json()
        selectedLeadingId = charViews[0]?.id || null
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

  const leadingScenarioBlock = $derived(
    selectedLeadingId && scenario?.participants?.[selectedLeadingId]
      ? scenario.participants[selectedLeadingId]
      : null
  )
  const openings = $derived(leadingScenarioBlock?.openings ?? [])

  async function initializeDialogue() {
    if (!selectedLeadingId) return
    error = null

    if (narratorMode) {
      return initializeNarratorDialogue()
    }

    if (selectedOpening === null && !customOpeningText.trim()) return
    stage = 'waiting-init'

    try {
      const selectedGreeting = customOpeningText.trim() || openings[selectedOpening]
      if (!selectedGreeting) {
        error = 'Write a custom opening or select one from the list.'
        stage = 'scenario'
        return
      }

      // Write the opening line directly
      const openingMessage = { speaker: selectedLeadingId, text: selectedGreeting }
      const chatInit = [openingMessage]
      await fetch(`/api/dialogue/${dialogueId}/full_chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(chatInit)
      })
      await fetch(`/api/dialogue/${dialogueId}/recent_chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(chatInit)
      })

      // Update characters.json with resolved leading_id and optional player_id
      const charsPayload = {
        participants: buildParticipantsDict(),
        leading_id: selectedLeadingId
      }
      if (playerModeEnabled && selectedPlayerId) {
        charsPayload.player_id = selectedPlayerId
      }
      await fetch(`/api/dialogue/${dialogueId}/characters`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(charsPayload)
      })

      // Queue the first reply
      const generateReplyId = crypto.randomUUID()
      await appendToQueue([{
        id: generateReplyId, type: 'generate_reply', parallel: false, depends_on: [],
        model: 'claude-sonnet-4-6',
        input: { dialogue_id: dialogueId, leading_char_id: selectedLeadingId },
        output_path: `infrastructure/dialogues/${dialogueId}/pending_turns.json`,
        status: 'pending'
      }])

      onDialogueReady({
        dialogueId, characters, leadingId: selectedLeadingId,
        playerId: (playerModeEnabled && selectedPlayerId) ? selectedPlayerId : null
      })
    } catch (err) {
      error = `Failed to start dialogue: ${err.message}`
      stage = 'scenario'
    }
  }

  async function initializeNarratorDialogue() {
    if (!goalScene.trim() || !goalDescription.trim()) {
      error = 'Scene description and goal are required.'
      stage = 'goals'
      return
    }
    stage = 'waiting-init'

    try {
      // Write goals.json (replaces scenario.json in narrator mode)
      const goalsData = {
        dialogue_id: dialogueId,
        scene: goalScene.trim(),
        goals: [{
          id: 'main_goal',
          description: goalDescription.trim(),
          priority: 'main',
          resolutions: {
            success: goalSuccess.trim() || 'Goal achieved.',
            player_refuses: goalPlayerRefuses.trim() || 'Player chose not to pursue this.',
            npc_refuses: goalNpcRefuses.trim() || 'NPC declined.'
          },
          status: 'active',
          resolved_as: null
        }]
      }
      await fetch(`/api/dialogue/${dialogueId}/goals`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(goalsData)
      })

      // Initialize empty chat files
      await fetch(`/api/dialogue/${dialogueId}/full_chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify([])
      })
      await fetch(`/api/dialogue/${dialogueId}/recent_chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify([])
      })

      // Update characters.json with leading_id, player_id, narrator flag
      const charsPayload = {
        participants: buildParticipantsDict(),
        leading_id: selectedLeadingId,
        narrator: true
      }
      if (playerModeEnabled && selectedPlayerId) {
        charsPayload.player_id = selectedPlayerId
      }
      await fetch(`/api/dialogue/${dialogueId}/characters`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(charsPayload)
      })

      // Queue the first generate_reply — NPCs will initiate the conversation
      await appendToQueue([{
        id: crypto.randomUUID(), type: 'generate_reply', parallel: false, depends_on: [],
        model: 'claude-sonnet-4-6',
        input: { dialogue_id: dialogueId, leading_char_id: selectedLeadingId },
        output_path: `infrastructure/dialogues/${dialogueId}/pending_turns.json`,
        status: 'pending'
      }])

      onDialogueReady({
        dialogueId, characters, leadingId: selectedLeadingId,
        playerId: (playerModeEnabled && selectedPlayerId) ? selectedPlayerId : null
      })
    } catch (err) {
      error = `Failed to start narrator dialogue: ${err.message}`
      stage = 'goals'
    }
  }
</script>

<div class="flex flex-col h-full overflow-y-auto p-4 gap-6">
  <!-- Header -->
  <div class="flex items-center gap-3">
    <button class="btn btn-ghost btn-sm" onclick={onBack}>
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" style="fill: none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="15 18 9 12 15 6"/>
      </svg>
      Back
    </button>
    <h1 class="text-xl font-bold">Scene Setup</h1>
  </div>

  {#if error}
    <div class="alert alert-error text-sm">
      <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 shrink-0" viewBox="0 0 24 24" style="fill: none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
      </svg>
      {error}
    </div>
  {/if}

  <!-- Participants — always visible -->
  <div class="grid gap-4" class:grid-cols-2={charViews.length === 2} class:grid-cols-3={charViews.length === 3}>
    {#each charViews as view (view.id)}
      <div class="card bg-base-200 overflow-hidden">
        <div class="overflow-hidden bg-base-300 mx-auto" style="aspect-ratio: 3/4; width: min(100%, calc(400px * 3 / 4));">
          {#if view.avatarSrc}
            <img src={view.avatarSrc} alt={view.name} class="object-cover w-full h-full" />
          {:else}
            <div class="w-full h-full flex items-center justify-center text-base-content/20">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-12 h-12" viewBox="0 0 24 24" style="fill: none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
            </div>
          {/if}
        </div>
        <div class="p-3 flex flex-col gap-1">
          <div class="font-semibold">{view.name}</div>
          {#if view.summary}
            <div class="text-xs text-base-content/50 leading-relaxed line-clamp-3">{view.summary}</div>
          {/if}
          {#if view.isRaw}
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
        {#if anyRaw}
          <p class="mb-2">
            <span class="text-warning font-medium">{rawNames.join(' and ')}</span>
            {rawNames.length > 1 ? ' need' : ' needs'} to be repacked first.
          </p>
        {/if}
        <p>Claude will generate an optimized scenario tailored to these {charViews.length} characters.</p>
      </div>
      <button class="btn btn-primary" onclick={beginSetup} disabled={stage === 'waiting-setup'}>
        {#if stage === 'waiting-setup'}
          <span class="loading loading-spinner loading-xs"></span>
        {/if}
        Begin
        {#if stage === 'review'}
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" style="fill: none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
        {/if}
      </button>
    </div>
  {/if}

  <!-- Scenario ready: pick leading char + opening -->
  {#if (stage === 'scenario' || stage === 'waiting-init') && scenario}
    <div class="flex flex-col gap-4">
      <!-- Scenario description -->
      <div class="bg-base-200 rounded-xl p-4 text-sm text-base-content/70 leading-relaxed">
        {leadingScenarioBlock?.scenario ?? ''}
      </div>

      <!-- Leading character selector -->
      <div class="flex flex-col gap-2">
        <div class="text-xs font-semibold text-base-content/50 uppercase tracking-wide">Leading character</div>
        <div class="grid gap-2" class:grid-cols-2={charViews.length === 2} class:grid-cols-3={charViews.length === 3}>
          {#each charViews as view (view.id)}
            <button
              class="btn btn-sm {selectedLeadingId === view.id ? 'btn-primary' : 'btn-ghost border border-base-100'}"
              onclick={() => { selectedLeadingId = view.id; selectedOpening = 0 }}
            >
              {view.name}
            </button>
          {/each}
        </div>
      </div>

      <!-- Player character picker (visible when TAVERN_VERBATIM=on) -->
      {#if playerModeEnabled}
        <div class="flex flex-col gap-2">
          <div class="text-xs font-semibold text-base-content/50 uppercase tracking-wide">Play as</div>
          <div class="grid gap-2" class:grid-cols-2={charViews.length === 2} class:grid-cols-3={charViews.length === 3}>
            {#each charViews as view (view.id)}
              <button
                class="btn btn-sm {selectedPlayerId === view.id ? 'btn-secondary' : 'btn-ghost border border-base-100'}"
                onclick={() => selectedPlayerId = view.id}
              >
                {view.name}
              </button>
            {/each}
          </div>
        </div>
      {/if}

      <!-- Opening options -->
      <div class="flex flex-col gap-2">
        <div class="text-xs font-semibold text-base-content/50 uppercase tracking-wide">Opening line</div>

        <!-- Custom opening -->
        <div class="flex flex-col gap-1">
          <textarea
            class="textarea textarea-bordered text-sm leading-relaxed w-full min-h-[120px] transition-colors border-2 {customOpeningText.trim() ? 'border-secondary bg-secondary/10' : 'border-transparent'}"
            placeholder="Write your own opening..."
            bind:value={customOpeningText}
            onfocus={() => selectedOpening = null}
          ></textarea>
          {#if customOpeningText.trim()}
            <div class="text-xs text-secondary/60">Custom opening active — generated options below are deselected</div>
          {/if}
        </div>

        <div class="divider text-xs text-base-content/30 my-0">or pick a generated opening</div>

        {#each openings as opening, i (i)}
          <button
            class="text-left rounded-xl p-3 text-sm leading-relaxed transition-colors border-2 {selectedOpening === i && !customOpeningText.trim() ? 'border-primary bg-primary/10' : 'border-transparent bg-base-200 hover:bg-base-100'}"
            onclick={() => { selectedOpening = i; customOpeningText = '' }}
          >
            <!-- eslint-disable-next-line svelte/no-at-html-tags -->
            {@html marked.parse(opening, { breaks: true })}
          </button>
        {/each}
      </div>

      <button
        class="btn btn-primary"
        onclick={initializeDialogue}
        disabled={(selectedOpening === null && !customOpeningText.trim()) || stage === 'waiting-init'}
      >
        {#if stage === 'waiting-init'}
          <span class="loading loading-spinner loading-xs"></span>
        {:else}
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" style="fill: none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
        {/if}
        Start Dialogue
      </button>
    </div>
  {/if}

  <!-- Narrator mode: goals setup -->
  {#if (stage === 'goals' || stage === 'waiting-init') && narratorMode}
    <div class="flex flex-col gap-4">
      <!-- Leading character selector -->
      <div class="flex flex-col gap-2">
        <div class="text-xs font-semibold text-base-content/50 uppercase tracking-wide">Leading character</div>
        <div class="grid gap-2" class:grid-cols-2={charViews.length === 2} class:grid-cols-3={charViews.length === 3}>
          {#each charViews as view (view.id)}
            <button
              class="btn btn-sm {selectedLeadingId === view.id ? 'btn-primary' : 'btn-ghost border border-base-100'}"
              onclick={() => selectedLeadingId = view.id}
            >
              {view.name}
            </button>
          {/each}
        </div>
      </div>

      <!-- Player character picker (when TAVERN_VERBATIM=on) -->
      {#if playerModeEnabled}
        <div class="flex flex-col gap-2">
          <div class="text-xs font-semibold text-base-content/50 uppercase tracking-wide">Play as</div>
          <div class="grid gap-2" class:grid-cols-2={charViews.length === 2} class:grid-cols-3={charViews.length === 3}>
            {#each charViews as view (view.id)}
              <button
                class="btn btn-sm {selectedPlayerId === view.id ? 'btn-secondary' : 'btn-ghost border border-base-100'}"
                onclick={() => selectedPlayerId = view.id}
              >
                {view.name}
              </button>
            {/each}
          </div>
        </div>
      {/if}

      <!-- Scene description -->
      <div class="flex flex-col gap-1">
        <div class="text-xs font-semibold text-base-content/50 uppercase tracking-wide">Scene</div>
        <textarea
          class="textarea textarea-bordered text-sm leading-relaxed w-full min-h-[80px]"
          placeholder="Where and when does this take place? Who is present? What's the atmosphere?"
          bind:value={goalScene}
        ></textarea>
      </div>

      <!-- Main goal -->
      <div class="flex flex-col gap-1">
        <div class="text-xs font-semibold text-base-content/50 uppercase tracking-wide">Goal</div>
        <input
          type="text"
          class="input input-bordered input-sm text-sm"
          placeholder="What is this conversation trying to accomplish?"
          bind:value={goalDescription}
        />
      </div>

      <!-- Resolutions -->
      <div class="flex flex-col gap-2">
        <div class="text-xs font-semibold text-base-content/50 uppercase tracking-wide">Possible resolutions</div>
        <input type="text" class="input input-bordered input-sm text-sm" placeholder="Success — what happens if the goal succeeds?" bind:value={goalSuccess} />
        <input type="text" class="input input-bordered input-sm text-sm" placeholder="Player refuses — what if the player walks away?" bind:value={goalPlayerRefuses} />
        <input type="text" class="input input-bordered input-sm text-sm" placeholder="NPC refuses — what if the NPC declines?" bind:value={goalNpcRefuses} />
      </div>

      <button
        class="btn btn-primary"
        onclick={initializeDialogue}
        disabled={!goalScene.trim() || !goalDescription.trim() || !selectedLeadingId || stage === 'waiting-init'}
      >
        {#if stage === 'waiting-init'}
          <span class="loading loading-spinner loading-xs"></span>
        {:else}
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" style="fill: none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
        {/if}
        Start Conversation
      </button>
    </div>
  {/if}
</div>
