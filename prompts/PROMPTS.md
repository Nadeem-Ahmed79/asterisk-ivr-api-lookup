# Prompt list

Each prompt is recorded once per language and stored as:

```
/var/lib/asterisk/sounds/so/custom/<name>.wav    # Somali
/var/lib/asterisk/sounds/en/custom/<name>.wav    # English
```

Format: 8 kHz, 16-bit, mono WAV (or `.sln`/`.g722` for HD). Convert with:

```bash
sox input.wav -r 8000 -c 1 -b 16 custom/welcome.wav
```

## Somali prompts

The Somali prompts should be **written and recorded by a native speaker**, then
checked in short listening tests with community members before going live.
Text-to-speech is only an option for dynamic parts (numbers, dates) and only
if it is actually clear to callers. Otherwise use recorded number and month
prompts, as `sub-say-date` in the dialplan already does.

## Prompts

| Name | English script (source text for translation) |
|---|---|
| `welcome` | Welcome to the humanitarian helpline. This call is free. |
| `select-language` | For Somali, press 1. For English, press 2. |
| `main-menu` | To check your registration, press 1. For the next distribution date, press 2. For an update on a case you reported, press 3. For general information, press 4. To speak to an agent, press 0. |
| `invalid-option` | Sorry, that is not a valid option. |
| `enter-case-number` | Please enter your case number, then press the hash key. |
| `enter-pin` | Please enter your four-digit PIN. |
| `verify-failed` | Sorry, we could not verify those details. Please try again. |
| `too-many-attempts` | We could not verify your details. We will connect you to someone who can help. |
| `system-unavailable` | Sorry, this service is not available right now. |
| `reg-registered` | You are registered. |
| `reg-pending` | Your registration is still being processed. |
| `reg-not_registered` | We could not find an active registration for you. |
| `dist-next-date` | Your next distribution is on |
| `dist-none` | No distribution is scheduled for you at the moment. |
| `month-01` … `month-12` | January … December |
| `case-received` | We have received your case, and it will be reviewed soon. |
| `case-in_progress` | Your case is being reviewed. |
| `case-resolved` | Your case has been resolved. |
| `case-none` | We have no open case for you. |
| `faq-menu` | For information about registration, press 1. For distributions, press 2. … To go back, press 9. To speak to an agent, press 0. |
| `faq-1` … `faq-5` | One recorded answer per topic. These can be replaced by staff at any time. |
| `after-answer` | To go back to the main menu, press 1. To speak to an agent, press 0. Or you can hang up now. |
| `transferring` | Please wait while we connect you to an agent. |
| `after-hours` | Our agents are available Saturday to Thursday, 8 am to 5 pm. |
| `offer-callback` | To ask an agent to call you back, press 1. |
| `callback-confirmed` | Thank you. An agent will call you back on this number. |
| `goodbye` | Thank you for calling. Goodbye. |

Numbers use Asterisk's standard `digits/` prompts, which also need to be
recorded in Somali (`sounds/so/digits/`).
