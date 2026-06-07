import { api } from './client';

export interface ActionCard {
  tool: string;
  description?: string;
  proof?: string;
  merit_reward?: number;
  hours?: number;
  reason?: string;
  amount?: number;
  task_id?: string;
  error?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  action?: ActionCard | null;
  created_at: string;
}

export const getMessages = (id: string) =>
  api.get(`/api/profile/${id}/messages`) as Promise<Message[]>;
export const sendMessage = (id: string, content: string) =>
  api.post(`/api/profile/${id}/chat`, { content }) as Promise<Message>;
