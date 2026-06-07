import { getMessages, sendMessage, type Message } from '$lib/api/chat';
import { session } from './session.svelte';

class Chat {
  messages = $state<Message[]>([]);
  sending = $state(false);

  async load() {
    const pid = session.profileId;
    if (!pid) return;
    this.messages = await getMessages(pid);
  }
  async send(content: string) {
    const pid = session.profileId;
    if (!pid) return;
    this.sending = true;
    // optimistic user bubble
    this.messages = [
      ...this.messages,
      { id: `local-${Date.now()}`, role: 'user', content, created_at: new Date().toISOString() }
    ];
    try {
      const reply = await sendMessage(pid, content);
      this.messages = [...this.messages, reply];
    } finally {
      this.sending = false;
    }
  }
}

export const chat = new Chat();
