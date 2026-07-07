# PiAPI Integration + Split Credits & Bundles — Design

**Goal:** Replace the single flat credit pool with separate Image/Video credit pools, add real image/video generation via PiAPI (single-key aggregator for Flux/Qwen/Nano Banana/GPT-Image/Kling/Veo/Sora2/Hailuo/Seedance/Wan/Luma), price every model at 30% profit margin, and ship a redesigned Credits screen + a new Bundles purchase screen for both kinds.

**Execution order:** two sequential implementation plans, run back to back without a check-in between them:
1. **PiAPI integration** — enums, async generation pipeline, model catalog, video generation screen.
2. **Credits & Bundles** — credit-kind ledger, redesigned account credits section, Bundles screen, payment wiring.

---

## 1. Data model changes

### 1.1 `ModelCategory.video`
`app/db/enums.py` gains `video = "video"`. This is a native Postgres enum (`modelcategory`) already used by `model_configs.category` and `ai_requests.model_category` — extending it requires `ALTER TYPE modelcategory ADD VALUE 'video'` in a migration, run in an autocommit block (Postgres forbids `ALTER TYPE ... ADD VALUE` inside a transaction). No `Tariff`/`UsageLimit` column is added for video — video is never covered by tariff quota, only by credits. `access_service.CATEGORY_LIMIT_FIELD` is left untouched (still keyed by `fast/medium/premium/image` only); `check_access()` short-circuits before ever indexing it for video — see §1.4.

### 1.2 `CreditKind`
New enum in `app/db/enums.py`:
```python
class CreditKind(str, enum.Enum):
    general = "general"
    image = "image"
    video = "video"
```
`general` preserves today's behaviour for `fast`/`medium`/`premium` chat overflow. New mapping (`app/services/limit_fields.py`, add alongside `CATEGORY_LIMIT_FIELD`):
```python
CREDIT_KIND_FOR_CATEGORY: dict[ModelCategory, CreditKind] = {
    ModelCategory.fast: CreditKind.general,
    ModelCategory.medium: CreditKind.general,
    ModelCategory.premium: CreditKind.general,
    ModelCategory.image: CreditKind.image,
    ModelCategory.video: CreditKind.video,
}
```

### 1.3 `credit_transactions.kind`
New column, native Postgres enum `creditkind` (fresh type — no `ALTER TYPE ADD VALUE` needed since nothing references it yet), `nullable=False`, `server_default='general'` so existing rows keep working unchanged.

`app/services/credit_service.py` — every function gains a `kind: CreditKind = CreditKind.general` keyword param and filters/tags by it:
```python
async def get_balance(session: AsyncSession, user: User, kind: CreditKind = CreditKind.general) -> int:
    total = (await session.execute(
        select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
            CreditTransaction.user_id == user.id, CreditTransaction.kind == kind
        )
    )).scalar_one()
    return int(total)
```
Same `kind` threading for `grant_credits()` and `spend_credits()`. Also add `get_lifetime_granted(session, user, kind) -> int` (sum of positive-amount rows only, i.e. `deposit`+`bonus`+`refund` types) — used by `/api/me` to show "available / lifetime granted" per §5.1.

### 1.4 `app/services/access_service.py`
`check_access()` and the `spend_credits` call site in `app/services/ai/ai_router.py` resolve `kind = CREDIT_KIND_FOR_CATEGORY[model.category]` and pass it through to `get_credit_balance(session, user, kind=kind)` / `spend_credits(session, user, amount, kind=kind, reason=...)`. For `video`, `CATEGORY_LIMIT_FIELD` has no entry — add `ModelCategory.video: ("video_limit_unused", "video_used_unused")`... **no**: instead, short-circuit in `check_access()` before the dict lookup: `if model.category == ModelCategory.video: tariff_has_quota = False` (video is credits-only by design, skip the tariff-quota branch entirely rather than fabricating unused Tariff columns).

