from django.db import models


class FuelStation(models.Model):
    opis_id = models.IntegerField()
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=512)
    city = models.CharField(max_length=128)
    state = models.CharField(max_length=2)
    rack_id = models.IntegerField(null=True, blank=True)
    retail_price = models.DecimalField(max_digits=8, decimal_places=6)
    latitude = models.FloatField()
    longitude = models.FloatField()
    geocode_confidence = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["state"]),
            models.Index(fields=["latitude", "longitude"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["opis_id", "address"],
                name="unique_station_opis_address",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state})"
