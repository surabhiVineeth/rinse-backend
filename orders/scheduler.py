from django.utils import timezone
from datetime import timedelta


def auto_dispatch_orders():
    """
    Scheduler handles exactly 2 things:

    1. scheduled → dispatched
       Finds unassigned orders and assigns an available valet.
       Runs every 30 seconds. If no valet is available, retries next run.

    2. at_cleaner → ready
       Simulates the cleaning partner marking an order ready.
       After 5 minutes at the cleaner, auto-advances to ready
       and assigns a valet for delivery.

    Everything else (picked_up, at_cleaner, delivered)
    is confirmed manually via the Valet UI.
    """
    from .models import Order, OrderStatusHistory, Valet

    now = timezone.now()

    _dispatch_scheduled_orders(now)
    _advance_cleaning_orders(now)


def _dispatch_scheduled_orders(now):
    """
    Step 2: scheduled → dispatched
    Find all unassigned scheduled orders and assign an available valet.
    """
    from .models import Order, OrderStatusHistory

    pending_orders = Order.objects.filter(
        status='scheduled',
        assigned_valet__isnull=True,
    )

    for order in pending_orders:
        valet = _find_available_valet()
        if not valet:
            print(f'[Scheduler] Order #{order.id} waiting — no valets available')
            break  # No point checking more orders if no valets are free

        # Assign the valet and dispatch the order
        valet.status = 'on_pickup'
        valet.save()

        order.assigned_valet = valet
        order.dispatch()  # scheduled → dispatched (FSM transition)
        order.save()

        OrderStatusHistory.objects.create(
            order=order,
            status=order.status,
            note=f'Valet {valet.name} dispatched for pickup',
        )
        print(f'[Scheduler] Order #{order.id} dispatched → {valet.name}')


def _advance_cleaning_orders(now):
    """
    Step 5: at_cleaner → ready
    After 5 minutes at the cleaner, mark ready and assign delivery valet.
    """
    from .models import Order, OrderStatusHistory

    cleaning_orders = Order.objects.filter(status='at_cleaner')

    for order in cleaning_orders:
        last_event = order.history.last()
        if not last_event:
            continue

        time_at_cleaner = now - last_event.timestamp
        if time_at_cleaner < timedelta(minutes=5):
            continue  # Not ready yet

        # Find a valet for delivery
        valet = _find_available_valet()
        if not valet:
            print(f'[Scheduler] Order #{order.id} ready but no delivery valet available')
            continue

        # Release the old pickup valet if still attached
        # (should already be released in the valet UI flow, but safety check)
        if order.assigned_valet and order.assigned_valet.status == 'on_pickup':
            order.assigned_valet.status = 'available'
            order.assigned_valet.save()

        # Assign delivery valet
        valet.status = 'on_delivery'
        valet.save()

        order.assigned_valet = valet
        order.mark_ready()  # at_cleaner → ready (FSM transition)
        order.save()

        OrderStatusHistory.objects.create(
            order=order,
            status=order.status,
            note=f'Cleaning complete. Valet {valet.name} assigned for delivery',
        )
        print(f'[Scheduler] Order #{order.id} ready → {valet.name} dispatched for delivery')


def _find_available_valet():
    """Returns the first available valet, or None if all are busy."""
    from .models import Valet
    return Valet.objects.filter(status=Valet.AVAILABLE).first()