### 1.5 `model_configs` new columns
```python
piapi_model: Mapped[str | None] = mapped_column(String(64))
piapi_task_type: Mapped[str | None] = mapped_column(String(64))
piapi_extra_input: Mapped[dict | None] = mapped_column(JSON)
duration_seconds: Mapped[int | None] = mapped_column(Integer)  # video only, informational + used for polling timeout
```
`piapi_extra_input` holds fixed per-model request fields PiAPI needs beyond `prompt` (e.g. Hailuo's `{"model": "v2.3", "duration": 6, "resolution": 768}`, Veo's `{"duration": "8s", "resolution": "720p", "generate_audio": false}`). Kept data-driven (DB row) rather than Python branches, matching how `credit_cost`/`max_context_tokens` already work.

### 1.6 `ai_requests.provider_task_id`
```python
provider_task_id: Mapped[str | None] = mapped_column(String(128), index=True, unique=True)
```
Needed because the PiAPI webhook only carries PiAPI's own `task_id` — this column is how the webhook handler finds the right `AIRequest` row.

### 1.7 `app/db/enums.ModelProvider` and `app/services/keys/enums.Provider`
Both gain a `piapi` member. `ModelProvider` is a native Postgres enum on `model_configs.provider` — extended the same way as §1.1 (`ALTER TYPE modelprovider ADD VALUE 'piapi'`, autocommit block). `keys.enums.Provider` is a plain `StrEnum`, no migration needed.

### 1.8 `PiApiSettings` (`app/config.py`)
```python
class PiApiSettings(_ProviderSettings):
    api_key: SecretStr | None = Field(default=None, alias="PIAPI_API_KEY")
    dev_key: SecretStr | None = Field(default=None, alias="PIAPI_DEV_KEY")
    webhook_secret: str = Field(default="", alias="PIAPI_WEBHOOK_SECRET")
```
Registered on `Settings` as `piapi: PiApiSettings = Field(default_factory=PiApiSettings)`. `app/services/keys/api_key_manager.py`'s `_PURPOSE_ATTR` gains:
```python
Provider.PIAPI: {KeyPurpose.IMAGE: "api_key", KeyPurpose.VIDEO: "api_key"},
```
(one real key serves both purposes — PiAPI doesn't split keys by modality).

---

## 2. PiAPI HTTP client

New file `app/services/ai/piapi_client.py`. Confirmed against PiAPI's own docs (verbatim examples fetched during design):

- Base URL: `https://api.piapi.ai/api/v1`
- Auth header: `X-API-Key: <key>`
- **Create task** — `POST /task`
  ```json
  {
    "model": "Qubico/flux1-dev",
    "task_type": "txt2img",
    "input": { "prompt": "...", "...": "..." },
    "config": { "webhook_config": { "endpoint": "https://<our-backend>/api/piapi/webhook?secret=<webhook_secret>", "secret": "" } }
  }
  ```
  Response: `{"code": 200, "message": "success", "data": {"task_id": "...", "status": "pending", ...}}`.
- **Get task** — `GET /task/{task_id}` → same `data` shape, `status` one of `pending|processing|completed|failed`.
- **Webhook** — PiAPI POSTs `{"timestamp": 1724511853, "data": {...same shape as get-task's data...}}` to the configured `endpoint` when the task reaches `completed` or `failed`.
- **Output field** varies by model family (`output.image_url` / `output.image_urls[]` for Flux-style unified image models; `output.generation.video.url` for Luma-style; other families follow the same "some nested path to a URL" pattern). Each `ModelConfig` row's `piapi_extra_input` is complemented by a small `output_path` **not** stored in the DB — instead, `piapi_client.py` implements one `extract_result_url(data: dict) -> str | None` function with an explicit per-known-shape fallback chain: try `output.image_url`, then `output.image_urls[0]`, then `output.video_url`, then `output.generation.video.url`, then `output.generation.video.url_no_watermark`. This keeps model-specific quirks in one reviewable function instead of scattered per-row config.

```python
@dataclass
class PiAPITaskResult:
    task_id: str
    status: str  # "pending" | "processing" | "completed" | "failed"
    result_url: str | None
    error_message: str | None

class PiAPIClient:
    async def create_task(self, model: str, task_type: str, input_: dict, webhook_url: str) -> str: ...  # -> task_id
    async def get_task(self, task_id: str) -> PiAPITaskResult: ...
```

Exact `model` / `task_type` / `piapi_extra_input` values per catalog row are confirmed against PiAPI's docs at implementation time for each row (§4 lists the ones already confirmed verbatim during design; the remainder — Kling 3.0 Omni, Sora2, Qwen Image, Nano Banana Pro, GPT-Image-1.5, Seedream 5 Lite — get a dedicated implementation-plan step each: fetch the model's own `piapi.ai/docs/<x>-api/create-task` page and transcribe the exact `model`/`task_type`/`input` fields before writing that seed row, rather than guessing).

