import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { AuthVisual } from "../components/auth/AuthVisual.jsx";
import { ArrowRightIcon } from "../components/icons/Icons.jsx";
import { MotionProvider, useMotionPreference } from "../components/motion/index.js";

const AUTH_MODES = new Set(["signin", "signup", "forgot", "verify"]);
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const initialForm = {
  confirmPassword: "",
  email: "",
  fullName: "",
  password: "",
  remember: false,
  terms: false,
};

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function EyeIcon({ crossed = false }) {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 20 20">
      <path d="M2.2 10s2.7-4.4 7.8-4.4 7.8 4.4 7.8 4.4-2.7 4.4-7.8 4.4S2.2 10 2.2 10Z" stroke="currentColor" />
      <circle cx="10" cy="10" r="2.2" stroke="currentColor" />
      {crossed ? <path d="m3.4 3.4 13.2 13.2" stroke="currentColor" strokeLinecap="round" /> : null}
    </svg>
  );
}

function GoogleGlyph() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20">
      <path d="M18.5 10.2c0-.6-.1-1.2-.2-1.7H10v3.2h4.7a4 4 0 0 1-1.8 2.6v2.1h2.9c1.7-1.6 2.7-3.8 2.7-6.2Z" fill="#4285f4" />
      <path d="M10 18.8c2.4 0 4.5-.8 5.9-2.3L13 14.3c-.8.5-1.8.9-3 .9-2.3 0-4.3-1.6-5-3.7H2v2.2a8.9 8.9 0 0 0 8 5.1Z" fill="#34a853" />
      <path d="M5 11.5a5.4 5.4 0 0 1 0-3.1V6.2H2a8.9 8.9 0 0 0 0 7.5l3-2.2Z" fill="#fbbc05" />
      <path d="M10 4.8c1.3 0 2.5.5 3.4 1.3L16 3.5A8.7 8.7 0 0 0 2 6.2l3 2.2c.7-2.1 2.7-3.6 5-3.6Z" fill="#ea4335" />
    </svg>
  );
}

function InlineSpinner() {
  return <span aria-hidden="true" className="auth-spinner" />;
}

function Field({
  autoComplete,
  error,
  id,
  label,
  onChange,
  placeholder,
  type = "text",
  value,
}) {
  const [visible, setVisible] = useState(false);
  const isPassword = type === "password";
  const describedBy = error ? `${id}-error` : undefined;

  return (
    <div className={`auth-field ${error ? "has-error" : ""}`}>
      <label htmlFor={id}>{label}</label>
      <div className="auth-field__control">
        <input
          aria-describedby={describedBy}
          aria-invalid={error ? "true" : undefined}
          autoComplete={autoComplete}
          id={id}
          name={id}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          type={isPassword && visible ? "text" : type}
          value={value}
        />
        {isPassword ? (
          <button
            aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
            className="auth-field__visibility"
            onClick={() => setVisible((current) => !current)}
            type="button"
          >
            <EyeIcon crossed={visible} />
          </button>
        ) : null}
      </div>
      {error ? <p className="auth-field__error" id={describedBy}>{error}</p> : null}
    </div>
  );
}

function SubmitButton({ busy, busyLabel, children }) {
  return (
    <motion.button
      className="auth-button auth-button--primary"
      disabled={busy}
      type="submit"
      whileHover={busy ? undefined : { y: -1 }}
      whileTap={busy ? undefined : { y: 1 }}
    >
      <span>{busy ? busyLabel : children}</span>
      {busy ? <InlineSpinner /> : <ArrowRightIcon />}
    </motion.button>
  );
}

function SignInForm({ busy, errors, form, onChange, onMode, onSubmit }) {
  return (
    <form className="auth-form" data-auth-form="signin" noValidate onSubmit={onSubmit}>
      <Field
        autoComplete="email"
        error={errors.email}
        id="signin-email"
        label="Email address"
        onChange={(value) => onChange("email", value)}
        placeholder="you@example.com"
        type="email"
        value={form.email}
      />
      <Field
        autoComplete="current-password"
        error={errors.password}
        id="signin-password"
        label="Password"
        onChange={(value) => onChange("password", value)}
        placeholder="Enter your password"
        type="password"
        value={form.password}
      />
      <div className="auth-form__options">
        <label className="auth-check" htmlFor="remember-me">
          <input
            checked={form.remember}
            id="remember-me"
            onChange={(event) => onChange("remember", event.target.checked)}
            type="checkbox"
          />
          <span>Remember me</span>
        </label>
        <button className="auth-text-button" onClick={() => onMode("forgot")} type="button">Forgot password?</button>
      </div>
      <SubmitButton busy={busy} busyLabel="Signing in…">Sign in</SubmitButton>
      <div className="auth-divider"><span>or</span></div>
      <button className="auth-button auth-button--google" type="button">
        <GoogleGlyph />
        <span>Continue with Google</span>
        <small>Demo</small>
      </button>
      <p className="auth-switch">New to InterSignal? <button onClick={() => onMode("signup")} type="button">Create account <span aria-hidden="true">→</span></button></p>
    </form>
  );
}

