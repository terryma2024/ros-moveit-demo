import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
/**
 * The registry's full variant set, merged into this project's button. `ghost`, `link`, `icon`,
 * `icon-sm` and `xs` come from the captured `radix-maia` button because the ported sheet and
 * sidebar use them. Their v4-only refinements (`has-data-[icon=...]` padding and `dark:` alpha
 * variants) are omitted: Tailwind 3 cannot alpha a `var()` colour, and dropping them changes no
 * behaviour this project uses.
 */
const buttonVariants = cva("inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50", { variants: { variant: { default: "bg-primary text-primary-foreground hover:bg-secondary", secondary: "bg-secondary text-secondary-foreground hover:bg-accent", destructive: "bg-destructive text-white hover:bg-failure", outline: "border border-input bg-transparent hover:bg-accent hover:text-accent-foreground", ghost: "hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground", link: "text-primary underline-offset-4 hover:underline" }, size: { default: "h-9 px-3", sm: "h-8 px-2", lg: "h-10 px-4", icon: "h-9 w-9", "icon-sm": "h-8 w-8", xs: "h-6 px-2.5 text-xs" } }, defaultVariants: { variant: "default", size: "default" } });
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}
const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, ...props }, ref) => <button ref={ref} className={cn(buttonVariants({ variant, size, className }))} {...props} />);
Button.displayName = "Button"; export { Button, buttonVariants };
