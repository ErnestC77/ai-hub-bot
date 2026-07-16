# Админка опций генерации — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать админу править опции качества/длительности/звука (активность, множитель, порядок, дефолт) без миграции и деплоя.

**Architecture:** Читаем/пишем таблицу `model_options` (создана планом 2) через admin-роутер по образцу `list_models`/`update_model`. `provider_params` показываем только на чтение — их значения выверены по схемам fal, и правка сырого JSON из UI = произвольный запрос провайдеру. Смена дефолта делается в одной транзакции (снять старый флаг → поставить новый), иначе частичный уникальный индекс `uq_model_option_default` уронит запрос.

**Tech Stack:** FastAPI + SQLAlchemy 2 (async) бэк; Next.js 16 + React 19 + TypeScript + Tailwind v4 фронт; pytest + Playwright.

**Спек:** `docs/superpowers/specs/2026-07-15-generation-quality-design.md` (этап 7).
**Предыдущие планы:** каталог fal (выполнен), backend опций (выполнен), фронт опций (выполнен). Этот — последний, админка.

## Global Constraints

- Admin-роутер уже несёт `dependencies=[Depends(current_admin)]` (`app/api/routes/admin.py:25`) — 403 не-админам приходит автоматически, отдельно не гейтить.
- **Патчить разрешено только: `label`, `credits_multiplier`, `sort_order`, `is_active`, `is_default`.** НЕ `kind`, НЕ `code`, НЕ `provider_params`, НЕ `model_id` — это контракт с провайдером, меняется миграцией.
- **`provider_params` админу ОТДАЁМ (на чтение), но PATCH их не меняет.** Правка сырого JSON из UI = возможность отправить провайдеру произвольные поля; значения выверены по схемам fal 2026-07-15.
- **Ровно один `is_default` на `(model_id, kind)`** — гарантируется частичным уникальным индексом `uq_model_option_default`. Поэтому: установка `is_default=true` обязана снять флаг с прежнего дефолта того же `(model_id, kind)` в ОДНОЙ транзакции; снять `is_default` с последней дефолтной опции нельзя (**400**) — иначе `recommended_credits` (цена дефолтной комбинации) станет неопределённой.
- **GET для админа показывает и неактивные опции** (в отличие от публичного `/api/models`, который фильтрует `is_active`).
- Множители выведены из живых замеров fal — в UI предупреждение, что ручная правка расходится с реальными списаниями.
- Комментарии/docstring на русском, как в остальном коде.
- Ветка `aurora-glass`. Рабочее дерево делят с другой сессией: **никогда `git add -A` / `git add .`**, только поимённо.

---

### Task 1: Бэкенд — GET списка опций и PATCH одной опции

**Files:**
- Modify: `app/api/routes/admin.py` (после блока `update_model`, ~строка 358)
- Test: `tests/api/test_admin.py`

**Interfaces:**
- Consumes: `ModelOption`, `ModelOptionKind` (`app/db/models`, `app/db/enums`); `AiModel`; паттерн `current_admin`/`get_db` из `admin.py`.
- Produces:
  - `GET /api/admin/models/{code}/options` → `list[AdminModelOptionOut]` (все опции модели, включая неактивные, по `(kind, sort_order)`).
  - `PATCH /api/admin/options/{option_id}` → `AdminModelOptionOut`.
  - `AdminModelOptionOut` (Pydantic): `id, model_code, kind, code, label, provider_params, credits_multiplier, is_default, sort_order, is_active`.
  Task 2 (клиент) повторяет эти имена полей.

- [ ] **Step 1: Написать падающие тесты**

Прочитать `tests/api/test_admin.py` — фикстуры `client`, `db_sessionmaker`; модели там создаются **инлайн** через `AiModel(...)` (хелпера-фабрики нет), в шапке уже импортированы `CostUnit, ModelCategory, ModelProvider, ModelTier` и `AiModel`. **Дописать в импорты** `ModelOptionKind` (из `app.db.enums`) и `ModelOption` (из `app.db.models`). Локальная фабрика для этого файла:

```python
def _media_model(code: str, category=ModelCategory.video) -> AiModel:
    return AiModel(
        provider=ModelProvider.fal, category=category, code=code,
        display_name=code.upper(), provider_model_id=f"fal-ai/{code}",
        tier=ModelTier.standard, cost_unit=CostUnit.second,
        min_credits=100, recommended_credits=500,
    )
```

