from django.urls import path

from relationships.web.automations import RelationshipAutomationsView
from relationships.web.history import (
    RelationshipHistoryRetryView,
    RelationshipHistoryView,
)
from relationships.web.overview import RelationshipOverviewView


app_name = "relationships"

urlpatterns = [
    path("", RelationshipOverviewView.as_view(), name="overview"),
    path("automacoes/", RelationshipAutomationsView.as_view(), name="automations"),
    path("historico/", RelationshipHistoryView.as_view(), name="history"),
    path(
        "historico/<int:pk>/tentar-novamente/",
        RelationshipHistoryRetryView.as_view(),
        name="history_retry",
    ),
]
