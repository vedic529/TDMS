"""Microsoft Entra ID authentication for the TDMS API.

Two things are kept strictly apart, because conflating them is how authorisation
bugs happen:

* **Authentication** — *is this really that person?* Microsoft answers it. TDMS
  verifies the answer cryptographically (`tokens.py`) and never sees a password.
* **Authorisation** — *what may they do in TDMS?* TDMS alone answers it, from the
  `users` row found by the verified `tid + oid` (`identity.py`), never from the
  email address in the token.
"""

from __future__ import annotations
