interface InfoLineArgs {
  steps: number;
  count: number;
  category: string;
}

interface StoppedArgs {
  applied: number;
  total: number;
}

interface ChatWidgetCopy {
  canvasToggleLabel: string;
  canvasOffLine: string;
  workingLabel: string;
  infoLineTemplate: (args: InfoLineArgs) => string;
  scopeFocusedPrefix: string;
  cardTitleApplied: string;
  rationaleLabel: string;
  undo: string;
  showOnCanvas: string;
  redoOnLatest: string;
  keepAsIs: string;
  reverted: string;
  stoppedTemplate: (args: StoppedArgs) => string;
  conflict: string;
  blocked: string;
}

export const chatWidgetCopy: ChatWidgetCopy = {
  canvasToggleLabel: 'Canvas',
  canvasOffLine: 'Canvas off — answering generally',
  workingLabel: 'Working on your canvas',
  infoLineTemplate: ({ steps, count, category }) =>
    `Whole flow · ${steps} steps · ${count} ${category} actions`,
  scopeFocusedPrefix: 'Focused on:',
  cardTitleApplied: 'Updated your canvas',
  rationaleLabel: 'Why',
  undo: 'Undo',
  showOnCanvas: 'Show on canvas',
  redoOnLatest: 'Redo on latest',
  keepAsIs: 'Keep as is',
  reverted: 'Reverted — canvas back to before this change.',
  stoppedTemplate: ({ applied, total }) => `Stopped — applied ${applied} of ${total} steps`,
  conflict:
    'The canvas changed while I was working — your edits are safe. Redo on the latest?',
  blocked: "I couldn't apply this change.",
};

export type { ChatWidgetCopy, InfoLineArgs, StoppedArgs };
