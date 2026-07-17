import { Cell } from "@/components/ui/cell";
import { Section } from "@/components/ui/section";

/**
 * Единый показ ошибки write-действия админки (пара к useActionError). Пусто ->
 * ничего не рендерит. Рассчитан на вставку внутри <List> экранов админки.
 */
export default function ActionError({ error }: { error: string }) {
  if (!error) return null;
  return (
    <Section>
      <Cell multiline subtitle={error}>
        ⚠️ Ошибка
      </Cell>
    </Section>
  );
}
