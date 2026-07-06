import { getInitData } from "../lib/telegram";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": getInitData(),
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}) as { detail?: string });
    throw new ApiError(res.status, detail.detail ?? res.statusText);
  }

  return res.json() as Promise<T>;
}

export type ModelCategory = "fast" | "medium" | "premium" | "image";

export interface CategoryLimitOut {
  used: number;
  limit: number;
}

export interface LimitsOut {
  daily_used: number;
  daily_limit: number;
  categories: Record<ModelCategory, CategoryLimitOut>;
}

export interface MeOut {
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  is_admin: boolean;
  active_model: string | null;
  tariff_code: string;
  tariff_name: string;
  subscription_expires_at: string | null;
  limits: LimitsOut;
  credits_balance: number;
}

export interface ModelOut {
  model_code: string;
  display_name: string;
  category: ModelCategory;
  is_premium: boolean;
}

export interface ChatResponse {
  answer: string;
  input_tokens: number;
  output_tokens: number;
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

export interface CreditPackageOut {
  code: string;
  name: string;
  credits: number;
  price_rub: number;
  price_stars: number;
}

export const api = {
  me: () => request<MeOut>("/api/me"),
  models: () => request<ModelOut[]>("/api/models"),
  chat: (modelCode: string, prompt: string) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ model_code: modelCode, prompt }),
    }),
  tools: () => request<ToolOut[]>("/api/tools"),
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
};
