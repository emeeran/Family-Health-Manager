import React from "react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);

    // Check for chunk load errors / dynamic import failures
    const isChunkLoadError =
      error?.name === "ChunkLoadError" ||
      /Failed to fetch dynamically imported module/i.test(error?.message || "") ||
      /error loading dynamically imported module/i.test(error?.message || "") ||
      /Importing a module script failed/i.test(error?.message || "");

    if (isChunkLoadError) {
      try {
        const lastReload = sessionStorage.getItem("last-chunk-reload");
        const now = Date.now();
        // Prevent infinite reload loops by throttling to once per 10 seconds
        if (!lastReload || now - parseInt(lastReload, 10) > 10000) {
          sessionStorage.setItem("last-chunk-reload", now.toString());
          window.location.reload();
        }
      } catch (e) {
        console.error("Failed to auto-reload on chunk load error", e);
      }
    }
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      const isChunkLoadError =
        this.state.error?.name === "ChunkLoadError" ||
        /Failed to fetch dynamically imported module/i.test(this.state.error?.message || "") ||
        /error loading dynamically imported module/i.test(this.state.error?.message || "") ||
        /Importing a module script failed/i.test(this.state.error?.message || "");

      return (
        <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
          <p className="text-sm font-medium text-destructive mb-2">
            {isChunkLoadError ? "App Update Available" : "Something went wrong"}
          </p>
          <p className="text-xs text-muted-foreground mb-4 max-w-md">
            {isChunkLoadError
              ? "A new version of the application has been deployed. Please reload the page to apply the update."
              : this.state.error?.message || "An unexpected error occurred."}
          </p>
          <button
            onClick={() => {
              if (isChunkLoadError) {
                window.location.reload();
              } else {
                this.setState({ hasError: false, error: null });
              }
            }}
            className="text-xs text-primary hover:underline font-medium px-4 py-2 border rounded-md hover:bg-muted transition-colors"
          >
            {isChunkLoadError ? "Reload Page" : "Try again"}
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
