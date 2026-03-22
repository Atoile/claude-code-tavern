<script>
  import CharactersPanel from './lib/panels/CharactersPanel.svelte'
  import SceneSetupPanel from './lib/panels/SceneSetupPanel.svelte'
  import DialoguePanel from './lib/panels/DialoguePanel.svelte'
  import DialoguesPanel from './lib/panels/DialoguesPanel.svelte'
  import QueueStatus from './lib/components/QueueStatus.svelte'

  let activePanel = $state('characters')
  let sceneSetupData = $state(null)
  let dialogueData = $state(null)

  function startScene(data) {
    sceneSetupData = data
    activePanel = 'scene-setup'
  }

  function openDialogue(data) {
    dialogueData = data
    activePanel = 'dialogue'
  }

  function goToCharacters() {
    activePanel = 'characters'
    sceneSetupData = null
  }

  async function openSavedDialogue(dialogueId, charsInfo) {
    try {
      const res = await fetch('/api/characters')
      const all = await res.json()
      const findChar = (id) => all.find(c => c.id === id) || null

      // Uninitialized dialogue: leading/replying not yet determined → resume scene setup
      if (!charsInfo?.leading) {
        const charA = findChar(charsInfo?.charA?.id)
        const charB = findChar(charsInfo?.charB?.id)
        if (!charA || !charB) return
        sceneSetupData = { charA, charB, resumeDialogueId: dialogueId }
        activePanel = 'scene-setup'
        return
      }

      const leading = findChar(charsInfo.leading.id)
      const replying = findChar(charsInfo.replying.id)
      if (!leading || !replying) return
      dialogueData = { dialogueId, charA: leading, charB: replying, leadingChar: leading }
      activePanel = 'dialogue'
    } catch {}
  }
</script>

<div class="flex h-screen bg-base-300 text-base-content overflow-hidden">
  <!-- Sidebar -->
  <aside class="flex flex-col w-16 bg-base-200 border-r border-base-100 shrink-0 z-10 relative">
    <div class="flex flex-col items-center py-4 gap-2">
      <div class="text-primary font-bold text-xs mb-4 tracking-widest" style="writing-mode: vertical-rl; transform: rotate(180deg);">TAVERN</div>

      <!-- Characters -->
      <button
        class="btn btn-ghost btn-square btn-sm tooltip tooltip-right {activePanel === 'characters' || activePanel === 'scene-setup' ? 'btn-active bg-base-100' : ''}"
        data-tip="Characters"
        onclick={() => activePanel = 'characters'}
        aria-label="Characters"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>
      </button>

      <!-- Dialogues -->
      <button
        class="btn btn-ghost btn-square btn-sm tooltip tooltip-right {activePanel === 'dialogues' || activePanel === 'dialogue' ? 'btn-active bg-base-100' : ''}"
        data-tip="Dialogues"
        onclick={() => activePanel = 'dialogues'}
        aria-label="Dialogues"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      </button>

      <!-- Queue -->
      <button
        class="btn btn-ghost btn-square btn-sm tooltip tooltip-right {activePanel === 'queue' ? 'btn-active bg-base-100' : ''}"
        data-tip="Queue"
        onclick={() => activePanel = 'queue'}
        aria-label="Queue"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="8" y1="6" x2="21" y2="6"/>
          <line x1="8" y1="12" x2="21" y2="12"/>
          <line x1="8" y1="18" x2="21" y2="18"/>
          <line x1="3" y1="6" x2="3.01" y2="6"/>
          <line x1="3" y1="12" x2="3.01" y2="12"/>
          <line x1="3" y1="18" x2="3.01" y2="18"/>
        </svg>
      </button>
    </div>
  </aside>

  <!-- Main Content -->
  <main class="flex-1 overflow-hidden flex flex-col">
    {#if activePanel === 'characters'}
      <CharactersPanel onStartScene={startScene} />
    {:else if activePanel === 'scene-setup'}
      <SceneSetupPanel
        charA={sceneSetupData?.charA}
        charB={sceneSetupData?.charB}
        resumeDialogueId={sceneSetupData?.resumeDialogueId || null}
        onBack={goToCharacters}
        onDialogueReady={openDialogue}
      />
    {:else if activePanel === 'dialogues'}
      <DialoguesPanel
        onOpenDialogue={openSavedDialogue}
        onNewScene={goToCharacters}
      />
    {:else if activePanel === 'dialogue'}
      <DialoguePanel
        dialogueId={dialogueData?.dialogueId}
        charA={dialogueData?.charA}
        charB={dialogueData?.charB}
        leadingChar={dialogueData?.leadingChar}
onBack={() => activePanel = 'dialogues'}
      />
    {:else if activePanel === 'queue'}
      <QueueStatus standalone={true} />
    {/if}
  </main>
</div>
