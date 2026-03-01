import traceback
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from .models import ErrorLog


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    request = context.get("request")

    ErrorLog.objects.create(
        user=request.user if request and request.user.is_authenticated else None,
        endpoint=request.path if request else "",
        method=request.method if request else "",
        error_message=str(exc),
        status_code=response.status_code if response else 500,
        traceback=traceback.format_exc()
    )

    if response is None:
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return response
