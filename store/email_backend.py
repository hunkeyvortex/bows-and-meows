import ssl
from django.core.mail.backends.smtp import EmailBackend


class RelaxedStrictSMTPBackend(EmailBackend):

    @property
    def ssl_context(self):
        context = ssl.create_default_context()

        # Python 3.13+ enables strict X509 checking by default.
        # Remove only the strict flag.
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            context.verify_flags &= ~ssl.VERIFY_X509_STRICT

        return context