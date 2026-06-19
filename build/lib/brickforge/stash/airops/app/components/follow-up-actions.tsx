import { memo } from 'react';
import { Check, X } from 'lucide-react';
import { cn } from '@/lib/utils';

export type FollowUpActionsProps = {
  question: string;
  onValidate: () => void;
  onCancel: () => void;
  disabled?: boolean;
};

export const FollowUpActions = memo(function FollowUpActions({
  question,
  onValidate,
  onCancel,
  disabled = false,
}: FollowUpActionsProps) {
  return (
    <div
      className="mt-2 flex items-center gap-2"
      data-response-type="checkin_followup"
    >
      <span className="text-sm text-foreground">{question}</span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onValidate}
          disabled={disabled}
          aria-label="Validate"
          className={cn(
            'flex size-8 items-center justify-center rounded-full transition-colors',
            'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/40 dark:text-green-300 dark:hover:bg-green-800/50',
            disabled && 'cursor-not-allowed opacity-50',
          )}
        >
          <Check className="size-4" />
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={disabled}
          aria-label="Cancel"
          className={cn(
            'flex size-8 items-center justify-center rounded-full transition-colors',
            'bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/40 dark:text-red-300 dark:hover:bg-red-800/50',
            disabled && 'cursor-not-allowed opacity-50',
          )}
        >
          <X className="size-4" />
        </button>
      </div>
    </div>
  );
});
