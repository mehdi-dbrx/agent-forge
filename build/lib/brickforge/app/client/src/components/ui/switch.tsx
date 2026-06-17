import * as React from 'react';

import { cn } from '@/lib/utils';

export interface SwitchProps
  extends Omit<
    React.ButtonHTMLAttributes<HTMLButtonElement>,
    'onChange' | 'children'
  > {
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  /** Optional label shown next to the switch */
  label?: React.ReactNode;
}

const Switch = React.forwardRef<HTMLButtonElement, SwitchProps>(
  (
    { className, checked = false, onCheckedChange, label, onClick, ...props },
    ref,
  ) => {
    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      onCheckedChange?.(!checked);
      onClick?.(e);
    };

    return (
      <label className="inline-flex cursor-pointer items-center gap-2">
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          ref={ref}
          onClick={handleClick}
          className={cn(
            'peer inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50',
            checked ? 'bg-primary' : 'bg-input',
            className,
          )}
          {...props}
        >
          <span
            className={cn(
              'pointer-events-none block h-5 w-5 rounded-full bg-background shadow-lg ring-0 transition-transform',
              checked ? 'translate-x-[22px]' : 'translate-x-0.5',
            )}
          />
        </button>
        {label != null && (
          <span className="text-sm font-medium text-foreground">{label}</span>
        )}
      </label>
    );
  },
);
Switch.displayName = 'Switch';

export { Switch };
