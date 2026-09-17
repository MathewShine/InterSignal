import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthPage } from "./AuthPage.jsx";

function renderAuth(path = "/auth?mode=signin") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<AuthPage delayScale={0} reducedMotionOverride />} path="/auth" />
        <Route element={<div>App route reached</div>} path="/app" />
        <Route element={<div>Landing route reached</div>} path="/" />
      </Routes>
    </MemoryRouter>,
  );
}

async function completeSignUp(user) {
  await user.type(screen.getByLabelText("Full name"), "Asha Patel");
  await user.type(screen.getByLabelText("Email address"), "asha@example.com");
  await user.type(screen.getByLabelText("Password"), "prototype-pass");
  await user.type(screen.getByLabelText("Confirm password"), "prototype-pass");
  await user.click(screen.getByLabelText(/I agree to the Terms/));
  await user.click(screen.getByRole("button", { name: "Create account" }));
}

afterEach(() => vi.restoreAllMocks());

describe("frontend-only authentication prototype", () => {
  it("renders the sign-in experience", () => {
    renderAuth();

    expect(screen.getByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
    expect(screen.getByLabelText("Email address")).toHaveAttribute("autocomplete", "email");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("switches naturally between sign in, create account, and forgot password", async () => {
    const user = userEvent.setup();
    renderAuth();

    await user.click(screen.getByRole("button", { name: /Create account/ }));
    expect(await screen.findByRole("heading", { name: "Create your InterSignal account" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Sign in/ }));
    expect(await screen.findByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Forgot password?" }));
    expect(await screen.findByRole("heading", { name: "Reset your password" })).toBeInTheDocument();
  });

  it("shows inline sign-in validation errors", async () => {
    const user = userEvent.setup();
    renderAuth();

    await user.type(screen.getByLabelText("Email address"), "not-an-email");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Password is required.")).toBeInTheDocument();
  });

  it("validates sign-up fields without creating an account", async () => {
    const user = userEvent.setup();
    renderAuth("/auth?mode=signup");

    await user.type(screen.getByLabelText("Full name"), "Asha Patel");
    await user.type(screen.getByLabelText("Email address"), "asha@example.com");
    await user.type(screen.getByLabelText("Password"), "prototype-pass");
    await user.type(screen.getByLabelText("Confirm password"), "different-pass");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
    expect(screen.getByText("Terms must be accepted.")).toBeInTheDocument();
  });

  it("navigates a valid dummy sign-in to /app without API or storage writes", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response());
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");
    renderAuth();

    await user.type(screen.getByLabelText("Email address"), "demo@example.com");
    await user.type(screen.getByLabelText("Password"), "anything");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("App route reached")).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(storageSpy).not.toHaveBeenCalled();
  });

  it("moves a dummy account creation to verification and continues to /app", async () => {
    const user = userEvent.setup();
    renderAuth("/auth?mode=signup");

    await completeSignUp(user);
    expect(await screen.findByRole("heading", { name: "Verify your email" })).toBeInTheDocument();
    expect(screen.getByText("asha@example.com")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Continue/ }));
    expect(await screen.findByText("App route reached")).toBeInTheDocument();
  });

  it("completes the dummy forgot-password state without sending email", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response());
    renderAuth("/auth?mode=forgot");

    await user.type(screen.getByLabelText("Email address"), "reset@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));

    expect(await screen.findByText("Check your inbox")).toBeInTheDocument();
    expect(screen.getByText("reset@example.com")).toBeInTheDocument();
    expect(screen.getByText(/No email was sent/)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("returns to the landing route from the brand logo without a duplicate back row", async () => {
    const user = userEvent.setup();
    const { container } = renderAuth();

    expect(container.querySelector(".auth-return")).not.toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Back to InterSignal home" }));
    await waitFor(() => expect(screen.getByText("Landing route reached")).toBeInTheDocument());
  });
});
