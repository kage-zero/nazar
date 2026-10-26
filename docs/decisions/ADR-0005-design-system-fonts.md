# ADR-0005: Design-system implementation and font substitutes

- **Status:** Accepted (2026-10-26)
- **Source of truth:** `docs/DESIGN.md`. The prompt calls it `design.md` / `DESIGN(1).md`; the actual file is `docs/DESIGN.md` and it is preserved unmodified.

## Decision

- **Tokens:** `apps/web/src/styles.css` defines tokens in a Tailwind v4 `@theme` with `--color-*: initial`, so **only** design-system colours exist as utilities: carbon, paper, canvas, mist, ash, smoke, slate, graphite, mint, voltage.
- **Fonts:** the SuisseIntl family is proprietary and not licensed to us, so we use the documented substitutes. All are self-hosted via `@fontsource` (SIL OFL), with no remote font requests:
  - SuisseIntlCond → **Anton** (display only, ≥ 48px, uppercase, line-height 0.9, −0.03em)
  - SuisseIntl → **Inter Variable** (supports the 450 weight used for secondary headings)
  - SuisseIntlMono → **JetBrains Mono** (12px labels)
- **Radii:** buttons 4–8px, cards 24–32px, nav pill 48px, tags 64px. No box-shadows or gradients anywhere.
- **3D viewport:** an inverted (black) card, as the design guide allows for dramatic contrast zones.

## Consequences

Visual QA compares Playwright screenshots against `docs/DESIGN.md` after every major UI change.
