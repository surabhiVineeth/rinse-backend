from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ClothingItem, Order, Valet, OrderStatusHistory
from .serializers import (
    ClothingItemSerializer,
    OrderSerializer,
    OrderCreateSerializer,
    ValetSerializer,
)


class ValetViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/valets/        → list all valets + their status (for the Valet tab dropdown)
    GET /api/valets/:id/    → single valet detail

    ReadOnlyModelViewSet = only GET, no POST/PUT/DELETE.
    Valets are managed via Django Admin, not the API.
    """
    queryset         = Valet.objects.all()
    serializer_class = ValetSerializer

    @action(detail=True, methods=['get'], url_path='current-order')
    def current_order(self, request, pk=None):
        """
        GET /api/valets/:id/current-order/

        Returns the order currently assigned to this valet.
        The Valet UI calls this to show the valet their active assignment.
        Returns 404 if the valet has no active order.
        """
        valet = self.get_object()
        order = Order.objects.filter(
            assigned_valet=valet,
            status__in=['dispatched', 'picked_up', 'ready'],
        ).prefetch_related('order_items__clothing_item', 'history').first()

        if not order:
            return Response(
                {'message': 'No active order assigned to this valet'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(OrderSerializer(order).data)


class ClothingItemListView(generics.ListAPIView):
    """
    GET /api/items/
    Returns the active catalog for the order form in React.
    Read-only. No POST/PUT/DELETE — the catalog is managed via Django Admin.

    generics.ListAPIView gives us GET (list) for free.
    We just define queryset and serializer_class.
    """
    queryset         = ClothingItem.objects.filter(is_active=True)
    serializer_class = ClothingItemSerializer


class OrderViewSet(viewsets.ModelViewSet):
    """
    ViewSet = multiple related endpoints grouped under one class.

    The Router (in urls.py) auto-generates these URLs from this one class:
        GET    /api/orders/       → list()
        POST   /api/orders/       → create()
        GET    /api/orders/:id/   → retrieve()

    We also add a custom action:
        GET    /api/orders/:id/timeline/  → timeline()
    """

    # Default queryset — prefetch_related loads related rows in bulk
    # instead of hitting the DB once per order (N+1 query problem)
    queryset = Order.objects.prefetch_related(
        'order_items__clothing_item',   # for each order, load its items + item details
        'history',                      # for each order, load its status history
    )

    def get_serializer_class(self):
        """
        Return different serializers for read vs write.
        Django calls this automatically before processing the request.
        """
        if self.action == 'create':
            return OrderCreateSerializer
        return OrderSerializer

    def create(self, request, *args, **kwargs):
        """
        POST /api/orders/
        1. Validate input with OrderCreateSerializer
        2. Save → creates Order + OrderItems + first history entry (via serializer.create)
        3. Return the full order using OrderSerializer (not the create serializer)
        """
        create_serializer = OrderCreateSerializer(data=request.data)
        create_serializer.is_valid(raise_exception=True)
        order = create_serializer.save()

        # Return the full order representation, not just the input fields
        response_serializer = OrderSerializer(order)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        """
        GET /api/orders/
        Returns all orders for the live map.
        Supports optional ?status= filter so React can filter by status if needed.
            e.g. GET /api/orders/?status=scheduled
        """
        queryset = self.get_queryset()

        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        serializer = OrderSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='timeline')
    def timeline(self, request, pk=None):
        """
        GET /api/orders/:id/timeline/
        Returns just the status history for a single order.
        Used when the user clicks an order to open the timeline drawer.
        """
        order = self.get_object()
        serializer = OrderSerializer(order)
        return Response({
            'id':          serializer.data['id'],
            'status':      serializer.data['status'],
            'history':     serializer.data['history'],
            'total':       serializer.data['total'],
            'item_count':  serializer.data['item_count'],
            'order_items': serializer.data['order_items'],
        })

    @action(detail=True, methods=['post'], url_path='advance')
    def advance(self, request, pk=None):
        """
        POST /api/orders/:id/advance/

        Called by the Valet UI when they tap a confirmation button.
        Advances the order to the next status and handles valet state.

        Valid valet-triggered transitions:
            dispatched  → picked_up     (valet confirms pickup from customer)
            picked_up   → at_cleaner    (valet confirms drop-off at cleaner)
            ready       → delivered     (valet confirms delivery to customer)
        """
        order = self.get_object()

        # Map: current status → (transition method, note, release valet after?)
        VALET_TRANSITIONS = {
            'dispatched': (order.pick_up,         'Valet confirmed pickup from customer',  False),
            'picked_up':  (order.drop_at_cleaner, 'Valet dropped clothes at cleaner',      True),
            'ready':      (order.deliver,          'Valet confirmed delivery to customer',  True),
        }

        if order.status not in VALET_TRANSITIONS:
            return Response(
                {'error': f'Cannot manually advance an order with status "{order.status}". '
                           f'This step is handled automatically.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        transition_fn, note, release_valet = VALET_TRANSITIONS[order.status]

        # Call the FSM transition
        transition_fn()

        # Release valet back to available if their leg is complete
        if release_valet and order.assigned_valet:
            order.assigned_valet.status = Valet.AVAILABLE
            order.assigned_valet.save()

        order.save()

        OrderStatusHistory.objects.create(
            order=order,
            status=order.status,
            note=note,
        )

        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=['post'], url_path='mark-ready')
    def mark_ready(self, request, pk=None):
        """
        POST /api/orders/:id/mark-ready/
        Called by the Cleaner UI to manually mark an order ready for delivery.
        Transitions: at_cleaner → ready, assigns an available delivery valet.
        """
        from .scheduler import _find_available_valet
        order = self.get_object()

        if order.status != 'at_cleaner':
            return Response(
                {'error': f'Order is "{order.status}", not at_cleaner.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Release pickup valet if still attached
        if order.assigned_valet and order.assigned_valet.status == 'on_pickup':
            order.assigned_valet.status = Valet.AVAILABLE
            order.assigned_valet.save()

        # Assign delivery valet
        delivery_valet = _find_available_valet()
        if delivery_valet:
            delivery_valet.status = 'on_delivery'
            delivery_valet.save()
            order.assigned_valet = delivery_valet

        order.mark_ready()
        order.save()

        OrderStatusHistory.objects.create(
            order=order,
            status=order.status,
            note=f'Cleaner marked order ready. {delivery_valet.name + " dispatched for delivery" if delivery_valet else "No valet available yet"}',
        )

        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        """
        POST /api/orders/:id/cancel/
        Only scheduled orders can be cancelled (not yet dispatched).
        """
        order = self.get_object()

        if order.status != 'scheduled':
            return Response(
                {'error': f'Cannot cancel an order with status "{order.status}". '
                           f'Only scheduled orders can be cancelled.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.cancel()
        order.save()

        OrderStatusHistory.objects.create(
            order=order,
            status=order.status,
            note='Order cancelled by customer',
        )

        return Response(OrderSerializer(order).data)
