# asterisk-ivr-api-lookup

A self-service IVR for Asterisk that lets callers check their own information,
such as registration status, next distribution date or case status, **after
verification**, by looking it up in a backend REST API.

It is a small, working reference design for helplines and call centres where
many callers only need a simple answer and agents are limited.

```
Caller ──► Asterisk dialplan ──► AGI (Python) ──► REST API (OAuth2) ──► CRM / database
             prompts, menus        verify + lookup    case management
             queue, callbacks      sets channel vars
```

## Features

- **Verified lookups.** Case number + PIN + caller ID are checked by the
  backend before anything personal is spoken. Failed attempts are limited in
  the dialplan, and the backend locks a case after repeated failures.
- **OAuth2 client credentials** with token caching and automatic refresh on `401`.
- **No dead air.** API timeouts and outages become `LOOKUP_RESULT=ERROR`,
  and the caller is sent to an agent or offered a callback.
- **Multi-language prompts** (Somali / English in this example), with dates
  spoken from recorded prompts so they work in languages Asterisk has no
  built-in grammar for.
- **Working-hours routing.** Agents during the day, callback requests after hours.
- **Privacy-aware logging.** Phone numbers and case IDs are masked, and the PIN
  is cleared from the channel straight after use.
- **Standard library only.** No pip install is needed on the Asterisk server.
- **Tests.** End-to-end tests of the AGI protocol against a mock API.

## Repository layout

```
asterisk/extensions_ivr.conf   dialplan: language, menu, verify, results, FAQ, queue, callback
agi/ivr_agi.py                 AGI script: OAuth2 API client, lookup and callback actions
mock-api/server.py             mock backend for local testing
mock-api/sample_data.json      fictional test cases
prompts/PROMPTS.md             prompt list with English source text for recording
tests/test_ivr_agi.py          end-to-end tests
```

## Quick start (no Asterisk needed)

```bash
python3 -m unittest discover -s tests -v
```

Run the mock API and simulate an AGI call by hand:

```bash
python3 mock-api/server.py &
printf 'agi_callerid: 252610000001\nagi_uniqueid: 1.1\n\n200 result=1\n200 result=1\n200 result=1\n200 result=1\n' \
  | IVR_LOG_FILE=/dev/stderr python3 agi/ivr_agi.py lookup 100001 4321
```

Output:

```
SET VARIABLE REG_STATUS "REGISTERED"
SET VARIABLE NEXT_DIST_DATE "20261105"
SET VARIABLE CASE_STATUS "IN_PROGRESS"
SET VARIABLE LOOKUP_RESULT "OK"
```

## Install on Asterisk

```bash
cp agi/ivr_agi.py /var/lib/asterisk/agi-bin/ && chmod 755 /var/lib/asterisk/agi-bin/ivr_agi.py
cp asterisk/extensions_ivr.conf /etc/asterisk/
echo '#include extensions_ivr.conf' >> /etc/asterisk/extensions.conf
asterisk -rx "dialplan reload"
```

Route the inbound DID to `Goto(ivr-entry,s,1)` and create a queue called
`helpline` in `queues.conf`, or change `QUEUE_NAME` in `[globals]`.

Configuration is read from environment variables, which you can set in the
Asterisk service unit (see `.env.example`):

| Variable | Default |
|---|---|
| `IVR_API_BASE_URL` | `http://127.0.0.1:8080` |
| `IVR_API_CLIENT_ID` / `IVR_API_CLIENT_SECRET` | demo values |
| `IVR_API_TIMEOUT` | `3` seconds |
| `IVR_TOKEN_CACHE` | `/tmp/ivr_agi_token.json` |
| `IVR_LOG_FILE` | `/var/log/asterisk/ivr_agi.log` |

## API contract

`POST /v1/self-service/lookup` (Bearer token)

```json
{ "case_id": "100001", "pin": "4321", "msisdn": "252610000001", "call_id": "1761040000.1" }
```

| Status | Meaning | IVR result |
|---|---|---|
| `200` | verified | `OK` + `REG_STATUS`, `NEXT_DIST_DATE`, `CASE_STATUS` |
| `403` | verification failed or locked | `VERIFY_FAILED` |
| `404` | unknown case | `NOT_FOUND` |
| other / timeout | backend problem | `ERROR` |

`POST /v1/callbacks` queues a callback request for agents.

Verification is done **on the backend**, not in the IVR. That way the rules
(PIN, registered numbers, lockout) stay in one place, and the IVR never sees
data it should not speak.

## Design notes

- The AGI only sets variables, and the dialplan decides what to play. Call-flow
  changes do not touch code, and the code stays easy to test.
- The same AGI works with FreeSWITCH-style deployments if it is wrapped as an
  ESL or `mod_python` call, because the logic is in plain functions.
- Somali prompts should be recorded by native speakers. See
  [`prompts/PROMPTS.md`](prompts/PROMPTS.md).

## Roadmap

- FAQ content served from the API (managed by staff in a web UI) instead of
  fixed prompt files
- Containment and drop-off reporting per menu option
- Per-agency branding on a shared platform (selected by DID)

## Disclaimer

All data in this repository is fictional. Do not commit real beneficiary or
customer data.

## License

MIT
