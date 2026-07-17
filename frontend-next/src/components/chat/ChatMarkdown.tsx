"use client";

import Markdown, { type Components } from "react-markdown";

/**
 * Ответ модели как форматированный текст: модели пишут markdown (###, **…**,
 * списки), и сырые звёздочки в пузыре выглядели мусором. react-markdown строит
 * React-элементы и HTML из текста НЕ вставляет — XSS исключён архитектурно.
 *
 * Пользовательские сообщения через этот компонент НЕ прогоняем: ввод юзера --
 * просто текст, интерпретировать его разметку значило бы искажать сказанное.
 *
 * Стили компактные под пузырь 12.5px: заголовки любых уровней -- одна жирная
 * строка чуть крупнее (h1 и h4 в чате не должны различаться как на лендинге).
 */
const heading = (props: React.HTMLAttributes<HTMLDivElement>) => (
  <div className="mb-1 mt-2.5 text-[13px] font-bold first:mt-0" {...props} />
);

const components: Components = {
  h1: heading,
  h2: heading,
  h3: heading,
  h4: heading,
  h5: heading,
  h6: heading,
  p: (props) => <p className="mb-2 last:mb-0" {...props} />,
  ul: (props) => <ul className="mb-2 list-disc space-y-1 pl-4 last:mb-0" {...props} />,
  ol: (props) => <ol className="mb-2 list-decimal space-y-1 pl-4 last:mb-0" {...props} />,
  a: (props) => (
    // Ссылки наружу: внутри Telegram WebView обычный target=_blank открывает
    // системный браузер -- то, что нужно; noreferrer обязателен для чужих URL.
    <a className="underline decoration-white/40 underline-offset-2" target="_blank" rel="noopener noreferrer" {...props} />
  ),
  code: (props) => {
    const { className, children, ...rest } = props;
    // react-markdown кладёт block-код в <pre><code class="language-...">,
    // inline-код приходит без className.
    const isBlock = /language-/.test(className ?? "");
    return isBlock ? (
      <code className={`${className ?? ""} block`} {...rest}>{children}</code>
    ) : (
      <code className="rounded bg-white/10 px-1 py-[1px] font-mono text-[11.5px]" {...rest}>
        {children}
      </code>
    );
  },
  pre: (props) => (
    <pre className="mb-2 overflow-x-auto rounded-[10px] bg-black/40 p-2.5 font-mono text-[11px] leading-[1.5] last:mb-0" {...props} />
  ),
  blockquote: (props) => (
    <blockquote className="mb-2 border-l-2 border-white/25 pl-2.5 text-foreground-muted last:mb-0" {...props} />
  ),
  hr: () => <hr className="my-2 border-white/15" />,
};

export default function ChatMarkdown({ text }: { text: string }) {
  return <Markdown components={components}>{text}</Markdown>;
}
