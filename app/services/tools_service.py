from dataclasses import dataclass


@dataclass(frozen=True)
class Tool:
    slug: str
    title: str
    description: str
    prompt_prefix: str
    recommended_category: str


TOOLS: list[Tool] = [
    Tool(
        slug="write-post",
        title="Написать пост",
        description="Готовый пост для соцсетей по теме",
        prompt_prefix="Напиши пост для соцсетей на следующую тему: ",
        recommended_category="fast",
    ),
    Tool(
        slug="reply-client",
        title="Ответить клиенту",
        description="Вежливый ответ клиенту по описанию ситуации",
        prompt_prefix="Составь вежливый ответ клиенту в следующей ситуации: ",
        recommended_category="fast",
    ),
    Tool(
        slug="translate",
        title="Перевести текст",
        description="Перевод текста на нужный язык",
        prompt_prefix="Переведи следующий текст, сохраняя стиль и смысл: ",
        recommended_category="fast",
    ),
    Tool(
        slug="write-code",
        title="Написать код",
        description="Код по описанию задачи",
        prompt_prefix="Напиши код для следующей задачи, с пояснениями: ",
        recommended_category="medium",
    ),
    Tool(
        slug="product-description",
        title="Сделать описание товара",
        description="Продающее описание товара для карточки",
        prompt_prefix="Напиши продающее описание товара по следующим данным: ",
        recommended_category="fast",
    ),
    Tool(
        slug="brainstorm",
        title="Придумать идею",
        description="Идеи и варианты по заданной теме",
        prompt_prefix="Придумай несколько идей на следующую тему: ",
        recommended_category="fast",
    ),
]


def list_tools() -> list[Tool]:
    return TOOLS


def get_tool(slug: str) -> Tool | None:
    return next((t for t in TOOLS if t.slug == slug), None)