---

## 3. Async generation pipeline

Today `AIRouter.generate()` is fully synchronous — `POST /api/chat/image` blocks until `ImageProvider.generate()` returns. PiAPI tasks can take 10s (Flux) to several minutes (Sora2/Veo), which doesn't fit a blocking HTTP request. New unified async path added **alongside** the untouched synchronous `/api/chat` (text) route:

- `POST /api/generate` — body `{model_code, prompt, extra}`. Handler:
  1. `check_access()` exactly as today (resolves `kind` via §1.4).
  2. Insert `AIRequest(status=processing)`, commit to get its id.
  3. If `model.provider == ModelProvider.piapi`: call `PiAPIClient.create_task(...)` synchronously (this call just registers the job, PiAPI responds in well under a second) and store the returned `task_id` in `provider_task_id`. Credits are **not** spent yet — spending happens on webhook success (§3.1), matching "don't charge for failed generations."
  4. Else (existing sync providers, e.g. `dall-e-3`): run the existing `ImageProvider.generate()` inside a FastAPI `BackgroundTasks` task so the endpoint still returns immediately; the background task updates the same `AIRequest` row and spends credits on completion, for a uniform contract with PiAPI rows.
  5. Return `{"request_id": ai_request.id}` immediately in both cases.
- `GET /api/generate/{request_id}` — returns `{status, result_url, error_message, credit_cost}`. 404s if the request doesn't belong to the caller.
- `POST /api/piapi/webhook?secret=<value>` — no auth via `current_user` (PiAPI calls this, not a logged-in user); rejects with 403 if `secret` doesn't match `settings.piapi.webhook_secret`. Looks up `AIRequest` by `provider_task_id` from the payload's `data.task_id`; on `status == "completed"`: extract result URL (§2), set `AIRequest.answer = result_url`, `status = success`, spend credits (`kind` derived from `model_category` on the row); on `status == "failed"`: set `status = error`, `error_message` from `data.error.message`, no credit spend. Idempotent — if the row is already `success`/`error`, return 200 without side effects (PiAPI may retry webhooks).

`/api/chat/image` is retired — `GenerateImage.tsx` moves to the new `/api/generate` + poll contract (§5.2), so both PiAPI and the existing `dall-e-3` row share one frontend code path.

### 3.1 Frontend polling contract
Mirrors the existing `waitForCredit` pattern in `CreditPurchaseSheet.tsx`: `POST /api/generate` → get `request_id` → poll `GET /api/generate/{id}` every 2s, timeout after `POLL_ATTEMPTS` (video rows use a longer timeout derived from `model.duration_seconds`, e.g. `max(60, duration_seconds * 20)` attempts-worth, since Sora2/Veo standard can take minutes).

---

## 4. Model catalog (real PiAPI models, 30% margin, 77₽/$, 0.65₽/credit floor)