Добавить тесты:

```python
async def test_admin_lists_model_options_including_inactive(client, db_sessionmaker):
    """Админ видит ВСЕ опции, включая выключенные -- в отличие от публичного
    /api/models, который скрывает is_active=false."""
    async with db_sessionmaker() as s:
        m = _media_model("wan_video", category=ModelCategory.video)  # хелпер файла
        s.add(m)
        await s.flush()
        s.add_all([
            ModelOption(model_id=m.id, kind=ModelOptionKind.quality, code="480p",
                        label="480p", provider_params={"resolution": "480p"},
                        credits_multiplier=0.5, is_default=False, sort_order=10, is_active=True),
            ModelOption(model_id=m.id, kind=ModelOptionKind.quality, code="720p",
                        label="720p", provider_params={"resolution": "720p"},
                        credits_multiplier=1.0, is_default=True, sort_order=20, is_active=True),
            ModelOption(model_id=m.id, kind=ModelOptionKind.quality, code="580p",
                        label="580p", provider_params={"resolution": "580p"},
                        credits_multiplier=0.75, is_default=False, sort_order=15, is_active=False),
        ])
        await s.commit()

    body = (await client.get("/api/admin/models/wan_video/options")).json()

    assert [o["code"] for o in body] == ["480p", "580p", "720p"]  # по sort_order, вкл. неактивную
    assert body[1]["is_active"] is False
    assert body[2]["is_default"] is True
    # provider_params админу отдаём (на чтение)
    assert body[0]["provider_params"] == {"resolution": "480p"}
    assert body[0]["model_code"] == "wan_video"


async def test_admin_options_unknown_model_404(client):
    resp = await client.get("/api/admin/models/nope/options")
    assert resp.status_code == 404


async def test_admin_patch_option_updates_editable_fields(client, db_sessionmaker):
    async with db_sessionmaker() as s:
        m = _media_model("wan_video", category=ModelCategory.video)
        s.add(m)
        await s.flush()
        opt = ModelOption(model_id=m.id, kind=ModelOptionKind.quality, code="480p",
                          label="480p", provider_params={"resolution": "480p"},
                          credits_multiplier=0.5, is_default=False, sort_order=10, is_active=True)
        s.add(opt)
        await s.commit()
        oid = opt.id

    resp = await client.patch(f"/api/admin/options/{oid}",
                              json={"label": "480p (эконом)", "credits_multiplier": 0.4,
                                    "sort_order": 5, "is_active": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["label"] == "480p (эконом)"
    assert float(body["credits_multiplier"]) == 0.4
    assert body["sort_order"] == 5
    assert body["is_active"] is False


async def test_admin_patch_option_ignores_forbidden_fields(client, db_sessionmaker):
    """kind/code/provider_params/model_id править нельзя -- это контракт провайдера."""
    async with db_sessionmaker() as s:
        m = _media_model("wan_video", category=ModelCategory.video)
        s.add(m)
        await s.flush()
        opt = ModelOption(model_id=m.id, kind=ModelOptionKind.quality, code="480p",
                          label="480p", provider_params={"resolution": "480p"},
                          credits_multiplier=0.5, is_default=False, sort_order=10, is_active=True)
        s.add(opt)
        await s.commit()
        oid = opt.id

    resp = await client.patch(f"/api/admin/options/{oid}",
                              json={"code": "hacked", "provider_params": {"resolution": "9000p"},
                                    "kind": "audio"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "480p"                                   # не изменилось
    assert body["provider_params"] == {"resolution": "480p"}        # не изменилось
    assert body["kind"] == "quality"                                # не изменилось


async def test_admin_setting_default_moves_flag_atomically(client, db_sessionmaker):
    """is_default=true снимает флаг с прежнего дефолта в одной транзакции --
    иначе частичный уникальный индекс uq_model_option_default уронит запрос."""
    async with db_sessionmaker() as s:
        m = _media_model("wan_video", category=ModelCategory.video)
        s.add(m)
        await s.flush()
        old = ModelOption(model_id=m.id, kind=ModelOptionKind.quality, code="720p",
                          label="720p", provider_params={}, credits_multiplier=1.0,
                          is_default=True, sort_order=20, is_active=True)
        new = ModelOption(model_id=m.id, kind=ModelOptionKind.quality, code="480p",
                          label="480p", provider_params={}, credits_multiplier=0.5,
                          is_default=False, sort_order=10, is_active=True)
        s.add_all([old, new])
        await s.commit()
        old_id, new_id = old.id, new.id

    resp = await client.patch(f"/api/admin/options/{new_id}", json={"is_default": True})
    assert resp.status_code == 200
    assert resp.json()["is_default"] is True

    # прежний дефолт перестал быть дефолтом
    body = (await client.get("/api/admin/models/wan_video/options")).json()
    by_id = {o["id"]: o for o in body}
    assert by_id[new_id]["is_default"] is True
    assert by_id[old_id]["is_default"] is False


async def test_admin_cannot_unset_last_default(client, db_sessionmaker):
    """Снять is_default с единственной дефолтной опции нельзя: recommended_credits
    (цена дефолтной комбинации) станет неопределённой. Ожидаем 400."""
    async with db_sessionmaker() as s:
        m = _media_model("wan_video", category=ModelCategory.video)
        s.add(m)
        await s.flush()
        opt = ModelOption(model_id=m.id, kind=ModelOptionKind.quality, code="720p",
                          label="720p", provider_params={}, credits_multiplier=1.0,
                          is_default=True, sort_order=20, is_active=True)
        s.add(opt)
        await s.commit()
        oid = opt.id

    resp = await client.patch(f"/api/admin/options/{oid}", json={"is_default": False})
    assert resp.status_code == 400


async def test_admin_patch_option_404(client):
    resp = await client.patch("/api/admin/options/999999", json={"label": "x"})
    assert resp.status_code == 404
```

