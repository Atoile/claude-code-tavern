<script>
  import { onMount, onDestroy, tick } from 'svelte'
  import { readQueue, appendToQueue } from '../stores/queue.js'
  import { marked } from 'marked'
  import ChatBubble from '../components/ChatBubble.svelte'

  let { dialogueId, characters = [], leadingId, playerId = null, onBack } = $props()

  // Fallback palette for characters without a custom color
  const FALLBACK_PALETTE = ['#9d174d', '#1e3a8a', '#065f46', '#7c2d12']

  // Compute readable text color from background hex using WCAG relative luminance
  function textColorFor(bg) {
    const hex = bg.replace('#', '')
    const srgb = [
      parseInt(hex.substring(0, 2), 16) / 255,
      parseInt(hex.substring(2, 4), 16) / 255,
      parseInt(hex.substring(4, 6), 16) / 255,
    ].map(c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
    const luminance = 0.2126 * srgb[0] + 0.7152 * srgb[1] + 0.0722 * srgb[2]
    return luminance > 0.25 ? '#1a1a1a' : '#f5f5f5'
  }

  function makeBubbleStyle(bg) {
    return { background: bg, color: textColorFor(bg) }
  }

  let messages = $state([])
  let sceneGoal = $state(null)
  let hasCheckpoint = $state(false)
  let hasMemory = $state(false)
  let isPolling = $state(false)
  let hasPendingTbc = $state(false)
  let dialogueComplete = $state(null)
  let pollInterval = null
  let directionText = $state('')
  let showDirectionInput = $state(false)
  let playerText = $state('')
  let error = $state(null)
  let chatContainer

  const isPlayerMode = $derived(!!playerId)
  const playerInputBlocked = $derived(isPlayerMode && hasPendingTbc)
  const narratorMode = import.meta.env.TAVERN_CHAT_MODE === 'narrator'

  function sanitizeName(name) {
    return (name || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
  }

  function displayName(c) {
    if (!c) return 'Character'
    if (c._isRaw) return c.filename?.replace(/\.png$/i, '').replace(/_/g, ' ') || 'Character'
    return c?.data?.meta?.name || c?.name || c?.id || 'Character'
  }

  function avatarSrcFor(c) {
    if (!c) return null
    if (c._isRaw) return null
    return c?.avatarPath ? `/${c.avatarPath}` : null
  }

  function resolveCharId(c) {
    if (!c) return null
    return c._isRaw ? sanitizeName(displayName(c)) : c.id
  }

  // Per-character lookup map: { [id]: { name, avatarSrc, isLeading, bubbleStyle } }
  const characterMap = $derived.by(() => {
    const map = {}
    let fallbackIndex = 0
    for (const c of characters) {
      const id = resolveCharId(c)
      if (!id) continue
      const isLeading = id === leadingId
      const charColor = c.data?.meta?.color
      const bg = charColor || FALLBACK_PALETTE[fallbackIndex % FALLBACK_PALETTE.length]
      if (!charColor) fallbackIndex++
      map[id] = {
        id,
        name: displayName(c),
        avatarSrc: avatarSrcFor(c),
        isLeading,
        bubbleStyle: makeBubbleStyle(bg)
      }
    }
    return map
  })

  const leadingChar = $derived(leadingId ? characterMap[leadingId] : null)
  const nonLeadingChars = $derived(Object.values(characterMap).filter(c => !c.isLeading))

  onMount(() => {
    loadMessages()
    startQueueWatcher()
  })

  onDestroy(() => {
    stopPolling()
  })

  async function loadMessages(scrollAfter = true) {
    try {
      const [chatRes, cpRes, memRes] = await Promise.all([
        fetch(`/api/dialogue/${dialogueId}/full_chat`),
        fetch(`/api/file-exists?path=infrastructure/dialogues/${dialogueId}/memory_checkpoint.json`),
        fetch(`/api/file-exists?path=infrastructure/dialogues/${dialogueId}/memory.json`)
      ])
      if (chatRes.ok) {
        const data = await chatRes.json()
        messages = Array.isArray(data) ? data : (data.messages || [])
        await tick()
        if (scrollAfter) scrollToBottom()
      }
      if (cpRes.ok) {
        const cpData = await cpRes.json()
        hasCheckpoint = cpData.exists
      }
      if (memRes.ok) {
        const memData = await memRes.json()
        hasMemory = memData.exists
      }
      // Check for pending TBC (NPC freeze that blocks player input)
      try {
        const tbcRes = await fetch(`/api/file-exists?path=infrastructure/dialogues/${dialogueId}/tbc.json`)
        if (tbcRes.ok) {
          const tbcData = await tbcRes.json()
          hasPendingTbc = tbcData.exists
        }
      } catch {}
      // Check for dialogue completion (goal resolved, conversation closed)
      try {
        const completeRes = await fetch(`/api/dialogue/${dialogueId}/complete`)
        if (completeRes.ok) {
          dialogueComplete = await completeRes.json()
        }
      } catch {}
      // Load scene goal for narrator mode (shown at top of chat)
      if (!sceneGoal) {
        try {
          const goalsRes = await fetch(`/api/dialogue/${dialogueId}/goals`)
          if (goalsRes.ok) {
            const goalsData = await goalsRes.json()
            const mainGoal = goalsData?.goals?.find(g => g.priority === 'main')
            if (mainGoal) sceneGoal = mainGoal
          }
        } catch {}
      }
    } catch (err) {
      error = `Failed to load messages: ${err.message}`
    }
  }

  function scrollToBottom() {
    if (chatContainer) {
      chatContainer.scrollTop = chatContainer.scrollHeight
    }
  }

  function isNearBottom() {
    if (!chatContainer) return true
    return chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight < 120
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval)
      pollInterval = null
    }
    isPolling = false
  }

  function startQueueWatcher() {
    stopPolling()
    let wasActive = false
    pollInterval = setInterval(async () => {
      const q = await readQueue()
      const active = q.filter(item =>
        item.input?.dialogue_id === dialogueId &&
        item.status !== 'error'
      )
      const nowActive = active.length > 0
      if (nowActive !== isPolling) isPolling = nowActive

      if (nowActive) {
        try {
          const previewRes = await fetch(`/api/dialogue/${dialogueId}/preview_turn`)
          if (previewRes.ok) {
            const preview = await previewRes.json()
            const previews = Array.isArray(preview) ? preview : (preview?.text ? [preview] : [])
            if (previews.length > 0) {
              messages = [...messages.filter(m => !m._preview), ...previews]
              await tick()
              if (isNearBottom()) scrollToBottom()
            }
          }
        } catch {}
      }

      if (wasActive && !nowActive) await loadMessages(isNearBottom())
      wasActive = nowActive
    }, 2000)
  }

  async function handlePlayerSend() {
    if (!playerText.trim() || !playerId) return
    error = null
    const text = playerText.trim()
    playerText = ''

    // Write the player's line directly to chat (same pattern as opening-line write)
    const playerMsg = { speaker: playerId, text }
    const chatRes = await fetch(`/api/dialogue/${dialogueId}/recent_chat`)
    const fullRes = await fetch(`/api/dialogue/${dialogueId}/full_chat`)
    const recent = chatRes.ok ? await chatRes.json() : []
    const full = fullRes.ok ? await fullRes.json() : []

    await Promise.all([
      fetch(`/api/dialogue/${dialogueId}/recent_chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify([...(Array.isArray(recent) ? recent : []), playerMsg].slice(-10))
      }),
      fetch(`/api/dialogue/${dialogueId}/full_chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify([...(Array.isArray(full) ? full : []), playerMsg])
      })
    ])

    await loadMessages()

    // Queue generate_reply — NPCs will react to the player's line
    const input = { dialogue_id: dialogueId, leading_char_id: leadingId }
    if (directionText.trim()) {
      input.user_prompt = directionText.trim()
      directionText = ''
      showDirectionInput = false
    }
    await appendToQueue([{
      id: crypto.randomUUID(),
      type: 'generate_reply',
      parallel: false,
      depends_on: [],
      model: 'claude-sonnet-4-6',
      input,
      output_path: `infrastructure/dialogues/${dialogueId}/pending_turns.json`,
      status: 'pending'
    }])
  }

  async function handleContinue() {
    if (isPlayerMode) {
      // In player mode, Continue without text = "Skip" — NPCs continue without player input
      if (playerText.trim()) return handlePlayerSend()
    }
    if (showDirectionInput && directionText.trim()) {
      return handleContinueWithDirection()
    }
    error = null
    const taskId = crypto.randomUUID()
    const tasks = [{
      id: taskId,
      type: 'generate_reply',
      parallel: false,
      depends_on: [],
      model: 'claude-sonnet-4-6',
      input: {
        dialogue_id: dialogueId,
        leading_char_id: leadingId
      },
      output_path: `infrastructure/dialogues/${dialogueId}/pending_turns.json`,
      status: 'pending'
    }]
    await appendToQueue(tasks)
  }

  async function handleContinueWithDirection() {
    if (!directionText.trim()) return
    error = null
    const taskId = crypto.randomUUID()
    const tasks = [{
      id: taskId,
      type: 'generate_reply',
      parallel: false,
      depends_on: [],
      model: 'claude-sonnet-4-6',
      input: {
        dialogue_id: dialogueId,
        leading_char_id: leadingId,
        user_prompt: directionText.trim()
      },
      output_path: `infrastructure/dialogues/${dialogueId}/pending_turns.json`,
      status: 'pending'
    }]
    await appendToQueue(tasks)
    directionText = ''
    showDirectionInput = false
  }

  async function handleContinueFromComplete() {
    await fetch(`/api/dialogue/${dialogueId}/complete`, { method: 'DELETE' })
    dialogueComplete = null
    await handleContinue()
  }

  async function handleRollback() {
    try {
      const [fullChatRes, checkpointRes] = await Promise.all([
        fetch(`/api/dialogue/${dialogueId}/full_chat`),
        fetch(`/api/dialogue/${dialogueId}/memory_checkpoint`)
      ])
      if (!fullChatRes.ok) return
      const fullChat = await fullChatRes.json()
      const msgs = Array.isArray(fullChat) ? fullChat : (fullChat.messages || [])
      // Need at least 2 messages so we don't roll back past the opening line
      if (msgs.length < 2) return

      const checkpoint = checkpointRes.ok ? await checkpointRes.json() : null

      // Rollback removes exactly one turn — the single most recent entry.
      const trimmed = msgs.slice(0, -1)
      const removed = msgs.slice(-1)
      return doRollback(trimmed, removed, checkpoint)
    } catch (err) {
      error = `Rollback failed: ${err.message}`
    }
  }

  async function doRollback(trimmed, removed, checkpoint) {
    const replyHistoryRes = await fetch(`/api/dialogue/${dialogueId}/reply_history`)
    const replyHistory = replyHistoryRes.ok ? await replyHistoryRes.json() : null
    const trimmedHistory = Array.isArray(replyHistory) && replyHistory.length > 0
      ? replyHistory.slice(0, -1)
      : replyHistory

    const lastTurn = trimmed.at(-1)
    const restoredState = lastTurn?._state ?? null
    const restoredPrompt = removed[0]?._prompt ?? null

    const rollbackOps = [
      fetch(`/api/dialogue/${dialogueId}/full_chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(trimmed)
      }),
      fetch(`/api/dialogue/${dialogueId}/recent_chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(trimmed.slice(-10))
      }),
      restoredState
        ? fetch(`/api/dialogue/${dialogueId}/turn_state`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(restoredState)
          })
        : fetch(`/api/dialogue/${dialogueId}/turn_state`, { method: 'DELETE' }),
      fetch(`/api/dialogue/${dialogueId}/short_memory`, { method: 'DELETE' }),
      trimmedHistory !== null
        ? fetch(`/api/dialogue/${dialogueId}/reply_history`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(trimmedHistory)
          })
        : Promise.resolve()
    ]

    if (checkpoint && trimmed.length < checkpoint.condensed_at) {
      rollbackOps.push(
        fetch(`/api/dialogue/${dialogueId}/memory`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(checkpoint.memory)
        }),
        fetch(`/api/dialogue/${dialogueId}/memory_checkpoint`, { method: 'DELETE' })
      )
      hasCheckpoint = false
    }

    await Promise.all(rollbackOps)
    await loadMessages()

    if (restoredPrompt) {
      directionText = restoredPrompt
      showDirectionInput = true
    }
  }

  function lookupCharForMessage(msg) {
    if (!msg) return null
    const speaker = msg.speaker || msg.character_id || msg.char_id || msg.name || ''
    return characterMap[speaker] || null
  }

  function isLeadingMessage(msg) {
    return lookupCharForMessage(msg)?.isLeading === true
  }

  function getMessageName(msg) {
    return lookupCharForMessage(msg)?.name || (msg?.speaker ?? '')
  }

  function getAvatarSrc(msg) {
    return lookupCharForMessage(msg)?.avatarSrc || null
  }

  function getBubbleStyle(msg) {
    return lookupCharForMessage(msg)?.bubbleStyle || null
  }
