"""DRF serializers for the fuel route API."""

from rest_framework import serializers


class CoordinateSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lng = serializers.FloatField()
    label = serializers.CharField(required=False, allow_blank=True)


class RouteRequestSerializer(serializers.Serializer):
    """
    Accept start/finish as either an address string or {lat, lng} coordinates.

    Examples:
      {"start": "Chicago, IL", "finish": "Denver, CO"}
      {"start": {"lat": 41.88, "lng": -87.66}, "finish": {"lat": 39.74, "lng": -104.99}}
    """

    start = serializers.JSONField()
    finish = serializers.JSONField()

    def validate_start(self, value):
        return self._validate_location(value, "start")

    def validate_finish(self, value):
        return self._validate_location(value, "finish")

    def _validate_location(self, value, field_name: str):
        if isinstance(value, str):
            if not value.strip():
                raise serializers.ValidationError("Address cannot be empty.")
            return value.strip()

        if isinstance(value, dict):
            if "lat" not in value or "lng" not in value:
                raise serializers.ValidationError("Coordinate object must include lat and lng.")
            return value

        raise serializers.ValidationError(
            "Must be an address string or an object with lat and lng."
        )
