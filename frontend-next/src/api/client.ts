import { getInitData } from "@/lib/telegram";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export class ConfirmationRequiredError extends Error {
  estimatedCredits: number;

  constructor(estimatedCredits: number) {
    super(`confirmation required: ${estimatedCredits} credits`);
    this.estimatedCredits = estimatedCredits;
  }
}

// 401 = протухший/невалидный Telegram initData: показываем понятный экран
// вместо пустых/«недоступных» состояний. Редирект через window.location (мы
// вне React-дерева); guard от повторных срабатываний и от цикла — сама
// страница /login-failed API не дёргает, плюс не редиректим, если уже на ней.
let unauthorizedRedirectFired = false;

function redirectOnUnauthorized(status: number) {
  if (status !== 401 || typeof window === "undefined") return;
  if (unauthorizedRedirectFired || window.location.pathname === "/login-failed") return;
  unauthorizedRedirectFired = true;
  window.location.assign("/login-failed");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": getInitData(),
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (res.status === 409 && typeof body.estimated_credits === "number") {
      // Confirmation-gate POST /api/chat (и будущего /api/generate): тело ровно
      // {"estimated_credits": N} БЕЗ ключа "detail" -- в отличие от 409
      // RequestInProgressError, у которого detail есть и который идёт ниже
      // обычным ApiError-путём.
      throw new ConfirmationRequiredError(body.estimated_credits);
    }
    redirectOnUnauthorized(res.status);
    throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText);
  }

  return res.json() as Promise<T>;
}

export type ModelCategory = "fast" | "medium" | "premium" | "image" | "video";

export interface MeOut {
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  is_admin: boolean;
  default_model_code: string;
  credits_balance: number;
  total_credits_purchased: number;
  total_credits_spent: number;
}

export type ModelOptionKind = "quality" | "duration" | "audio" | "aspect_ratio";

export interface ModelOptionOut {
  kind: ModelOptionKind;
  code: string;
  label: string;
  /** Во сколько раз опция дороже дефолта. Выведен из замеров провайдера. */
  credits_multiplier: number;
  is_default: boolean;
  sort_order: number;
}

export interface ModelOut {
  code: string;
  display_name: string;
  tier: "economy" | "standard" | "premium" | "pro" | "ultra";
  min_credits: number;
  recommended_credits: number;
  /** Эффективный минимум списания (для видео уже с учётом VIDEO_MIN_CREDITS).
   * Использовать его как пол цены в CTA, а не min_credits. */
  min_charge_credits: number;
  /** Наборы задаёт модель. Пусто -- у провайдера нет соответствующей ручки. */
  options: ModelOptionOut[];
  /**
   * Множитель за генерацию по фото (i2i), либо null если модель редактирование
   * не поддерживает. null -> фото-бокс не показываем; иначе CTA с фото дороже
   * в edit_multiplier раз. Число с бэка (не хардкодим, чтобы не разъехалось).
   */
  edit_multiplier: number | null;
}

export interface ChatResponse {
  answer: string;
  charged_credits: number;
  balance_after: number;
  /** id ответа для дедупа восстановления (GET /api/chat/recent). */
  message_id: string;
}

export interface RecentAnswer {
  id: string;
  prompt: string;
  answer: string;
}

export interface GenerationStatus {
  status: "pending" | "reserved" | "processing" | "completed" | "failed" | "refunded";
  result_url: string | null;
  error_message: string | null;
  charged_credits: number;
}

export interface ToolOut {
  slug: string;
  title: string;
  description: string;
  prompt_prefix: string;
  recommended_category: ModelCategory;
  /** 3-сек превью-луп карточки (public/trends/<slug>.mp4). */
  preview_url: string;
}

export interface ReferralOut {
  link: string;
  referred_count: number;
  bonus_count: number;
  earned_credits: number;
  bonus_amount: number;
}

export interface CreatePaymentResponse {
  payment_id: number;
  invoice_link?: string | null;
  confirmation_url?: string | null;
}

export interface PaymentStatusOut {
  payment_id: number;
  status: "created" | "pending" | "succeeded" | "canceled" | "refunded" | "failed";
}

