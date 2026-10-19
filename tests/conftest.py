"""Never let a test suite inherit an application database connection.

DB writes require a separately provisioned seraph_test_* database containing
seraph_test_guard(token text) with the explicit local test token. No source
database is bootstrapped or modified while checking this opt-in.
"""
import asyncio
import os
from urllib.parse import urlparse

DISABLED = 'postgresql://disabled:disabled@127.0.0.1:1/disabled'


def _usage(message):
    """A configuration mistake, reported as one.

    `pytest.UsageError` prints a single line; an exception escaping
    `pytest_configure` prints an INTERNALERROR traceback, which made a wrong
    password look like a broken harness.
    """
    import pytest
    return pytest.UsageError(message)


def validate_test_target(dsn, token):
    name = urlparse(dsn).path.lstrip('/')
    if not name.startswith('seraph_test_') or not token:
        raise ValueError('DB tests require a seraph_test_* database and SERAPH_TEST_TOKEN')
    return name


def pytest_configure(config):
    dsn = os.environ.get('SERAPH_TEST_DB_DSN')
    os.environ['SERAPH_DB_DSN'] = DISABLED
    if not dsn:
        return
    token = os.environ.get('SERAPH_TEST_TOKEN')
    try:
        name = validate_test_target(dsn, token)
    except ValueError as exc:
        raise _usage(f'SERAPH_TEST_DB_DSN is set but unusable: {exc}') from exc

    async def verify():
        import asyncpg
        conn = await asyncpg.connect(dsn, timeout=3)
        try:
            async with conn.transaction(readonly=True):
                actual = await conn.fetchval('SELECT current_database()')
                if actual != name:
                    raise ValueError('Test database identity mismatch')
                guarded = await conn.fetchval(
                    'SELECT EXISTS (SELECT 1 FROM seraph_test_guard WHERE token=$1)', token)
                if not guarded:
                    raise ValueError('Missing disposable database marker')
        finally:
            await conn.close()
    try:
        asyncio.run(verify())
    except Exception as exc:                       # noqa: BLE001 - reported
        # Setting the opt-in and then failing to reach the database is a
        # configuration mistake, and the guard must still refuse. It used to
        # refuse by letting the exception escape `pytest_configure`, which
        # pytest renders as an INTERNALERROR traceback -- so a wrong password
        # looked like a broken test harness. It is reported as what it is.
        raise _usage(
            f'SERAPH_TEST_DB_DSN is set but the database could not be '
            f'verified: {type(exc).__name__}: {exc}. The target must be a '
            f'disposable seraph_test_* database containing '
            f'seraph_test_guard(token) with SERAPH_TEST_TOKEN. Unset '
            f'SERAPH_TEST_DB_DSN to skip the DB tests instead.') from exc
    os.environ['SERAPH_DB_DSN'] = dsn
