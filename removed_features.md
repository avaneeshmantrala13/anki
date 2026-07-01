# Modified Anki Behaviour — BrainLift

BrainLift is built to be **additive**: it does not remove any Anki functionality.
This file documents the one place where existing Anki behaviour is *modified*, as
required by the PRD's modification policy.

## Default landing screen after profile load

**What changed.** After a profile loads, the main window now shows the **BrainLift
guided landing** ("brainliftHome" state) instead of opening directly on the deck
browser. The landing renders in the normal content area with a clear "next step",
a 4-step path, and simple buttons (Study, Add, Browse, Stats). The deck browser and
every other screen remain one click away and completely unchanged.

**Why.** New users reported being dropped into the deck browser with no idea what to do.
The PRD calls for a clear, guided experience; making the guided hub the landing screen
directly addresses that.

**Scope / reversibility.** Implemented via the public `gui_hooks.profile_did_open` hook
and a custom main-window state registered on `mw`; no upstream navigation code is
modified. The deck-browser bottom bar is hidden only while on the landing and restored
on exit. Removing BrainLift restores Anki's original startup screen.

**AI.** None.

## Onboarding gate before the first review session

**What changed.** For a user who has **not yet completed BrainLift onboarding**, the
first attempt to enter a review session is intercepted. Anki bounces back to the deck
overview and shows a dialog:

- **Set up now** — opens the BrainLift onboarding form; after it is completed, the
  review session continues automatically.
- **Skip for now** — proceeds straight into the review session and does not ask again
  for the rest of the session.

**Why.** The PRD (Feature 1 — Intelligent Onboarding) states: *"Every new user should
complete an onboarding process before beginning their first review session."* The plan,
coverage, and readiness measurements are meaningless without the student's exam date and
goal, so the gate ensures those exist before study begins.

**Alternatives considered.**
- *Guided nudge only* (auto-open the BrainLift home): kept, but on its own it does not
  satisfy the "before beginning their first review session" wording.
- *Hard requirement (no skip)*: rejected to preserve user autonomy and avoid trapping a
  user who just wants to review.

**Scope / reversibility.**
- Only affects users who have **not** onboarded. Once onboarded, the hook returns
  immediately and Anki behaves exactly as upstream.
- "Skip for now" fully restores normal behaviour for the session.
- Implemented entirely via the public `gui_hooks.state_did_change` hook in
  `qt/aqt/brainlift/__init__.py`; no upstream review/scheduler code is altered.

**Maintenance impact.** Minimal — it is an isolated hook subscription. Removing BrainLift
removes the gate with no residual changes to Anki's review flow.

**AI.** None. The gate and onboarding are fully deterministic.