Если хелпера `_admin_model` в файле нет — прочитать, как соседние admin-тесты создают `AiModel`, и переиспользовать их приём (там наверняка есть фабрика). Импортировать `ModelOption`, `ModelOptionKind`.

- [ ] **Step 2: Прогнать — падают**

Run: `python -m pytest tests/api/test_admin.py -v -k "option"`
Expected: FAIL (404 на несуществующих роутах).

- [ ] **Step 3: Реализовать эндпоинты**

В `app/api/routes/admin.py` после `update_model` добавить (импортировать `ModelOption`, `ModelOptionKind` в шапке файла, рядом с `AiModel`):

```python
# --- model options -----------------------------------------------------------

class AdminModelOptionOut(BaseModel):
    id: int
    model_code: str
    kind: str
    code: str
    label: str
    provider_params: dict
    credits_multiplier: float
    is_default: bool
    sort_order: int
    is_active: bool


def _to_option_out(opt: ModelOption, model_code: str) -> AdminModelOptionOut:
    return AdminModelOptionOut(
        id=opt.id, model_code=model_code, kind=opt.kind.value, code=opt.code,
        label=opt.label, provider_params=opt.provider_params or {},
        credits_multiplier=float(opt.credits_multiplier), is_default=opt.is_default,
        sort_order=opt.sort_order, is_active=opt.is_active,
    )


@router.get("/models/{code}/options", response_model=list[AdminModelOptionOut])
async def list_model_options(
    code: str, session: AsyncSession = Depends(get_db)
) -> list[AdminModelOptionOut]:
    model = (
        await session.execute(select(AiModel).where(AiModel.code == code))
    ).scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Модель не найдена")
    # Админу -- ВСЕ опции, включая неактивные (публичный /api/models их скрывает).
    options = (
        await session.execute(
            select(ModelOption)
            .where(ModelOption.model_id == model.id)
            .order_by(ModelOption.kind, ModelOption.sort_order)
        )
    ).scalars().all()
    return [_to_option_out(o, model.code) for o in options]


class ModelOptionUpdateRequest(BaseModel):
    # provider_params/kind/code/model_id НЕ здесь -- это контракт провайдера,
    # правится миграцией. Правка сырого JSON из UI = произвольный запрос к fal.
    label: str | None = None
    credits_multiplier: float | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    is_default: bool | None = None


@router.patch("/options/{option_id}", response_model=AdminModelOptionOut)
async def update_model_option(
    option_id: int, body: ModelOptionUpdateRequest, session: AsyncSession = Depends(get_db)
) -> AdminModelOptionOut:
    opt = (
        await session.execute(select(ModelOption).where(ModelOption.id == option_id))
    ).scalar_one_or_none()
    if opt is None:
        raise HTTPException(status_code=404, detail="Опция не найдена")

    patch = body.model_dump(exclude_unset=True)

    if "is_default" in patch:
        if patch["is_default"] is False and opt.is_default:
            # Нельзя оставить (model, kind) без дефолта: recommended_credits =
            # цена дефолтной комбинации, она обязана существовать.
            raise HTTPException(
                status_code=400,
                detail="Нельзя снять дефолт с единственной дефолтной опции -- "
                       "сначала назначьте дефолтом другую опцию этого вида",
            )
        if patch["is_default"] is True and not opt.is_default:
            # Снимаем флаг с прежнего дефолта того же (model_id, kind) в ЭТОЙ же
            # транзакции -- иначе частичный уникальный индекс уронит вставку.
            await session.execute(
                update(ModelOption)
                .where(
                    ModelOption.model_id == opt.model_id,
                    ModelOption.kind == opt.kind,
                    ModelOption.is_default.is_(True),
                )
                .values(is_default=False)
            )

    for field, value in patch.items():
        setattr(opt, field, value)
    await session.commit()

    model = (
        await session.execute(select(AiModel).where(AiModel.id == opt.model_id))
    ).scalar_one()
    return _to_option_out(opt, model.code)
```

