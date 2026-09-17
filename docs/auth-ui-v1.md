# InterSignal Auth UI V1

Milestone: `INTERSIGNAL_AUTH_UI_V1`

Profile: `FRONTEND_ONLY_DUMMY_AUTH_FLOW_V1`

## Scope

This milestone is a frontend-only authentication prototype. It provides the public interaction and routing needed to review sign in, account creation, password reset, and email verification, but it does not authenticate or create users.

`AUTHENTICATION_BACKEND = NOT_IMPLEMENTED`

## Routes

- `/` — existing public landing page.
- `/auth?mode=signin` — dummy sign-in form.
- `/auth?mode=signup` — dummy account-creation form.
- `/auth?mode=forgot` — dummy reset-link flow.
- `/auth?mode=verify` — dummy email-verification state.
- `/app` — temporary authenticated-entry placeholder for route verification only.

On desktop widths of 1024px and above, every auth mode is contained within a fixed `100dvh` split layout. Tablet and mobile layouts retain natural document scrolling for usability. The brand-panel InterSignal mark is the sole return-to-landing control.

## Dummy behaviour

Forms perform client-side presence, email-format, password-match, and terms checks. Valid submissions wait briefly to expose loading states, then navigate in memory through the prototype flow. The Google action is visual only. Reset and verification actions do not send email.

No password, user, token, cookie, or authentication session is persisted. The prototype does not call an authentication API, an OAuth provider, or any other external identity service. `/app` has no route guard and is directly accessible by design.

## Future backend boundary

A later authentication milestone may replace the submit handlers with a dedicated authentication client and add server-issued session handling plus route protection. That integration must preserve the form's accessible labels and error surfaces while keeping credentials out of browser persistence. The `/app` placeholder must be replaced only as part of Step 04.05C; it is not the Home or Intelligence Canvas implementation.
