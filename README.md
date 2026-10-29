# Bethorahzan — Growth in 3 Dimensions

A purpose-built **Flask + SQLAlchemy + Stripe** web platform for the Christ-governed Bethorahzan community, led by the Admiral of Bethorahzan with the Council of Twelve Generals. Original design assets provided by the community are included.

**Design direction:** classic institutional / governmental, contemporary editorial typography, technology-inspired geometry; terracotta, midnight blue and warm taupe. Front end: HTML5, Jinja2, Bootstrap 5 and custom CSS. Back end: Python Flask, SQLAlchemy, session-based authentication.

## Application map

| Public website | Member portal | Restricted administration |
| --- | --- | --- |
| Home / vision | Profile and interests | Overview, giving totals |
| About / governance | Appointment requests and updates | Members and CSV export |
| Teachings and video archive | Event RSVP | Events: create / edit / delete |
| Events and event details | Shop order history | Teachings: create / edit / delete |
| Impact and causes | Digital course access | Appointments: review and confirm |
| Giving via Stripe Checkout | Work posting / funding | Products: create / edit / archive |
| Books, courses and shop | Work applications / status | Shop orders and fulfillment details |
| Work opportunities | Stripe Connect payout onboarding | Causes and donation records |
| Contact & policy pages | Employer completion confirmation | Job funding, moderation, assignment, refund, settlement |
| Registration / login | Member dashboard | Work applications / contact inbox |

## Run locally

Requirements: Python 3.12+ (3.11 should also work), Git. Run in **PowerShell** on Windows or a terminal on macOS/Linux:

```bash
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # PowerShell: Copy-Item .env.example .env
# Edit .env with a UNIQUE SECRET_KEY; use the Stripe TEST keys for testing.
flask --app app init-db
flask --app app seed
flask --app app create-admin
flask --app app run --debug
```

Open **http://127.0.0.1:5000**. Use the email and password chosen by `create-admin`, then visit `/admin` to manage content. `flask seed` creates **sample/demo** events, shop resources and giving categories. Replace placeholder entries before a public launch. There is intentionally **no preset administrator password**.

Generate a secret key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Stripe configuration

1. Get a Stripe account approved for the intended activities. **Marketplaces with delayed worker settlement require explicit evaluation of the Stripe Connect model and applicable law.** The application is **not** an escrow account, a bank, or a money transmitter service. Do not represent it as one.
2. Fill `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, and `STRIPE_WEBHOOK_SECRET` in `.env`. The publishable key is reserved for future client-side UI; the current integration uses hosted Checkout.
3. Set up the signed Stripe webhook at `https://YOUR_DOMAIN/stripe/webhook`. Subscribe to `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, and `refund.updated`, and `refund.failed`. Only a **verified** webhook changes a purchase/donation/job to paid/funded.
4. Local Stripe CLI testing: `stripe listen --forward-to localhost:5000/stripe/webhook`. Copy the returned `whsec_...` into the `.env` file and restart the server.
5. Use **test mode** for donation, product and employer checkout scenarios before enabling real charges.

### Worker marketplace lifecycle

1. Any registered member posts a project, entering the **total employer budget** (e.g., `$200`).
2. The app stores: employer charge `$200`; proposed worker compensation `$180`; Bethorahzan fee `$20` (**10% of total**).
3. Employer pays via Stripe-hosted Checkout. After signed webhook verification, the job becomes `pending_review` and is **not public** yet.
4. Admin verifies the scope, eligibility and budget, then approves the job for the public Opportunities page.
5. Members apply; admin assigns one applicant. Work happens outside the application; employer or admin confirms delivery, and admin verifies completion.
6. Worker completes Stripe Connect Express onboarding. Admin releases `$180` by a **Stripe Connect transfer**, using the underlying charge as the source transaction; platform share is `$20` **before Stripe/payment-related costs**.
7. If nobody is assigned, admin can request a **full refund** to the original payment method while job status is `pending_review` or `open`.
8. Finalize a written marketplace agreement, disputes/chargebacks process, worker verification/KYC, cancellation procedures, payout timing and Stripe Connect approved account configuration before accepting live funds. Stripe may pay out the platform's balance on its own schedule; this implementation does **not** guarantee funds can be held indefinitely.

**Important:** Stripe Connect country support and transfer restrictions vary by account and jurisdiction. Onboarding is provisioned for **US Express accounts** in this starter build; don't advertise worker payouts worldwide until specifically enabled and validated. This build provides a manual governance workflow, **not** an automated legal escrow service.