function SignUpForm({ busy, errors, form, onChange, onMode, onSubmit }) {
  return (
    <form className="auth-form" data-auth-form="signup" noValidate onSubmit={onSubmit}>
      <Field autoComplete="name" error={errors.fullName} id="signup-name" label="Full name" onChange={(value) => onChange("fullName", value)} placeholder="Your full name" value={form.fullName} />
      <Field autoComplete="email" error={errors.email} id="signup-email" label="Email address" onChange={(value) => onChange("email", value)} placeholder="you@example.com" type="email" value={form.email} />
      <div className="auth-form__paired">
        <Field autoComplete="new-password" error={errors.password} id="signup-password" label="Password" onChange={(value) => onChange("password", value)} placeholder="Create a password" type="password" value={form.password} />
        <Field autoComplete="new-password" error={errors.confirmPassword} id="signup-confirm-password" label="Confirm password" onChange={(value) => onChange("confirmPassword", value)} placeholder="Repeat password" type="password" value={form.confirmPassword} />
      </div>
      <div className="auth-terms">
        <label className="auth-check" htmlFor="accept-terms">
          <input
            aria-describedby={errors.terms ? "terms-error" : undefined}
            aria-invalid={errors.terms ? "true" : undefined}
            checked={form.terms}
            id="accept-terms"
            onChange={(event) => onChange("terms", event.target.checked)}
            type="checkbox"
          />
          <span>I agree to the <a href="#terms">Terms</a> and <a href="#privacy">Privacy Policy</a></span>
        </label>
        {errors.terms ? <p className="auth-field__error" id="terms-error">{errors.terms}</p> : null}
      </div>
      <SubmitButton busy={busy} busyLabel="Creating account…">Create account</SubmitButton>
      <p className="auth-switch">Already have an account? <button onClick={() => onMode("signin")} type="button">Sign in <span aria-hidden="true">→</span></button></p>
    </form>
  );
}

function ForgotPasswordForm({ busy, email, error, onEmail, onMode, onSubmit, sent }) {
  if (sent) {
    return (
      <div className="auth-confirmation" role="status">
        <span aria-hidden="true" className="auth-confirmation__mark">✓</span>
        <h2>Check your inbox</h2>
        <p>We sent a reset link to:</p>
        <strong>{email}</strong>
        <p className="auth-demo-note">This is demo UI only. No email was sent.</p>
        <button className="auth-button auth-button--secondary" onClick={() => onMode("signin")} type="button">Back to sign in</button>
      </div>
    );
  }

  return (
    <form className="auth-form" data-auth-form="forgot" noValidate onSubmit={onSubmit}>
      <Field autoComplete="email" error={error} id="reset-email" label="Email address" onChange={onEmail} placeholder="you@example.com" type="email" value={email} />
      <SubmitButton busy={busy} busyLabel="Sending…">Send reset link</SubmitButton>
      <button className="auth-back-button" onClick={() => onMode("signin")} type="button"><span aria-hidden="true">←</span> Back to sign in</button>
    </form>
  );
}

function VerificationPanel({ email, onContinue, onDifferentEmail }) {
  const [resent, setResent] = useState(false);

  return (
    <div className="auth-verification">
      <div aria-hidden="true" className="auth-verification__envelope"><span /></div>
      <p>We sent a verification link to:</p>
      <strong>{email || "your email address"}</strong>
      <button className="auth-button auth-button--primary" onClick={onContinue} type="button">Continue <ArrowRightIcon /></button>
      <div className="auth-verification__actions">
        <button onClick={() => setResent(true)} type="button">{resent ? "Email resent" : "Resend email"}</button>
        <button onClick={onDifferentEmail} type="button">Use a different email</button>
      </div>
      <p className="auth-demo-note">Prototype verification only. No email was sent.</p>
    </div>
  );
}

const modeContent = {
  forgot: {
    eyebrow: "ACCOUNT ACCESS",
    heading: "Reset your password",
    supporting: "Enter the email associated with your InterSignal account.",
  },
  signin: {
    eyebrow: "WELCOME TO INTERSIGNAL",
    heading: "Welcome back.",
    supporting: "Sign in to continue to InterSignal.",
  },
  signup: {
    eyebrow: "CREATE YOUR WORKSPACE",
    heading: "Create your InterSignal account",
    supporting: "Set up your workspace for research, portfolio context and market intelligence.",
  },
  verify: {
    eyebrow: "ONE MORE STEP",
    heading: "Verify your email",
    supporting: "Confirm your address before continuing to the prototype workspace.",
  },
};