Убедиться, что `update` импортирован из `sqlalchemy` в шапке файла (если нет — добавить к `from sqlalchemy import ...`).

- [ ] **Step 4: Прогнать — проходят**

Run: `python -m pytest tests/api/test_admin.py -v -k "option"`
Expected: PASS (все 7).

- [ ] **Step 5: Полный сьют**

Run: `python -m pytest tests/ -q`
Expected: PASS (базовая линия перед планом: 331 passed, 2 skipped → 338 passed).

- [ ] **Step 6: Коммит**

```bash
git add app/api/routes/admin.py tests/api/test_admin.py
git commit -m "feat(admin): CRUD опций моделей -- список и PATCH

GET /api/admin/models/{code}/options отдаёт ВСЕ опции (включая неактивные,
в отличие от публичного /api/models). PATCH /api/admin/options/{id} правит
только label/credits_multiplier/sort_order/is_active/is_default -- kind/code/
provider_params остаются контрактом провайдера. Смена дефолта снимает старый
флаг в одной транзакции (иначе partial unique index уронит); снять последний
дефолт нельзя (400)."
```

---

### Task 2: Клиент — типы и adminApi

**Files:**
- Modify: `frontend-next/src/api/client.ts` (тип рядом с `AdminModelOut`; методы в объекте `adminApi`)

**Interfaces:**
- Consumes: `ModelOptionKind` (уже есть в client.ts из плана фронта), `request`-хелпер.
- Produces: `AdminModelOptionOut`; `adminApi.modelOptions(code)`, `adminApi.updateOption(id, patch)`. Task 3 их вызывает.

- [ ] **Step 1: Добавить тип**

В `frontend-next/src/api/client.ts` рядом с `AdminModelOut`:

```ts
export interface AdminModelOptionOut {
  id: number;
  model_code: string;
  kind: ModelOptionKind;
  code: string;
  label: string;
  provider_params: Record<string, unknown>;
  credits_multiplier: number;
  is_default: boolean;
  sort_order: number;
  is_active: boolean;
}
```

- [ ] **Step 2: Добавить методы в `adminApi`**

Рядом с `models`/`updateModel` в объекте `adminApi`:

```ts
  modelOptions: (code: string) =>
    request<AdminModelOptionOut[]>(`/api/admin/models/${encodeURIComponent(code)}/options`),
  updateOption: (
    id: number,
    patch: Partial<Pick<AdminModelOptionOut, "label" | "credits_multiplier" | "sort_order" | "is_active" | "is_default">>,
  ) =>
    request<AdminModelOptionOut>(`/api/admin/options/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend-next && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 4: Коммит**

```bash
git add frontend-next/src/api/client.ts
git commit -m "feat(admin-client): adminApi.modelOptions/updateOption + тип

provider_params наружу приходят (на чтение), но updateOption их не патчит --
Pick разрешает только label/credits_multiplier/sort_order/is_active/is_default."
```

---

### Task 3: Экран AdminModelOptions + вкладка

**Files:**
- Create: `frontend-next/src/screens/admin/AdminModelOptions.tsx`
- Modify: `frontend-next/src/app/admin/page.tsx` (массив вкладок + рендер)