### Books, courses, donations

- Products can be configured as **digital** or **physical**. For physical products, Stripe Checkout collects a shipping address; the listed product price must include shipping and any applicable taxes because the current build does not automatically calculate shipping fees or tax. Admins review order records and fulfill shipping manually.
- Digital courses can include a private access link that appears in the purchaser's portal only after verified payment; hosting and digital-rights protection of external content remain your responsibility.
- Giving categories are admin-manageable. Donations can be made without creating an account. Donor names and payment references are only shown in restricted admin views.
- A public financial reporting policy, disbursement controls, charity registration/tax status and donor communications must be finalized before public fundraising. Do **not** call gifts tax-deductible without a valid registration and qualified determination.

## Deployment

- Docker deployment is supported with the included `Dockerfile` and `Procfile`.
- Use **managed PostgreSQL** for production by setting `DATABASE_URL=postgresql+psycopg://...`; default SQLite is for local development and demos only.
- Set `SECRET_KEY` to a secure random value, `FLASK_ENV=production`, and `COOKIE_SECURE=1`. Deploy only behind HTTPS and a trusted reverse proxy; set up database backup/restore procedures.
- Run `flask --app app init-db` **once** before launching the first instance. SQLAlchemy's `create_all()` does **not** migrate existing tables; adopt Alembic/Flask-Migrate before later schema changes.
- Production app: `gunicorn -w 2 -b 0.0.0.0:8000 app:app`; check `/healthz`.
- Static assets are served through Flask for a small initial deployment; consider a CDN/edge static host at scale.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

CI configuration in `.github/workflows/tests.yml` runs automated route, auth, event CRUD, appointment, job-budget and payment-configuration checks in GitHub Actions. **This package has undergone source compilation and template syntax checks here, but runtime Flask tests could not be executed in the artifact environment because dependencies could not be downloaded.** Run tests in your local environment or GitHub Actions before public use.

## Publish to GitHub

The GitHub connector currently does not expose repository creation and no accessible repositories were returned for the connected account. To create **`Bethorahzan`** under your GitHub user without sharing your password, unpack the ZIP, then:

**Windows PowerShell:** Install the [GitHub CLI](https://cli.github.com/) and Git, open PowerShell in the project directory, and run:

```powershell
.\publish_github.ps1
```

**macOS / Linux:**

```bash
./publish_github.sh
```

Both scripts use your local GitHub CLI login and create a **private** `Bethorahzan` repository, commit the code, and push `main`. After the repo exists and is shared with your connected GitHub integration, further edits may be possible directly via the GitHub connector.

## Production-readiness checklist

- [ ] Professional legal review of charity status, tax receipts, donation policies, worker marketplace terms, refunds, custody of funds and Stripe Connect compliance
- [ ] Verify Stripe live account approval and end-to-end test payments/webhooks/transfers/refunds in test mode
- [ ] Add notification email/SMTP or transactional provider for booking confirmations, contact handling, receipts, job assignment and payouts
- [ ] Add audit logs, role-specific care-team permissions, MFA for administrators, abuse prevention / login rate limits, and secure password reset / email verification
- [ ] Establish safeguarding policies for minors, vulnerable adults, prayer/counseling details, and health-related data, plus a privacy retention/deletion program
- [ ] Add database migrations, backups, production monitoring, account re-verification, refund reconciliation and stock concurrency protections
- [ ] Verify digital content rights and real product inventory, fulfillment, tax/shipping rules, and polished final policies
- [ ] Replace example event dates, courses, product descriptions and program claims with approved information

## Architecture

```
Bethorahzan/
├── app.py                   # application factory, routes, admin, checkout, webhook
├── models.py                # database schema and user authentication
├── templates/               # public pages, member portal, admin workflows
│   └── admin/               # restricted administrator templates
├── static/css/style.css     # custom institutional design system
├── static/js/site.js        # interaction enhancements
├── static/img/              # supplied emblem and wordmark, ready for web use
├── tests/                   # pytest suite
├── Dockerfile / Procfile
├── .env.example / .gitignore
├── .github/workflows/       # GitHub Actions
└── publish_github.ps1/.sh   # GitHub creation and push scripts
```

© Bethorahzan. Brand imagery was supplied by the project owner; maintain provenance and obtain usage authorization for all future media.