function AuthExperience({ delayScale }) {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { reducedMotion } = useMotionPreference();
  const requestedMode = searchParams.get("mode") ?? "signin";
  const mode = AUTH_MODES.has(requestedMode) ? requestedMode : "signin";
  const [form, setForm] = useState(() => ({ ...initialForm, email: location.state?.email ?? "" }));
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [resetSent, setResetSent] = useState(false);
  const headingRef = useRef(null);
  const previousMode = useRef(mode);
  const content = modeContent[mode];

  useEffect(() => {
    if (previousMode.current !== mode) {
      headingRef.current?.focus();
      previousMode.current = mode;
    }
    setErrors({});
    setBusy(false);
    if (mode !== "forgot") setResetSent(false);
  }, [mode]);

  function updateField(name, value) {
    setForm((current) => ({ ...current, [name]: value }));
    setErrors((current) => ({ ...current, [name]: undefined }));
  }

  function changeMode(nextMode, options = {}) {
    navigate(`/auth?mode=${nextMode}`, { replace: false, state: options.state });
  }

  function validateEmail(value) {
    if (!value.trim()) return "Email address is required.";
    if (!EMAIL_PATTERN.test(value.trim())) return "Enter a valid email address.";
    return undefined;
  }

  async function submitSignIn(event) {
    event.preventDefault();
    const nextErrors = {
      email: validateEmail(form.email),
      password: form.password ? undefined : "Password is required.",
    };
    setErrors(nextErrors);
    if (Object.values(nextErrors).some(Boolean)) return;
    setBusy(true);
    await wait(650 * delayScale);
    navigate("/app");
  }

  async function submitSignUp(event) {
    event.preventDefault();
    const nextErrors = {
      confirmPassword: form.confirmPassword === form.password ? undefined : "Passwords do not match.",
      email: validateEmail(form.email),
      fullName: form.fullName.trim() ? undefined : "Full name is required.",
      password: form.password ? undefined : "Password is required.",
      terms: form.terms ? undefined : "Terms must be accepted.",
    };
    setErrors(nextErrors);
    if (Object.values(nextErrors).some(Boolean)) return;
    setBusy(true);
    await wait(750 * delayScale);
    navigate("/auth?mode=verify", { state: { email: form.email.trim() } });
  }

  async function submitReset(event) {
    event.preventDefault();
    const emailError = validateEmail(form.email);
    setErrors({ email: emailError });
    if (emailError) return;
    setBusy(true);
    await wait(600 * delayScale);
    setBusy(false);
    setResetSent(true);
  }

  const variants = reducedMotion
    ? { enter: { opacity: 0 }, center: { opacity: 1 }, exit: { opacity: 0 } }
    : { enter: { opacity: 0, y: 8 }, center: { opacity: 1, y: 0 }, exit: { opacity: 0, y: -6 } };

  return (
    <main className="auth-page" data-auth-mode={mode} data-authentication-backend="NOT_IMPLEMENTED">
      <AuthVisual />
      <section aria-label="Authentication" className="auth-panel">
        <div className="auth-panel__inner">
          <AnimatePresence initial={false} mode="wait">
            <motion.div
              animate="center"
              className="auth-mode"
              exit="exit"
              initial="enter"
              key={`${mode}-${mode === "forgot" && resetSent ? "sent" : "form"}`}
              transition={{ duration: reducedMotion ? 0.12 : 0.2, ease: [0.22, 1, 0.36, 1] }}
              variants={variants}
            >
              {mode === "forgot" && resetSent ? null : (
                <header className="auth-mode__header">
                  <p className="technical-label">{content.eyebrow}</p>
                  <h1 ref={headingRef} tabIndex="-1">{content.heading}</h1>
                  <p>{content.supporting}</p>
                </header>
              )}

              {mode === "signin" ? <SignInForm busy={busy} errors={errors} form={form} onChange={updateField} onMode={changeMode} onSubmit={submitSignIn} /> : null}
              {mode === "signup" ? <SignUpForm busy={busy} errors={errors} form={form} onChange={updateField} onMode={changeMode} onSubmit={submitSignUp} /> : null}
              {mode === "forgot" ? <ForgotPasswordForm busy={busy} email={form.email} error={errors.email} onEmail={(value) => updateField("email", value)} onMode={changeMode} onSubmit={submitReset} sent={resetSent} /> : null}
              {mode === "verify" ? <VerificationPanel email={location.state?.email ?? form.email} onContinue={() => navigate("/app")} onDifferentEmail={() => changeMode("signup")} /> : null}
            </motion.div>
          </AnimatePresence>
        </div>
      </section>
    </main>
  );
}

export function AuthPage({ delayScale = 1, reducedMotionOverride }) {
  useEffect(() => {
    document.body.classList.add("auth-route-active");
    return () => document.body.classList.remove("auth-route-active");
  }, []);

  return (
    <MotionProvider reducedMotionOverride={reducedMotionOverride}>
      <a className="skip-link" href="#auth-content">Skip to authentication</a>
      <div id="auth-content">
        <AuthExperience delayScale={delayScale} />
      </div>
    </MotionProvider>
  );
}
