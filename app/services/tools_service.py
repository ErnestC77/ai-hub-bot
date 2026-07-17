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
    Tool(
        slug="summarize",
        title="Сжать в выжимку",
        description="Краткая суть длинного текста",
        prompt_prefix="Сделай краткую выжимку следующего текста, сохранив главное: ",
        recommended_category="fast",
    ),
    Tool(
        slug="business-email",
        title="Деловое письмо",
        description="Письмо в деловом тоне по задаче",
        prompt_prefix="Напиши деловое письмо по следующей задаче: ",
        recommended_category="fast",
    ),
    Tool(
        slug="rewrite-tone",
        title="Переписать текст",
        description="Тот же смысл, другой тон",
        prompt_prefix="Перепиши следующий текст, сохранив смысл, но изменив тон: ",
        recommended_category="fast",
    ),
    Tool(
        slug="explain-simple",
        title="Объяснить просто",
        description="Сложная тема простыми словами",
        prompt_prefix="Объясни простыми словами, как для новичка: ",
        recommended_category="fast",
    ),
    Tool(
        slug="video-script",
        title="Сценарий ролика",
        description="Сценарий для Reels или Shorts",
        prompt_prefix="Напиши сценарий короткого вертикального ролика на тему: ",
        recommended_category="fast",
    ),
    Tool(
        slug="content-plan",
        title="Контент-план",
        description="План публикаций на неделю",
        prompt_prefix="Составь контент-план публикаций на неделю по теме: ",
        recommended_category="medium",
    ),
    Tool(
        slug="sales-script",
        title="Скрипт продаж",
        description="Диалог для продажи товара",
        prompt_prefix="Составь скрипт продаж по следующим данным: ",
        recommended_category="medium",
    ),
    Tool(
        slug="resume",
        title="Резюме под вакансию",
        description="Резюме и сопроводительное письмо",
        prompt_prefix="Составь резюме и сопроводительное письмо по следующим данным: ",
        recommended_category="medium",
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
    Tool(
        slug="anime-portrait",
        title="Аниме-портрет",
        description="Портрет в аниме-стиле",
        prompt_prefix="Портрет в аниме-стиле, выразительные глаза, мягкий свет, ",
        recommended_category="image",
    ),
    Tool(
        slug="cartoon-3d",
        title="3D-персонаж",
        description="Мультяшный объёмный герой",
        prompt_prefix="Мультяшный 3D-персонаж, объёмный рендер, мягкий студийный свет, ",
        recommended_category="image",
    ),
    Tool(
        slug="logo-concept",
        title="Логотип-концепт",
        description="Идея знака для бренда",
        prompt_prefix="Минималистичный логотип, векторный знак, чистый фон, ",
        recommended_category="image",
    ),
    Tool(
        slug="interior-design",
        title="Дизайн интерьера",
        description="Комната в выбранном стиле",
        prompt_prefix="Интерьер комнаты, дизайнерская съёмка, естественный свет, ",
        recommended_category="image",
    ),
    Tool(
        slug="food-photo",
        title="Аппетитное блюдо",
        description="Вкусная съёмка еды",
        prompt_prefix="Аппетитная съёмка блюда, макро, тёплый свет, ",
        recommended_category="image",
    ),
    Tool(
        slug="book-cover",
        title="Обложка книги",
        description="Обложка для книги или альбома",
        prompt_prefix="Обложка книги, выразительная композиция, кинематографичный свет, ",
        recommended_category="image",
    ),
    Tool(
        slug="tattoo-sketch",
        title="Эскиз тату",
        description="Набросок татуировки",
        prompt_prefix="Эскиз татуировки, чёткие линии, белый фон, ",
        recommended_category="image",
    ),
    Tool(
        slug="yt-thumbnail",
        title="Обложка для видео",
        description="Кликабельная обложка ролика",
        prompt_prefix="Яркая обложка для видео, крупные акценты, высокий контраст, ",
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
    Tool(
        slug="product-video",
        title="Реклама товара",
        description="Товар в эффектном движении",
        prompt_prefix="Рекламный ролик товара, плавное вращение, студийный свет: ",
        recommended_category="video",
    ),
    Tool(
        slug="logo-animation",
        title="Анимация логотипа",
        description="Логотип в движении",
        prompt_prefix="Анимация логотипа, плавное появление, мягкое свечение: ",
        recommended_category="video",
    ),
    Tool(
        slug="drone-flight",
        title="Пролёт дрона",
        description="Кинематографичная съёмка с воздуха",
        prompt_prefix="Кинематографичный пролёт дрона над сценой: ",
        recommended_category="video",
    ),
    Tool(
        slug="time-lapse",
        title="Таймлапс",
        description="Ускоренная смена света и облаков",
        prompt_prefix="Таймлапс, ускоренное движение облаков и света: ",
        recommended_category="video",
    ),
    Tool(
        slug="anime-clip",
        title="Аниме-клип",
        description="Короткая аниме-сцена",
        prompt_prefix="Короткая аниме-сцена, выразительная анимация: ",
        recommended_category="video",
    ),
    Tool(
        slug="pet-clip",
        title="Питомец-звезда",
        description="Забавное видео с питомцем",
        prompt_prefix="Забавное видео с питомцем, крупный план, мягкий свет: ",
        recommended_category="video",
    ),
    Tool(
        slug="car-showcase",
        title="Авто в движении",
        description="Кинематографичный проезд машины",
        prompt_prefix="Кинематографичный проезд автомобиля, отражения, закатный свет: ",
        recommended_category="video",
    ),
    Tool(
        slug="nature-loop",
        title="Природный луп",
        description="Зацикленный живой пейзаж",
        prompt_prefix="Зацикленная природная сцена, плавное движение: ",
        recommended_category="video",
    ),
]


def list_tools() -> list[Tool]:
    return TOOLS


def get_tool(slug: str) -> Tool | None:
    return next((t for t in TOOLS if t.slug == slug), None)
