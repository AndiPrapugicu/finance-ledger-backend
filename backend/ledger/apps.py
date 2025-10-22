from django.apps import AppConfig

class LedgerConfig(AppConfig):
    default_auto_field = 'django.db.models.AutoField'
    name = 'backend.ledger'

    def ready(self):
        # ensure signal handlers in backend.api.events are imported and registered
        import api.events  # noqa: F401