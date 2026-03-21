<script>
  import { onMount, onDestroy, tick } from 'svelte'
  import { readQueue, appendToQueue } from '../stores/queue.js'
  import ChatBubble from '../components/ChatBubble.svelte'

  let { dialogueId, charA, charB, onBack, initialTaskIds = [] } = $props()

  // charA = leading char, charB = replying char (passed from SceneSetupPanel after init)
  // leadingChar = same as charA here

  let messages = $state([])
  let hasCheckpoint = $state(false)
  let isPolling = $state(false)
  let pollInterval = null
  let directionText = $state('')
  let showDirectionInput = $state(false)
  let error = $state(null)
  let chatContainer

  function sanitizeName(name) {
    return (name || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
  }

  const leadingName = $derived(charA?._isRaw
    ? charA.filename?.replace(/\.png$/i, '')
    : (charA?.data?.meta?.name || charA?.name || charA?.id || 'Character A'))

  const replyingName = $derived(charB?._isRaw
    ? charB.filename?.replace(/\.png$/i, '')
    : (charB?.data?.meta?.name || charB?.name || charB?.id || 'Character B'))

  const leadingAvatarSrc = $derived((!charA?._isRaw && charA?.avatarPath) ? `/${charA.avatarPath}` : null)
  const replyingAvatarSrc = $derived((!charB?._isRaw && charB?.avatarPath) ? `/${charB.avatarPath}` : null)

  const leadingId = $derived(charA?._isRaw ? sanitizeName(leadingName) : charA?.id)
  const replyingId = $derived(charB?._isRaw ? sanitizeName(replyingName) : charB?.id)

  onMount(() => {
    loadMessages()
    if (initialTaskIds.length > 0) {
      startPolling(initialTaskIds)
    }
  })

  onDestroy(() => {
    stopPolling()
  })

  async function loadMessages() {
    try {
      const [chatRes, cpRes] = await Promise.all([
        fetch(`/api/dialogue/${dialogueId}/recent_chat`),
        fetch(`/api/file-exists?path=infrastructure/dialogues/${dialogueId}/memory_checkpoint.json`)
      ])
      if (chatRes.ok) {
        const data = await chatRes.json()
        messages = Array.isArray(data) ? data : (data.messages || [])
        await tick()
        scrollToBottom()
      }
      if (cpRes.ok) {
        const cpData = await cpRes.json()
        hasCheckpoint = cpData.exists
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

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval)
      pollInterval = null
    }
    isPolling = false
  }

  function startPolling(taskIds) {
    stopPolling()
    isPolling = true
    pollInterval = setInterval(async () => {
      const q = await readQueue()
      const ourTasks = q.filter(item => taskIds.includes(item.id))
      const allDone = ourTasks.every(item => item.status === 'done' || item.status === 'error')
      const allGone = ourTasks.length === 0
      if (allDone || allGone) {
        stopPolling()
        await loadMessages()
      }
    }, 2000)
  }

  async function handleContinue() {
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
        replying_char_id: replyingId,
        both_chars: true
      },
      output_path: `infrastructure/dialogues/${dialogueId}/pending_turns.json`,
      status: 'pending'
    }]
    await appendToQueue(tasks)
    startPolling([taskId])
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
        replying_char_id: replyingId,
        both_chars: true,
        user_prompt: directionText.trim()
      },
      output_path: `infrastructure/dialogues/${dialogueId}/pending_turns.json`,
      status: 'pending'
    }]
    await appendToQueue(tasks)
    directionText = ''
    showDirectionInput = false
    startPolling([taskId])
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
      if (msgs.length < 2) return

      const checkpoint = checkpointRes.ok ? await checkpointRes.json() : null
      const trimmed = msgs.slice(0, -2)

      await Promise.all([
        fetch(`/api/dialogue/${dialogueId}/full_chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(trimmed)
        }),
        fetch(`/api/dialogue/${dialogueId}/recent_chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(trimmed.slice(-10))
        })
      ])

      // If rollback crossed the last condensing boundary, restore memory from checkpoint
      if (checkpoint && trimmed.length < checkpoint.condensed_at) {
        await Promise.all([
          fetch(`/api/dialogue/${dialogueId}/memory`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(checkpoint.memory)
          }),
          fetch(`/api/dialogue/${dialogueId}/memory_checkpoint`, { method: 'DELETE' }),
          fetch(`/api/dialogue/${dialogueId}/short_memory`, { method: 'DELETE' })
        ])
        hasCheckpoint = false
      }

      await loadMessages()
    } catch (err) {
      error = `Rollback failed: ${err.message}`
    }
  }

  function isLeadingMessage(msg) {
    if (!msg) return false
    const speaker = msg.speaker || msg.character_id || msg.char_id || msg.name || ''
    return speaker === leadingId || speaker === leadingName
  }

  function getMessageName(msg) {
    if (!msg) return ''
    const speaker = msg.speaker || msg.character_id || msg.char_id || msg.name || ''
    if (speaker === leadingId || speaker === leadingName) return leadingName
    return replyingName
  }

  function getAvatarSrc(msg) {
    if (isLeadingMessage(msg)) return leadingAvatarSrc
    return replyingAvatarSrc
  }
