"""Offline login test-case generator (no LLM / no API key required).

Run inside VS Code (Run button or `python generate_login_offline.py`) to
produce test_cases/PROJ-101.xlsx from the PROJ-101 login requirements.

It reuses the package's RequirementExtractor (for an identical requirements
hash) and ExcelRepository (for identical formatting), so if you later run the
live app on the same JSON it will treat these as 'unchanged' and not rewrite.
"""

import json
from pathlib import Path

from testcasegen.domain import TestCase
from testcasegen.extraction import RequirementExtractor
from testcasegen.storage import ExcelRepository

OUTPUT_DIR = "./test_cases"
JIRA_ID = "PROJ-101"
SOURCE_JSON = "sample_jira.json"


# Authored test cases derived directly from the PROJ-101 acceptance criteria
# and the attached technical spec. Each is traceable to a stated requirement.
TEST_CASES = [
    {"test_title": "Successful login with valid credentials",
     "description": "Verify a registered user can log in with a valid email and correct password.",
     "steps": "1. Navigate to the login page over HTTPS\n2. Enter a valid registered email\n3. Enter the correct password\n4. Click 'Login'",
     "data": "Email: registered valid email; Password: correct password (>= 8 chars)",
     "expected_result": "User is authenticated and redirected to the personal dashboard."},
    {"test_title": "Generic error shown for invalid credentials",
     "description": "Verify wrong credentials produce a generic error without revealing the failing field.",
     "steps": "1. Open the login page\n2. Enter an email and an incorrect password\n3. Click 'Login'",
     "data": "Email: valid format; Password: incorrect",
     "expected_result": "Error 'Invalid email or password' is displayed; message does not indicate which field is wrong."},
    {"test_title": "No field-level disclosure for non-existent email",
     "description": "Verify the system never reveals whether an email exists in the system.",
     "steps": "1. Open the login page\n2. Enter an unregistered email with any password\n3. Click 'Login'",
     "data": "Email: not registered; Password: any value",
     "expected_result": "Same generic 'Invalid email or password' error; system does not reveal that the email is unknown."},
    {"test_title": "Account locked after 5 consecutive failed attempts",
     "description": "Verify the account is locked after 5 consecutive failed login attempts.",
     "steps": "1. Open the login page\n2. Submit wrong credentials for the same account 5 times\n3. Attempt a 6th login",
     "data": "Email: valid registered; Password: wrong (x5)",
     "expected_result": "After the 5th failed attempt the account is locked and further attempts are blocked."},
    {"test_title": "Locked account displays support message",
     "description": "Verify the correct lock message is shown once the account is locked.",
     "steps": "1. Trigger account lock with 5 failed attempts\n2. Attempt to log in again",
     "data": "Email: locked account",
     "expected_result": "Message 'Your account has been locked. Contact support to unlock.' is displayed."},
    {"test_title": "Failed attempt counter resets on successful login",
     "description": "Verify the failed-attempt counter resets to 0 after a successful login.",
     "steps": "1. Submit wrong password 3 times (below lock threshold)\n2. Submit the correct password and log in\n3. Log out\n4. Submit wrong password again",
     "data": "Email: valid registered; Password: 3 wrong then correct",
     "expected_result": "Counter resets to 0 after success; a single later failure does not lock the account."},
    {"test_title": "Remember Me keeps session active for 30 days",
     "description": "Verify selecting 'Remember Me' persists the session for 30 days via a secure cookie.",
     "steps": "1. Open the login page\n2. Enter valid credentials\n3. Check 'Remember Me'\n4. Log in and inspect the session cookie",
     "data": "Email/Password: valid; Remember Me: checked",
     "expected_result": "JWT session cookie set with 30-day expiry and HttpOnly, Secure, SameSite=Strict flags."},
    {"test_title": "Session expires after 30 minutes of inactivity without Remember Me",
     "description": "Verify the session expires after 30 minutes of inactivity when 'Remember Me' is unchecked.",
     "steps": "1. Log in with 'Remember Me' unchecked\n2. Remain inactive for 30 minutes\n3. Attempt an authenticated action",
     "data": "Email/Password: valid; Remember Me: unchecked; Idle: 30 min",
     "expected_result": "Session is expired/invalidated and the user must re-authenticate."},
    {"test_title": "Password field masks all characters",
     "description": "Verify the password input masks characters during entry.",
     "steps": "1. Open the login page\n2. Type characters into the password field",
     "data": "Password: any non-empty value",
     "expected_result": "All typed characters are masked (dots/asterisks), never shown as plain text."},
    {"test_title": "Email format validation rejects invalid email",
     "description": "Verify the email field enforces standard RFC 5322 email format.",
     "steps": "1. Open the login page\n2. Enter an improperly formatted email\n3. Enter any password and click 'Login'",
     "data": "Email: 'userexample.com' (missing @); Password: valid length",
     "expected_result": "Login rejected with an email-format validation error; authentication is not attempted."},
    {"test_title": "Password minimum length boundary (8 characters)",
     "description": "Verify the minimum password length of 8 characters is enforced.",
     "steps": "1. Enter a valid email\n2. Enter a 7-character password and submit\n3. Enter an 8-character password and submit",
     "data": "Password: 7 chars (invalid) then 8 chars (valid boundary)",
     "expected_result": "7-character password is rejected; 8-character password passes the length constraint."},
    {"test_title": "Password maximum length boundary (128 characters)",
     "description": "Verify the maximum password length of 128 characters is enforced per the technical spec.",
     "steps": "1. Enter a valid email\n2. Enter a 128-character password (valid)\n3. Enter a 129-character password (invalid)",
     "data": "Password: 128 chars (valid) then 129 chars (invalid)",
     "expected_result": "128-character password accepted by the length rule; 129-character password rejected."},
    {"test_title": "Login page accessible over HTTPS only",
     "description": "Verify the login page and auth endpoints are served only over HTTPS (TLS 1.2+).",
     "steps": "1. Attempt to access the login page over HTTP\n2. Observe redirection / connection behaviour",
     "data": "URL: http:// version of the login page",
     "expected_result": "Request is served over HTTPS (TLS 1.2+); plain HTTP is not used for authentication."},
    {"test_title": "Forgot Password link navigates to reset flow",
     "description": "Verify the 'Forgot Password' link routes the user to the password reset flow.",
     "steps": "1. Open the login page\n2. Click the 'Forgot Password' link",
     "data": "N/A",
     "expected_result": "User is navigated to the password reset flow."},
    {"test_title": "Rate limiting blocks excessive login requests",
     "description": "Verify the rate limiter caps login requests at 10 per minute per IP.",
     "steps": "1. From a single IP, send more than 10 login requests within one minute\n2. Observe responses beyond the limit",
     "data": "Source: single IP; Requests: 11+ within 60 seconds",
     "expected_result": "Requests beyond 10 per minute per IP are throttled/blocked."},
    {"test_title": "Cross-browser and responsive login support",
     "description": "Verify login works on Chrome, Firefox, and Safari across desktop and mobile.",
     "steps": "1. Open the login page on Chrome, Firefox, Safari (desktop)\n2. Repeat on mobile viewports\n3. Complete a valid login on each",
     "data": "Browsers: Chrome, Firefox, Safari; Viewports: desktop and mobile",
     "expected_result": "Login renders and authenticates correctly on all listed browsers and viewports."},
    {"test_title": "Locked account requires manual support unlock",
     "description": "Verify a locked account cannot self-unlock and requires support intervention per the spec.",
     "steps": "1. Lock an account via 5 failed attempts\n2. Retry with correct credentials\n3. Confirm access stays blocked until support unlocks",
     "data": "Email: locked account; Password: correct",
     "expected_result": "Account stays locked despite correct credentials; access restored only after manual support unlock."},
    {"test_title": "Session token stored in memory, not localStorage",
     "description": "Verify the session token is held in memory and not persisted in localStorage per the spec.",
     "steps": "1. Log in with valid credentials\n2. Inspect browser localStorage and memory/cookies",
     "data": "Email/Password: valid",
     "expected_result": "Token held in memory (and Remember Me cookie when applicable); never written to localStorage."},
]


def main() -> None:
    src = Path(SOURCE_JSON)
    jira_data = json.loads(src.read_text(encoding="utf-8")) if src.exists() else {"id": JIRA_ID}

    requirements = RequirementExtractor().extract(jira_data)
    requirements.jira_id = JIRA_ID
    req_hash = requirements.content_hash()

    test_cases = []
    for i, raw in enumerate(TEST_CASES, 1):
        tc = TestCase.from_dict(raw)
        tc.test_id = f"TC-{JIRA_ID}-{i:03d}"
        tc.jira_id = JIRA_ID
        test_cases.append(tc)

    path = ExcelRepository(OUTPUT_DIR).save(JIRA_ID, test_cases, req_hash)
    print(f"Generated {len(test_cases)} login test cases -> {path}")
    for tc in test_cases:
        print(f"  {tc.test_id}: {tc.test_title}")


if __name__ == "__main__":
    main()
