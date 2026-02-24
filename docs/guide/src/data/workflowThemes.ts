export interface WorkflowTheme {
  accentVar: string;
  surfaceVar: string;
  borderVar: string;
}

export const workflowThemes = {
  voiceRx: {
    accentVar: "--workflow-voice-accent",
    surfaceVar: "--workflow-voice-surface",
    borderVar: "--workflow-voice-border",
  },
  kairaBot: {
    accentVar: "--workflow-kaira-accent",
    surfaceVar: "--workflow-kaira-surface",
    borderVar: "--workflow-kaira-border",
  },
  kairaEvals: {
    accentVar: "--workflow-evals-accent",
    surfaceVar: "--workflow-evals-surface",
    borderVar: "--workflow-evals-border",
  },
} as const;