**Interfaces:**
- Consumes: `adminApi.models`, `adminApi.modelOptions`, `adminApi.updateOption`, `AdminModelOptionOut` (Task 2); UI-компоненты `List/Section/Cell/Input/Switch/Select/Placeholder/Spinner` (`@/components/ui/*`); `SegmentedControl` для выбора модели.
- Produces: вкладка «Опции» в админке.

- [ ] **Step 1: Написать экран**

Создать `frontend-next/src/screens/admin/AdminModelOptions.tsx`. Прочитать `AdminModels.tsx` и повторить его каркас (`useEffect` → загрузка, `applyUpdate` по id, `List`/`Section`/`Cell`/`Input`/`Switch`). Выбор модели — через `Select` по списку `adminApi.models()` (медиа-категории: у текстовых опций нет). Опции группируются по `kind`.

```tsx
"use client";

import { useEffect, useState } from "react";

import { adminApi, type AdminModelOptionOut, type AdminModelOut } from "@/api/client";
import { Cell } from "@/components/ui/cell";
import { Input } from "@/components/ui/input";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Select } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";

const KIND_LABEL: Record<string, string> = {
  quality: "Качество",
  duration: "Длительность",
  audio: "Звук",
};

export default function AdminModelOptions() {
  const [models, setModels] = useState<AdminModelOut[] | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [options, setOptions] = useState<AdminModelOptionOut[] | null>(null);
  const [error, setError] = useState("");

  // Только медиа-модели: у текстовых опций нет.
  useEffect(() => {
    adminApi.models().then((all) => {
      const media = all.filter((m) => m.category !== "text");
      setModels(media);
      if (media.length > 0) setSelected(media[0].code);
    }).catch(() => setModels([]));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setOptions(null);
    adminApi.modelOptions(selected).then(setOptions).catch(() => setOptions([]));
  }, [selected]);

  function applyUpdate(updated: AdminModelOptionOut) {
    // Смена дефолта могла снять флаг с другой опции -- перечитываем весь список.
    if (updated.is_default) {
      adminApi.modelOptions(selected).then(setOptions).catch(() => {});
      return;
    }
    setOptions((prev) => prev?.map((o) => (o.id === updated.id ? updated : o)) ?? null);
  }

  async function patch(
    id: number,
    body: Partial<Pick<AdminModelOptionOut, "label" | "credits_multiplier" | "sort_order" | "is_active" | "is_default">>,
  ) {
    setError("");
    try {
      applyUpdate(await adminApi.updateOption(id, body));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить");
    }
  }

  if (models === null) {
    return <Placeholder><Spinner size="m" /></Placeholder>;
  }
  if (models.length === 0) {
    return <Placeholder header="Нет медиа-моделей" description="Опции есть только у фото/видео-моделей." />;
  }

  // Группировка по kind, порядок как пришёл (бэк сортирует по kind, sort_order).
  const byKind: Record<string, AdminModelOptionOut[]> = {};
  for (const o of options ?? []) (byKind[o.kind] ??= []).push(o);

  return (
    <List>
      <Section header="Модель">
        <Cell>
          <Select value={selected} onChange={(e) => setSelected(e.target.value)}>
            {models.map((m) => (
              <option key={m.code} value={m.code}>{m.display_name}</option>
            ))}
          </Select>
        </Cell>
      </Section>

      <Section header="⚠️ Осторожно с множителями">
        <Cell multiline subtitle="Множители выведены из реальных списаний провайдера. Ручная правка расходится с фактической себестоимостью -- меняйте только зная, что делаете." >
          Множители = цена относительно дефолта
        </Cell>
      </Section>

      {options === null ? (
        <Placeholder><Spinner size="s" /></Placeholder>
      ) : options.length === 0 ? (
        <Placeholder header="Опций нет" description="У этой модели нет настраиваемых опций." />
      ) : (
        Object.entries(byKind).map(([kind, opts]) => (
          <Section key={kind} header={KIND_LABEL[kind] ?? kind}>
            {opts.map((o) => (
              <Cell
                key={o.id}
                multiline
                subtitle={o.is_default ? "дефолт" : undefined}
                after={
                  <div className="flex flex-col items-end gap-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-foreground-muted">Активна</span>
                      <Switch checked={o.is_active} onChange={(e) => patch(o.id, { is_active: e.target.checked })} />
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-foreground-muted">Дефолт</span>
                      <Switch checked={o.is_default} onChange={(e) => patch(o.id, { is_default: e.target.checked })} />
                    </div>
                  </div>
                }
              >
                <div className="flex flex-col gap-1.5">
                  <span>{o.label} <span className="text-xs text-foreground-muted">({o.code})</span></span>
                  <div className="flex flex-wrap gap-1.5">
                    <Input
                      header="Множитель"
                      type="number"
                      step="0.001"
                      className="w-[90px]"
                      defaultValue={o.credits_multiplier}
                      onBlur={(e) => {
                        const v = Number(e.target.value);
                        if (v !== o.credits_multiplier && v > 0) patch(o.id, { credits_multiplier: v });
                      }}
                    />
                    <Input
                      header="Порядок"
                      type="number"
                      className="w-[70px]"
                      defaultValue={o.sort_order}
                      onBlur={(e) => {
                        const v = Number(e.target.value);
                        if (v !== o.sort_order) patch(o.id, { sort_order: v });
                      }}
                    />
                  </div>
                  <code className="text-[10px] text-foreground-dim">{JSON.stringify(o.provider_params)}</code>
                </div>
              </Cell>
            ))}
          </Section>
        ))
      )}

      {error && (
        <Section>
          <Cell subtitle={error}>Ошибка</Cell>
        </Section>
      )}
    </List>
  );
}
```

