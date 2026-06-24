from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.views import FormContextMixin, SearchableListView
from patients.forms import PatientForm
from patients.models import Patient


class PatientListView(SearchableListView, ListView):
    model = Patient
    template_name = "patients/patient_list.html"
    context_object_name = "patients"
    paginate_by = 12
    search_fields = ["full_name", "cpf", "phone", "email"]


class PatientCreateView(FormContextMixin, LoginRequiredMixin, CreateView):
    model = Patient
    form_class = PatientForm
    template_name = "core/form.html"
    success_url = reverse_lazy("patients:list")
    page_title = "Paciente"
    section_label = "Cadastro"
    back_url_name = "patients:list"

    def form_valid(self, form):
        messages.success(self.request, "Paciente cadastrado com sucesso.")
        return super().form_valid(form)


class PatientUpdateView(FormContextMixin, LoginRequiredMixin, UpdateView):
    model = Patient
    form_class = PatientForm
    template_name = "core/form.html"
    success_url = reverse_lazy("patients:list")
    page_title = "Paciente"
    section_label = "Cadastro"
    back_url_name = "patients:list"

    def form_valid(self, form):
        messages.success(self.request, "Paciente atualizado com sucesso.")
        return super().form_valid(form)

# Create your views here.
