"""
Auth package — JWT token creation/validation and password hashing.

Flow: AuthenticationFlow
Entrypoint: get_current_user() dependency

Contract:
- Passwords are hashed with bcrypt via passlib.
- JWTs are signed with HS256 using a configurable secret.
- Token expiry defaults to 24 hours.
- get_current_user() extracts and validates the Bearer token.

Failure modes:
1. Invalid/expired token → 401 Unauthorized
2. User not found in DB → 401 Unauthorized
3. Missing Authorization header → 401 Unauthorized
"""
