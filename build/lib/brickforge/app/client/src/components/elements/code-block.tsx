import { cn } from '@/lib/utils';
import type { HTMLAttributes, ReactNode } from 'react';
import { createContext } from 'react';

type CodeBlockContextType = {
  code: string;
};

const CodeBlockContext = createContext<CodeBlockContextType>({
  code: '',
});

type CodeBlockProps = HTMLAttributes<HTMLDivElement> & {
  code: string;
  language: string;
  showLineNumbers?: boolean;
  children?: ReactNode;
};

export const CodeBlock = ({
  code,
  language,
  showLineNumbers = false,
  className,
  children,
  ...props
}: CodeBlockProps) => (
  <CodeBlockContext.Provider value={{ code }}>
    <div
      className={cn(
        'relative w-full overflow-hidden rounded-md border bg-background text-foreground',
        className,
      )}
      {...props}
    >
      <div className="relative">
        <pre
          className="overflow-x-auto p-4"
          style={{
            margin: 0,
            fontSize: '0.875rem',
            background: 'hsl(var(--background))',
            color: 'hsl(var(--foreground))',
          }}
        >
          <code className="font-mono text-sm">{code}</code>
        </pre>
        {children && (
          <div className="absolute top-2 right-2 flex items-center gap-2">
            {children}
          </div>
        )}
      </div>
    </div>
  </CodeBlockContext.Provider>
);
