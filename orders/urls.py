from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, ValetViewSet, ClothingItemListView

# -----------------------------------------------------------------------
# Router auto-generates URLs from ViewSets:
#
# Orders:
#   GET    /orders/                  → list()
#   POST   /orders/                  → create()
#   GET    /orders/{id}/             → retrieve()
#   GET    /orders/{id}/timeline/    → timeline()
#   POST   /orders/{id}/advance/     → advance()  (valet confirms step)
#
# Valets:
#   GET    /valets/                  → list()
#   GET    /valets/{id}/             → retrieve()
#   GET    /valets/{id}/current-order/ → current_order()
# -----------------------------------------------------------------------
router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'valets', ValetViewSet, basename='valet')

urlpatterns = [
    path('', include(router.urls)),

    # ClothingItemListView is a simple read-only view, not a ViewSet,
    # so we register it manually instead of through the Router
    path('items/', ClothingItemListView.as_view(), name='clothing-items'),
]
