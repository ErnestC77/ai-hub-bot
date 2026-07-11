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

export interface ModelOut {
  code: string;
  display_name: string;
  tier: "economy" | "standard" | "premium" | "pro" | "ultra";
  min_credits: number;
  recommended_credits: number;
}

export interface ChatResponse {
  answer: string;
  charged_credits: number;
  balance_after: number;
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
}

export interface ReferralOut {
  link: string;
  referred_count: number;
  bonus_count: number;
}

export interface TariffOut {
  code: string;
  name: string;
  description: string | null;
  price_rub: number;
  price_stars: number;
  period_days: number;
  fast_limit: number;
  medium_limit: number;
  premium_limit: number;
  image_limit: number;
  is_current: boolean;
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
  name: string;
  credits: number;
  price_rub: number;
  price_stars: number;
}

export const api = {
  me: () => request<MeOut>("/api/me"),
  models: (category: "text" | "image" | "video" = "text") =>
    request<ModelOut[]>(`/api/models?category=${category}`),
  chat: (modelCode: string, prompt: string, confirm = false) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ model_code: modelCode, prompt, confirm }),
    }),
  tools: () => request<ToolOut[]>("/api/tools"),
  generate: (modelCode: string, prompt: string, imageUrl?: string, durationSeconds?: number, confirm = false) =>
    request<{ request_id: number; estimated_credits: number }>("/api/generate", {
      method: "POST",
      body: JSON.stringify({
        model_code: modelCode,
        prompt,
        image_url: imageUrl ?? null,
        duration_seconds: durationSeconds ?? null,
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
      throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText);
    }
    return res.json() as Promise<{ url: string }>;
  },
  banners: () => request<BannerOut[]>("/api/banners"),
  referral: () => request<ReferralOut>("/api/referral/me"),
  tariffs: () => request<TariffOut[]>("/api/tariffs"),
  createStarsPayment: (tariffCode: string) =>
    request<CreatePaymentResponse>("/api/payments/stars/create", {
      method: "POST",
      body: JSON.stringify({ tariff_code: tariffCode }),
    }),
  createYookassaPayment: (tariffCode: string) =>
    request<CreatePaymentResponse>("/api/payments/yookassa/create", {
      method: "POST",
      body: JSON.stringify({ tariff_code: tariffCode }),
    }),
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

export interface AdminStatsOut {
  today_new_users: number;
  today_payments_count: number;
  today_payments_amount_rub: number;
  today_ai_requests: number;
  today_api_cost_usd: number;
  today_errors: number;
  month_revenue_rub: number;
  month_active_subscriptions: number;
}

export interface AdminUserOut {
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  is_admin: boolean;
  is_blocked: boolean;
  tariff_code: string | null;
  subscription_expires_at: string | null;
  credits_balance: number;
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
  model_code: string;
  provider: string;
  display_name: string;
  category: ModelCategory;
  credit_cost: number;
  is_active: boolean;
  is_premium: boolean;
}

export interface AdminTariffOut {
  code: string;
  name: string;
  price_rub: number;
  price_stars: number;
  fast_limit: number;
  medium_limit: number;
  premium_limit: number;
  image_limit: number;
  daily_limit: number;
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

export const adminApi = {
  stats: () => request<AdminStatsOut>("/api/admin/stats"),
  users: (query?: string) =>
    request<AdminUserOut[]>(`/api/admin/users${query ? `?query=${encodeURIComponent(query)}` : ""}`),
  blockUser: (telegramId: number) =>
    request<AdminUserOut>(`/api/admin/users/${telegramId}/block`, { method: "POST" }),
  unblockUser: (telegramId: number) =>
    request<AdminUserOut>(`/api/admin/users/${telegramId}/unblock`, { method: "POST" }),
  grantSubscription: (telegramId: number, tariffCode: string) =>
    request<AdminUserOut>(`/api/admin/users/${telegramId}/grant`, {
      method: "POST",
      body: JSON.stringify({ tariff_code: tariffCode }),
    }),
  cancelSubscription: (telegramId: number) =>
    request<AdminUserOut>(`/api/admin/users/${telegramId}/cancel-subscription`, { method: "POST" }),
  grantCredits: (telegramId: number, amount: number) =>
    request<AdminUserOut>(`/api/admin/users/${telegramId}/grant-credits`, {
      method: "POST",
      body: JSON.stringify({ amount }),
    }),
  payments: () => request<AdminPaymentOut[]>("/api/admin/payments"),
  refundPayment: (id: number) => request<AdminPaymentOut>(`/api/admin/payments/${id}/refund`, { method: "POST" }),
  models: () => request<AdminModelOut[]>("/api/admin/models"),
  toggleModel: (modelCode: string, isActive: boolean) =>
    request<AdminModelOut>(`/api/admin/models/${modelCode}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    }),
  updateModelCreditCost: (modelCode: string, creditCost: number) =>
    request<AdminModelOut>(`/api/admin/models/${modelCode}`, {
      method: "PATCH",
      body: JSON.stringify({ credit_cost: creditCost }),
    }),
  tariffsAdmin: () => request<AdminTariffOut[]>("/api/admin/tariffs"),
  updateTariff: (code: string, patch: Partial<AdminTariffOut>) =>
    request<AdminTariffOut>(`/api/admin/tariffs/${code}`, { method: "PATCH", body: JSON.stringify(patch) }),
  banners: () => request<AdminBannerOut[]>("/api/admin/banners"),
  createBanner: (body: BannerWriteFields) =>
    request<AdminBannerOut>("/api/admin/banners", { method: "POST", body: JSON.stringify(body) }),
  updateBanner: (id: number, patch: Partial<BannerWriteFields>) =>
    request<AdminBannerOut>(`/api/admin/banners/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteBanner: (id: number) => request<{ ok: boolean }>(`/api/admin/banners/${id}`, { method: "DELETE" }),
};
