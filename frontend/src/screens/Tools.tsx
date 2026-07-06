import { useEffect, useState } from "react";
import { Cell, List, Placeholder, Section, Spinner } from "@telegram-apps/telegram-ui";
import { useNavigate } from "react-router-dom";

import { api, type ToolOut } from "../api/client";

export default function Tools() {
  const [tools, setTools] = useState<ToolOut[] | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.tools().then(setTools).catch(() => setTools([]));
  }, []);

  if (tools === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  return (
    <List>
      <Section header="Готовые инструменты">
        {tools.map((tool) => (
          <Cell
            key={tool.slug}
            subtitle={tool.description}
            onClick={() => navigate("/chat", { state: { prefillPrompt: tool.prompt_prefix } })}
          >
            {tool.title}
          </Cell>
        ))}
      </Section>
    </List>
  );
}
