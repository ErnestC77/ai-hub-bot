import type { ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";

function SheetHeader({ children }: { children: ReactNode }) {
  return <div className="px-4 pb-2 pt-1 text-center text-[15px] font-semibold text-foreground">{children}</div>;
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
        <Dialog.Overlay className="fade-in fixed inset-0 z-40 bg-[rgba(5,3,12,0.62)] backdrop-blur-[3px]" />
        <Dialog.Content
          className="sheet-up fixed inset-x-0 bottom-0 z-50 max-h-[85vh] overflow-y-auto rounded-t-[26px] border-t border-white/[0.12] bg-[linear-gradient(180deg,#150d2c,#0b0716)] pb-[env(safe-area-inset-bottom)] focus:outline-none"
          aria-describedby={undefined}
        >
          <div aria-hidden className="mx-auto mb-2.5 mt-3.5 h-1 w-[38px] rounded-full bg-white/20" />
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
