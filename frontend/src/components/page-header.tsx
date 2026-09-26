import type { ReactNode } from "react";
import { errorText } from "@/lib/api";
import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description ? <p className="max-w-3xl text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}

/** Loading / error placeholder sized for a chart or card body. */
export function DataState({
  isLoading,
  error,
  isEmpty,
  height = 280,
  children,
}: {
  isLoading: boolean;
  error: unknown;
  isEmpty?: boolean;
  height?: number;
  children: ReactNode;
}) {
  let message: string | null = null;
  if (error) message = errorText(error);
  else if (isLoading) message = "Loading…";
  else if (isEmpty) message = "No data yet.";

  if (!message) return <>{children}</>;
  return (
    <div
      role={error ? "alert" : "status"}
      style={{ height }}
      className={cn("flex items-center justify-center text-sm", error ? "text-destructive" : "text-muted-foreground")}
    >
      {message}
    </div>
  );
}
