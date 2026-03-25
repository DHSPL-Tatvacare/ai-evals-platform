# Step 1: Split `isLoading` into Granular Flags

## Goal

Replace the single shared `isLoading` boolean with two specific flags:
`isLoadingSessions` and `isLoadingMessages`. This eliminates ambiguity in
readiness checks and prevents `selectSession` from interfering with
session-level gates.

## File: `src/stores/chatStore.ts`

### 1a. Update the interface

In `ChatStoreState`, replace:

```ts
isLoading: boolean;
```

With:

```ts
isLoadingSessions: boolean;
isLoadingMessages: boolean;
```

### 1b. Update initial state

In the `create(...)` initializer, replace:

```ts
isLoading: false,
```

With:

```ts
isLoadingSessions: false,
isLoadingMessages: false,
```

### 1c. Update `loadSessions`

Change every `isLoading` reference inside `loadSessions` to `isLoadingSessions`:

- Line ~80: `set({ isLoadingSessions: true, error: null })`
- Line ~97 (success): `isLoadingSessions: false`
- Line ~104 (error): `isLoadingSessions: false`

### 1d. Update `selectSession`

Change every `isLoading` reference inside `selectSession` to `isLoadingMessages`:

- Line ~120: `set({ currentSessionId: sessionId, messages: [], isLoadingMessages: true, error: null })`
- Line ~126 (success): `isLoadingMessages: false`
- Line ~134 (error): `isLoadingMessages: false`

### 1e. Keep a derived `isLoading` getter (backward compat)

If any other consumer relies on a single `isLoading`, add a convenience
selector. But prefer updating consumers directly (steps 3-4).

---

## File: `src/hooks/useKairaChat.ts`

### 1f. Update the hook return type

In `UseKairaChatReturn`, replace:

```ts
isLoading: boolean;
```

With:

```ts
isLoadingSessions: boolean;
isLoadingMessages: boolean;
```

### 1g. Update the hook body

Pull both flags from the store instead of the single `isLoading`:

```ts
const {
  // ...
  isLoadingSessions,
  isLoadingMessages,
  // ...
} = useChatStore();
```

Return both:

```ts
return {
  // ...
  isLoadingSessions,
  isLoadingMessages,
  // ...
};
```

---

## Consumers to update (forward reference -- done in later steps)

- `KairaBotTabView.tsx` -- uses `isLoading` in the `isReady` gate (step 3).
- `ChatView.tsx` -- uses `isLoading` in its own spinner gate (step 4).

For now, these will show TypeScript errors. That is expected -- they are
resolved in steps 3 and 4.

## Verification

- `npx tsc -b` will show errors in KairaBotTabView and ChatView (expected).
- chatStore unit behavior: `loadSessions` only sets `isLoadingSessions`,
  `selectSession` only sets `isLoadingMessages`. No cross-contamination.
