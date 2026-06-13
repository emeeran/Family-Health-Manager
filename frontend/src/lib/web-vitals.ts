/**
 * Web Vitals tracking utility.
 *
 * Reports Core Web Vitals metrics (LCP, INP, CLS, TTFB) to the console
 * in development mode. Can be extended to send metrics to an analytics
 * endpoint in production.
 *
 * Performance optimization (#20): provides baseline visibility into
 * real-user performance characteristics.
 */

type MetricName = "LCP" | "INP" | "CLS" | "TTFB" | "FCP";

interface MetricPayload {
  name: MetricName;
  value: number;
  rating: string;
  delta: number;
  navigationType: string;
}

function logMetric(metric: MetricPayload): void {
  const icon =
    metric.rating === "good" ? "✅" : metric.rating === "needs-improvement" ? "⚠️" : "❌";
  console.debug(
    `[Web Vitals] ${icon} ${metric.name}: ${metric.value.toFixed(0)}ms (${metric.rating})`
  );
}

export function initWebVitals(): void {
  // Only run in browser
  if (typeof window === "undefined") return;

  // Dynamic import keeps web-vitals out of the critical path
  import("web-vitals")
    .then((webVitals) => {
      const report = (metric: MetricPayload) => logMetric(metric);

      webVitals.onLCP(report);
      webVitals.onINP(report);
      webVitals.onCLS(report);
      webVitals.onTTFB(report);
      webVitals.onFCP(report);
    })
    .catch(() => {
      // Silently skip if web-vitals fails to load
    });
}
