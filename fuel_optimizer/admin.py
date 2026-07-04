from django.contrib import admin

from .models import FuelStation


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "retail_price", "latitude", "longitude", "opis_id")
    list_filter = ("state",)
    search_fields = ("name", "city", "address")
    readonly_fields = ("geocode_confidence",)
