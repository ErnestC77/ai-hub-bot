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
