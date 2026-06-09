// A dataset's lifecycle state as the setup surface sees it: 'active_edited' is the FE-derived
// state where an active dataset has unsaved draft changes (the API only persists active|draft).
export type DatasetStatus = 'draft' | 'active' | 'active_edited';
