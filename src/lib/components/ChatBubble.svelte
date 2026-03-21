<script>
  import { marked } from 'marked'

  let { message, isLeading = false, characterName = '', avatarSrc = null } = $props()
  // isLeading = true means character is on the right side

  const html = $derived(marked.parse(message.content || message.text || message, { breaks: true }))
</script>

<style>
  :global(.bubble-content em) {
    color: #ccc;
  }
</style>

<div class="chat {isLeading ? 'chat-end' : 'chat-start'}">
  <div class="chat-image avatar">
    {#if avatarSrc}
      <div class="w-10 rounded overflow-hidden">
        <img src={avatarSrc} alt={characterName} class="object-cover w-full h-full" />
      </div>
    {:else}
      <div class="w-10 h-10 rounded bg-base-300 flex items-center justify-center text-base-content/40">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>
      </div>
    {/if}
  </div>
  <div class="chat-header text-xs text-base-content/50 mb-1">{characterName}</div>
  <div class="chat-bubble {isLeading ? 'chat-bubble-primary' : ''} prose prose-sm max-w-[70%] bubble-content" style="max-width: 70%; font-size: 18px; {isLeading ? '' : 'background-color: #9d174d; color: #fce7f3;'}">
    {@html html}
  </div>
</div>
