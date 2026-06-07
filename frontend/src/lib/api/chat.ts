import { api } from './client';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export const getMessages = (id: string) =>
  api.get(`/api/profile/${id}/messages`) as Promise<Message[]>;
export const sendMessage = (id: string, content: string) =>
  api.post(`/api/profile/${id}/chat`, { content }) as Promise<Message>;
