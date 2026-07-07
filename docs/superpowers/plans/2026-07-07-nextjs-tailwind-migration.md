# Next.js + Tailwind v4 Frontend Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `ai-hub-bot`'s Vite + `@telegram-apps/telegram-ui` frontend with a Next.js (App Router, full Node server) + Tailwind CSS v4 frontend, deployed as its own Render service, with zero change to backend business logic and zero visual regression versus the current dark theme.

**Architecture:** Two Render services — `ai-hub-frontend` (new Next.js app, this plan) and `ai-hub-backend` (existing FastAPI, untouched except CORS). The Next.js app is fully client-rendered for personalized data (Telegram `initData` auth only exists in the browser), uses normal path routing instead of `HashRouter`, and replaces every `telegram-ui` import with a same-named, same-prop-shape local component built on Tailwind + (only where real interaction/accessibility logic is needed) Radix primitives.

**Tech Stack:** Next.js (App Router, latest), React 18, TypeScript, Tailwind CSS v4, `@radix-ui/react-dialog`, `@radix-ui/react-switch`, `clsx`, `tailwind-merge`.

## Global Constraints

- Backend (`app/`, `alembic/`, aiogram bot code) is **not modified** except: adding CORS middleware for the new frontend origin (Task 26).
- No new features. Every screen must keep identical business logic (state, API calls, validation) to its current Vite counterpart — only presentation layer changes.
- Visual result must match the current dark theme (same palette, same spacing) — this is a stack swap, not a redesign.
- Old `frontend/` (Vite) directory is deleted only in the final cutover task (Task 28), after the new app is verified end-to-end.
- All new frontend code lives under `frontend-next/src/`.
- Every primitive component's prop names must match the `telegram-ui` component it replaces (documented per-task below) so screen-migration tasks are a mechanical import swap, not a rewrite of usage sites.

---

## Task 1: Scaffold the Next.js project

**Files:**
- Create: `frontend-next/package.json`, `frontend-next/tsconfig.json`, `frontend-next/next.config.ts`, `frontend-next/eslint.config.mjs`, `frontend-next/src/app/layout.tsx` (placeholder), `frontend-next/src/app/page.tsx` (placeholder), `frontend-next/src/app/globals.css` (placeholder)
- Test: manual (dev server boots)

**Interfaces:**
- Produces: a runnable Next.js dev server at `frontend-next/`, with TypeScript path alias `@/*` → `frontend-next/src/*`, Tailwind v4 wired into `globals.css`, `clsx`/`tailwind-merge`/`@radix-ui/react-dialog`/`@radix-ui/react-switch` installed as dependencies.

- [ ] **Step 1: Scaffold with create-next-app**

Run from the repo root:

```bash
npx create-next-app@latest frontend-next \
  --typescript --tailwind --app --src-dir --eslint \
  --import-alias "@/*" --turbopack --no-src-dir=false
```

When prompted, accept defaults. This produces a Next.js App Router project with Tailwind v4 already wired (current `create-next-app` versions default to Tailwind v4).

- [ ] **Step 2: Install the extra dependencies this migration needs**

```bash
cd frontend-next
npm install clsx tailwind-merge @radix-ui/react-dialog @radix-ui/react-switch
```

- [ ] **Step 3: Verify the dev server boots**

```bash
npm run dev
```

Expected: server starts on `http://localhost:3000`, default Next.js starter page renders with no console errors.

- [ ] **Step 4: Strip the starter page content**

Replace the body of `frontend-next/src/app/page.tsx` with a minimal placeholder so later tasks build on a clean slate:

```tsx
export default function Home() {
  return <div>ai-hub-bot (migrating)</div>;
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend-next
git commit -m "Scaffold Next.js + Tailwind v4 project for frontend migration"
```

---

## Task 2: Design tokens and global styles

**Files:**
- Modify: `frontend-next/src/app/globals.css`
- Create: `frontend-next/src/lib/cn.ts`
- Test: `frontend-next/src/lib/cn.test.ts` (if a test runner is added later — for this task, verify by visual inspection per Step 3, no automated test framework is introduced solely for a one-line utility)

**Interfaces:**
- Produces: `cn(...inputs: ClassValue[]): string` from `@/lib/cn`, used by every component task from here on. CSS custom properties/utilities: `bg-bg-deep`, `bg-bg-elevated`, `bg-surface`, `bg-surface-strong`, `border-border-soft`, `text-foreground`, `text-foreground-muted`, `bg-brand-1`, `bg-brand-2`, `bg-brand-3`, `text-success`, `rounded-lg` (20px), `rounded-md` (14px), `shadow-glow`, `ease-out`, `.heading-font`, `.press-scale`, and the raw CSS var `--brand-gradient`.

- [ ] **Step 1: Write `cn.ts`**

```ts
// frontend-next/src/lib/cn.ts
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 2: Replace `globals.css` with the ported design tokens**

This is a direct port of `frontend/src/global.css` (Vite) into Tailwind v4's CSS-first `@theme` config. Same palette, same values — only the mechanism changes.

```css
/* frontend-next/src/app/globals.css */
@import "tailwindcss";

@theme {
  --color-bg-deep: #050506;
  --color-bg-elevated: #0e0e12;
  --color-surface: rgba(255, 255, 255, 0.06);
  --color-surface-strong: rgba(255, 255, 255, 0.1);
  --color-border-soft: rgba(255, 255, 255, 0.09);
  --color-foreground: #f5f5f7;
  --color-foreground-muted: #96979f;
  --color-brand-1: #ff5f6d;
  --color-brand-2: #ff2d78;
  --color-brand-3: #b721ff;
  --color-success: #2ecc71;
  --radius-lg: 20px;
  --radius-md: 14px;
  --shadow-glow: 0 8px 24px rgba(255, 45, 120, 0.35);
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
}

