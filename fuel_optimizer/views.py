"""REST API views for fuel route planning."""

import json

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from fuel_optimizer.serializers import RouteRequestSerializer
from fuel_optimizer.services.route_service import RouteServiceError, plan_fuel_route


class RouteView(APIView):
    """
    POST /api/v1/route/ — plan a driving route with optimal fuel stops.

    GET /api/v1/route/?start=...&finish=... — same logic via query params (browser-friendly).
    """

    def post(self, request: Request) -> Response:
        serializer = RouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._plan_route(serializer.validated_data["start"], serializer.validated_data["finish"])

    def get(self, request: Request) -> Response:
        start = request.query_params.get("start")
        finish = request.query_params.get("finish")
        if not start or not finish:
            return Response(
                {"detail": "Query parameters 'start' and 'finish' are required."},
                status=400,
            )
        start = self._parse_query_location(start)
        finish = self._parse_query_location(finish)
        serializer = RouteRequestSerializer(data={"start": start, "finish": finish})
        serializer.is_valid(raise_exception=True)
        return self._plan_route(serializer.validated_data["start"], serializer.validated_data["finish"])

    @staticmethod
    def _parse_query_location(value: str):
        value = value.strip()
        if value.startswith("{"):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        return value

    def _plan_route(self, start, finish) -> Response:
        try:
            payload = plan_fuel_route(start, finish)
        except RouteServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)
        return Response(payload)
