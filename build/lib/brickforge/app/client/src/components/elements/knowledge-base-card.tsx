import { memo } from 'react';

export type KnowledgeBaseCardProps = {
  header: string;
  items: string[];
  footer?: string;
};

export const KnowledgeBaseCard = memo(function KnowledgeBaseCard({
  header,
  items,
  footer,
}: KnowledgeBaseCardProps) {
  return (
    <div
      className="rounded-lg bg-gray-100 px-4 py-3 shadow-sm dark:bg-gray-800/60"
      data-response-type="knowledge_base"
    >
      {header && <p className="font-semibold text-foreground">{header}</p>}
      {items.length > 0 && (
        <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-foreground">
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      )}
      {footer && (
        <>
          <hr className="my-3 border-gray-300 dark:border-gray-600" />
          <p className="text-sm text-foreground">{footer}</p>
        </>
      )}
    </div>
  );
});
