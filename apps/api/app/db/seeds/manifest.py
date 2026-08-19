"""The elevated bootstrap list — the single source of truth for Access Model v1.1.

This list exists in exactly one place. Tests and the sign-in provisioning path
both import it, so what is approved and what is enforced cannot drift apart.

What changed from Step 4
------------------------
Step 4 tried to *insert* these accounts and was blocked: `users.display_name` is
NOT NULL and no business-supplied names existed. Access Model v1.1 supersedes
that approach. The list now declares **email → target role** only, and the
account itself is created at the first verified Microsoft sign-in, where the
display name arrives from the Entra profile claims rather than from a guess.

How an entry is used
--------------------
Exactly once, at initial identity binding:

    Microsoft verifies the person
      -> the tenant is on the allow-list
      -> no TDMS user has this (tid, oid)
      -> the verified email matches an entry here
      -> the account is created at that entry's role

After binding, the durable identity is `tid + oid`. The mailbox text is never
consulted for authorisation again, so a later mailbox rename cannot promote or
demote anyone.

A domain is not an entry. `@chelsongordon.com` and `@vconsultancy.com.au` were
supplied as organisational domains; belonging to one grants VIEWER through the
normal tenant rule and nothing more.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Status for a newly provisioned account (`account_status` enum).
INITIAL_ACCOUNT_STATUS = "ACTIVE"

#: The role every other authenticated user from an approved tenant receives.
DEFAULT_ACCESS_LEVEL = "VIEWER"


@dataclass(frozen=True)
class BootstrapUser:
    """One approved elevated account: an address and the role it binds to."""

    organisation_email: str
    access_level: str


# ---------------------------------------------------------------------------
# The approved list
# ---------------------------------------------------------------------------

ELEVATED_BOOTSTRAP: tuple[BootstrapUser, ...] = (
    # -- Super Admin (4) ----------------------------------------------------
    BootstrapUser("a.chattopadhyay@chelsongordon.com", "SUPER_ADMIN"),
    BootstrapUser("w.rajjak@chelsongordon.com", "SUPER_ADMIN"),
    BootstrapUser("v.yadav@chelsongordon.com", "SUPER_ADMIN"),
    BootstrapUser("d.panda@chelsongordon.com", "SUPER_ADMIN"),
    # -- Admin (2) ----------------------------------------------------------
    BootstrapUser("c.dejsakultorn@chelsongordon.com", "ADMIN"),
    # Access Model v1.1 moved this account from Super Admin to Admin.
    BootstrapUser("n.verma@chelsongordon.com", "ADMIN"),
    # -- Data Editor (0) ----------------------------------------------------
    # Intentionally empty. Data Editor is granted by approving an access
    # request or by a Super Admin role change, never by a bootstrap list.
)

#: What the list must resolve to. Asserted by the tests and at import, so an
#: accidental edit cannot quietly change who holds authority.
EXPECTED_COUNTS: dict[str, int] = {
    "VIEWER": 0,
    "DATA_EDITOR": 0,
    "ADMIN": 2,
    "SUPER_ADMIN": 4,
}

#: Who is notified when an access request is submitted (Access Model v1.1 §50).
#: The four Super Admins — and only they may decide a request.
APPROVAL_NOTIFICATION_RECIPIENTS: tuple[str, ...] = tuple(
    u.organisation_email for u in ELEVATED_BOOTSTRAP if u.access_level == "SUPER_ADMIN"
)

#: The mailbox notifications are sent from (Access Model v1.1 §51).
NOTIFICATION_SENDER = "v.yadav@chelsongordon.com"


def bootstrap_role_for(email: str) -> str | None:
    """The elevated role approved for this address, or None.

    Matching is case-insensitive because `organisation_email` is `citext` and
    Microsoft may return a differently-cased `preferred_username`.
    """
    key = (email or "").strip().lower()
    if not key:
        return None
    for user in ELEVATED_BOOTSTRAP:
        if user.organisation_email == key:
            return user.access_level
    return None


def validate_manifest(users: tuple[BootstrapUser, ...] = ELEVATED_BOOTSTRAP) -> list[str]:
    """Return a list of problems with the list itself. Empty means valid."""
    problems: list[str] = []

    seen: dict[str, str] = {}
    for user in users:
        email = user.organisation_email
        if email != email.strip():
            problems.append(f"{email!r}: surrounding whitespace")
        if email != email.lower():
            problems.append(f"{email!r}: must be stored in lowercase canonical form")
        if email.startswith("@") or "*" in email or "%" in email:
            problems.append(f"{email!r}: looks like a domain or wildcard, not an account")
        if "@" not in email:
            problems.append(f"{email!r}: not an email address")

        key = email.lower()
        if key in seen:
            problems.append(f"{email!r}: duplicates {seen[key]!r}")
        seen[key] = email

        if user.access_level not in EXPECTED_COUNTS:
            problems.append(f"{email!r}: unknown access level {user.access_level!r}")
        elif user.access_level == DEFAULT_ACCESS_LEVEL:
            problems.append(
                f"{email!r}: VIEWER is the default for every approved user and is "
                "not an elevated bootstrap role"
            )

    for level, expected in EXPECTED_COUNTS.items():
        actual = sum(1 for u in users if u.access_level == level)
        if actual != expected:
            problems.append(f"{level}: list has {actual}, approved count is {expected}")

    return problems
