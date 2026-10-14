# Meta WhatsApp setup: teammate guide

Goal: get a free WhatsApp test number for CampusPulse **without the account getting locked** (error 131031, "Business Account locked").

## Why the first account got locked (avoid all of these)

- A **new or barely used Facebook account**, which is the biggest trigger.
- **Retrying business-portfolio creation** after Meta said "check back later".
- No two-factor authentication, or details that look made up.
- Many changes in a short time.

## 0. Before you start (5 min)

1. Use **your real, long-standing Facebook account**: real name, profile photo, ideally 1+ year old and used normally. **Don't** create a new Facebook account for this.
2. Turn on **two-factor authentication**: Facebook → Settings → Accounts Center → Password and security → Two-factor authentication.
3. Make sure your Facebook **email and phone are confirmed**.
4. **No VPN.** Use your normal laptop and network.
5. Set aside 30 minutes and do it in one sitting. **If Meta ever says "try again later", stop and wait.** Don't keep clicking.

## 1. Create the business portfolio (once)

1. Go to **business.facebook.com** → **Create an account** (business portfolio).
2. Fill in **real details**:
   - Business name: e.g. `CampusPulse Labs` or `<YourName> Projects`. **Don't** use "WhatsApp", "Meta", "Facebook" or a real company's name.
   - Your real name.
   - Your real email, one you can open right now.
3. **Open the confirmation email and verify it immediately.**
4. Create it **only once**. If it errors, wait an hour before trying again.

## 2. Register as a developer and create the app

1. Go to **developers.facebook.com** → **Get started**, if you're not registered yet. Verify with your phone/email when asked.
2. **My Apps → Create App**:
   - App name: `CampusPulse Demo` (again, no "WhatsApp"/"Meta" in the name).
   - Use case: **"Connect with customers through WhatsApp"**.
   - Business portfolio: choose the one from step 1.
3. Finish. **Don't** publish the app, add other products, or apply as a Tech Provider. You don't need any of that.

## 3. Get the test number working

1. In the app: **WhatsApp → API Setup**.
2. Wait **1–2 minutes** for the test number to register. The page says so.
3. **"To" field → Manage phone number list → Add phone number** → add **only your own number first** → enter the WhatsApp code.
4. Click **Send message** (the hello_world template) to your own number.
5. ✅ **The hello_world message arrives on your phone?** The account is healthy, so continue.
   ❌ **Nothing arrives within 2 minutes?** Stop here. Don't retry repeatedly. Tell Jeet. Check **business.facebook.com → Account Quality** for a restriction and **Request review**.
6. Reply **"hi"** from your phone to the test number. This opens the 24-hour window.
7. Now add the other team phones (max 5 in total), **one at a time**, each entering its own code. Don't add all of them in a rush.

## 4. Create a permanent access token

The token on the API Setup page expires in 24 hours. Make one that doesn't:

1. **business.facebook.com → Settings → Users → System users → Add**. Name: `campuspulse-bot`, role **Admin**.
2. Select it → **Assign assets**:
   - **Apps** → `CampusPulse Demo` → **Full control**.
   - **WhatsApp accounts** → your WhatsApp account → **Full control**.
3. **Generate token**:
   - App: `CampusPulse Demo`.
   - Expiration: **Never**.
   - Permissions: tick `whatsapp_business_messaging` and `whatsapp_business_management`.
4. Copy the token **once** and keep it private.

## 5. App secret

**App settings → Basic → App Secret → Show** (asks for your Facebook password) → copy.

## 6. Hand over to Jeet (safely)

| Value | Where | Secret? |
|---|---|---|
| Phone Number ID | WhatsApp → API Setup | no |
| WhatsApp Business Account ID | WhatsApp → API Setup | no |
| Permanent access token | step 4 | **YES** |
| App secret | step 5 | **YES** |

Send the two **secret** values **in a private 1-to-1 chat** (not the team group), or better, type them into Jeet's `backend/.env` yourself:

```
NOTIFIER=meta
META_WA_TOKEN=<permanent token>
META_WA_PHONE_NUMBER_ID=<phone number id>
META_WA_BUSINESS_ACCOUNT_ID=<waba id>
META_APP_SECRET=<app secret>
```

Don't paste secrets into AI chats, screenshots or the GitHub repo.

## 7. Demo day

About 30 minutes before presenting, **every staff phone sends "hi"** to the test number. That opens a fresh 24-hour window, so work orders deliver for free.
