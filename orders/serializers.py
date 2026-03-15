from rest_framework import serializers
from .models import ClothingItem, Order, OrderItem, OrderStatusHistory, Valet


class ValetSerializer(serializers.ModelSerializer):
    """
    Used by GET /api/valets/ — the Valet UI dropdown and valet pins on the map.
    completed_orders_count is a @property on the model, exposed as read-only here.
    """
    completed_orders_count = serializers.IntegerField(read_only=True)
    status_display         = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model  = Valet
        fields = [
            'id', 'name', 'phone', 'status', 'status_display',
            'latitude', 'longitude',
            'completed_orders_count', 'joined_at',
        ]


class ClothingItemSerializer(serializers.ModelSerializer):
    """
    Used by GET /api/items/ — returns the catalog for the order form.
    React fetches this once on load to build the item picker UI.
    """
    class Meta:
        model = ClothingItem
        fields = ['id', 'name', 'slug', 'category', 'price', 'icon']
        # is_active is intentionally excluded — filtered at the view level


# ---------------------------------------------------------------------------
# Order reading serializers (used in GET responses)
# ---------------------------------------------------------------------------

class OrderStatusHistorySerializer(serializers.ModelSerializer):
    """One entry in the order timeline — "Picked Up at 10:45 AM"."""

    class Meta:
        model = OrderStatusHistory
        fields = ['status', 'timestamp', 'note']


class OrderItemSerializer(serializers.ModelSerializer):
    """
    A line item inside an order response.
    We nest the full clothing_item object so React doesn't need
    a second request to get the item name and icon.
    """
    clothing_item = ClothingItemSerializer(read_only=True)
    subtotal      = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model  = OrderItem
        fields = ['id', 'clothing_item', 'quantity', 'price_per_item', 'subtotal']


class OrderSerializer(serializers.ModelSerializer):
    """
    Full order representation — used in GET /api/orders/ and GET /api/orders/:id/
    Includes nested items, timeline history, and assigned valet.
    """
    order_items    = OrderItemSerializer(many=True, read_only=True)
    history        = OrderStatusHistorySerializer(many=True, read_only=True)
    assigned_valet = ValetSerializer(read_only=True)
    total          = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    item_count     = serializers.IntegerField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model  = Order
        fields = [
            'id', 'customer_name', 'address', 'latitude', 'longitude',
            'status', 'status_display', 'total', 'item_count',
            'assigned_valet',
            'order_items', 'history',
            'created_at', 'updated_at',
        ]


# ---------------------------------------------------------------------------
# Order creation serializer (used in POST /api/orders/)
# ---------------------------------------------------------------------------

class OrderItemInputSerializer(serializers.Serializer):
    """
    Validates a single item in the order creation request.

    Expected shape from React:
        { "clothing_item_slug": "dress-shirt", "quantity": 3 }
    """
    clothing_item_slug = serializers.SlugField()
    quantity           = serializers.IntegerField(min_value=1, max_value=50)


class OrderCreateSerializer(serializers.ModelSerializer):
    """
    Handles POST /api/orders/ — creates an Order + its OrderItems + first history entry.

    Request body shape:
    {
        "customer_name": "John Smith",
        "address": "123 Main St, San Francisco, CA",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "items": [
            { "clothing_item_slug": "dress-shirt", "quantity": 3 },
            { "clothing_item_slug": "pants",       "quantity": 2 }
        ]
    }
    """
    # This field is write-only — it accepts the items list on input
    # but is not included in the response (we return OrderSerializer instead)
    items = OrderItemInputSerializer(many=True, write_only=True)

    class Meta:
        model  = Order
        fields = ['customer_name', 'address', 'latitude', 'longitude', 'items']

    def validate_items(self, items):
        """
        Custom validation for the items list.
        Runs automatically because the method is named validate_<fieldname>.
        """
        if not items:
            raise serializers.ValidationError("Order must contain at least one item.")

        # Verify every slug actually exists in our catalog and is active
        slugs = [item['clothing_item_slug'] for item in items]
        found = ClothingItem.objects.filter(slug__in=slugs, is_active=True)
        found_slugs = set(found.values_list('slug', flat=True))

        invalid = set(slugs) - found_slugs
        if invalid:
            raise serializers.ValidationError(
                f"Invalid or unavailable items: {', '.join(invalid)}"
            )

        return items

    def create(self, validated_data):
        """
        Called by serializer.save() — creates all DB rows atomically.
        'atomic' means: if any step fails, ALL of it rolls back.
        No partial orders in the database.
        """
        from django.db import transaction

        items_data = validated_data.pop('items')

        with transaction.atomic():
            # 1. Create the Order
            order = Order.objects.create(**validated_data)

            # 2. Create OrderItems — one per item in the request
            for item_data in items_data:
                clothing_item = ClothingItem.objects.get(slug=item_data['clothing_item_slug'])
                OrderItem.objects.create(
                    order=order,
                    clothing_item=clothing_item,
                    quantity=item_data['quantity'],
                    price_per_item=clothing_item.price,  # snapshot price right now
                )

            # 3. Write the first history entry
            OrderStatusHistory.objects.create(
                order=order,
                status=order.status,
                note='Order placed by customer',
            )

        return order
