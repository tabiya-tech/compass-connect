import pytest

from app.context_vars import user_language_ctx_var
from app.i18n.types import Locale


@pytest.fixture(autouse=True)
def set_user_language_locale():
    """
    Set the user language locale context variable for all tests in this package.

    The phase handlers produce their fallback messages via the i18n service (t()),
    which reads the locale from user_language_ctx_var. Without this, get_locale()
    raises LookupError. We set it as part of test preparation and reset afterwards.
    """
    # GIVEN the user language locale is set
    token = user_language_ctx_var.set(Locale.EN_US)
    yield
    # cleanup: reset the context variable after the test
    user_language_ctx_var.reset(token)
