import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/shared/password-input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/alert";
import { UserPlus, Loader2, Check, X } from "lucide-react";
import { register as registerUser, login } from "@/lib/api/auth";
import { useNavigate } from "react-router-dom";

const registerSchema = z
  .object({
    username: z.string().min(3, "Username must be at least 3 characters").max(50),
    password: z
      .string()
      .min(8, "Password must be at least 8 characters")
      .regex(/[A-Z]/, "Must contain an uppercase letter")
      .regex(/[0-9]/, "Must contain a digit")
      .regex(/[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/, "Must contain a special character"),
    confirmPassword: z.string(),
  })
  .refine((d) => d.password === d.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type RegisterFormValues = z.infer<typeof registerSchema>;

export function RegisterForm() {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
  });

  const password = watch("password", "");

  async function onSubmit(data: RegisterFormValues) {
    setError(null);
    setLoading(true);
    try {
      await registerUser({ username: data.username, password: data.password });
      // After successful registration, log in (backend sets httpOnly cookie)
      await login({ username: data.username, password: data.password });
      navigate("/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Registration failed");
      setLoading(false);
    }
  }

  const checks = [
    { label: "8+ characters", met: password.length >= 8 },
    { label: "Uppercase letter", met: /[A-Z]/.test(password) },
    { label: "Digit", met: /[0-9]/.test(password) },
    { label: "Special character", met: /[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/.test(password) },
  ];

  return (
    <Card className="border-0 shadow-none md:border md:shadow-sm">
      <CardHeader className="space-y-1 pb-4">
        <CardTitle className="text-xl">Create account</CardTitle>
        <CardDescription className="text-xs">Set up your household health tracker</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
          {error && (
            <Alert variant="destructive" className="text-xs py-2 animate-shake">
              {error}
            </Alert>
          )}
          <div className="space-y-1">
            <Label htmlFor="username" className="text-xs">
              Username
            </Label>
            <Input
              id="username"
              {...register("username")}
              placeholder="Choose a username"
              className="h-9"
              autoComplete="username"
            />
            {errors.username && (
              <p className="text-[11px] text-destructive">{errors.username.message}</p>
            )}
          </div>
          <div className="space-y-1">
            <Label htmlFor="password" className="text-xs">
              Password
            </Label>
            <PasswordInput
              id="password"
              {...register("password")}
              placeholder="Create a password"
              className="h-9"
              autoComplete="new-password"
            />
            <div className="grid grid-cols-2 gap-1 mt-1.5">
              {checks.map((c) => (
                <div
                  key={c.label}
                  className={`flex items-center gap-1 text-[11px] transition-colors ${c.met ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}`}
                >
                  {c.met ? (
                    <Check className="h-2.5 w-2.5" />
                  ) : (
                    <X className="h-2.5 w-2.5 opacity-40" />
                  )}
                  {c.label}
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="confirmPassword" className="text-xs">
              Confirm Password
            </Label>
            <PasswordInput
              id="confirmPassword"
              {...register("confirmPassword")}
              placeholder="Confirm your password"
              className="h-9"
              autoComplete="new-password"
            />
            {errors.confirmPassword && (
              <p className="text-[11px] text-destructive">{errors.confirmPassword.message}</p>
            )}
          </div>
          <Button type="submit" className="w-full h-9" disabled={loading}>
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
            ) : (
              <UserPlus className="h-3.5 w-3.5 mr-1.5" />
            )}
            {loading ? "Creating account..." : "Create Account"}
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            Already have an account?{" "}
            <a
              href="/login"
              className="text-primary font-medium underline-offset-4 hover:underline"
            >
              Sign in
            </a>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