`Select` существует: `frontend-next/src/components/ui/select.tsx` (`forwardRef<HTMLSelectElement>`, принимает нативные `<option>` детьми). Образец использования — `frontend-next/src/screens/admin/AdminBanners.tsx`. Импорт: `import { Select } from "@/components/ui/select";`.

- [ ] **Step 2: Зарегистрировать вкладку**

В `frontend-next/src/app/admin/page.tsx`:
- в массив вкладок (там где `{ key: "models", label: "Модели" }`, строка ~20) добавить `{ key: "options", label: "Опции" }`;
- в импорты — `import AdminModelOptions from "@/screens/admin/AdminModelOptions";`;
- в рендер (рядом с `{tab === "models" && <AdminModels />}`) — `{tab === "options" && <AdminModelOptions />}`.

- [ ] **Step 3: Typecheck + build**

Run: `cd frontend-next && npx tsc --noEmit && npm run lint && npm run build`
Expected: всё зелёное (build 13 роутов).

- [ ] **Step 4: Коммит**

```bash
git add frontend-next/src/screens/admin/AdminModelOptions.tsx frontend-next/src/app/admin/page.tsx
git commit -m "feat(admin): вкладка Опции -- правка множителей/дефолта/активности

Выбор модели -> группировка опций по виду. Множитель/порядок правятся по blur,
активность/дефолт -- тумблерами. provider_params показаны только на чтение
(моноширинным). Смена дефолта перечитывает список (флаг мог сняться с другой
опции). Предупреждение, что множители = реальная себестоимость."
```

---

### Task 4: e2e

**Files:**
- Create: `frontend-next/e2e/admin-model-options.spec.ts`

**Interfaces:**
- Consumes: экран из Task 3, `adminApi` из Task 2; харнесс `mockTelegramWebApp` (`e2e/mock-telegram.ts`).
- Produces: регрессия на вкладку и PATCH.

- [ ] **Step 1: Написать тест**

