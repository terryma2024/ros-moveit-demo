"use client";

import * as LabelPrimitive from "@radix-ui/react-label";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The captured `radix-maia` `registry:ui` label, converted to this project's Tailwind 3.4.17
 * token set. The registry source imports the `radix-ui` umbrella package; this project already
 * depends on the scoped `@radix-ui/react-label`, so the primitive is identical while the import
 * binding stays within the existing dependency closure. No class needed conversion beyond keeping
 * the token utilities, but the v4-shaped `data-[disabled=true]:` selectors are written here as the
 * v3-equivalent `group-data-[disabled=true]:` / `peer-disabled:` pair the registry uses.
 */
function Label({ className, ...props }: React.ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn(
        "flex items-center gap-2 text-sm leading-none font-medium select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export { Label };
