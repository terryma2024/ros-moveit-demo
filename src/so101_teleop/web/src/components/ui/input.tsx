import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The captured `radix-maia` `registry:ui` input, converted from its Tailwind v4 source to this
 * project's Tailwind 3.4.17 token set. The conversion is mechanical and explicit:
 * `rounded-4xl` has no v3 equivalent, so it becomes the token radius (`rounded-md`);
 * `bg-input/30` and `ring-ring/50` rely on v4 alpha composition of a `var()` colour, so they
 * become the solid token utilities; the `file:` and `aria-invalid` behaviour, the focus ring and
 * the disabled semantics are kept exactly as the registry defines them.
 */
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-9 w-full min-w-0 rounded-md border border-input bg-card px-3 py-1 text-base text-foreground transition-colors outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-70 aria-invalid:border-destructive aria-invalid:ring-2 aria-invalid:ring-destructive md:text-sm",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
