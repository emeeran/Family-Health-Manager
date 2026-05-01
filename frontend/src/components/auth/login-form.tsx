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
import { LogIn, Loader2 } from "lucide-react";
import { login } from "@/lib/api/auth";
import { useNavigate } from "react-router-dom";

const loginSchema = z.object({
  username: z.string().min(3, "Username must be at least 3 characters"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export function LoginForm() {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  async function onSubmit(data: LoginFormValues) {
    setError(null);
    setLoading(true);
    try {
      await login({ username: data.username, password: data.password });
      navigate("/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
      setLoading(false);
    }
  }

  return (
    <Card className="border-0 shadow-none md:border md:shadow-sm">
      <CardHeader className="space-y-1 pb-4">
        <CardTitle className="text-xl">Welcome back</CardTitle>
        <CardDescription className="text-xs">
          Sign in to your health tracker account
        </CardDescription>
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
              placeholder="Enter username"
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
              placeholder="Enter password"
              className="h-9"
              autoComplete="current-password"
            />
            {errors.password && (
              <p className="text-[11px] text-destructive">{errors.password.message}</p>
            )}
          </div>
          <Button type="submit" className="w-full h-9" disabled={loading}>
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
            ) : (
              <LogIn className="h-3.5 w-3.5 mr-1.5" />
            )}
            {loading ? "Signing in..." : "Sign In"}
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            Don&apos;t have an account?{" "}
            <a
              href="/register"
              className="text-primary font-medium underline-offset-4 hover:underline"
            >
              Create one
            </a>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