</script>

<div class="flex flex-col h-full">
  <!-- Header -->
  <div class="flex items-center gap-3 px-4 py-3 border-b border-base-100 bg-base-200 shrink-0">
    <button class="btn btn-ghost btn-sm btn-square" onclick={onBack} aria-label="Back">
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="15 18 9 12 15 6"/>
      </svg>
    </button>

    <!-- Character pair header -->
    <div class="flex items-center gap-2 flex-1">
      {#if replyingAvatarSrc}
        <div class="avatar">
          <div class="w-7 h-7 rounded-full overflow-hidden">
            <img src={replyingAvatarSrc} alt={replyingName} class="object-cover w-full h-full" />
          </div>
        </div>
      {/if}
      <span class="text-sm text-base-content/60">{replyingName}</span>
      <span class="text-base-content/30 text-xs">×</span>
      <span class="text-sm font-medium">{leadingName}</span>
      {#if leadingAvatarSrc}
        <div class="avatar">
          <div class="w-7 h-7 rounded-full overflow-hidden">
            <img src={leadingAvatarSrc} alt={leadingName} class="object-cover w-full h-full" />
          </div>
        </div>
      {/if}
    </div>

    {#if isPolling}
      <span class="loading loading-spinner loading-xs text-primary"></span>
    {/if}
  </div>

  {#if error}
    <div class="alert alert-error text-sm mx-4 mt-2 shrink-0">
      <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
      </svg>
      {error}
    </div>
  {/if}

  <!-- Chat area -->
  <div class="flex-1 overflow-y-auto px-4 py-4" bind:this={chatContainer}>
    {#if messages.length === 0 && !isPolling}
      <div class="text-center text-base-content/30 text-sm mt-16">
        No messages yet.
      </div>
    {/if}

    {#each messages as msg, i (i)}
      <ChatBubble
        message={msg}
        isLeading={isLeadingMessage(msg)}
        characterName={getMessageName(msg)}
        avatarSrc={getAvatarSrc(msg)}
      />
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
    {#if showDirectionInput}
      <div class="flex gap-2 mb-3">
        <input
          type="text"
          placeholder="Direction for the scene..."
          class="input input-bordered input-sm flex-1 text-sm"
          bind:value={directionText}
          onkeydown={(e) => e.key === 'Enter' && handleContinueWithDirection()}
        />
        <button class="btn btn-primary btn-sm" onclick={handleContinueWithDirection} disabled={!directionText.trim()}>
          Send
        </button>
        <button class="btn btn-ghost btn-sm" onclick={() => { showDirectionInput = false; directionText = '' }}>
          Cancel
        </button>
      </div>
    {/if}

    <div class="flex gap-2 flex-wrap">
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

      <button
        class="btn btn-ghost btn-sm"
        onclick={() => showDirectionInput = !showDirectionInput}
        disabled={isPolling}
      >
        + Direction
      </button>

      {#if hasCheckpoint}
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
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="23 4 23 10 17 10"/>
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg>
      </button>
    </div>
  </div>
</div>