Credit-cost formula used throughout: `credits = ceil(cost_usd × 77 / 0.7 / 0.65)` = `ceil(cost_usd × 169.23)`. Rows below are the ones with a PiAPI-confirmed USD price; **Midjourney is excluded (PiAPI does not offer it) and Z-Image is excluded (no price found anywhere on PiAPI's site)**, per explicit instruction.

All new rows: `is_active=True`, `provider=ModelProvider.piapi`, `key_purpose="image"` or `"video"` matching category.

| model_code | display_name | category | piapi `model` | piapi `task_type` | piapi_extra_input | credit_cost |
|---|---|---|---|---|---|---|
| `piapi-flux-dev` | AI Photo Fast | image | `Qubico/flux1-dev` | `txt2img` | `{"width":1024,"height":1024}` | 3 |
| `piapi-qwen-image` | AI Photo Edit | image | *(confirm at impl time, `piapi.ai/docs/qwen-api/*`)* | *(same)* | `{}` | 3 |
| `piapi-gpt-image-1-5` | AI Photo Pro | image | *(confirm, `piapi.ai/docs/gpt-image-api/*`)* | *(same)* | `{"size":"1024x1024","quality":"medium"}` | 8 |
| `piapi-nano-banana-pro` | AI Photo Ultra | image | *(confirm, `piapi.ai/docs/nano-banana-api/*`)* | *(same)* | `{"resolution":"2k"}` | 18 |
| `piapi-seedream5-lite` | AI Photo Lite | image | *(confirm, `piapi.ai/docs/seedream-api/seedream-5-lite`)* | *(same)* | `{}` | 6 |
| `piapi-veo3-fast` | AI Video Fast | video | `veo3.1` | `veo3.1-video-fast` | `{"duration":"5s","resolution":"720p","generate_audio":false}` | 51 |
| `piapi-wan26` | AI Video Standard | video | `Wan` | `wan26-txt2video` *(confirm exact string, only `wan26-img2video` was verbatim-confirmed)* | `{"resolution":"720p","duration":5}` | 68 |
| `piapi-sora2` | AI Video Sora | video | *(confirm, `piapi.ai/docs/sora2*`)* | *(same)* | `{"duration":5}` | 68 |
| `piapi-hailuo` | AI Video Hailuo | video | `hailuo` | `video_generation` | `{"model":"v2.3","duration":6,"resolution":768,"expand_prompt":true}` | 39 |
| `piapi-kling3-omni` | AI Video Kling | video | *(confirm, `piapi.ai/docs/kling-api/*`)* | *(same)* | `{"resolution":"720p","duration":5}` | 85 |
| `piapi-seedance2-fast` | AI Video Seedance | video | `seedance` | `seedance-2-fast` | `{"duration":5,"aspect_ratio":"16:9"}` | 119 |
| `piapi-luma` | AI Video Luma | video | *(confirm, `piapi.ai/docs/dream-machine/create-task`)* | *(same)* | `{}` | 34 |

Existing `dall-e-3` row (`app/db/seed.py`) is untouched — stays the one non-PiAPI image row, same credit_cost as today.

Chips shown on the Credits screen (§5.1) come from `GET /api/models?include_inactive=false` filtered by `category`, i.e. purely from this table — no hardcoded frontend list.

---

## 5. Credits & Bundles UI

### 5.1 Redesigned Account credits section (`frontend-next/src/app/account/page.tsx`)
Replaces the single `💎 {credits_balance} кредитов` cell with two cards (new component `frontend-next/src/components/account/CreditCard.tsx`), one per `CreditKind.image`/`CreditKind.video`:
- Icon + "Image Credits"/"Video Credits" header
- `{available} / {lifetime_granted}` with a progress bar (portion used)
- `+` button → navigates to `/bundles?kind=image` or `/bundles?kind=video`
- Row of chips: active model `display_name`s for that category (§4 table), from `api.models()` filtered client-side by category

`MeOut` gains `credits: {image: {balance, lifetime_granted}, video: {...}, general: {...}}` (backend: `/api/me` calls `get_balance`/`get_lifetime_granted` three times, once per kind). `credits_balance: number` (legacy flat field) stays for backward compat during rollout but is no longer rendered — it maps to `general` kind only now (was previously the sum of everything, since everything used to be `general`).

### 5.2 New Bundles screen (`frontend-next/src/app/bundles/page.tsx`)
Full page (not a Sheet), matches the reference: back arrow, hero icon + gradient, "Image bundles"/"Video bundles" title switched by tab, feature-checklist card (derived from the same model chips as §5.1), segmented Image/Video tabs (no Music tab — out of scope), list of bundle cards with strikethrough original price, discounted price, "BEST VALUE" badge on the top bundle, "Save X%" text. Tapping a card opens the existing choose-method flow (Stars/YooKassa), reusing the `waitForCredit`-style poll from `CreditPurchaseSheet.tsx` (extracted into a shared hook since both the old sheet and the new screen need it) — **`CreditPurchaseSheet.tsx` and its `+` entry point are removed**, replaced entirely by the Bundles screen.

### 5.3 Bundle catalog & payment
`CreditPackage` dataclass (`app/services/credit_packages.py`) gains `kind: CreditKind`, `original_price_rub: float | None`, `is_best_value: bool`. New bundle rows per kind (image/video), reusing the existing 100/500/2000-style tiering with a 30%-off "2000" tier marked best value, mirroring the reference screenshot's "500 generations — 1750 (was 2500)" pattern scaled to each kind's credit costs from §4. `payment.payload` gains `"kind": package.kind.value` (§ existing `{"credits": N}` shape, extended); `activation.py` reads `payload.get("kind", "general")` and passes it to `grant_credits(..., kind=CreditKind(payload_kind))`. `POST /api/payments/credits/{stars,yookassa}/create` unchanged in shape — `package_code` alone still resolves everything since `kind` now lives on the `CreditPackage` row itself.

### 5.4 New video generation screen (`frontend-next/src/app/generate-video/page.tsx`)
Mirrors `generate-image/page.tsx` structurally (back arrow, model picker via chips scoped to `category=video`, prompt textarea, generate button) but simpler — no aspect/resolution chips (each PiAPI video model's `piapi_extra_input` fixes those server-side per §4). Uses the async poll contract from §3.1. Result renders as `<video controls src={result_url} className="w-full rounded-lg" />` instead of an `<img>`. Reachable from the FAB long-press or a new tabbar/account entry point — **exact entry point decided during planning**, not blocking this spec (it's a one-line routing decision, not an architectural one).

`generate-image/page.tsx` is reworked to call the new `POST /api/generate` + poll instead of the retired synchronous `api.generateImage()`.

---

## 6. Migration sequencing

Single Alembic revision, in this order (native-enum `ALTER TYPE ... ADD VALUE` must run outside a transaction block):
1. `op.execute("COMMIT")` then `ALTER TYPE modelcategory ADD VALUE IF NOT EXISTS 'video'"` (autocommit block per Alembic's `op.get_context().autocommit_block()`).
2. Same pattern for `ALTER TYPE modelprovider ADD VALUE IF NOT EXISTS 'piapi'`.
3. Normal transactional migration: create `creditkind` enum type, add `credit_transactions.kind` (default `'general'`), add `model_configs.{piapi_model,piapi_task_type,piapi_extra_input,duration_seconds}`, add `ai_requests.provider_task_id` (unique index).

---

## 7. Out of scope (explicitly deferred)

- Midjourney and Z-Image (no confirmed PiAPI pricing).
- Music/3D PiAPI categories (Udio, Trellis, etc.) — not requested.
- Per-model premium tiers beyond the one row per family in §4 (e.g. Kling's HD+audio variant, Seedance's "Recommended" 720p tier) — same formula applies, added as extra catalog rows later on demand.
- Task cancellation (PiAPI has no unified cancel endpoint per its own docs).
