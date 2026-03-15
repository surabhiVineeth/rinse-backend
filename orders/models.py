from django.db import models
from django.utils import timezone
from django_fsm import FSMField, transition
from decimal import Decimal


class ClothingItem(models.Model):
    """
    The catalog of items Rinse supports.
    This is managed by Rinse (via Admin) — not created by customers.

    One ClothingItem can appear in many orders via OrderItem.
    """

    CATEGORY_TOPS      = 'tops'
    CATEGORY_BOTTOMS   = 'bottoms'
    CATEGORY_OUTERWEAR = 'outerwear'
    CATEGORY_FORMAL    = 'formal'
    CATEGORY_HOUSEHOLD = 'household'

    CATEGORY_CHOICES = [
        (CATEGORY_TOPS,      'Tops'),
        (CATEGORY_BOTTOMS,   'Bottoms'),
        (CATEGORY_OUTERWEAR, 'Outerwear'),
        (CATEGORY_FORMAL,    'Formal'),
        (CATEGORY_HOUSEHOLD, 'Household'),
    ]

    name     = models.CharField(max_length=100)              # "Dress Shirt"
    slug     = models.SlugField(unique=True)                 # "dress-shirt" — URL/API safe identifier
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    price    = models.DecimalField(max_digits=6, decimal_places=2)  # e.g. 5.99
    icon     = models.CharField(max_length=10, default='👕')        # emoji for the UI
    is_active = models.BooleanField(default=True)            # hide from order form without deleting

    def __str__(self):
        return f"{self.name} (${self.price})"

    class Meta:
        ordering = ['category', 'name']


class Valet(models.Model):
    """
    A Rinse delivery partner — the person who picks up and delivers orders.

    Status lifecycle:
        available   → gets assigned an order → on_pickup
        on_pickup   → picks up from customer, drops at cleaner → available
        available   → gets assigned for delivery → on_delivery
        on_delivery → delivers to customer → available

    off_duty = not working that day (admin can toggle this)
    """

    AVAILABLE    = 'available'
    ON_PICKUP    = 'on_pickup'
    ON_DELIVERY  = 'on_delivery'
    OFF_DUTY     = 'off_duty'

    STATUS_CHOICES = [
        (AVAILABLE,   'Available'),
        (ON_PICKUP,   'On Pickup'),
        (ON_DELIVERY, 'On Delivery'),
        (OFF_DUTY,    'Off Duty'),
    ]

    name       = models.CharField(max_length=100)
    phone      = models.CharField(max_length=20, blank=True)
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=AVAILABLE)

    # Where the valet is based — used as their starting pin on the map
    # In a real app this would update in real-time from a mobile app
    latitude   = models.FloatField(default=0.0)
    longitude  = models.FloatField(default=0.0)

    joined_at  = models.DateTimeField(auto_now_add=True)

    @property
    def completed_orders_count(self):
        """Total delivered orders this valet has handled."""
        return self.orders.filter(status='delivered').count()

    def __str__(self):
        return f"{self.name} ({self.status})"

    class Meta:
        ordering = ['name']


