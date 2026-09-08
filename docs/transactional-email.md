# Transactional email

Django multipart email messages use `store.email_backend.BrevoAPIEmailBackend`
whenever BREVO_API_KEY is configured. It calls Brevo's HTTPS transactional API;
otherwise EMAIL_BACKEND selects the development/SMTP backend. Password resets
and allauth use Django's default sender and backend as well.

## Production environment (set privately, never commit credentials)

- BREVO_API_KEY: retain the existing secret.
- BREVO_SENDER_EMAIL: orders@bowwandmeow.com
- BREVO_SENDER_NAME: Boww & Meow
- DEFAULT_FROM_EMAIL: orders@bowwandmeow.com (legacy compatibility; the effective
  Django sender is composed from BREVO_SENDER_NAME and BREVO_SENDER_EMAIL so a
  bare address never drops the display name).
- ORDER_NOTIFICATION_EMAIL: set the owner's requested mailbox privately in Render.
  Empty disables owner messages. The real recipient is intentionally not in this file.
- STOREFRONT_BASE_URL: https://bowwandmeow.com (customer and CRM email links).

## Events and timing

Customer confirmation remains at COD creation or successful online payment.
Payment-confirmed/payment-failed, packed, shipped, delivered and cancelled events
remain supported. There is no out-for-delivery order state in this application.
The separate owner-new-order message is scheduled after successful checkout order
creation, including pending online orders. It explicitly warns staff to verify
payment before fulfilment. It is not copied to the customer. There is no dedicated
CRM order-detail GET page, so the message links to the authenticated CRM orders list.
Admin/import-created orders do not trigger checkout notifications automatically.
Test-mode checkout records follow the same email path: the model has no reliable
test-order flag. Do not mistake an email about a test order for a fulfilment request.

## Duplicate protection and failure semantics

Migration 0028 introduces one unique OrderEmailDelivery row per order and event.
Delivery is invoked after transaction commit. A durable claim is inserted BEFORE
calling the provider, preventing duplicate attempts from concurrent callbacks,
refreshes, repeated transitions or duplicate notification paths. Re-entering a
previously emailed state does not resend that event.

This guarantees at-most-one application send attempt, NOT exactly-once inbox
delivery. A crash between claiming and sending can lose a message; a network
timeout can mean the provider accepted it despite a local failure. There are no
automatic retries. Inspect Brevo delivery logs before any manual recovery; do
not delete claims or blindly replay failed/attempting records. `sent` means the
backend accepted the message, not proof of inbox delivery. Logs contain only
order/event identifiers or HTTP status, never recipient/payload/exception text.

## Deployment after review

1. Review changes; do not deploy without approval.
2. Set ORDER_NOTIFICATION_EMAIL privately and confirm the sender/base URL values.
3. Apply `python manage.py migrate` before serving the new code. Render's existing
   start command already runs migrations. Do not send email before migration 0028.
4. Verify with an explicitly approved test order and check Brevo/customer/owner
   delivery. Customer emails sent BEFORE this migration have no ledger record;
   do not manually replay historical notification calls.
5. No historical email backfill, production stock changes or payment changes are
   performed by this migration.

Run checks/tests with an isolated database and locmem email backend, clearing
BREVO_API_KEY for the test process so no real messages can be sent.