Прочитать `frontend-next/e2e/admin-models.spec.ts` — повторить харнесс (`test.beforeEach` с `mockTelegramWebApp`, env `TEST_ADMIN_TELEGRAM_ID`/`TEST_BOT_TOKEN`). Создать `frontend-next/e2e/admin-model-options.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockTelegramWebApp } from "./mock-telegram";

test.beforeEach(async ({ page }) => {
  const adminId = Number(process.env.TEST_ADMIN_TELEGRAM_ID);
  await mockTelegramWebApp(page, process.env.TEST_BOT_TOKEN ?? "test-token", adminId);
});

test("вкладка Опции открывается и показывает опции модели", async ({ page }) => {
  // Мокаем admin-эндпоинты, чтобы тест не зависел от содержимого БД.
  await page.route("**/api/admin/models", (route) =>
    route.fulfill({
      json: [{
        code: "wan_video", provider: "fal", category: "video", tier: "standard",
        display_name: "Wan Video", provider_model_id: "fal-ai/wan", min_credits: 466,
        recommended_credits: 932, is_active: true, is_visible: true, sort_order: 10,
        input_price_usd_per_1m_tokens: 0, output_price_usd_per_1m_tokens: 0,
      }],
    }),
  );
  await page.route("**/api/admin/models/wan_video/options", (route) =>
    route.fulfill({
      json: [
        { id: 1, model_code: "wan_video", kind: "quality", code: "480p", label: "480p",
          provider_params: { resolution: "480p" }, credits_multiplier: 0.5,
          is_default: false, sort_order: 10, is_active: true },
        { id: 2, model_code: "wan_video", kind: "quality", code: "720p", label: "720p",
          provider_params: { resolution: "720p" }, credits_multiplier: 1.0,
          is_default: true, sort_order: 20, is_active: true },
      ],
    }),
  );

  await page.goto("/admin");
  await page.getByRole("button", { name: "Опции" }).click();

  await expect(page.getByText("480p")).toBeVisible();
  await expect(page.getByText("720p")).toBeVisible();
  await expect(page.getByText("Качество")).toBeVisible();  // заголовок секции по kind
});

test("переключение активности опции шлёт PATCH", async ({ page }) => {
  await page.route("**/api/admin/models", (route) =>
    route.fulfill({
      json: [{
        code: "wan_video", provider: "fal", category: "video", tier: "standard",
        display_name: "Wan Video", provider_model_id: "fal-ai/wan", min_credits: 466,
        recommended_credits: 932, is_active: true, is_visible: true, sort_order: 10,
        input_price_usd_per_1m_tokens: 0, output_price_usd_per_1m_tokens: 0,
      }],
    }),
  );
  await page.route("**/api/admin/models/wan_video/options", (route) =>
    route.fulfill({
      json: [{ id: 1, model_code: "wan_video", kind: "quality", code: "480p", label: "480p",
        provider_params: { resolution: "480p" }, credits_multiplier: 0.5,
        is_default: false, sort_order: 10, is_active: true }],
    }),
  );

  let patched: any = null;
  await page.route("**/api/admin/options/1", (route) => {
    patched = route.request().postDataJSON();
    route.fulfill({
      json: { id: 1, model_code: "wan_video", kind: "quality", code: "480p", label: "480p",
        provider_params: { resolution: "480p" }, credits_multiplier: 0.5,
        is_default: false, sort_order: 10, is_active: false },
    });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Опции" }).click();
  // первый тумблер «Активна» у опции 480p
  await page.getByText("480p").first().scrollIntoViewIfNeeded();
  await page.locator('input[type="checkbox"]').first().click();

  await expect.poll(() => patched).toMatchObject({ is_active: false });
});
```

- [ ] **Step 2: Прогнать**

Docker-бэкенд поднят; env:
```bash
cd frontend-next
export TEST_BOT_TOKEN=$(grep -m1 '^BOT_TOKEN=' ../.env | cut -d= -f2- | tr -d '\r"')
export TEST_ADMIN_TELEGRAM_ID=$(grep -m1 '^ADMIN_IDS=' ../.env | cut -d= -f2- | cut -d, -f1 | tr -d '\r" ')
npx playwright test admin-model-options --reporter=line
```
Expected: 2 passed. Если селектор тумблера хрупкий (несколько чекбоксов) — уточнить по `data-testid` или роли; **не ослаблять** ассерт `patched`.

- [ ] **Step 3: Коммит**

```bash
git add frontend-next/e2e/admin-model-options.spec.ts
git commit -m "test(e2e): вкладка Опции -- рендер и PATCH активности"
```

---

## Приёмка плана

- [ ] `python -m pytest tests/ -q` — зелёный (≥ 338 passed).
- [ ] `cd frontend-next && npx tsc --noEmit && npm run lint && npm run build` — зелёное.
- [ ] `npx playwright test` — зелёный.
- [ ] Ручная проверка на живом бэке: вкладка «Опции» → выбрать `veo_video` → три секции (Качество/Длительность/Звук); сменить дефолт длительности с 8с на 4с → у 8с флаг снялся; попытка снять единственный дефолт → ошибка.

## Что этот план НЕ делает

- Не добавляет опции и не меняет `provider_params`/`code`/`kind` — это контракт с провайдером, только миграцией.
- Не трогает публичный `/api/models` и экраны генерации (сделаны прошлым планом).