class Order(models.Model):
    """
    Represents a single customer laundry order.

    Timeline:
        scheduled → dispatched → picked_up → at_cleaner → ready → delivered
    """

    SCHEDULED   = 'scheduled'
    DISPATCHED  = 'dispatched'
    PICKED_UP   = 'picked_up'
    AT_CLEANER  = 'at_cleaner'
    READY       = 'ready'
    DELIVERED   = 'delivered'
    CANCELLED   = 'cancelled'

    STATUS_CHOICES = [
        (SCHEDULED,  'Scheduled'),
        (DISPATCHED, 'Dispatched'),
        (PICKED_UP,  'Picked Up'),
        (AT_CLEANER, 'At Cleaner'),
        (READY,      'Ready for Delivery'),
        (DELIVERED,  'Delivered'),
        (CANCELLED,  'Cancelled'),
    ]

    customer_name = models.CharField(max_length=100)
    address       = models.CharField(max_length=255)
    latitude      = models.FloatField()
    longitude     = models.FloatField()

    # The valet assigned to this order.
    # null=True because no valet is assigned at order creation time.
    # on_delete=SET_NULL means if a valet is deleted, the order record is kept
    # but assigned_valet becomes null (not CASCADE — don't delete orders).
    # related_name='orders' lets us do valet.orders.all()
    assigned_valet = models.ForeignKey(
        Valet,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='orders',
    )

    # FSMField enforces valid transitions. protected=True means
    # you cannot set status directly — must use transition methods.
    status = FSMField(default=SCHEDULED, choices=STATUS_CHOICES, protected=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ------------------------------------------------------------------
    # Computed property — never stored in DB, always calculated fresh
    # This way it's always accurate even if prices change... wait no.
    # Actually we snapshot price on OrderItem so this is always correct.
    # ------------------------------------------------------------------
    @property
    def total(self):
        """Sum of (quantity × price_per_item) across all order items."""
        return sum(
            item.quantity * item.price_per_item
            for item in self.order_items.all()
        )

    @property
    def item_count(self):
        """Total number of individual garments in this order."""
        return sum(item.quantity for item in self.order_items.all())

    # ------------------------------------------------------------------
    # State machine transitions
    # ------------------------------------------------------------------
    @transition(field=status, source=SCHEDULED, target=DISPATCHED)
    def dispatch(self):
        pass

    @transition(field=status, source=DISPATCHED, target=PICKED_UP)
    def pick_up(self):
        pass

    @transition(field=status, source=PICKED_UP, target=AT_CLEANER)
    def drop_at_cleaner(self):
        pass

    @transition(field=status, source=AT_CLEANER, target=READY)
    def mark_ready(self):
        pass

    @transition(field=status, source=READY, target=DELIVERED)
    def deliver(self):
        pass

    @transition(field=status, source=SCHEDULED, target=CANCELLED)
    def cancel(self):
        pass

    def __str__(self):
        return f"Order #{self.id} — {self.customer_name} ({self.status})"

    class Meta:
        ordering = ['-created_at']


class OrderItem(models.Model):
    """
    Junction table between Order and ClothingItem.

    Stores what items are in an order and how many.
    Also snapshots the price at the time of order — so if ClothingItem.price
    changes later, old order totals remain accurate.

    Example: Order #5 has 3 dress shirts and 2 pants.
        OrderItem(order=5, clothing_item=dress_shirt, quantity=3, price_per_item=5.99)
        OrderItem(order=5, clothing_item=pants,       quantity=2, price_per_item=6.99)
    """

    # PROTECT means: if someone tries to delete a ClothingItem that has
    # order history, Django will raise an error instead of deleting.
    # This protects historical order data.
    order          = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='order_items')
    clothing_item  = models.ForeignKey(ClothingItem, on_delete=models.PROTECT, related_name='order_items')
    quantity       = models.PositiveIntegerField(default=1)

    # Snapshot of the price at the time the order was placed
    price_per_item = models.DecimalField(max_digits=6, decimal_places=2)

    @property
    def subtotal(self):
        return self.quantity * self.price_per_item

    def __str__(self):
        return f"{self.quantity}x {self.clothing_item.name} @ ${self.price_per_item}"

    class Meta:
        # One order cannot have duplicate entries for the same clothing item
        unique_together = ['order', 'clothing_item']


class OrderStatusHistory(models.Model):
    """
    Append-only log of every status change for an order.
    Drives the timeline view in the UI.
    """

    order     = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='history')
    status    = models.CharField(max_length=50, choices=Order.STATUS_CHOICES)
    timestamp = models.DateTimeField(default=timezone.now)
    note      = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Order #{self.order_id} → {self.status} at {self.timestamp:%H:%M}"

    class Meta:
        ordering = ['timestamp']
