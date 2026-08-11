from django.urls import path

from ...api_views.auth.views import (
    LoginAPIView,
    IframeTokenAPIView,
)

urlpatterns = [
    path("login/", LoginAPIView.as_view()),
    path("iframe-token/", IframeTokenAPIView.as_view()),
]