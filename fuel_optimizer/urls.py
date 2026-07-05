from django.urls import path

from fuel_optimizer.views import RouteView

urlpatterns = [
    path("api/v1/route/", RouteView.as_view(), name="route"),
]
