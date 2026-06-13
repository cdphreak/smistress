# M5c — M5 frontend: mode sheet, toy discreetness, dossier tags

**Date:** 2026-06-13
**Status:** approved (design)
**Predecessors:** M5a (supervision modes core, #28), M5b (discreetness content filter, #29)

## Goal

Surface the M5a/M5b backend — supervision modes (control-depth axis) and the
deterministic discreetness content filter — in the SvelteKit PWA, and bring the
deferred generated OpenAPI types back in sync.

The backend for the core is already in place: `GET/PUT /profile/{id}/supervision`
(mode + per-mode notes) exists, and toys already accept `noise` / `visibility` /
`discreet_capable`. M5c is mostly frontend, with two small backend extensions
(a toy PATCH endpoint, and dossier surfacing of mode + task tags).

## Backend

### 1. `PATCH /profile/{id}/toys/{toy_id}`

Toys are currently create-only (`POST`/`GET`). Add:

- Service `update_toy(session, profile_id, toy_id, patch)` in
  `app/services/profile.py`: patches `name`, `type`, `notes`,
  `intiface_capable`, `noise`, `visibility`, `discreet_capable`. Raises a
  not-found error if the toy doesn't exist or belongs to another profile.
  Service flushes; endpoint commits (house convention).
- Endpoint in `app/api/profile.py` returning `ToyOut`; `404` on not-found.
- Request schema `ToyPatch` (all fields optional) in `app/schemas/onboarding.py`.

### 2. Dossier surfacing

- Extend `ActiveTask` (in `app/schemas/chat.py`) with `intensity: int` and
  `discreetness: str`, populated in `build_dossier` from the materialized Task
  (both columns already exist on the row).
- Add `supervision_mode: str` to `DossierOut`, read via `sup_svc.get_mode`.
  **Decision:** embed the mode in `DossierOut` rather than a separate fetch, so
  the dossier badge stays in sync with the single dossier refresh the chat page
  already performs.
- Required-toy names are **not** surfaced in the dossier (YAGNI — the compact bar
  shows intensity + discreetness only; toy requirements belong to the future
  task-card / proof flow).

## Frontend

### 3. `lib/api/supervision.ts`

New API client: `getSupervision`, `setMode`, `setNote`. Types:

- `SupervisionMode = 'full' | 'discreet' | 'task' | 'homeoffice' | 'vacation'`
- `Supervision = { mode: SupervisionMode; notes: Record<string, string> }`

A small `supervision` rune store (mirrors the existing safety store pattern) holds
current mode + notes for the chat surface.

### 4. `lib/chat/ModeSheet.svelte`

Bottom sheet reusing StopSheet's scrim/sheet markup and styling. Lists all five
modes with their one-line meanings; the current mode is highlighted. Tapping a
mode calls `setMode`. A per-mode note `TextArea` saves via `setNote`. Vacation is
visually flagged as "economy frozen."

### 5. `DossierBar.svelte`

- Add a **mode badge** button (e.g. `MODE · DISCREET`) that opens `ModeSheet`.
- Append intensity/discreetness **tags** to the active-task line
  (e.g. `… · intensity 40 · discreet`).
- Owns the sheet open-state.

### 6. `lib/onboarding/Toys.svelte`

Add three flag checkboxes (noise, visibility, discreet-capable) to the existing
form; extend the `Toy` type and the emitted payload. Gain an optional `initial`
prop so the component doubles as an edit form (prefilled values).

### 7. Profile page toy editing

The toy list shows the flags and an **Edit** affordance per toy that reopens
`Toys.svelte` prefilled; wire `updateToy` (new in `lib/api/profile.ts`) → the new
`PATCH` endpoint. The existing "Add" path is unchanged.

## Verification

### 8. Regenerate generated types

Run `gen:api` to regenerate `openapi.json` + `src/lib/types/api.ts`, committing the
cleaned-up result. This is the verification gate and the deferred sync from M5b.
The generated file is imported nowhere in `src/`, so there is no runtime risk —
it serves as drift detection only.

## Testing

- **Vitest:** `ModeSheet` (mode select + note save), `DossierBar` (badge + tags
  render), `Toys` (flags emit; edit-prefill).
- **pytest:** the new `update_toy` service + endpoint (incl. wrong-profile 404),
  and the extended dossier fields (`intensity` / `discreetness` /
  `supervision_mode`).

## Out of scope (→ later)

- Required-toy display in the dossier.
- Schedule / calendar (Addendum B6).
- The `punitive` flag + `pending_review` proof state (→ M6 queued proof).
