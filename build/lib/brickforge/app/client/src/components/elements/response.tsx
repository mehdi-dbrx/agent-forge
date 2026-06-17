import { type ComponentProps, memo } from 'react';
import { DatabricksMessageCitationStreamdownIntegration } from '../databricks-message-citation';
import { Streamdown } from 'streamdown';

type ResponseProps = ComponentProps<typeof Streamdown>;

export const Response = memo(
  (props: ResponseProps) => {
    return (
      <Streamdown
        code={false}
        mermaid={false}
        components={{
          a: DatabricksMessageCitationStreamdownIntegration,
        }}
        className="flex flex-col gap-4"
        {...props}
      />
    );
  },
  (prevProps, nextProps) => prevProps.children === nextProps.children,
);

Response.displayName = 'Response';
