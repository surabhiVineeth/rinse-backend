from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'orders'

    def ready(self):
        """
        Called once when Django finishes loading all apps.
        This is the correct place to start background jobs.

        We guard with a try/except so a scheduler failure never
        prevents Django from starting — important in production.
        """
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.interval import IntervalTrigger
            from django_apscheduler.jobstores import DjangoJobStore
            from .scheduler import auto_dispatch_orders

            scheduler = BackgroundScheduler()
            scheduler.add_jobstore(DjangoJobStore(), 'default')

            # Run every 30 seconds
            # replace_existing=True prevents duplicate jobs if Django reloads
            scheduler.add_job(
                auto_dispatch_orders,
                trigger=IntervalTrigger(seconds=30),
                id='auto_dispatch_orders',
                replace_existing=True,
            )

            scheduler.start()
            print('[Scheduler] Started — running every 30 seconds')

        except Exception as e:
            print(f'[Scheduler] Failed to start: {e}')
