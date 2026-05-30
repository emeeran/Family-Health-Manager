import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { LoginForm } from "@/components/auth/login-form";

// Mock react-router-dom
const mockNavigate = jest.fn();
jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

// Mock the login API
const mockLogin = jest.fn();
jest.mock("@/lib/api/auth", () => ({
  login: (...args: any[]) => mockLogin(...args),
}));

describe("LoginForm", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("should render the login form with username and password fields", () => {
    render(<LoginForm />);

    expect(screen.getByText("Welcome back")).toBeInTheDocument();
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("should show validation errors for short inputs", async () => {
    render(<LoginForm />);

    const usernameInput = screen.getByLabelText(/username/i);
    const passwordInput = screen.getByLabelText(/password/i);

    // Type short values to trigger validation
    fireEvent.change(usernameInput, { target: { value: "ab" } });
    fireEvent.change(passwordInput, { target: { value: "short" } });

    // Submit the form
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText(/username must be at least 3 characters/i)).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText(/password must be at least 8 characters/i)).toBeInTheDocument();
    });
  });

  it("should navigate to dashboard on successful login", async () => {
    mockLogin.mockResolvedValueOnce({ access_token: "token", requires_2fa: false });

    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText(/username/i), {
      target: { value: "testuser" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith({
        username: "testuser",
        password: "password123",
      });
      expect(mockNavigate).toHaveBeenCalledWith("/dashboard");
    });
  });

  it("should navigate to 2FA page when requires_2fa is true", async () => {
    mockLogin.mockResolvedValueOnce({ requires_2fa: true });

    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText(/username/i), {
      target: { value: "testuser" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/login/2fa?username=testuser");
    });
  });

  it("should show error message on login failure", async () => {
    mockLogin.mockRejectedValueOnce(new Error("Invalid credentials"));

    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText(/username/i), {
      target: { value: "testuser" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
    });
  });

  it("should show loading state during login", async () => {
    // Create a promise that won't resolve immediately
    let resolveLogin: (value: any) => void;
    mockLogin.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveLogin = resolve;
      })
    );

    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText(/username/i), {
      target: { value: "testuser" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByRole("button")).toBeDisabled();
      expect(screen.getByText(/signing in/i)).toBeInTheDocument();
    });

    // Resolve the login to clean up
    resolveLogin!({ access_token: "token" });
  });
});
