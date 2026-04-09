import { apiRequest } from '@/services/api/client';
import type { BuilderChatRequest, BuilderChatResponse } from './types';

export async function sendBuilderMessage(body: BuilderChatRequest): Promise<BuilderChatResponse> {
  return apiRequest<BuilderChatResponse>('/api/report-builder/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
