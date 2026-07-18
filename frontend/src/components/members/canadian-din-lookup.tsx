import { useState, memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, Globe, Search } from "lucide-react";
import { getCanadianProduct } from "@/lib/api/members";
import { ApiError } from "@/lib/api-client";
import type { CanadianDrugProduct } from "@/lib/types/member";

interface CanadianDinLookupProps {
  memberId: string;
}

export const CanadianDinLookup = memo(function CanadianDinLookup({
  memberId,
}: CanadianDinLookupProps) {
  const [din, setDin] = useState("");
  const [product, setProduct] = useState<CanadianDrugProduct | null | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function lookup() {
    const d = din.trim();
    if (!/^\d{8}$/.test(d)) {
      setError("Enter an 8-digit DIN.");
      setProduct(undefined);
      return;
    }
    setLoading(true);
    setError(null);
    setProduct(undefined);
    try {
      const result = await getCanadianProduct(memberId, d);
      setProduct(result.product);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Session expired — please refresh and sign in again."
          : "Couldn't reach Health Canada. Please retry."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <Globe className="h-4 w-4 text-red-500" />
          Canadian DIN Lookup
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex gap-2 mb-2">
          <input
            value={din}
            onChange={(e) => setDin(e.target.value.replace(/\D/g, "").slice(0, 8))}
            onKeyDown={(e) => e.key === "Enter" && lookup()}
            placeholder="8-digit DIN (e.g. 02246893)"
            inputMode="numeric"
            className="flex-1 max-w-xs rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <Button size="sm" onClick={lookup} disabled={loading || din.length !== 8}>
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            Lookup
          </Button>
        </div>

        {error && <p className="text-sm text-destructive font-medium">{error}</p>}

        {product !== undefined &&
          !error &&
          (product ? (
            <div className="rounded-md border border-border bg-muted/20 p-3">
              <p className="text-sm font-semibold">
                {product.brand_name}
                {product.descriptor ? ` ${product.descriptor}` : ""}
              </p>
              <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] text-muted-foreground">
                <span>
                  DIN: <span className="font-mono text-foreground">{product.din}</span>
                </span>
                {product.company_name && <span>Company: {product.company_name}</span>}
                {product.class_name && <span>Class: {product.class_name}</span>}
                {product.last_update_date && <span>Updated: {product.last_update_date}</span>}
              </div>
              <a
                href={`https://health-products.canada.ca/dpd-bdpp/info?lang=en&din=${product.din}`}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-block text-[11px] text-blue-600 hover:underline dark:text-blue-400"
              >
                Full record on canada.ca ↗
              </a>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              No Canadian product found for DIN {din}.
            </p>
          ))}
        <p className="mt-2 text-[10px] text-muted-foreground/70">
          Source: Health Canada DPD. DPD is code-based (no name search) — find the 8-digit DIN on
          the bottle or prescription label.
        </p>
      </CardContent>
    </Card>
  );
});
