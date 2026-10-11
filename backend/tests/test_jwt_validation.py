"""JWT library migration preserves typed sessions and fails closed on bad claims."""
import time
import unittest
import uuid

import jwt
from src.config.settings import settings
from src.core.security import create_access_token, create_refresh_token, decode_token


class JWTValidationTests(unittest.TestCase):
    def test_issued_sessions_and_required_claims(self):
        identifiers = {"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "jti": str(uuid.uuid4())}
        access = create_access_token(identifiers)
        refresh = create_refresh_token(identifiers)
        self.assertEqual(decode_token(access)["sub"], identifiers["sub"])
        self.assertEqual(decode_token(refresh, "refresh")["jti"], identifiers["jti"])
        self.assertIsNone(decode_token(refresh))
        self.assertIsNone(decode_token(access, "refresh"))
        valid = jwt.decode(access, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM], audience="corten")
        for claim in ("exp", "iat", "sub", "aud", "iss", "sid", "type"):
            with self.subTest(missing=claim):
                payload = {key: value for key, value in valid.items() if key != claim}
                token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
                self.assertIsNone(decode_token(token))

    def test_invalid_claims_and_algorithms_fail_closed(self):
        valid = jwt.decode(create_access_token({"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4())}),
                           settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM], audience="corten")
        for changes in ({"aud": "other-app"}, {"iss": "other-service"}, {"sub": "invalid"},
                        {"sid": {}}, {"iat": time.time() + 3600}, {"exp": time.time() - 1},
                        {"exp": float("inf")}, {"iat": float("inf")}):
            with self.subTest(changes=changes):
                token = jwt.encode({**valid, **changes}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
                self.assertIsNone(decode_token(token))
        self.assertIsNone(decode_token(jwt.encode(valid, None, algorithm="none")))
        self.assertIsNone(decode_token(jwt.encode(valid, settings.JWT_SECRET_KEY, algorithm="HS384")))
