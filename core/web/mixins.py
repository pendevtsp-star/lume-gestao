from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse


class SearchableListView(LoginRequiredMixin):
    search_fields = []

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if not query:
            return queryset

        filters = Q()
        for field in self.search_fields:
            filters |= Q(**{f"{field}__icontains": query})
        return queryset.filter(filters)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["q"] = self.request.GET.get("q", "").strip()
        context["querystring"] = query_params.urlencode()
        return context


class FormContextMixin:
    page_title = ""
    section_label = ""
    back_url_name = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        context["section_label"] = self.section_label
        context["back_url"] = reverse(self.back_url_name)
        return context