:root {
  --brand-gradient: linear-gradient(135deg, var(--color-brand-1), var(--color-brand-2) 55%, var(--color-brand-3));
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

html,
body {
  background: var(--color-bg-deep);
  color: var(--color-foreground);
}

body {
  font-family:
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    Inter,
    sans-serif;
}

.heading-font {
  font-family: "Space Grotesk", -apple-system, sans-serif;
  letter-spacing: -0.01em;
}

.press-scale {
  transition:
    transform 150ms var(--ease-out),
    box-shadow 150ms var(--ease-out);
  cursor: pointer;
}
.press-scale:active {
  transform: scale(0.97);
}

@media (prefers-reduced-motion: reduce) {
  .press-scale {
    transition: none;
  }
}

::-webkit-scrollbar {
  display: none;
}
```

- [ ] **Step 3: Verify visually**

```bash
npm run dev
```

Open `http://localhost:3000`. Expected: page background is near-black (`#050506`), text is light. Open DevTools console, run:

```js
getComputedStyle(document.body).backgroundColor
```

Expected: `"rgb(5, 5, 6)"`.

- [ ] **Step 4: Commit**

```bash
git add frontend-next/src/app/globals.css frontend-next/src/lib/cn.ts
git commit -m "Port design tokens to Tailwind v4 @theme"
```

---

## Task 3: Primitives — Spinner, Placeholder, Progress

**Files:**
- Create: `frontend-next/src/components/ui/spinner.tsx`
- Create: `frontend-next/src/components/ui/placeholder.tsx`
- Create: `frontend-next/src/components/ui/progress.tsx`

**Interfaces:**
- Consumes: `cn` from `@/lib/cn` (Task 2).
- Produces:
  - `Spinner({ size = "m" }: { size?: "s" | "m" | "l" })` from `@/components/ui/spinner`.
  - `Placeholder({ header, description, children }: { header?: string; description?: string; children?: ReactNode })` from `@/components/ui/placeholder`.
  - `Progress({ value }: { value: number })` from `@/components/ui/progress` (`value` is 0–100).

- [ ] **Step 1: `spinner.tsx`**

```tsx
// frontend-next/src/components/ui/spinner.tsx
import { cn } from "@/lib/cn";

const SIZE_PX: Record<"s" | "m" | "l", number> = { s: 16, m: 24, l: 32 };

export function Spinner({ size = "m", className }: { size?: "s" | "m" | "l"; className?: string }) {
  const px = SIZE_PX[size];
  return (
    <span
      className={cn("inline-block animate-spin rounded-full border-2 border-border-soft border-t-brand-2", className)}
      style={{ width: px, height: px }}
      role="status"
      aria-label="Загрузка"
    />
  );
}
```

- [ ] **Step 2: `placeholder.tsx`**

```tsx
// frontend-next/src/components/ui/placeholder.tsx
import type { ReactNode } from "react";

export function Placeholder({
  header,
  description,
  children,
}: {
  header?: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 px-8 text-center">
      {children}
      {header && <h2 className="heading-font text-lg font-semibold text-foreground">{header}</h2>}
      {description && <p className="text-sm text-foreground-muted">{description}</p>}
    </div>
  );
}
```

- [ ] **Step 3: `progress.tsx`**

```tsx
// frontend-next/src/components/ui/progress.tsx
export function Progress({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface">
      <div
        className="h-full rounded-full bg-[image:var(--brand-gradient)] transition-[width] duration-300"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
```

- [ ] **Step 4: Verify with a throwaway page**

Temporarily add to `frontend-next/src/app/page.tsx`:

```tsx
import { Spinner } from "@/components/ui/spinner";
import { Placeholder } from "@/components/ui/placeholder";
import { Progress } from "@/components/ui/progress";

export default function Home() {
  return (
    <Placeholder header="Test" description="Checking primitives">
      <Spinner size="m" />
      <div className="w-40"><Progress value={40} /></div>
    </Placeholder>
  );
}
```

Run `npm run dev`, open `http://localhost:3000`. Expected: centered column with a spinning ring, "Test" heading, muted description, and a 40%-filled gradient progress bar. Then revert `page.tsx` to the Task 1 placeholder.

- [ ] **Step 5: Commit**

```bash
git add frontend-next/src/components/ui/spinner.tsx frontend-next/src/components/ui/placeholder.tsx frontend-next/src/components/ui/progress.tsx
git commit -m "Add Spinner, Placeholder, Progress primitives"
```

---

## Task 4: Primitives — Button, IconButton

**Files:**
- Create: `frontend-next/src/components/ui/button.tsx`
- Create: `frontend-next/src/components/ui/icon-button.tsx`

**Interfaces:**
- Consumes: `cn` (Task 2), `Spinner` (Task 3).
- Produces:
  - `Button` from `@/components/ui/button` — props: `mode?: "filled" | "bezeled" | "gray" | "outline" | "white" | "plain"` (default `"filled"`), `size?: "s" | "m" | "l"` (default `"m"`), `stretched?: boolean`, `loading?: boolean`, plus all native `<button>` attributes. All six modes are needed: `gray` is used by `Tariffs.tsx`/`AdminUsers.tsx` for de-emphasized/current-state buttons, `white` by `MyAccount.tsx`'s "Unlock Premium" CTA sitting on a colored gradient card.
  - `IconButton` from `@/components/ui/icon-button` — props: all native `<button>` attributes (used as `<IconButton onClick={...} aria-label="...">+</IconButton>`).

- [ ] **Step 1: `button.tsx`**

```tsx
// frontend-next/src/components/ui/button.tsx
import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";
import { Spinner } from "@/components/ui/spinner";

export type ButtonMode = "filled" | "bezeled" | "gray" | "outline" | "white" | "plain";
export type ButtonSize = "s" | "m" | "l";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  mode?: ButtonMode;
  size?: ButtonSize;
  stretched?: boolean;
  loading?: boolean;
}

const MODE_CLASSES: Record<ButtonMode, string> = {
  filled: "bg-[image:var(--brand-gradient)] text-white shadow-glow border border-transparent",
  bezeled: "bg-surface text-foreground border border-border-soft",
  gray: "bg-surface-strong text-foreground border border-transparent",
  outline: "bg-transparent text-foreground border border-border-soft",
  white: "bg-white text-brand-2 border border-transparent",
  plain: "bg-transparent text-foreground border border-transparent",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  s: "text-[13px] px-3 py-2 gap-1.5",
  m: "text-[14px] px-4 py-2.5 gap-2",
  l: "text-[16px] px-5 py-3.5 gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { mode = "filled", size = "m", stretched, loading, disabled, className, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "press-scale inline-flex items-center justify-center rounded-full font-semibold disabled:opacity-40",
        MODE_CLASSES[mode],
        SIZE_CLASSES[size],
        stretched && "w-full",
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner size="s" /> : children}
    </button>
  );
});
```

`loading` replaces the button's children with a centered spinner (matching real `telegram-ui` `Button` behavior) rather than showing both at once — this keeps the button's width stable via its existing padding instead of jumping when the spinner is added alongside text.

- [ ] **Step 2: `icon-button.tsx`**

```tsx
// frontend-next/src/components/ui/icon-button.tsx
import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

export const IconButton = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement>>(
  function IconButton({ className, ...rest }, ref) {
    return (
      <button
        ref={ref}
        className={cn(
          "press-scale inline-flex h-8 w-8 items-center justify-center rounded-full bg-surface text-foreground border border-border-soft",
          className,
        )}
        {...rest}
      />
    );
  },
);
```

- [ ] **Step 3: Verify**

Temporarily render in `page.tsx`:

```tsx
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";

export default function Home() {
  return (
    <div className="flex gap-3 p-6">
      <Button mode="filled">Generate</Button>
      <Button mode="bezeled" size="s">Тарифы</Button>
      <Button loading>Loading</Button>
      <IconButton aria-label="Add">+</IconButton>
    </div>
  );
}
```

`npm run dev`, open `http://localhost:3000`. Expected: gradient pill button, bezeled smaller button, and the third button showing only a spinner (no "Loading" text, since `loading` replaces children). Revert `page.tsx` after checking.

- [ ] **Step 4: Commit**

```bash
git add frontend-next/src/components/ui/button.tsx frontend-next/src/components/ui/icon-button.tsx
git commit -m "Add Button, IconButton primitives"
```

---

## Task 5: Primitives — List, Section, Cell

**Files:**
- Create: `frontend-next/src/components/ui/list.tsx`
- Create: `frontend-next/src/components/ui/section.tsx`
- Create: `frontend-next/src/components/ui/cell.tsx`

**Interfaces:**
- Consumes: `cn` (Task 2).
- Produces:
  - `List({ children })` from `@/components/ui/list` — plain vertical container.
  - `Section({ header, footer, children })` from `@/components/ui/section` — `header?: string`, `footer?: string` (`footer` is used by `Referral.tsx` to show the referral link text below the section).
  - `Cell({ before, after, subtitle, multiline, onClick, children, className })` from `@/components/ui/cell` — `before?: ReactNode`, `after?: ReactNode`, `subtitle?: string`, `multiline?: boolean`, `onClick?: () => void`.

- [ ] **Step 1: `list.tsx`**

```tsx
// frontend-next/src/components/ui/list.tsx
import type { ReactNode } from "react";

export function List({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-4 px-4 pb-4">{children}</div>;
}
```

- [ ] **Step 2: `section.tsx`**

```tsx
// frontend-next/src/components/ui/section.tsx
import type { ReactNode } from "react";

export function Section({
  header,
  footer,
  children,
}: {
  header?: string;
  footer?: string;
  children: ReactNode;
}) {
  return (
    <div>
      {header && (
        <div className="px-3 pb-1.5 text-xs font-medium uppercase tracking-wide text-foreground-muted">{header}</div>
      )}
      <div className="overflow-hidden rounded-lg border border-border-soft bg-surface">{children}</div>
      {footer && <div className="px-3 pt-1.5 text-xs text-foreground-muted">{footer}</div>}
    </div>
  );
}
```

- [ ] **Step 3: `cell.tsx`**

```tsx
// frontend-next/src/components/ui/cell.tsx
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface CellProps {
  before?: ReactNode;
  after?: ReactNode;
  subtitle?: string;
  multiline?: boolean;
  onClick?: () => void;
  children?: ReactNode;
  className?: string;
}

export function Cell({ before, after, subtitle, multiline, onClick, children, className }: CellProps) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-3 border-b border-border-soft px-4 py-3 text-left last:border-b-0",
        onClick && "press-scale",
        className,
      )}
    >
      {before}
      <div className={cn("min-w-0 flex-1", multiline ? "" : "truncate")}>
        <div className="truncate text-[15px] text-foreground">{children}</div>
        {subtitle && <div className="truncate text-xs text-foreground-muted">{subtitle}</div>}
      </div>
      {after}
    </Tag>
  );
}
```

- [ ] **Step 4: Verify**

Temporarily render:

```tsx
import { List } from "@/components/ui/list";
import { Section } from "@/components/ui/section";
import { Cell } from "@/components/ui/cell";

export default function Home() {
  return (
    <List>
      <Section header="Тестовая секция">
        <Cell subtitle="Подпись" onClick={() => alert("click")}>Заголовок ячейки</Cell>
        <Cell after={<span>→</span>}>Вторая ячейка</Cell>
      </Section>
    </List>
  );
}
```

`npm run dev`. Expected: a rounded card with two rows separated by a hairline border, first row clickable (cursor pointer, shrinks slightly on click), subtitle in muted gray below the title. Revert `page.tsx`.

- [ ] **Step 5: Commit**

```bash
git add frontend-next/src/components/ui/list.tsx frontend-next/src/components/ui/section.tsx frontend-next/src/components/ui/cell.tsx
git commit -m "Add List, Section, Cell primitives"
```

---

## Task 6: Primitives — Input, Textarea, Select

**Files:**
- Create: `frontend-next/src/components/ui/input.tsx`
- Create: `frontend-next/src/components/ui/textarea.tsx`
- Create: `frontend-next/src/components/ui/select.tsx`

**Interfaces:**
- Consumes: `cn` (Task 2).
- Produces:
  - `Input` from `@/components/ui/input` — all native `<input>` attributes plus `header?: string`.
  - `Textarea` from `@/components/ui/textarea` — all native `<textarea>` attributes plus `header?: string`.
  - `Select` from `@/components/ui/select` — all native `<select>` attributes plus `header?: string`.

- [ ] **Step 1: `input.tsx`**

```tsx
// frontend-next/src/components/ui/input.tsx
import { type InputHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  header?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { header, className, ...rest },
  ref,
) {
  return (
    <label className="flex flex-col gap-1.5">
      {header && <span className="text-xs font-medium text-foreground-muted">{header}</span>}
      <input
        ref={ref}
        className={cn(
          "w-full rounded-md border border-border-soft bg-transparent px-3 py-2.5 text-[15px] text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-brand-2",
          className,
        )}
        {...rest}
      />
    </label>
  );
});
```

- [ ] **Step 2: `textarea.tsx`**

```tsx
// frontend-next/src/components/ui/textarea.tsx
import { type TextareaHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  header?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { header, className, ...rest },
  ref,
) {
  return (
    <label className="flex flex-col gap-1.5">
      {header && <span className="text-xs font-medium text-foreground-muted">{header}</span>}
      <textarea
        ref={ref}
        className={cn(
          "w-full rounded-md border border-border-soft bg-transparent px-3 py-2.5 text-[15px] text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-brand-2",
          className,
        )}
        {...rest}
      />
    </label>
  );
});
```

- [ ] **Step 3: `select.tsx`**

```tsx
// frontend-next/src/components/ui/select.tsx
import { type SelectHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  header?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { header, className, children, ...rest },
  ref,
) {
  return (
    <label className="flex flex-col gap-1.5">
      {header && <span className="text-xs font-medium text-foreground-muted">{header}</span>}
      <select
        ref={ref}
        className={cn(
          "w-full rounded-md border border-border-soft bg-bg-elevated px-3 py-2.5 text-[15px] text-foreground focus:outline-none focus:ring-2 focus:ring-brand-2",
          className,
        )}
        {...rest}
      >
        {children}
      </select>
    </label>
  );
});
```

Note: `Select` is a styled native `<select>`, not a Radix `Select` — the only usage in the app (`AdminBanners.tsx`, action type picker with 2 options) doesn't need Radix's custom-popover behavior, so a native element is the YAGNI-correct choice here.

- [ ] **Step 4: Verify**

Temporarily render:

```tsx
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";

export default function Home() {
  return (
    <div className="flex flex-col gap-4 p-6">
      <Input header="Заголовок" placeholder="Введите текст" />
      <Textarea header="Описание" placeholder="Опишите, что хотите создать" rows={4} />
      <Select header="Действие" defaultValue="prompt">
        <option value="prompt">Промпт</option>
        <option value="link">Ссылка</option>
      </Select>
    </div>
  );
}
```

`npm run dev`. Expected: dark input/textarea/select fields with light text and placeholder, matching the tokens from Task 2 (this directly verifies the bug fixed in the old Vite app — inputs must be dark by construction here, not via a workaround). Revert `page.tsx`.

- [ ] **Step 5: Commit**

```bash
git add frontend-next/src/components/ui/input.tsx frontend-next/src/components/ui/textarea.tsx frontend-next/src/components/ui/select.tsx
git commit -m "Add Input, Textarea, Select primitives"
```

---

## Task 7: Primitives — Switch, SegmentedControl

**Files:**
- Create: `frontend-next/src/components/ui/switch.tsx`
- Create: `frontend-next/src/components/ui/segmented-control.tsx`

**Interfaces:**
- Consumes: `cn` (Task 2), `@radix-ui/react-switch` (Task 1).
- Produces:
  - `Switch` from `@/components/ui/switch` — props: `checked: boolean`, `onChange: (e: { target: { checked: boolean } }) => void` (shaped to match the native-event style call sites already use, e.g. `onChange={(e) => toggle(m.model_code, e.target.checked)}`).
  - `SegmentedControl` + `SegmentedControl.Item` from `@/components/ui/segmented-control` — `SegmentedControl.Item` props: `selected: boolean`, `onClick: () => void`, `children`.

- [ ] **Step 1: `switch.tsx`**

```tsx
// frontend-next/src/components/ui/switch.tsx
import * as RadixSwitch from "@radix-ui/react-switch";

export interface SwitchProps {
  checked: boolean;
  onChange: (e: { target: { checked: boolean } }) => void;
}

export function Switch({ checked, onChange }: SwitchProps) {
  return (
    <RadixSwitch.Root
      checked={checked}
      onCheckedChange={(next) => onChange({ target: { checked: next } })}
      className="relative h-6 w-10 shrink-0 rounded-full bg-surface-strong outline-none data-[state=checked]:bg-[image:var(--brand-gradient)]"
    >
      <RadixSwitch.Thumb className="block h-4 w-4 translate-x-1 rounded-full bg-white transition-transform data-[state=checked]:translate-x-5" />
    </RadixSwitch.Root>
  );
}
```

- [ ] **Step 2: `segmented-control.tsx`**

```tsx
// frontend-next/src/components/ui/segmented-control.tsx
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

function SegmentedControlItem({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "press-scale flex-1 rounded-full px-3 py-2 text-sm font-medium transition-colors",
        selected ? "bg-[image:var(--brand-gradient)] text-white" : "text-foreground-muted",
      )}
    >
      {children}
    </button>
  );
}

function SegmentedControlRoot({ children }: { children: ReactNode }) {
  return <div className="flex gap-1 rounded-full border border-border-soft bg-surface p-1">{children}</div>;
}

export const SegmentedControl = Object.assign(SegmentedControlRoot, { Item: SegmentedControlItem });
```

- [ ] **Step 3: Verify**

Temporarily render:

```tsx
"use client";
import { useState } from "react";
import { Switch } from "@/components/ui/switch";
import { SegmentedControl } from "@/components/ui/segmented-control";

export default function Home() {
  const [on, setOn] = useState(false);
  const [tab, setTab] = useState("a");
  return (
    <div className="flex flex-col gap-4 p-6">
      <Switch checked={on} onChange={(e) => setOn(e.target.checked)} />
      <SegmentedControl>
        <SegmentedControl.Item selected={tab === "a"} onClick={() => setTab("a")}>A</SegmentedControl.Item>
        <SegmentedControl.Item selected={tab === "b"} onClick={() => setTab("b")}>B</SegmentedControl.Item>
      </SegmentedControl>
    </div>
  );
}
```

`npm run dev`. Expected: toggling the switch slides the thumb and fills the track with the brand gradient; clicking A/B moves the gradient-filled active pill. Revert `page.tsx` (this test file must have `"use client"` at the top since it uses `useState` — remember to remove the whole file content back to the Task 1 placeholder, which has no directive needed since it's not interactive).

- [ ] **Step 4: Commit**

```bash
git add frontend-next/src/components/ui/switch.tsx frontend-next/src/components/ui/segmented-control.tsx
git commit -m "Add Switch, SegmentedControl primitives"
```

---

## Task 8: Primitive — Sheet (replaces Modal)

**Files:**
- Create: `frontend-next/src/components/ui/sheet.tsx`

**Interfaces:**
- Consumes: `cn` (Task 2), `@radix-ui/react-dialog` (Task 1).
- Produces: `Sheet` + `Sheet.Header` from `@/components/ui/sheet` — props: `open: boolean`, `onOpenChange: (open: boolean) => void`, `header?: ReactNode` (usually a `<Sheet.Header>` element), `children`. This is the direct replacement for `telegram-ui`'s `Modal` + `Modal.Header` (same call shape: `<Sheet open={...} onOpenChange={...} header={<Sheet.Header>Title</Sheet.Header>}>...</Sheet>`).

- [ ] **Step 1: `sheet.tsx`**

```tsx
// frontend-next/src/components/ui/sheet.tsx
import type { ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";

function SheetHeader({ children }: { children: ReactNode }) {
  return <div className="px-4 pb-2 pt-4 text-center text-[15px] font-semibold text-foreground">{children}</div>;
}

interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  header?: ReactNode;
  children: ReactNode;
}

function SheetRoot({ open, onOpenChange, header, children }: SheetProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60 data-[state=open]:animate-in data-[state=open]:fade-in" />
        <Dialog.Content
          className="fixed inset-x-0 bottom-0 z-50 max-h-[85vh] overflow-y-auto rounded-t-lg border-t border-border-soft bg-bg-elevated pb-[env(safe-area-inset-bottom)] focus:outline-none"
          aria-describedby={undefined}
        >
          <Dialog.Title asChild>
            <div>{header}</div>
          </Dialog.Title>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export const Sheet = Object.assign(SheetRoot, { Header: SheetHeader });
```

- [ ] **Step 2: Verify**

Temporarily render (needs `"use client"`):

```tsx
"use client";
import { useState } from "react";
import { Sheet } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";

export default function Home() {
  const [open, setOpen] = useState(false);
  return (
    <div className="p-6">
      <Button onClick={() => setOpen(true)}>Open sheet</Button>
      <Sheet open={open} onOpenChange={setOpen} header={<Sheet.Header>Тестовая шторка</Sheet.Header>}>
        <div className="p-4 text-foreground">Содержимое</div>
      </Sheet>
    </div>
  );
}
```

`npm run dev`. Expected: clicking the button slides up a dark bottom sheet with a dimmed overlay behind it; clicking the overlay or pressing Escape closes it. Revert `page.tsx`.

- [ ] **Step 3: Commit**

```bash
git add frontend-next/src/components/ui/sheet.tsx
git commit -m "Add Sheet primitive (Radix Dialog) replacing telegram-ui Modal"
```

---

## Task 9: Port shared lib — api client, Telegram wrapper, image cost, trend styles

**Files:**
- Create: `frontend-next/src/api/client.ts`
- Create: `frontend-next/src/lib/telegram.ts`
- Create: `frontend-next/src/lib/imageCost.ts`
- Create: `frontend-next/src/lib/trendStyles.ts`
- Create: `frontend-next/.env.local.example`

**Interfaces:**
- Produces: `api`, `adminApi`, `ApiError`, and every exported type from `@/api/client` (identical names/shapes to the current `frontend/src/api/client.ts` — see full content below); `tg`, `initTelegram`, `getInitData`, `openLink`, `openTelegramLink`, `openInvoice`, `haptic` from `@/lib/telegram`; `computeImageCreditCost` from `@/lib/imageCost`; `getTrendStyle`, `TrendStyle` from `@/lib/trendStyles`.

- [ ] **Step 1: `api/client.ts` — port with one change (absolute backend URL)**

Read `frontend/src/api/client.ts` for reference (301 lines, all `ModelOut`/`MeOut`/`TariffOut`/admin types plus the `api`/`adminApi` objects). Copy it verbatim into `frontend-next/src/api/client.ts` with exactly one change: the `request()` function's `fetch()` call target.

```ts
// frontend-next/src/api/client.ts
import { getInitData } from "@/lib/telegram";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": getInitData(),
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}) as { detail?: string });
    throw new ApiError(res.status, detail.detail ?? res.statusText);
  }

  return res.json() as Promise<T>;
}
```

Then append every type and the `api`/`adminApi` objects **unchanged** from `frontend/src/api/client.ts` lines 30–303 (all interfaces: `ModelCategory`, `CategoryLimitOut`, `LimitsOut`, `MeOut`, `ModelOut`, `ChatResponse`, `ImageAspect`, `ImageResolution`, `ImageGenerateResponse`, `ToolOut`, `ReferralOut`, `TariffOut`, `CreatePaymentResponse`, `PaymentStatusOut`, `BannerOut`, `CreditPackageOut`, the `api` object with all its methods, and the admin section: `AdminStatsOut`, `AdminUserOut`, `AdminPaymentOut`, `AdminModelOut`, `AdminTariffOut`, `AdminBannerOut`, `BannerWriteFields`, `adminApi`).

- [ ] **Step 2: `lib/telegram.ts` — port, dropping the now-unnecessary theme-forcing code, fixing SSR safety**

The old file's `forceDarkTheme()`/`FORCED_DARK_THEME_VARS`/`themeChanged` listener existed only to counteract `@telegram-apps/telegram-ui` resolving colors through `--tg-theme-*`. Since this migration removes that library entirely, none of that is needed — delete it. Also guard the module-level `window` access, since Next.js pre-renders client components on the server first (Vite never did this, so the old code never needed the guard):

```ts
// frontend-next/src/lib/telegram.ts
type InvoiceStatus = "paid" | "cancelled" | "failed" | "pending";

interface TelegramWebApp {
  initData: string;
  ready(): void;
  expand(): void;
  openLink(url: string, options?: { try_instant_view?: boolean }): void;
  openTelegramLink(url: string): void;
  openInvoice(url: string, callback: (status: InvoiceStatus) => void): void;
  BackButton: {
    show(): void;
    hide(): void;
    onClick(cb: () => void): void;
    offClick(cb: () => void): void;
  };
  HapticFeedback: {
    impactOccurred(style: "light" | "medium" | "heavy"): void;
    notificationOccurred(type: "error" | "success" | "warning"): void;
  };
}

declare global {
  interface Window {
    Telegram?: { WebApp: TelegramWebApp };
  }
}

export const tg: TelegramWebApp | undefined =
  typeof window !== "undefined" ? window.Telegram?.WebApp : undefined;

export function initTelegram(): void {
  if (!tg) return;
  tg.ready();
  tg.expand();
}

export function getInitData(): string {
  return tg?.initData ?? "";
}

export function openLink(url: string): void {
  if (tg) {
    tg.openLink(url, { try_instant_view: false });
  } else {
    window.open(url, "_blank");
  }
}

export function openTelegramLink(url: string): void {
  if (tg) {
    tg.openTelegramLink(url);
  } else {
    window.open(url, "_blank");
  }
}

export function openInvoice(url: string, onStatus: (status: InvoiceStatus) => void): void {
  if (tg) {
    tg.openInvoice(url, onStatus);
  } else {
    window.open(url, "_blank");
  }
}

export function haptic(style: "light" | "medium" | "heavy" = "light"): void {
  tg?.HapticFeedback.impactOccurred(style);
}
```

- [ ] **Step 3: `lib/imageCost.ts` and `lib/trendStyles.ts` — verbatim ports**

Copy `frontend/src/lib/imageCost.ts` to `frontend-next/src/lib/imageCost.ts` unchanged except the import path:

```ts
// frontend-next/src/lib/imageCost.ts
import type { ImageAspect, ImageResolution } from "@/api/client";

const ASPECT_TO_BUCKET: Record<ImageAspect, "square" | "landscape" | "portrait"> = {
  auto: "square",
  "1:1": "square",
  "4:3": "square",
  "4:5": "square",
  "5:4": "square",
  "3:2": "landscape",
  "16:9": "landscape",
  "21:9": "landscape",
  "2:3": "portrait",
  "3:4": "portrait",
  "9:16": "portrait",
};

const COST_MULTIPLIER: Record<string, number> = {
  "square:1k": 1,
  "square:2k": 2,
  "square:4k": 3,
  "landscape:1k": 2,
  "landscape:2k": 3,
  "landscape:4k": 4,
  "portrait:1k": 2,
  "portrait:2k": 3,
  "portrait:4k": 4,
};

export function computeImageCreditCost(baseCost: number, aspect: ImageAspect, resolution: ImageResolution): number {
  const bucket = ASPECT_TO_BUCKET[aspect] ?? "square";
  const multiplier = COST_MULTIPLIER[`${bucket}:${resolution}`] ?? 1;
  return Math.max(1, Math.round(baseCost * multiplier));
}
```

Copy `frontend/src/lib/trendStyles.ts` to `frontend-next/src/lib/trendStyles.ts` verbatim (no import path to change, it's self-contained):

```ts
// frontend-next/src/lib/trendStyles.ts
export interface TrendStyle {
  gradient: string;
  emoji: string;
}

const DEFAULT_STYLE: TrendStyle = { gradient: "linear-gradient(160deg, #6a5cf6, #b721ff)", emoji: "✨" };

const STYLES_BY_SLUG: Record<string, TrendStyle> = {
  "write-post": { gradient: "linear-gradient(160deg, #ff9a56, #ff2d78)", emoji: "📝" },
  "reply-client": { gradient: "linear-gradient(160deg, #4facfe, #6a5cf6)", emoji: "💬" },
  translate: { gradient: "linear-gradient(160deg, #38f9d7, #2ecc71)", emoji: "🌐" },
  "write-code": { gradient: "linear-gradient(160deg, #30cfd0, #5433a7)", emoji: "💻" },
  "product-description": { gradient: "linear-gradient(160deg, #fa709a, #ffb347)", emoji: "🛍️" },
  brainstorm: { gradient: "linear-gradient(160deg, #a18cd1, #ff2d78)", emoji: "💡" },
};

export function getTrendStyle(slug: string): TrendStyle {
  return STYLES_BY_SLUG[slug] ?? DEFAULT_STYLE;
}
```

- [ ] **Step 4: `.env.local.example`**

```
# frontend-next/.env.local.example
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 5: Verify types compile**

```bash
cd frontend-next
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend-next/src/api/client.ts frontend-next/src/lib/telegram.ts frontend-next/src/lib/imageCost.ts frontend-next/src/lib/trendStyles.ts frontend-next/.env.local.example
git commit -m "Port api client and shared lib to Next.js"
```

---

## Task 10: Port MeContext

**Files:**
- Create: `frontend-next/src/context/MeContext.tsx`

**Interfaces:**
- Consumes: `api`, `MeOut` from `@/api/client` (Task 9).
- Produces: `MeProvider`, `useMe(): { me: MeOut | null; loading: boolean; refresh: () => Promise<void> }` from `@/context/MeContext`.

- [ ] **Step 1: Port verbatim (client component)**

```tsx
// frontend-next/src/context/MeContext.tsx
"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type MeOut } from "@/api/client";

interface MeContextValue {
  me: MeOut | null;
  loading: boolean;
  refresh: () => Promise<void>;
}

const MeContext = createContext<MeContextValue>({
  me: null,
  loading: true,
  refresh: async () => {},
});

export function MeProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<MeOut | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setMe(await api.me());
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return <MeContext.Provider value={{ me, loading, refresh }}>{children}</MeContext.Provider>;
}

export function useMe(): MeContextValue {
  return useContext(MeContext);
}
```

The only change from the Vite version is the added `"use client"` directive — required in Next.js App Router for any module using `useState`/`useEffect`/Context.

- [ ] **Step 2: Verify types compile**

```bash
cd frontend-next
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend-next/src/context/MeContext.tsx
git commit -m "Port MeContext to Next.js"
```

---

## Task 11: App shell — layout, login-failed screen, error boundary

**Files:**
- Create: `frontend-next/src/app/layout.tsx`
- Create: `frontend-next/src/components/shell.tsx`
- Create: `frontend-next/src/app/login-failed/page.tsx`
- Create: `frontend-next/src/app/error.tsx`

**Interfaces:**
- Consumes: `MeProvider` (Task 10), `initTelegram` (Task 9), `Button` (Task 4).
- Produces: the root layout every screen renders inside; `Shell` client component providing the bottom tabbar + FAB + fullscreen-route handling (direct port of `frontend/src/App.tsx`'s `Shell`/`Fab`, using `usePathname`/`useRouter` from `next/navigation` instead of `react-router-dom`).

- [ ] **Step 1: `components/shell.tsx` — port of `Shell`/`Fab` from `App.tsx`**

```tsx
// frontend-next/src/components/shell.tsx
"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { initTelegram } from "@/lib/telegram";
import { cn } from "@/lib/cn";

const TABS = [
  { path: "/", text: "Home", icon: "🏠" },
  { path: "/trends", text: "Trends", icon: "✨" },
  { path: "/account", text: "My Account", icon: "👤" },
];

const FULLSCREEN_ROUTES = ["/chat", "/generate-image"];

function Fab() {
  const router = useRouter();
  return (
    <button
      onClick={() => router.push("/chat")}
      aria-label="Открыть чат с нейросетью"
      className="press-scale fixed bottom-20 right-4 z-[2] flex h-[58px] w-[58px] items-center justify-center rounded-full bg-[image:var(--brand-gradient)] text-2xl shadow-glow"
    >
      ✨
    </button>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isFullscreen = FULLSCREEN_ROUTES.includes(pathname);

  useEffect(() => {
    initTelegram();
  }, []);

  return (
    <>
      <div className="min-h-screen" style={{ paddingBottom: isFullscreen ? 0 : 64 }}>
        {children}
      </div>

      {!isFullscreen && <Fab />}

      {!isFullscreen && (
        <div className="fixed inset-x-0 bottom-0 z-[2] border-t border-white/[0.08] bg-black/72 backdrop-blur-xl">
          <div className="flex">
            {TABS.map((tab) => {
              const selected = pathname === tab.path;
              return (
                <button
                  key={tab.path}
                  onClick={() => router.push(tab.path)}
                  className="flex flex-1 flex-col items-center gap-0.5 py-2 text-xs text-foreground-muted"
                >
                  <span
                    className={cn("text-xl transition-transform duration-200", selected && "scale-[1.12]")}
                    style={selected ? { filter: "drop-shadow(0 0 8px rgba(255,45,120,0.6))" } : undefined}
                  >
                    {tab.icon}
                  </span>
                  <span className={selected ? "text-foreground" : undefined}>{tab.text}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 2: `app/layout.tsx`**

```tsx
// frontend-next/src/app/layout.tsx
import type { Metadata } from "next";
import "./globals.css";
import { MeProvider } from "@/context/MeContext";
import { Shell } from "@/components/shell";

export const metadata: Metadata = {
  title: "AI Hub",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>
        <MeProvider>
          <Shell>{children}</Shell>
        </MeProvider>
      </body>
    </html>
  );
}
```

- [ ] **Step 3: `app/login-failed/page.tsx` — replaces the silent-401 case**

This is the screen a user lands on if `MeContext.me` stays `null` after loading (invalid/missing Telegram `initData`) — the pattern noted in the design spec, modeled on the competitor bot's own error screen.

```tsx
// frontend-next/src/app/login-failed/page.tsx
"use client";

import { Button } from "@/components/ui/button";

export default function LoginFailedPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-8 text-center">
      <h1 className="heading-font text-xl font-bold text-foreground">Не удалось войти</h1>
      <p className="text-sm text-foreground-muted">Сессия истекла или вход не удался. Перезапустите приложение.</p>
      <Button onClick={() => window.location.reload()}>Перезапустить</Button>
    </div>
  );
}
```

- [ ] **Step 4: `app/error.tsx` — global error boundary styled on-brand**

```tsx
// frontend-next/src/app/error.tsx
"use client";

import { Button } from "@/components/ui/button";

export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-8 text-center">
      <h1 className="heading-font text-xl font-bold text-foreground">Что-то пошло не так</h1>
      <p className="text-sm text-foreground-muted">Попробуйте ещё раз.</p>
      <Button onClick={reset}>Повторить</Button>
    </div>
  );
}
```

- [ ] **Step 5: Verify**

```bash
npm run dev
```

Open `http://localhost:3000`. Expected: dark page, bottom tabbar with Home/Trends/My Account, pink FAB bottom-right. Clicking tabs navigates via real URL paths (check the browser address bar changes to `/trends`, `/account` — no `#`). Open `http://localhost:3000/login-failed` directly: expected dark "Не удалось войти" screen with a working "Перезапустить" button.

- [ ] **Step 6: Commit**

```bash
git add frontend-next/src/app/layout.tsx frontend-next/src/components/shell.tsx frontend-next/src/app/login-failed frontend-next/src/app/error.tsx
git commit -m "Add app shell (tabbar/FAB), login-failed screen, global error boundary"
```

---

## Task 12: Shared components — HeroCarousel, ImageStack, TrendCard

**Files:**
- Create: `frontend-next/src/components/HeroCarousel.tsx`
- Create: `frontend-next/src/components/ImageStack.tsx`
- Create: `frontend-next/src/components/TrendCard.tsx`

**Interfaces:**
- Consumes: `BannerOut` type (Task 9), `getTrendStyle` (Task 9), `cn` (Task 2).
- Produces: `HeroCarousel({ banners: BannerOut[] })`, `ImageStack({ images: string[] })`, `TrendCard` — same props as their Vite counterparts.

- [ ] **Step 1: Read the three source files and port them**

Read `frontend/src/components/HeroCarousel.tsx`, `frontend/src/components/ImageStack.tsx`, `frontend/src/components/TrendCard.tsx` in full. Port each to `frontend-next/src/components/` with these mechanical changes only:
- Add `"use client"` at the top of any file using `useState`/`useEffect`/`useRef`/event handlers.
- Replace every inline `style={{ ... }}` object with equivalent Tailwind utility classes using the tokens from Task 2 (`bg-surface`, `border-border-soft`, `text-foreground`, `text-foreground-muted`, `rounded-lg`/`rounded-md`, `bg-[image:var(--brand-gradient)]` for the brand gradient). Where a value is fully dynamic (e.g., a computed `transform: translateX(...)` for carousel position, or a per-item gradient string from `getTrendStyle`), keep it as an inline `style` prop — Tailwind classes are for static/token-based styling only, not computed values.
- No telegram-ui imports exist in these three files (confirmed by the import grep in the design spec) — no primitive swap needed here, only the styling mechanism changes.

- [ ] **Step 2: Verify visually**

Temporarily import and render `HeroCarousel` with a hand-built `BannerOut[]` array (2–3 fake banners) in `page.tsx`, and `TrendCard`/`ImageStack` similarly. `npm run dev`, confirm layout/spacing/gradients match the current Vite app's Home screen visually (compare against a screenshot of the live bot if unsure). Revert `page.tsx`.

- [ ] **Step 3: Commit**

```bash
git add frontend-next/src/components/HeroCarousel.tsx frontend-next/src/components/ImageStack.tsx frontend-next/src/components/TrendCard.tsx
git commit -m "Port HeroCarousel, ImageStack, TrendCard to Tailwind"
```

---

## Task 13: Shared components — PhotoUploadBox, AspectRatioSheet

**Files:**
- Create: `frontend-next/src/components/PhotoUploadBox.tsx`
- Create: `frontend-next/src/components/AspectRatioSheet.tsx`

**Interfaces:**
- Consumes: `Sheet` (Task 8), `ImageAspect` type (Task 9), `cn` (Task 2).
- Produces: `PhotoUploadBox({ photos: File[]; onChange: (files: File[]) => void })`, `AspectRatioSheet({ open, value, onOpenChange, onSelect })` — same props as their Vite counterparts.

- [ ] **Step 1: Port `PhotoUploadBox.tsx`**

Read `frontend/src/components/PhotoUploadBox.tsx` in full. Port it with the same mechanical rules as Task 12 (add `"use client"`, convert static inline styles to Tailwind classes, keep genuinely dynamic inline styles as-is). It has no `telegram-ui` import per the grep inventory except one line already noted in the design spec: `color: "var(--tgui--destructive_text_color)"` for the error message — replace that with a plain destructive-red Tailwind class, e.g. `text-red-400`, since `--tgui--destructive_text_color` no longer exists once `telegram-ui` is removed.

- [ ] **Step 2: Port `AspectRatioSheet.tsx` — swap `Modal` for `Sheet`**

Read `frontend/src/components/AspectRatioSheet.tsx` in full (90 lines). Port it to `frontend-next/src/components/AspectRatioSheet.tsx`:
- Add `"use client"`.
- Replace `import { Modal } from "@telegram-apps/telegram-ui"` with `import { Sheet } from "@/components/ui/sheet"`.
- Replace `<Modal open={open} onOpenChange={onOpenChange} header={<Modal.Header>Aspect ratio</Modal.Header>}>` with `<Sheet open={open} onOpenChange={onOpenChange} header={<Sheet.Header>Aspect ratio</Sheet.Header>}>` (identical prop shape — this is the mechanical swap the Sheet primitive was designed for).
- Convert the grid/button inline styles to Tailwind classes (`grid grid-cols-2 gap-2.5 p-4` for the wrapper; the per-option button already uses CSS custom properties like `var(--brand-2)`/`var(--surface)`/`var(--border-soft)` — these now resolve through the Tailwind `@theme` tokens from Task 2 unchanged, since `@theme` still emits them as plain CSS custom properties in addition to utility classes, so no functional change is required there beyond confirming the property names match Task 2's token names (`--color-brand-2`, `--color-surface`, `--color-border-soft` — note the `--color-` prefix Tailwind v4 adds; update the three `var(--brand-2)`/`var(--surface)`/`var(--border-soft)`/`var(--foreground-muted)` references in this file to `var(--color-brand-2)`/`var(--color-surface)`/`var(--color-border-soft)`/`var(--color-foreground-muted)` to match).

- [ ] **Step 3: Verify**

Temporarily wire `AspectRatioSheet` into `page.tsx` with a `useState` for `open`/`value` and a button to open it. `npm run dev`, click the button: expected a bottom sheet listing 11 aspect-ratio options in a 2-column grid, selecting one closes the sheet. Revert `page.tsx`.

- [ ] **Step 4: Commit**

```bash
git add frontend-next/src/components/PhotoUploadBox.tsx frontend-next/src/components/AspectRatioSheet.tsx
git commit -m "Port PhotoUploadBox and AspectRatioSheet (Modal -> Sheet)"
```

---

## Task 14: Screen — Home

**Files:**
- Create: `frontend-next/src/app/page.tsx` (replacing the Task 1 placeholder)

**Interfaces:**
- Consumes: `useMe` (Task 10), `api`, `BannerOut` (Task 9), `HeroCarousel`, `ImageStack` (Task 12), `Button`, `Placeholder`, `Spinner` (Tasks 3–4).

- [ ] **Step 1: Port**

Read `frontend/src/screens/Home.tsx` in full (99 lines). Port to `frontend-next/src/app/page.tsx`:
- Add `"use client"`.
- Replace `import { Button, Placeholder, Spinner } from "@telegram-apps/telegram-ui"` with `import { Button } from "@/components/ui/button"`, `import { Placeholder } from "@/components/ui/placeholder"`, `import { Spinner } from "@/components/ui/spinner"`.
- Replace `import { useNavigate } from "react-router-dom"` and `const navigate = useNavigate()` with `import { useRouter } from "next/navigation"` and `const router = useRouter()`; replace every `navigate("/x")` call with `router.push("/x")`.
- Replace `import { api, type BannerOut } from "../api/client"` with `import { api, type BannerOut } from "@/api/client"`; same relative-to-`@/`-alias swap for `HeroCarousel`, `ImageStack`, `MeContext` imports.
- All inline styles convert to Tailwind classes using Task 2 tokens (this file already uses `className="glass-card"`/`className="heading-font"`/`className="brand-button press-scale"` for some elements — these utility classes don't exist yet in the new app; replace `glass-card` with `rounded-lg border border-border-soft bg-surface backdrop-blur-xl`, and `brand-button` with the `Button` primitive's `filled` mode instead of a raw `<button>` — i.e. change the raw `<button className="brand-button press-scale">✨ Generate</button>` to `<Button onClick={generate}>✨ Generate</Button>`).

- [ ] **Step 2: Write the Playwright verification test**

Create `frontend-next/e2e/home.spec.ts` (Playwright config is set up in Task 27; this file is written now and run then):

```ts
// frontend-next/e2e/home.spec.ts
import { test, expect } from "@playwright/test";

test("home screen renders hero and generate CTA", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Generate Image")).toBeVisible();
  await page.getByRole("button", { name: /Generate/ }).first().click();
  await expect(page).toHaveURL(/\/generate-image$/);
});
```

- [ ] **Step 3: Commit**

```bash
git add frontend-next/src/app/page.tsx frontend-next/e2e/home.spec.ts
git commit -m "Port Home screen to Next.js/Tailwind"
```

---

## Task 15: Screen — Trends

**Files:**
- Create: `frontend-next/src/app/trends/page.tsx`
- Create: `frontend-next/e2e/trends.spec.ts`

**Interfaces:**
- Consumes: `api`, `ToolOut` (Task 9), `TrendCard` (Task 12), `Placeholder`, `Spinner` (Task 3).

- [ ] **Step 1: Port, with one interface change**

Read `frontend/src/screens/Trends.tsx` in full. Port to `frontend-next/src/app/trends/page.tsx` with the same mechanical rules as Task 14: `"use client"`, `@telegram-apps/telegram-ui` → `@/components/ui/placeholder` + `@/components/ui/spinner`, `../` imports → `@/` imports, inline styles → Tailwind classes.

One functional change is required: the current `openTool` handler calls `navigate("/chat", { state: { prefillPrompt: tool.prompt_prefix } })` — `react-router-dom`'s history `state` has no equivalent in `next/navigation`'s `router.push`. Replace it with a query parameter, which Task 20's `Chat` screen reads back:

```tsx
function openTool(tool: ToolOut) {
  router.push(`/chat?prefill=${encodeURIComponent(tool.prompt_prefix)}`);
}
```

- [ ] **Step 2: Write the Playwright test**

```ts
// frontend-next/e2e/trends.spec.ts
import { test, expect } from "@playwright/test";

test("trends screen lists tool cards and opens chat with a prefilled prompt", async ({ page }) => {
  await page.goto("/trends");
  await expect(page.getByText("✨ Photo & Text Trends")).toBeVisible();
  const firstCard = page.locator("button", { hasText: /.+/ }).first();
  await firstCard.click();
  await expect(page).toHaveURL(/\/chat\?prefill=/);
});
```

- [ ] **Step 3: Commit**

```bash
git add frontend-next/src/app/trends/page.tsx frontend-next/e2e/trends.spec.ts
git commit -m "Port Trends screen to Next.js/Tailwind"
```

---

## Task 16: Screen — MyAccount + CreditPurchaseSheet

**Files:**
- Create: `frontend-next/src/app/account/page.tsx`
- Create: `frontend-next/src/components/account/CreditPurchaseSheet.tsx`
- Create: `frontend-next/e2e/account.spec.ts`

**Interfaces:**
- Consumes: `useMe` (Task 10), `api`, `CreditPackageOut` (Task 9), `Button`, `Cell`, `IconButton`, `List`, `Placeholder`, `Progress`, `Section`, `Spinner`, `Sheet` (Tasks 3–8).

- [ ] **Step 1: Port `MyAccount.tsx`**

Read `frontend/src/screens/MyAccount.tsx` in full. Port to `frontend-next/src/app/account/page.tsx`. Component mapping for this file's imports (`Button, Cell, IconButton, List, Placeholder, Progress, Section, Spinner` from `telegram-ui`): swap each for the matching import from `@/components/ui/*` (Tasks 3–5). `Progress`'s `value` prop usage (`me.limits.daily_used / me.limits.daily_limit) * 100`) is unchanged — the new `Progress` primitive (Task 3) takes the same `value: number` (0–100) prop.

- [ ] **Step 2: Port `CreditPurchaseSheet.tsx` — swap `Modal` for `Sheet`**

Read `frontend/src/screens/account/CreditPurchaseSheet.tsx` in full. Port to `frontend-next/src/components/account/CreditPurchaseSheet.tsx` with the same `Modal` → `Sheet` swap as Task 13's `AspectRatioSheet` (identical call shape: `<Modal open onOpenChange={...} header={<Modal.Header>...</Modal.Header>}>` → `<Sheet open onOpenChange={...} header={<Sheet.Header>...</Sheet.Header>}>`), plus `Button, Cell, List, Section, Spinner` swapped to the new primitives.

- [ ] **Step 3: Write the Playwright test**

```ts
// frontend-next/e2e/account.spec.ts
import { test, expect } from "@playwright/test";

test("account screen shows plan and credits", async ({ page }) => {
  await page.goto("/account");
  await expect(page.getByText("Current plan")).toBeVisible();
  await expect(page.getByText("Credits")).toBeVisible();
  await expect(page.getByText(/кредитов/)).toBeVisible();
});
```

(`"Current plan"` and `"Credits"` are hardcoded English labels in the current Russian-language screen — kept verbatim from the source during the port, so they're stable, literal strings to assert on.)

- [ ] **Step 4: Commit**

```bash
git add frontend-next/src/app/account/page.tsx frontend-next/src/components/account/CreditPurchaseSheet.tsx frontend-next/e2e/account.spec.ts
git commit -m "Port MyAccount screen and CreditPurchaseSheet to Next.js/Tailwind"
```

---

## Task 17: Screen — Tariffs + PaymentMethodSheet

**Files:**
- Create: `frontend-next/src/app/tariffs/page.tsx`
- Create: `frontend-next/src/components/tariffs/PaymentMethodSheet.tsx`
- Create: `frontend-next/e2e/tariffs.spec.ts`

**Interfaces:**
- Consumes: `api`, `TariffOut` (Task 9), `Button`, `Cell`, `List`, `Placeholder`, `Section`, `Spinner`, `Sheet` (Tasks 3–8).

- [ ] **Step 1: Port `Tariffs.tsx`**

Read `frontend/src/screens/Tariffs.tsx` in full. Port to `frontend-next/src/app/tariffs/page.tsx`, swapping `Button, Cell, List, Placeholder, Section, Spinner` per the established mapping. This screen uses `Button mode={tariff.is_current ? "gray" : "filled"}` — the `gray` mode added to the `Button` primitive in Task 4.

- [ ] **Step 2: Port `PaymentMethodSheet.tsx`**

Read `frontend/src/screens/tariffs/PaymentMethodSheet.tsx` in full. Port to `frontend-next/src/components/tariffs/PaymentMethodSheet.tsx` with the same `Modal` → `Sheet` swap, plus `Button, Cell, List, Section, Spinner`.

- [ ] **Step 3: Write the Playwright test**

```ts
// frontend-next/e2e/tariffs.spec.ts
import { test, expect } from "@playwright/test";

test("tariffs screen lists plans under the Тарифы section", async ({ page }) => {
  await page.goto("/tariffs");
  await expect(page.getByText("Тарифы")).toBeVisible();
});
```

- [ ] **Step 4: Commit**

```bash
git add frontend-next/src/app/tariffs/page.tsx frontend-next/src/components/tariffs/PaymentMethodSheet.tsx frontend-next/e2e/tariffs.spec.ts
git commit -m "Port Tariffs screen and PaymentMethodSheet to Next.js/Tailwind"
```

---

## Task 18: Screen — Referral

**Files:**
- Create: `frontend-next/src/app/referral/page.tsx`
- Create: `frontend-next/e2e/referral.spec.ts`

**Interfaces:**
- Consumes: `api`, `ReferralOut` (Task 9), `Button`, `Cell`, `List`, `Placeholder`, `Section`, `Spinner` (Tasks 3–5), `openTelegramLink` (Task 9).

- [ ] **Step 1: Port**

Read `frontend/src/screens/Referral.tsx` in full. Port to `frontend-next/src/app/referral/page.tsx`, swapping `Button, Cell, List, Placeholder, Section, Spinner`. This screen uses `Section`'s `footer` prop (`<Section header="Реферальная программа" footer={data.link}>`) — added to the `Section` primitive in Task 5.

- [ ] **Step 2: Write the Playwright test**

```ts
// frontend-next/e2e/referral.spec.ts
import { test, expect } from "@playwright/test";

test("referral screen shows invite stats and actions", async ({ page }) => {
  await page.goto("/referral");
  await expect(page.getByText("Реферальная программа")).toBeVisible();
  await expect(page.getByRole("button", { name: "Поделиться" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Скопировать" })).toBeVisible();
});
```

- [ ] **Step 3: Commit**

```bash
git add frontend-next/src/app/referral/page.tsx frontend-next/e2e/referral.spec.ts
git commit -m "Port Referral screen to Next.js/Tailwind"
```

---

## Task 19: Screen — Settings

**Files:**
- Create: `frontend-next/src/app/settings/page.tsx`
- Create: `frontend-next/e2e/settings.spec.ts`

**Interfaces:**
- Consumes: `Cell`, `List`, `Section` (Task 5), `openTelegramLink` (Task 9).

- [ ] **Step 1: Port**

Read `frontend/src/screens/Settings.tsx` in full (22 lines — the simplest screen in the app). Port to `frontend-next/src/app/settings/page.tsx`, swapping `Cell, List, Section`.

- [ ] **Step 2: Write the Playwright test**

```ts
// frontend-next/e2e/settings.spec.ts
import { test, expect } from "@playwright/test";

test("settings screen renders", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByText("AI Hub")).toBeVisible();
});
```

- [ ] **Step 3: Commit**

```bash
git add frontend-next/src/app/settings/page.tsx frontend-next/e2e/settings.spec.ts
git commit -m "Port Settings screen to Next.js/Tailwind"
```

---

## Task 20: Screen — Chat + ModelPicker

**Files:**
- Create: `frontend-next/src/app/chat/page.tsx`
- Create: `frontend-next/src/components/chat/ModelPicker.tsx`
- Create: `frontend-next/e2e/chat.spec.ts`

**Interfaces:**
- Consumes: `api`, `ModelOut`, `ChatResponse` (Task 9), `Button`, `Placeholder`, `Spinner`, `Textarea` (Tasks 3, 6), `Cell`, `List`, `Modal`→`Sheet`, `Section` (for `ModelPicker`).

- [ ] **Step 1: Port `Chat.tsx`, with the prefill mechanism changed to match Task 15**

Read `frontend/src/screens/Chat.tsx` in full. Port to `frontend-next/src/app/chat/page.tsx`, swapping `Button, Placeholder, Spinner, Textarea`.

The current file reads its prefill value via `react-router-dom`'s `useLocation().state`:

```tsx
const location = useLocation();
const prefill = (location.state as { prefillPrompt?: string } | null)?.prefillPrompt ?? "";
```

Since Task 15 now sends the prefill as a `?prefill=` query parameter instead of router state, replace this with `next/navigation`'s `useSearchParams`:

```tsx
"use client";
import { useSearchParams } from "next/navigation";
// ...
const searchParams = useSearchParams();
const prefill = searchParams.get("prefill") ?? "";
```

Everything else in the file (the `prompt`/`messages`/`sending` state, `send()`, the message list rendering) is unchanged.

- [ ] **Step 2: Port `ModelPicker.tsx`**

Read `frontend/src/screens/chat/ModelPicker.tsx` in full. Port to `frontend-next/src/components/chat/ModelPicker.tsx`. Note this component uses `Modal`'s `trigger` prop pattern (`<Modal ... trigger={<Button size="s" mode="bezeled">...}>`) — the `Sheet` primitive built in Task 8 does **not** have a `trigger` prop (it's a controlled `open`/`onOpenChange` component only, matching every other Modal usage in the app). Convert this call site to the controlled pattern: hoist an `open` state into `ModelPicker` itself, render the trigger `Button` with `onClick={() => setOpen(true)}` next to `<Sheet open={open} onOpenChange={setOpen} ...>`.

- [ ] **Step 3: Write the Playwright test**

```ts
// frontend-next/e2e/chat.spec.ts
import { test, expect } from "@playwright/test";

test("chat screen renders input and model picker", async ({ page }) => {
  await page.goto("/chat");
  await expect(page.getByPlaceholder("Сообщение...")).toBeVisible();
});
```

- [ ] **Step 4: Commit**

```bash
git add frontend-next/src/app/chat/page.tsx frontend-next/src/components/chat/ModelPicker.tsx frontend-next/e2e/chat.spec.ts
git commit -m "Port Chat screen and ModelPicker to Next.js/Tailwind"
```

---

## Task 21: Screen — GenerateImage

**Files:**
- Create: `frontend-next/src/app/generate-image/page.tsx`
- Create: `frontend-next/e2e/generate-image.spec.ts`

**Interfaces:**
- Consumes: `api`, `ImageAspect`, `ImageResolution`, `ModelOut` (Task 9), `AspectRatioSheet`, `PhotoUploadBox` (Task 13), `computeImageCreditCost` (Task 9), `haptic` (Task 9), `Cell`, `List`, `Modal`→`Sheet`, `Section`, `Spinner`, `Textarea` (Tasks 3–8).

This is the most complex screen (267 lines in the current Vite version, already restructured earlier in this project to show 1K/2K/4K as three inline buttons instead of a hidden sheet — see git history commit `82302c7`).

- [ ] **Step 1: Port**

Read `frontend-next`'s already-ported `AspectRatioSheet.tsx`/`PhotoUploadBox.tsx` (Task 13) and `frontend/src/screens/GenerateImage.tsx` in full (current version, post-`82302c7`). Port to `frontend-next/src/app/generate-image/page.tsx`:
- `"use client"`.
- `Cell, List, Modal, Section, Spinner, Textarea` from `telegram-ui` → `Cell` (Task 5), `List` (Task 5), `Sheet` (Task 8, replacing `Modal`/`Modal.Header`), `Section` (Task 5), `Spinner` (Task 3), `Textarea` (Task 6).
- The model-picker `<Modal open={pickerOpen} onOpenChange={setPickerOpen} header={<Modal.Header>Выберите модель</Modal.Header>}>` → `<Sheet open={pickerOpen} onOpenChange={setPickerOpen} header={<Sheet.Header>Выберите модель</Sheet.Header>}>`.
- The resolution row (3 buttons: 1K/2K/4K) and aspect-ratio chip are already plain `<button>` elements with inline styles from `chipStyle()` — convert `chipStyle(active: boolean)` from a function returning a `CSSProperties` object to a function returning a Tailwind class string using `cn`, e.g.:

```tsx
function chipClass(active: boolean): string {
  return cn(
    "press-scale flex-1 rounded-full border border-border-soft px-3 py-2.5 text-[13px] font-semibold text-white",
    active ? "bg-[image:var(--brand-gradient)]" : "bg-surface",
  );
}
```

- `useNavigate` → `useRouter`/`router.push`/`router.back()` (the header's back button called `navigate(-1)` — replace with `router.back()`).

- [ ] **Step 2: Write the Playwright test — reproduces this session's dark-theme regression check**

```ts
// frontend-next/e2e/generate-image.spec.ts
import { test, expect } from "@playwright/test";

test("generate-image screen has a dark textarea and resolution buttons", async ({ page }) => {
  await page.goto("/generate-image");
  const textarea = page.getByPlaceholder("Опишите, что хотите создать");
  await expect(textarea).toBeVisible();
  const bg = await textarea.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(bg).not.toBe("rgb(255, 255, 255)");

  await expect(page.getByRole("button", { name: "1K" })).toBeVisible();
  await expect(page.getByRole("button", { name: "2K" })).toBeVisible();
  await expect(page.getByRole("button", { name: "4K" })).toBeVisible();
});
```

- [ ] **Step 3: Commit**

```bash
git add frontend-next/src/app/generate-image/page.tsx frontend-next/e2e/generate-image.spec.ts
git commit -m "Port GenerateImage screen to Next.js/Tailwind"
```

---

## Task 22: Admin — AdminPanel shell

**Files:**
- Create: `frontend-next/src/app/admin/page.tsx`
- Create: `frontend-next/e2e/admin-panel.spec.ts`

**Interfaces:**
- Consumes: `useMe` (Task 10), `Placeholder` (Task 3), `SegmentedControl` (Task 7).

- [ ] **Step 1: Port**

Read `frontend/src/screens/admin/AdminPanel.tsx` in full. Port to `frontend-next/src/app/admin/page.tsx`, swapping `Placeholder, SegmentedControl` for the Task 3/7 primitives. This screen renders one of the 6 admin sub-screens (Stats/Users/Payments/Models/Tariffs/Banners) based on `SegmentedControl` tab state — the sub-screens themselves are ported in Tasks 23–25 and imported here unchanged in structure from the current `AdminPanel.tsx`.

- [ ] **Step 2: Write the Playwright test**

This screen already has a clear, meaningful default-state assertion available: a non-admin user (the default mocked Telegram identity every other spec in this plan uses) must see the access-denied placeholder, never the tab switcher or any admin data.

```ts
// frontend-next/e2e/admin-panel.spec.ts
import { test, expect } from "@playwright/test";

test("admin panel blocks non-admin users", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByText("Доступ запрещён")).toBeVisible();
});
```

- [ ] **Step 3: Commit**

```bash
git add frontend-next/src/app/admin/page.tsx frontend-next/e2e/admin-panel.spec.ts
git commit -m "Port AdminPanel shell to Next.js/Tailwind"
```

---

## Task 23: Admin — Stats, Users

**Files:**
- Create: `frontend-next/src/screens/admin/AdminStats.tsx`
- Create: `frontend-next/src/screens/admin/AdminUsers.tsx`
- Create: `frontend-next/e2e/admin-stats.spec.ts`
- Create: `frontend-next/e2e/admin-users.spec.ts`

**Interfaces:**
- Consumes: `adminApi`, `AdminStatsOut`, `AdminUserOut` (Task 9), `Cell`, `List`, `Placeholder`, `Section`, `Spinner` (Tasks 3, 5), `Button`, `Input` (Tasks 4, 6).

- [ ] **Step 1: Port `AdminStats.tsx`**

Read `frontend/src/screens/admin/AdminStats.tsx` in full. Port to `frontend-next/src/screens/admin/AdminStats.tsx` (kept as a plain component under `src/screens/admin/`, not an `app/` route, since it's rendered conditionally inside `AdminPanel`'s tab switcher from Task 22 — same structure as the current Vite app). Swap `Cell, List, Placeholder, Section, Spinner`.

- [ ] **Step 2: Port `AdminUsers.tsx`**

Read `frontend/src/screens/admin/AdminUsers.tsx` in full. Port to `frontend-next/src/screens/admin/AdminUsers.tsx`. Swap `Button, Cell, Input, List, Section, Spinner`.

- [ ] **Step 3: Wire both into `AdminPanel` (Task 22) and verify manually**

Import `AdminStats`/`AdminUsers` in `frontend-next/src/app/admin/page.tsx`. `npm run dev`, open `/admin` (requires a logged-in admin user via mocked `initData` — see Task 27 for the mocking setup that the two Playwright specs below depend on; for a quick manual check without that, temporarily hardcode `is_admin: true` in a local `MeContext` stub, then revert). Expected: switching to "Статистика"/"Пользователи" tabs renders their respective lists.

- [ ] **Step 4: Write the Playwright tests**

These cannot run standalone yet — they need the admin-flavored Telegram mock Task 27 adds. Write them now; Task 27 wires the mock into every spec file including these two.

```ts
// frontend-next/e2e/admin-stats.spec.ts
import { test, expect } from "@playwright/test";

test("admin stats tab shows today's numbers", async ({ page }) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "Статистика" }).click();
  await expect(page.getByText("Сегодня")).toBeVisible();
});
```

```ts
// frontend-next/e2e/admin-users.spec.ts
import { test, expect } from "@playwright/test";

test("admin users tab shows the search section", async ({ page }) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "Пользователи" }).click();
  await expect(page.getByText("Поиск по Telegram ID или username")).toBeVisible();
});
```

- [ ] **Step 5: Commit**

```bash
git add frontend-next/src/screens/admin/AdminStats.tsx frontend-next/src/screens/admin/AdminUsers.tsx frontend-next/e2e/admin-stats.spec.ts frontend-next/e2e/admin-users.spec.ts
git commit -m "Port AdminStats and AdminUsers to Next.js/Tailwind"
```

---

## Task 24: Admin — Payments, Models

**Files:**
- Create: `frontend-next/src/screens/admin/AdminPayments.tsx`
- Create: `frontend-next/src/screens/admin/AdminModels.tsx`
- Create: `frontend-next/e2e/admin-payments.spec.ts`
- Create: `frontend-next/e2e/admin-models.spec.ts`

**Interfaces:**
- Consumes: `adminApi`, `AdminPaymentOut`, `AdminModelOut` (Task 9), `Button`, `Cell`, `Input`, `List`, `Placeholder`, `Section`, `Spinner`, `Switch` (Tasks 3–7).

- [ ] **Step 1: Port `AdminPayments.tsx`**

Read `frontend/src/screens/admin/AdminPayments.tsx` in full. Port to `frontend-next/src/screens/admin/AdminPayments.tsx`. Swap `Button, Cell, List, Placeholder, Section, Spinner`.

- [ ] **Step 2: Port `AdminModels.tsx`**

Read `frontend/src/screens/admin/AdminModels.tsx` in full. Port to `frontend-next/src/screens/admin/AdminModels.tsx`. Swap `Cell, Input, List, Placeholder, Section, Spinner, Switch` — note the `Switch` call site (`<Switch checked={m.is_active} onChange={(e) => toggle(m.model_code, e.target.checked)} />`) matches the Task 7 `Switch` primitive's prop shape exactly, no logic change needed.

- [ ] **Step 3: Wire into `AdminPanel` and verify manually**

Same manual-check procedure as Task 23 Step 3, for the "Платежи"/"Модели" tabs.

- [ ] **Step 4: Write the Playwright tests**

`AdminModels`'s `Section header="Модели"` renders the exact same text as its own `SegmentedControl.Item` tab label — asserting plain visibility would pass even if the tab click did nothing (the tab label text is already on the page). Assert the count goes from 1 (tab only) to 2 (tab + section header) after the click, which only holds if the section actually rendered.

```ts
// frontend-next/e2e/admin-payments.spec.ts
import { test, expect } from "@playwright/test";

test("admin payments tab shows recent payments", async ({ page }) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "Платежи" }).click();
  await expect(page.getByText("Последние платежи")).toBeVisible();
});
```

```ts
// frontend-next/e2e/admin-models.spec.ts
import { test, expect } from "@playwright/test";

test("admin models tab renders the models section", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByText("Модели")).toHaveCount(1); // only the tab label, section not mounted yet
  await page.getByRole("button", { name: "Модели" }).click();
  await expect(page.getByText("Модели")).toHaveCount(2); // tab label + Section header
});
```

- [ ] **Step 5: Commit**

```bash
git add frontend-next/src/screens/admin/AdminPayments.tsx frontend-next/src/screens/admin/AdminModels.tsx frontend-next/e2e/admin-payments.spec.ts frontend-next/e2e/admin-models.spec.ts
git commit -m "Port AdminPayments and AdminModels to Next.js/Tailwind"
```

---

## Task 25: Admin — Tariffs, Banners

**Files:**
- Create: `frontend-next/src/screens/admin/AdminTariffs.tsx`
- Create: `frontend-next/src/screens/admin/AdminBanners.tsx`
- Create: `frontend-next/e2e/admin-tariffs.spec.ts`
- Create: `frontend-next/e2e/admin-banners.spec.ts`

**Interfaces:**
- Consumes: `adminApi`, `AdminTariffOut`, `AdminBannerOut`, `BannerWriteFields` (Task 9), `Button`, `Cell`, `Input`, `List`, `Placeholder`, `Section`, `Select`, `Spinner`, `Switch` (Tasks 3–7).

- [ ] **Step 1: Port `AdminTariffs.tsx`**

Read `frontend/src/screens/admin/AdminTariffs.tsx` in full. Port to `frontend-next/src/screens/admin/AdminTariffs.tsx`. Swap `Button, Cell, Input, List, Section, Spinner, Switch`.

- [ ] **Step 2: Port `AdminBanners.tsx`**

Read `frontend/src/screens/admin/AdminBanners.tsx` in full (the most form-heavy admin screen — 6 `Input`s, 1 `Select`, 1 `Switch`). Port to `frontend-next/src/screens/admin/AdminBanners.tsx`. Swap `Button, Cell, Input, List, Placeholder, Section, Select, Spinner, Switch`. The `Select` call site (`<Select header="Действие по клику" value={form.action_type} onChange={(e) => setForm({ ...form, action_type: e.target.value as "prompt" | "link" })}>`) matches the Task 6 `Select` primitive's native-`onChange`-event shape exactly.

- [ ] **Step 3: Wire into `AdminPanel` and verify manually**

Same manual-check procedure as Task 23 Step 3, for the "Тарифы"/"Карусель" tabs. Specifically confirm the banner creation form's inputs render with dark backgrounds and light text/placeholders (this form is where the original `telegram-ui` white-textarea-class bug would have been most visible if it existed here too).

- [ ] **Step 4: Write the Playwright tests**

`AdminTariffs`'s `Section header="Тарифы"` has the same tab/section text-collision as `AdminModels` in Task 24 — use the same before/after count assertion. `AdminBanners`'s section headers ("Карусель на главной", "Новый баннер") don't collide with any tab label, so a plain visibility check is enough there.

```ts
// frontend-next/e2e/admin-tariffs.spec.ts
import { test, expect } from "@playwright/test";

test("admin tariffs tab renders the tariffs section", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByText("Тарифы")).toHaveCount(1); // only the tab label
  await page.getByRole("button", { name: "Тарифы" }).click();
  await expect(page.getByText("Тарифы")).toHaveCount(2); // tab label + Section header
});
```

```ts
// frontend-next/e2e/admin-banners.spec.ts
import { test, expect } from "@playwright/test";

test("admin banners tab shows the carousel list and the new-banner form", async ({ page }) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "Карусель" }).click();
  await expect(page.getByText("Карусель на главной")).toBeVisible();
  await expect(page.getByText("Новый баннер")).toBeVisible();
  await expect(page.getByRole("button", { name: "Добавить баннер" })).toBeVisible();
});
```

- [ ] **Step 5: Commit**

```bash
git add frontend-next/src/screens/admin/AdminTariffs.tsx frontend-next/src/screens/admin/AdminBanners.tsx frontend-next/e2e/admin-tariffs.spec.ts frontend-next/e2e/admin-banners.spec.ts
git commit -m "Port AdminTariffs and AdminBanners to Next.js/Tailwind"
```

---

## Task 26: Deploy config — Render service, Dockerfile, CORS

**Files:**
- Create: `frontend-next/Dockerfile`
- Modify: `render.yaml`
- Modify: `app/main.py` (backend CORS)

**Interfaces:**
- Produces: a buildable Docker image for `ai-hub-frontend`; a `render.yaml` with two services; FastAPI CORS middleware allowing the frontend's origin.

- [ ] **Step 1: `frontend-next/Dockerfile`**

```dockerfile
# frontend-next/Dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
```

This relies on Next.js's `output: "standalone"` build mode. Add it to `frontend-next/next.config.ts`:

```ts
// frontend-next/next.config.ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
```

- [ ] **Step 2: Read the current `render.yaml` and add the new service**

Read `render.yaml` in full first. Add a second service alongside the existing backend one (keep the existing service block completely unchanged):

```yaml
  - type: web
    name: ai-hub-frontend
    runtime: docker
    dockerfilePath: ./frontend-next/Dockerfile
    dockerContext: ./frontend-next
    envVars:
      - key: NEXT_PUBLIC_API_URL
        sync: false
    plan: starter
    autoDeploy: false
```

Set `autoDeploy: false` deliberately — per the existing project memory, Render's `autoDeploy: "yes"` has been observed to silently not fire on this account for the backend service; manual deploy triggers via the Render API are already the established workflow, so match it here rather than assuming auto-deploy will work.

- [ ] **Step 3: Add CORS to the FastAPI backend**

Read `app/main.py` in full first, to place this correctly relative to existing middleware/lifespan setup. Add (import `CORSMiddleware` from `fastapi.middleware.cors`):

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url] if settings.frontend_url else [],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Add `frontend_url: str | None = None` to the settings model in `app/config.py` (read that file first to match its existing pattern for optional string settings), sourced from a `FRONTEND_URL` env var.

- [ ] **Step 4: Verify locally**

```bash
# terminal 1
cd frontend-next && npm run build && node .next/standalone/server.js
# terminal 2
cd .. && FRONTEND_URL=http://localhost:3000 uvicorn app.main:app --reload
```

Open `http://localhost:3000`, confirm `/api/me` requests succeed without a CORS error in the browser console (network tab shows `Access-Control-Allow-Origin: http://localhost:3000` on the response).

- [ ] **Step 5: Commit**

```bash
git add frontend-next/Dockerfile frontend-next/next.config.ts render.yaml app/main.py app/config.py
git commit -m "Add Next.js frontend Render service and backend CORS"
```

---

## Task 27: End-to-end verification across all screens

**Files:**
- Create: `frontend-next/playwright.config.ts`
- Create: `frontend-next/e2e/mock-telegram.ts`
- Modify: every `e2e/*.spec.ts` file created in Tasks 14–25 (add the Telegram mock)

**Interfaces:**
- Produces: a runnable `npm run test:e2e` in `frontend-next` covering all 8 top-level screens, the admin panel shell, and all 6 admin sub-screens (15 spec files total).

- [ ] **Step 1: `playwright.config.ts`**

```ts
// frontend-next/playwright.config.ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
  },
  use: {
    baseURL: "http://localhost:3000",
  },
});
```

Install Playwright:

```bash
cd frontend-next
npm install -D @playwright/test
npx playwright install chromium
```

- [ ] **Step 2: `e2e/mock-telegram.ts` — reusable init script**

This reproduces the mocking pattern already used earlier in this project (documented in project memory): a mocked `window.Telegram.WebApp` with HMAC-signed `initData`, since real generation always needs a genuine Telegram session otherwise.

```ts
// frontend-next/e2e/mock-telegram.ts
import crypto from "node:crypto";
import type { Page } from "@playwright/test";

function signInitData(botToken: string, telegramId: number): string {
  const authDate = Math.floor(Date.now() / 1000);
  const user = JSON.stringify({ id: telegramId, first_name: "Test", username: "test_user" });
  const params: Record<string, string> = {
    auth_date: String(authDate),
    query_id: "test_query_id",
    user,
  };
  const dataCheckString = Object.keys(params)
    .sort()
    .map((k) => `${k}=${params[k]}`)
    .join("\n");
  const secretKey = crypto.createHmac("sha256", "WebAppData").update(botToken).digest();
  const hash = crypto.createHmac("sha256", secretKey).update(dataCheckString).digest("hex");
  const search = new URLSearchParams({ ...params, hash });
  return search.toString();
}

export async function mockTelegramWebApp(page: Page, botToken: string, telegramId = 999999): Promise<void> {
  const initData = signInitData(botToken, telegramId);
  await page.addInitScript((data) => {
    (window as unknown as { Telegram: unknown }).Telegram = {
      WebApp: {
        initData: data,
        ready: () => {},
        expand: () => {},
        openLink: () => {},
        openTelegramLink: () => {},
        openInvoice: () => {},
        BackButton: { show: () => {}, hide: () => {}, onClick: () => {}, offClick: () => {} },
        HapticFeedback: { impactOccurred: () => {}, notificationOccurred: () => {} },
      },
    };
  }, initData);
}
```

- [ ] **Step 3: Wire the mock into every spec file — two flavors**

Nine spec files (`home`, `trends`, `account`, `tariffs`, `referral`, `settings`, `chat`, `generate-image`, `admin-panel`) test as a regular, non-admin user — the default `telegramId` (`999999`) is correct for them:

```ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token");
});
```

(Insert this block right after the imports in each of those 9 files, keeping the existing `test(...)` bodies unchanged. `admin-panel.spec.ts` specifically relies on this non-admin identity — it asserts the access-denied gate.)

The 6 admin sub-screen specs from Tasks 23–25 (`admin-stats`, `admin-users`, `admin-payments`, `admin-models`, `admin-tariffs`, `admin-banners`) need a Telegram ID the target backend actually recognizes as an admin (per that backend's `ADMIN_IDS` setting — see `README.md`'s "Обязательные переменные окружения" section). Pass it explicitly instead of relying on the default:

```ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  const adminId = Number(process.env.TEST_ADMIN_TELEGRAM_ID);
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token", adminId);
});
```

(Insert this block right after the imports in each of those 6 files.)

- [ ] **Step 4: Run the full suite**

```bash
cd frontend-next
TEST_BOT_TOKEN=<real BOT_TOKEN from .env> TEST_ADMIN_TELEGRAM_ID=<a Telegram ID listed in the backend's ADMIN_IDS> npm run test:e2e
```

Add the script to `package.json`: `"test:e2e": "playwright test"`.

Expected: all 15 tests pass. If a test fails because the backend isn't running locally (real `/api/me` 401s without a real bot token matching a real backend `.env`), run the backend locally per Task 26 Step 4 first. If only the 6 admin specs fail with an access-denied assertion error, `TEST_ADMIN_TELEGRAM_ID` doesn't match an ID in the running backend's `ADMIN_IDS`.

- [ ] **Step 5: Commit**

```bash
git add frontend-next/playwright.config.ts frontend-next/e2e frontend-next/package.json
git commit -m "Add Playwright E2E suite covering all migrated screens"
```

---

## Task 28: Cutover

**Files:**
- Modify: `.env` (bot's `WEBAPP_URL`)
- Delete: `frontend/` (entire old Vite app)
- Modify: `Dockerfile` (root — remove the now-obsolete frontend-build stage that copied Vite's `dist/` into the backend image, since the frontend is now its own service)
- Modify: `README.md`

**Interfaces:**
- None — this is the final integration step, no new code interfaces.

- [ ] **Step 1: Deploy both Render services**

Trigger deploys for `ai-hub-backend` (picks up the Task 26 CORS change) and the new `ai-hub-frontend` service, following this project's established manual-trigger workflow (Render's `autoDeploy` has not been reliable here — `POST /v1/services/{id}/deploys` then poll `/deploys/{id}` for `status: "live"`, as documented in project memory).

- [ ] **Step 2: Smoke-test the deployed frontend against the deployed backend**

Open the new frontend's Render URL directly in a browser (not through Telegram) — expect the `/login-failed` behavior (no real `initData` outside Telegram) rather than a crash. Then open the bot in real Telegram with the Mini App URL temporarily pointed at the new frontend (via BotFather's web app URL setting, or however `WEBAPP_URL` is currently wired per `app/main.py`'s lifespan bot setup) and click through all 8 screens manually once.

- [ ] **Step 3: Switch `WEBAPP_URL`**

Update the `WEBAPP_URL` env var (wherever it's set for the production backend service — Render dashboard or `.env`) to the new frontend's URL, redeploy the backend so its `lifespan` re-registers the Menu Button per the existing pattern in `README.md`.

- [ ] **Step 4: Remove the old Vite frontend and its build stage**

```bash
git rm -r frontend
```

Read the root `Dockerfile` in full, remove the `frontend-build` stage and the `COPY --from=frontend-build /frontend/dist frontend/dist` line (the backend no longer serves any frontend — Next.js does, from its own service/Dockerfile in `frontend-next/`).

- [ ] **Step 5: Update `README.md`**

Read the current `README.md` in full. Replace the "Локальная разработка" and "Структура" sections' references to `frontend/` (Vite) with `frontend-next/` (Next.js), and the "Продакшен" section to describe the two-service topology from Task 26 instead of the single combined image.

- [ ] **Step 6: Final verification**

```bash
npx tsc --noEmit --project frontend-next/tsconfig.json
cd frontend-next && npm run lint && npm run test:e2e
```

Expected: all pass. Manually re-open the bot in Telegram once more after this cleanup commit to confirm nothing broke (the old `frontend/` removal and Dockerfile change don't affect the already-deployed `ai-hub-frontend`/`ai-hub-backend` services until the next deploy, so this is a safety check before the *next* backend deploy goes out).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Cut over to Next.js frontend: remove Vite app, update Dockerfile and README"
```
