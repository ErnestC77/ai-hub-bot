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
      className="relative h-5 w-[34px] shrink-0 rounded-full bg-surface-strong outline-none data-[state=checked]:bg-[image:var(--brand-gradient)]"
    >
      <RadixSwitch.Thumb className="block h-4 w-4 translate-x-[2px] rounded-full bg-white transition-transform data-[state=checked]:translate-x-[16px]" />
    </RadixSwitch.Root>
  );
}