</script>

<div class="flex flex-col h-full">
  <!-- Header -->
  <div class="flex items-center gap-3 px-4 py-3 border-b border-base-100 bg-base-200 shrink-0">
    <button class="btn btn-ghost btn-sm btn-square" onclick={onBack} aria-label="Back">
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" style="fill: none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="15 18 9 12 15 6"/>
      </svg>
    </button>

    <!-- Participant chips: non-leading on the left, leading on the right -->
    <div class="flex items-center gap-2 flex-1 flex-wrap">
      {#each nonLeadingChars as c, i (c.id)}
        {#if i > 0}<span class="text-base-content/30 text-xs">·</span>{/if}
        {#if c.avatarSrc}
          <div class="avatar">
            <div class="w-7 h-7 rounded-full overflow-hidden">
              <img src={c.avatarSrc} alt={c.name} class="object-cover w-full h-full" />
            </div>
          </div>
        {/if}
        <span class="text-sm text-base-content/60">{c.name}</span>
      {/each}
      {#if leadingChar && nonLeadingChars.length > 0}
        <span class="text-base-content/30 text-xs">×</span>
      {/if}
      {#if leadingChar}
        <span class="text-sm font-medium">{leadingChar.name}</span>
        {#if leadingChar.avatarSrc}
          <div class="avatar">
            <div class="w-7 h-7 rounded-full overflow-hidden">
              <img src={leadingChar.avatarSrc} alt={leadingChar.name} class="object-cover w-full h-full" />
            </div>
          </div>
        {/if}
      {/if}
    </div>

    {#if isPolling}
      <span class="loading loading-spinner loading-xs text-primary"></span>
    {/if}
  </div>

  {#if error}
    <div class="alert alert-error text-sm mx-4 mt-2 shrink-0">
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" style="fill: none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
      </svg>
      {error}
    </div>
  {/if}

  <!-- Chat area -->
  <div class="flex-1 overflow-y-auto px-4 py-4" bind:this={chatContainer}>
    {#if sceneGoal}
      <div class="rounded-xl px-4 py-3 mb-4 text-sm leading-relaxed" style="background-color: #92400e20; border: 1px solid #92400e40; color: #fbbf24;">
        <div class="text-xs font-semibold uppercase tracking-wide mb-1" style="color: #d97706;">Goal</div>
        <div>{sceneGoal.description}</div>
      </div>
    {/if}

    {#if messages.length === 0 && !isPolling}
      <div class="text-center text-base-content/30 text-sm mt-16">
        No messages yet.
      </div>
    {/if}

    {#each messages as msg, i (i)}
      {#if msg.speaker === '_narrator' || msg.type === 'narration'}
        <!-- Narrator beat — centered, grey background, constrained width -->
        <div class="flex justify-center py-2">
          <div class="text-sm text-base-content/60 italic leading-relaxed rounded-lg px-4 py-2" style="max-width: 60%; background-color: color-mix(in srgb, currentColor 8%, transparent);">
            <!-- eslint-disable-next-line svelte/no-at-html-tags -->
            {@html marked.parse(msg.content || msg.text || '', { breaks: true })}
          </div>
        </div>
      {:else}
        <ChatBubble
          message={msg}
          isLeading={isLeadingMessage(msg)}
          characterName={getMessageName(msg)}
          avatarSrc={getAvatarSrc(msg)}
          bubbleStyle={getBubbleStyle(msg)}
        />
      {/if}
    {/each}

    {#if isPolling}
      <div class="flex items-center gap-2 text-sm text-base-content/40 mt-4 px-2">
        <span class="loading loading-dots loading-xs"></span>
        Generating...
      </div>
    {/if}
  </div>

  <!-- Controls -->
  <div class="shrink-0 border-t border-base-100 bg-base-200 px-4 py-3">
    {#if dialogueComplete}
      <!-- Dialogue completed — goal resolved -->
      <div class="flex items-center gap-3 text-sm">
        <div class="badge badge-success badge-sm">Complete</div>
        <span class="text-base-content/60">
          {dialogueComplete.outcome === 'success' ? 'Goal achieved' : dialogueComplete.outcome === 'npc_refuses' ? 'NPC declined' : dialogueComplete.outcome === 'player_refuses' ? 'Player withdrew' : dialogueComplete.outcome}
          {#if dialogueComplete.detail} — {dialogueComplete.detail}{/if}
        </span>
        {#if !narratorMode}
          <button class="btn btn-primary btn-sm" onclick={handleContinueFromComplete} disabled={isPolling}>
            Continue
          </button>
        {/if}
      </div>
    {:else if isPlayerMode && !playerInputBlocked}
      <!-- Player character input (hidden when NPC TBC is pending) -->
      <div class="flex gap-2 mb-3">
        <input
          type="text"
          placeholder="Type as your character..."
          class="input input-bordered input-sm flex-1 text-sm"
          bind:value={playerText}
          onkeydown={(e) => e.key === 'Enter' && handlePlayerSend()}
          disabled={isPolling}
        />
        <button class="btn btn-primary btn-sm" onclick={handlePlayerSend} disabled={!playerText.trim() || isPolling}>
          Send
        </button>
      </div>
    {:else}
      <!-- Normal controls (hidden when dialogue is complete) -->
      {#if showDirectionInput}
        <div class="flex gap-2 mb-3">
          <input
            type="text"
            placeholder="Direction for the scene..."
            class="input input-bordered input-sm flex-1 text-sm"
            bind:value={directionText}
            onkeydown={(e) => e.key === 'Enter' && (isPlayerMode ? handlePlayerSend() : handleContinueWithDirection())}
          />
          {#if !isPlayerMode}
            <button class="btn btn-primary btn-sm" onclick={handleContinueWithDirection} disabled={!directionText.trim()}>
              Send
            </button>
          {/if}
          <button class="btn btn-ghost btn-sm" onclick={() => { showDirectionInput = false; directionText = '' }}>
            Cancel
          </button>
        </div>
      {/if}

      <div class="flex gap-2 flex-wrap">
        {#if !isPlayerMode || playerInputBlocked}
          <button
            class="btn btn-primary btn-sm"
            onclick={handleContinue}
            disabled={isPolling}
          >
            {#if isPolling}
              <span class="loading loading-spinner loading-xs"></span>
            {/if}
            Continue
          </button>
        {:else}
          <button
            class="btn btn-ghost btn-sm"
            onclick={handleContinue}
            disabled={isPolling}
          >
            {#if isPolling}
              <span class="loading loading-spinner loading-xs"></span>
            {/if}
            Skip
          </button>
        {/if}

        <button
          class="btn btn-ghost btn-sm"
          onclick={() => showDirectionInput = !showDirectionInput}
          disabled={isPolling}
        >
          + Direction
        </button>

        {#if messages.length >= 2 && (!hasMemory || hasCheckpoint)}
          <button
            class="btn btn-ghost btn-sm text-error"
            onclick={handleRollback}
            disabled={isPolling}
          >
            Rollback
          </button>
        {/if}

        <button
          class="btn btn-ghost btn-sm ml-auto"
          onclick={loadMessages}
          disabled={isPolling}
          aria-label="Refresh"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" style="fill: none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
        </button>
      </div>
    {/if}
  </div>
</div>
