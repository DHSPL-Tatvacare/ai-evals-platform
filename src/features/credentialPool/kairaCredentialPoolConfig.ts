import type { CredentialPoolConfig } from './types';

export const kairaCredentialPoolConfig: CredentialPoolConfig = {
  title: 'Execution Credential Pool',
  description: 'Manage the Kaira user IDs and auth tokens available to this adversarial run.',
  primaryFieldKey: 'userId',
  dedupeKeys: ['userId'],
  fields: [
    {
      key: 'userId',
      label: 'User ID',
      placeholder: 'MyTatva user ID',
      description: 'Only one active case may run on a user ID at a time.',
      required: true,
    },
    {
      key: 'authToken',
      label: 'Auth Token',
      placeholder: 'Bearer token for this user',
      description: 'Token paired with the user ID for this run.',
      required: true,
      secret: true,
    },
  ],
  csvSchema: [
    {
      name: 'userId',
      label: 'User ID',
      description: 'Kaira / MyTatva user identifier',
      required: true,
      example: 'c22a5505-f514-11f0-9722-000d3a3e18d5',
      group: 'credentials',
    },
    {
      name: 'authToken',
      label: 'Auth Token',
      description: 'Auth token paired with the user ID',
      required: true,
      example: 'eyJhbGciOi...',
      group: 'credentials',
    },
  ],
  storage: {
    appId: 'kaira-bot',
    key: 'credential-pool-groups',
    visibility: 'private',
  },
  redactedFieldKeys: ['authToken'],
};
