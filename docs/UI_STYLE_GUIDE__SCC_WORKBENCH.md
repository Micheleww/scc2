# SCC Workbench UI Style Guide (VS Code-like, Stable)

Goal: keep SCC Workbench UI visually consistent and low-maintenance by inheriting the VS Code/Monaco "workbench" design language.

Scope:
- Applies to `scc-top/tools/scc_ui/**` Workbench UI.
- Intended for any AI/agent that modifies or adds UI in this repo.

## Single Source Of Truth (Tokens + Base CSS)

Do not invent a new design system. Use the existing variables and classes:
- Tokens: `scc-top/tools/scc_ui/src/styles/tokens.css`
- Layout components: `scc-top/tools/scc_ui/src/styles/app.css`
- VS Code-derived baseline typography/focus/codicon sizing: `scc-top/tools/scc_ui/src/styles/vscode-style.css`

Rule: no hard-coded colors in JSX/CSS unless defining a token in `tokens.css`.

## Design Language (What We Copy From VS Code)

The Workbench UI intentionally mirrors VS Code structure:
- Activity bar (left rail), sidebar, main content, status bar.
- Dense typography, minimal chrome, a lot of "pill" and "list row" patterns.
- Focus outline is a first-class affordance.

Reference sources (upstream inspiration):
- `vscode-main/extensions/theme-2026/themes/styles.css` (radii/shadows/z-index layering conventions)
- VS Code/Monaco workbench conventions expressed via `--vscode-*` CSS variables.

We do NOT aim for 1:1 CSS parity with `vscode-main`. We aim for:
- consistent look and spacing
- token-driven theming (light/dark)
- minimal CSS surface area

## Required CSS Variables

Use these `--vscode-*` variables (defined in `tokens.css`) instead of raw values:
- Base: `--vscode-foreground`, `--vscode-icon-foreground`, `--vscode-focusBorder`
- Inputs: `--vscode-input-background`, `--vscode-input-foreground`, `--vscode-input-border`
- Buttons: `--vscode-button-background`, `--vscode-button-foreground`, `--vscode-button-hoverBackground`
- Surfaces: `--vscode-activityBar-background`, `--vscode-sideBar-background`, `--vscode-editor-background`, `--vscode-panel-background`
- Borders: `--vscode-activityBar-border`, `--vscode-sideBar-border`, `--vscode-panel-border`
- Status bar: `--vscode-statusBar-background`, `--vscode-statusBar-foreground`, `--vscode-statusBar-border`

SCC-specific vars (also in `tokens.css`):
- `--scc-pill-background`
- `--scc-dot-background`
- `--scc-sidebar-link-*`
- `--scc-error-foreground`

Monospace:
- Use `fontFamily: "var(--mono)"` for IDs/logs/json. The token is defined in `tokens.css`.

## Layout Conventions

Use the existing structural classes from `app.css`:
- Root shell: `.scc-workbench`, `.scc-shell`
- Activity bar: `.scc-activitybar` (48px rail)
- Sidebar: `.scc-sidebar` (280px)
- Main: `.scc-main` / `.scc-editor`
- Status bar: `.scc-statusbar` (22px)

Spacing and density (match existing Workbench patterns):
- Outer page padding: `12px`
- Form controls: `borderRadius: 6`, `padding: "6px 10px"`, `fontSize: 12`
- "Card" containers: use `className="scc-pill"` plus inline `padding: 12`, `borderRadius: 10`, `display: "grid"`, `gap: 10`
- List rows: border `1px solid var(--vscode-input-border)`, radius `8`, hover via slightly higher alpha background

## Interaction Conventions (Must-Haves)

Focus styles:
- Do not disable outline. Baseline focus is defined in `vscode-style.css` and uses `--vscode-focusBorder`.

Links:
- For in-app navigation inside the Workbench frame, prefer the existing "viewer" pattern (open in right pane).
- Use the existing `ViewerLink` helper from `WorkbenchApp.tsx` when available instead of plain `<a>` for "open in viewer" behaviors.

Tables:
- Prefer CSS-grid "table" blocks (as used in Flow view) instead of HTML `<table>` to match density and styling.
- Use `fontFamily: "var(--mono)"` in time/ids columns.

Errors:
- Error text should use `color: "var(--scc-error-foreground)"` and `fontSize: 12`.

## Do / Don't (Fail-Closed Style Rules)

Do:
- Use `var(--vscode-*)` and `var(--scc-*)` tokens.
- Keep spacing dense and consistent (`12px` page padding; `6px` control radius).
- Use `scc-pill` for "cards" and "pills" instead of custom containers.
- Keep new UI best-effort: endpoints may be missing; render gracefully, never crash the Workbench.

Don't:
- Hardcode colors, shadows, gradients, or fonts in new components.
- Introduce a new UI library (MUI/Ant/Tailwind) into Workbench UI.
- Add new global CSS unless strictly necessary; prefer tokens or local inline styles.
- Create "floating" UI patterns inconsistent with ActivityBar/Sidebar/Main/StatusBar.

## Reference Implementation Patterns

Good examples to copy:
- Flow view "grid table" pattern: `scc-top/tools/scc_ui/src/workbench/WorkbenchApp.tsx`
- Tasks list + details pane pattern: `scc-top/tools/scc_ui/src/workbench/WorkbenchApp.tsx`
- Overview dashboard pattern (summary cards + lists): `scc-top/tools/scc_ui/src/workbench/WorkbenchApp.tsx`

Token changes:
- Only edit `scc-top/tools/scc_ui/src/styles/tokens.css`.
- Keep naming stable; prefer `--vscode-*` names for compatibility with upstream-derived CSS.

