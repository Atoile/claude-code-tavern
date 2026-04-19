<script>
  import { marked } from 'marked'

  let { message, isLeading = false, characterName = '', avatarSrc = null, bubbleStyle = null } = $props()
  // isLeading = true means character is on the right side
  // bubbleStyle = { background, color } per character; null falls back to theme defaults

  const html = $derived(marked.parse(message.content || message.text || message, { breaks: true }))

  const inlineStyle = $derived.by(() => {
    const parts = ['max-width: 70%', 'font-size: 18px']
    if (bubbleStyle) {
      parts.push(`background-color: ${bubbleStyle.background}`)
      parts.push(`color: ${bubbleStyle.color}`)
    }
    if (message?._preview) parts.push('opacity: 0.6')
    return parts.join('; ')
  })
</script>

<style>
  :global(.bubble-content em) {
    opacity: 0.7;
  }
  :global(.bubble-content code) {
    background: rgba(0, 0, 0, 0.15);
    color: inherit;
  }
</style>

<div class="chat {isLeading ? 'chat-end' : 'chat-start'}">
  <div class="chat-image avatar">
    {#if avatarSrc}
      <img src={avatarSrc} alt={characterName} class="w-20 h-auto rounded" style="display: block;" />
    {:else}
      <div class="w-20 h-20 rounded bg-base-300 flex items-center justify-center text-base-content/40">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" style="fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>
      </div>
    {/if}
  </div>
  <div class="chat-header text-xs text-base-content/50 mb-1">{characterName}</div>
  <div class="chat-bubble {isLeading && !bubbleStyle ? 'chat-bubble-primary' : ''} prose prose-sm max-w-[70%] bubble-content" style={inlineStyle}>
    <!-- eslint-disable-next-line svelte/no-at-html-tags -->
    {@html html}
  </div>
</div>
