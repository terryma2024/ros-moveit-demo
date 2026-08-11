import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
const buttonVariants = cva("inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 disabled:pointer-events-none disabled:opacity-50", { variants: { variant: { default: "bg-sky-600 text-white hover:bg-sky-500", secondary: "bg-slate-700 text-white hover:bg-slate-600", destructive: "bg-red-700 text-white hover:bg-red-600", outline: "border border-slate-600 bg-transparent hover:bg-slate-800" }, size: { default: "h-9 px-3", sm: "h-8 px-2", lg: "h-10 px-4" } }, defaultVariants: { variant: "default", size: "default" } });
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}
const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, ...props }, ref) => <button ref={ref} className={cn(buttonVariants({ variant, size, className }))} {...props} />);
Button.displayName = "Button"; export { Button, buttonVariants };