export interface BannerOut {
  id: number;
  title: string;
  subtitle: string | null;
  badge_text: string | null;
  cta_text: string;
  image_url: string;
  action_type: "prompt" | "link";
  action_value: string;
}

export interface CreditPackageOut {
  code: string;
  title: string;
  credits: number;
  price_rub: number;
  price_stars: number;
  /** «Примерно на сколько хватит» -- до N фото / M видео по самой дешёвой модели. */
  approx_photos: number;
  approx_videos: number;
}

export const api = {
  me: () => request<MeOut>("/api/me"),
  setDefaultModel: (modelCode: string) =>
    request<MeOut>("/api/me/default-model", {
      method: "PUT",
      body: JSON.stringify({ model_code: modelCode }),
    }),
  models: (category: "text" | "image" | "video" = "text") =>
    request<ModelOut[]>(`/api/models?category=${category}`),
  chat: (modelCode: string, prompt: string, confirm = false) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ model_code: modelCode, prompt, confirm }),
    }),
  chatRecent: () => request<RecentAnswer[]>("/api/chat/recent"),
  tools: () => request<ToolOut[]>("/api/tools"),
  generate: (
    modelCode: string,
    prompt: string,
    imageUrl?: string,
    optionCodes?: Record<string, string>,
    confirm = false,
  ) =>
    request<{ request_id: number; estimated_credits: number }>("/api/generate", {
      method: "POST",
      body: JSON.stringify({
        model_code: modelCode,
        prompt,
        image_url: imageUrl ?? null,
        // Коды опций, не сырые значения: наборы задаёт модель, см. ModelOut.options.
        option_codes: optionCodes ?? null,
        confirm,
      }),
    }),
  generationStatus: (requestId: number) => request<GenerationStatus>(`/api/generate/${requestId}`),
  uploadImage: async (file: File): Promise<{ url: string }> => {
    // НЕ через общий request(): для FormData браузер сам проставляет
    // Content-Type с правильным boundary, а общий хелпер жёстко шлёт
    // application/json.
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE_URL}/api/upload/image`, {
      method: "POST",
      headers: { "X-Telegram-Init-Data": getInitData() },
      body: form,
    });
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
      redirectOnUnauthorized(res.status);
      throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText);
    }
    return res.json() as Promise<{ url: string }>;
  },
  banners: () => request<BannerOut[]>("/api/banners"),
  referral: () => request<ReferralOut>("/api/referral/me"),
  paymentStatus: (paymentId: number) => request<PaymentStatusOut>(`/api/payments/${paymentId}/status`),
  creditPackages: () => request<CreditPackageOut[]>("/api/credits/packages"),
  createStarsCreditPayment: (packageCode: string) =>
    request<CreatePaymentResponse>("/api/payments/credits/stars/create", {
      method: "POST",
      body: JSON.stringify({ package_code: packageCode }),
    }),
  createYookassaCreditPayment: (packageCode: string) =>
    request<CreatePaymentResponse>("/api/payments/credits/yookassa/create", {
      method: "POST",
      body: JSON.stringify({ package_code: packageCode }),
    }),
};

// --- admin ---------------------------------------------------------------

export interface ModelUsageOut {
  model_code: string;
  requests: number;
  credits_spent: number;
  cost_usd: number;
}

export interface UserSpendOut {
  telegram_id: number;
  credits_spent: number;
}

export interface AdminStatsOut {
  today_new_users: number;
  today_payments_count: number;
  today_payments_amount_rub: number;
  today_ai_requests: number;
  today_api_cost_usd: number;
  today_errors: number;
  today_revenue_credits: number;
  today_revenue_rub_estimated: number;
  today_margin_rub: number;
  today_avg_cost_credits: number;
  model_usage: ModelUsageOut[];
  top_users_by_spend: UserSpendOut[];
  month_revenue_rub: number;
  month_credits_purchases_count: number;
}

export interface AdminUserOut {
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  is_admin: boolean;
  is_blocked: boolean;
  credits_balance: number;
  total_credits_purchased: number;
  total_credits_spent: number;
}

export interface AdminTransactionOut {
  id: number;
  type: "purchase" | "spend" | "refund" | "reserve" | "release" | "admin_adjustment";
  amount: number;
  balance_before: number;
  balance_after: number;
  provider: string | null;
  model_code: string | null;
  request_id: number | null;
  description: string | null;
  created_at: string;
}

export interface AdminPaymentOut {
  id: number;
  telegram_id: number;
  provider: string;
  amount: number;
  currency: string;
  status: string;
  created_at: string;
}

export interface AdminModelOut {
  code: string;
  provider: string;
  category: "text" | "image" | "video";
  tier: "economy" | "standard" | "premium" | "pro" | "ultra";
  display_name: string;
  provider_model_id: string;
  input_price_usd_per_1m_tokens: number;
  output_price_usd_per_1m_tokens: number;
  min_credits: number;
  recommended_credits: number;
  is_active: boolean;
  is_visible: boolean;
  sort_order: number;
}

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

export interface AdminBannerOut {
  id: number;
  title: string;
  subtitle: string | null;
  badge_text: string | null;
  cta_text: string;
  image_url: string;
  action_type: "prompt" | "link";
  action_value: string;
  sort_order: number;
  is_active: boolean;
}

export type BannerWriteFields = Omit<AdminBannerOut, "id">;

export interface AdminPackageOut {
  code: string;
  title: string;
  credits: number;
  price_rub: number;
  price_stars: number;
  description: string | null;
  is_active: boolean;
}

export interface AdminSettingOut {
  key: string;
  value: string;
  type: "int" | "float" | "bool" | "str";
  description: string | null;
}

export const adminApi = {
  stats: () => request<AdminStatsOut>("/api/admin/stats"),
  users: (query?: string) =>
    request<AdminUserOut[]>(`/api/admin/users${query ? `?query=${encodeURIComponent(query)}` : ""}`),
  blockUser: (telegramId: number) =>
    request<AdminUserOut>(`/api/admin/users/${telegramId}/block`, { method: "POST" }),
  unblockUser: (telegramId: number) =>
    request<AdminUserOut>(`/api/admin/users/${telegramId}/unblock`, { method: "POST" }),
  adjustCredits: (telegramId: number, amount: number, reason?: string) =>
    request<AdminUserOut>(`/api/admin/users/${telegramId}/credits`, {
      method: "POST",
      body: JSON.stringify({ amount, reason }),
    }),
  userTransactions: (telegramId: number) =>
    request<AdminTransactionOut[]>(`/api/admin/users/${telegramId}/transactions`),
  payments: () => request<AdminPaymentOut[]>("/api/admin/payments"),
  refundPayment: (id: number) => request<AdminPaymentOut>(`/api/admin/payments/${id}/refund`, { method: "POST" }),
  models: () => request<AdminModelOut[]>("/api/admin/models"),
  updateModel: (
    code: string,
    patch: Partial<Pick<AdminModelOut, "is_active" | "is_visible" | "min_credits" | "recommended_credits" | "sort_order">>,
  ) => request<AdminModelOut>(`/api/admin/models/${code}`, { method: "PATCH", body: JSON.stringify(patch) }),
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
  packages: () => request<AdminPackageOut[]>("/api/admin/packages"),
  updatePackage: (code: string, patch: Partial<Pick<AdminPackageOut, "credits" | "price_rub" | "price_stars" | "is_active">>) =>
    request<AdminPackageOut>(`/api/admin/packages/${code}`, { method: "PATCH", body: JSON.stringify(patch) }),
  settings: () => request<AdminSettingOut[]>("/api/admin/settings"),
  updateSetting: (key: string, value: string) =>
    request<AdminSettingOut>(`/api/admin/settings/${key}`, { method: "PATCH", body: JSON.stringify({ value }) }),
  banners: () => request<AdminBannerOut[]>("/api/admin/banners"),
  createBanner: (body: BannerWriteFields) =>
    request<AdminBannerOut>("/api/admin/banners", { method: "POST", body: JSON.stringify(body) }),
  updateBanner: (id: number, patch: Partial<BannerWriteFields>) =>
    request<AdminBannerOut>(`/api/admin/banners/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteBanner: (id: number) => request<{ ok: boolean }>(`/api/admin/banners/${id}`, { method: "DELETE" }),
};
