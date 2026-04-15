/**
 * VIN masking utility. By default, hides the last 6 characters of a VIN
 * (the sequential production number) and replaces them with asterisks so
 * that the public cannot resolve a specific vehicle. The hashed value
 * stays available for backend operations (CR ordering, garage actions,
 * etc.) because callers continue to pass the raw VIN — only the
 * *displayed* form is masked.
 *
 * Full VINs should only be revealed to pre-qualified buyers viewing
 * vehicles they have saved to their own garage.
 */
export function maskVin(vin: string | null | undefined, canReveal = false): string {
  if (!vin) return "";
  if (canReveal) return vin;
  if (vin.length <= 11) return vin;
  return `${vin.slice(0, vin.length - 6)}******`;
}
