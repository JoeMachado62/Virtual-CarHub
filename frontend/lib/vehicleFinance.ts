export type CreditTierId = "A+" | "A" | "A-" | "B+" | "B-" | "C+" | "C" | "D" | "F";

export type CreditTierDefinition = {
  id: CreditTierId;
  label: string;
  minScore: number;
  maxScore: number | null;
  apr: number;
};

export type VehiclePriceBreakdown = {
  vehicleCost: number;
  auctionFee: number;
  detailShopFee: number;
  vchFee: number;
  marketingFee: number;
  cashPrice: number;
  transportIncluded: boolean;
  usesEstimatedSourcePrice: boolean;
};

export const DETAIL_SHOP_FEE = 150;
export const VCH_FEE = 1500;
export const MARKETING_FEE = 599;
export const DEFAULT_LOAN_TERM_MONTHS = 72;
export const DEFAULT_CREDIT_TIER: CreditTierId = "A";

export const CREDIT_TIER_DEFINITIONS: CreditTierDefinition[] = [
  { id: "A+", label: "750+", minScore: 750, maxScore: null, apr: 6.95 },
  { id: "A", label: "720-749", minScore: 720, maxScore: 749, apr: 7.59 },
  { id: "A-", label: "700-719", minScore: 700, maxScore: 719, apr: 8.5 },
  { id: "B+", label: "680-699", minScore: 680, maxScore: 699, apr: 9.5 },
  { id: "B-", label: "640-679", minScore: 640, maxScore: 679, apr: 10.75 },
  { id: "C+", label: "620-639", minScore: 620, maxScore: 639, apr: 12.49 },
  { id: "C", label: "600-619", minScore: 600, maxScore: 619, apr: 14.49 },
  { id: "D", label: "550-599", minScore: 550, maxScore: 599, apr: 19.42 },
  { id: "F", label: "Below 550", minScore: 0, maxScore: 549, apr: 21.85 },
];

function roundMoney(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

export function getCreditTierDefinition(tierId: CreditTierId): CreditTierDefinition {
  return CREDIT_TIER_DEFINITIONS.find((tier) => tier.id === tierId) || CREDIT_TIER_DEFINITIONS[1];
}

export function buildVehiclePriceBreakdown(params: {
  sourcePrice?: number | null;
  buyFee?: number | null;
  priceWholesaleEstimate?: number | null;
  fallbackAdvertisedPrice?: number | null;
}): VehiclePriceBreakdown {
  const sourcePrice = params.sourcePrice ?? params.priceWholesaleEstimate ?? 0;
  const auctionFee = params.buyFee ?? 0;
  const hasKnownSourcePrice = Boolean(params.sourcePrice != null || params.priceWholesaleEstimate != null);
  const calculatedCashPrice = sourcePrice + auctionFee + DETAIL_SHOP_FEE + VCH_FEE + MARKETING_FEE;
  const fallbackAdvertisedPrice = params.fallbackAdvertisedPrice ?? 0;
  const cashPrice = hasKnownSourcePrice ? calculatedCashPrice : fallbackAdvertisedPrice;

  return {
    vehicleCost: roundMoney(sourcePrice),
    auctionFee: roundMoney(auctionFee),
    detailShopFee: DETAIL_SHOP_FEE,
    vchFee: VCH_FEE,
    marketingFee: MARKETING_FEE,
    cashPrice: roundMoney(cashPrice),
    transportIncluded: false,
    usesEstimatedSourcePrice: !hasKnownSourcePrice,
  };
}

export function estimateMonthlyPayment(
  principal: number,
  annualRate: number,
  months = DEFAULT_LOAN_TERM_MONTHS,
): number {
  if (principal <= 0 || months <= 0) return 0;

  const monthlyRate = annualRate / 100 / 12;
  if (monthlyRate <= 0) {
    return roundMoney(principal / months);
  }

  const factor = Math.pow(1 + monthlyRate, months);
  const payment = principal * ((monthlyRate * factor) / (factor - 1));
  return roundMoney(payment);
}

export function estimateMonthlyPaymentForTier(
  principal: number,
  tierId: CreditTierId,
  months = DEFAULT_LOAN_TERM_MONTHS,
): number {
  return estimateMonthlyPayment(principal, getCreditTierDefinition(tierId).apr, months);
}
