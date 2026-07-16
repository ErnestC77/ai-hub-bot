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
    # Фото-тренды -- recommended_category="image": фронт роутит их на /generate-image.
    Tool(
        slug="ai-avatar",
        title="AI-аватар",
        description="Кинематографичный портрет по описанию",
        prompt_prefix="AI-аватар в кинематографичном освещении, крупный детализированный портрет, ",
        recommended_category="image",
    ),
    Tool(
        slug="restyle-photo",
        title="Фото в новом стиле",
        description="Портрет в модном визуальном стиле",
        prompt_prefix="Портрет в стиле неонового киберпанка, высокая детализация, ",
        recommended_category="image",
    ),
    Tool(
        slug="product-photo",
        title="Товар на подиуме",
        description="Предметная студийная съёмка товара",
        prompt_prefix="Предметная съёмка товара на минималистичном фоне, студийный свет, ",
        recommended_category="image",
    ),
    # Видео-тренды -- recommended_category="video": фронт роутит их на /generate-video.
    Tool(
        slug="animate-photo",
        title="Оживить кадр",
        description="Плавная анимация статичной сцены",
        prompt_prefix="Плавная кинематографичная анимация сцены: ",
        recommended_category="video",
    ),
    Tool(
        slug="talking-avatar",
        title="Говорящий аватар",
        description="Видео с говорящим цифровым аватаром",
        prompt_prefix="Видео с говорящим цифровым аватаром, ",
        recommended_category="video",
    ),
    Tool(
        slug="short-clip",
        title="Вертикальный клип",
        description="Короткий динамичный вертикальный клип",
        prompt_prefix="Короткий вертикальный клип в динамичном стиле: ",
        recommended_category="video",
    ),
]


def list_tools() -> list[Tool]:
    return TOOLS


def get_tool(slug: str) -> Tool | None:
    return next((t for t in TOOLS if t.slug == slug), None)
